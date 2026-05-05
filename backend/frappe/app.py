"""
Frappe ASGI Application — FastAPI Entry Point

Replaces frappe/app.py — provides the main ASGI application that integrates
Frappe's request lifecycle with FastAPI.

Features:
  - Request lifecycle: init → connect → session setup → route → destroy
  - Static file serving from ``sites/{site}/public/``
  - Error handlers mapping Frappe exceptions to HTTP status codes
  - CORS middleware from site config
  - Health check endpoint
  - RPC and REST API endpoint registration
"""

from __future__ import annotations

import json
import os
import traceback
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    HTTPException,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

import frappe
from frappe.api import handle_resource_request, handle_rpc_request
from frappe.handler import logout, run_doc_method, upload_file
from frappe.rate_limiter import api_rate_limit, guest_rate_limit, login_rate_limit
from frappe.types import _dict

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

# Default site — can be overridden via env var
DEFAULT_SITE = os.environ.get("FRAPPE_DEFAULT_SITE", "site1.localhost")
SITES_PATH = os.environ.get("SITES_PATH", os.path.join(os.getcwd(), "sites"))

# Exception → HTTP status code mapping
EXCEPTION_STATUS_CODES: dict[type, int] = {
    frappe.DoesNotExistError: 404,
    frappe.PermissionError: 403,
    frappe.ValidationError: 417,
    frappe.AuthenticationError: 401,
    frappe.SessionExpiredError: 401,
    frappe.RateLimitExceededError: 429,
    frappe.DuplicateEntryError: 409,
    frappe.MandatoryError: 417,
    frappe.LinkValidationError: 422,
    frappe.TimestampMismatchError: 409,
}


# ─────────────────────────────────────────────────────────────────────────────
# Request context middleware
# ─────────────────────────────────────────────────────────────────────────────


class FrappeRequestMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that manages the Frappe request lifecycle.

    For every incoming request:
      1. Determine the target site (header, cookie, or default).
      2. Call ``frappe.init(site)``.
      3. Call ``frappe.connect()``.
      4. Set up the session from JWT cookie / header.
      5. Populate ``frappe.local.request``, ``response``, ``form_dict``.
      6. After the response is generated, call ``frappe.destroy()``.
    """

    async def dispatch(self, request: Request, call_next):
        site = _resolve_site(request)

        # 1. Initialise Frappe for this site
        try:
            frappe.init(site, sites_path=SITES_PATH)
        except Exception as exc:
            return _error_response(
                500,
                frappe._("Failed to initialise site {0}: {1}").format(site, str(exc)),
            )

        # 2. Connect to database
        try:
            frappe.connect()
        except Exception as exc:
            frappe.destroy()
            return _error_response(
                500,
                frappe._("Database connection failed: {0}").format(str(exc)),
            )

        # 3. Set up request context
        try:
            _setup_request_context(request)
        except Exception as exc:
            frappe.destroy()
            return _error_response(400, str(exc))

        # 4. Session management
        try:
            _setup_session(request)
        except Exception:
            # If session setup fails, continue as Guest
            pass

        # 5. Execute request
        try:
            response = await call_next(request)
        except frappe.FrappeException as exc:
            response = _handle_frappe_exception(exc)
        except Exception as exc:
            if frappe.conf.get("developer_mode"):
                tb = traceback.format_exc()
                response = _error_response(500, f"{exc}\n\n{tb}")
            else:
                response = _error_response(500, frappe._("Internal Server Error"))
        finally:
            # 6. Cleanup
            frappe.destroy()

        # Ensure session cookie is set
        try:
            if (
                hasattr(frappe, "local")
                and hasattr(frappe.local, "session")
                and frappe.local.session
                and frappe.local.session.get("sid")
            ):
                response.set_cookie(
                    key="sid",
                    value=frappe.local.session.sid,
                    httponly=True,
                    samesite="Lax",
                    max_age=frappe.sessions.get_expiry_in_seconds(),
                )
        except Exception:
            pass

        return response


# ─────────────────────────────────────────────────────────────────────────────
# Site resolver
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_site(request: Request) -> str:
    """Determine which site this request belongs to.

    Resolution order:
      1. ``X-Frappe-Site-Name`` header
      2. ``site_name`` query parameter
      3. ``site_name`` cookie
      4. Environment variable ``FRAPPE_DEFAULT_SITE``
      5. Fallback to ``site1.localhost``
    """
    site = (
        request.headers.get("X-Frappe-Site-Name")
        or request.query_params.get("site_name")
        or request.cookies.get("site_name")
        or DEFAULT_SITE
    )
    return site


# ─────────────────────────────────────────────────────────────────────────────
# Request context setup
# ─────────────────────────────────────────────────────────────────────────────


async def _setup_request_context(request: Request) -> None:
    """Populate ``frappe.local.request``, ``response``, and ``form_dict``.

    This mirrors the setup that the original Werkzeug-based Frappe does
    for every request.
    """
    # Build the request dict
    headers = dict(request.headers)
    cookies = dict(request.cookies)

    frappe.local.request = _dict(
        {
            "headers": headers,
            "cookies": cookies,
            "path": request.url.path,
            "method": request.method,
            "query_params": dict(request.query_params),
            "url": str(request.url),
            "client": {"host": request.client.host if request.client else None},
        }
    )

    # Initialise response container
    frappe.local.response = _dict({"docs": []})

    # Parse body into form_dict
    form_dict = _dict()

    # Merge query params first
    form_dict.update(request.query_params)

    # Parse JSON body for mutating methods
    if request.method in ("POST", "PUT", "PATCH"):
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                body = await request.json()
                if isinstance(body, dict):
                    form_dict.update(body)
            except Exception:
                pass
        elif "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
            try:
                form_data = await request.form()
                for key, value in form_data.multi_items():
                    if key in form_dict and not isinstance(form_dict[key], list):
                        form_dict[key] = [form_dict[key]]
                    if key in form_dict and isinstance(form_dict[key], list):
                        form_dict[key].append(value)
                    else:
                        form_dict[key] = value
            except Exception:
                pass

    # Add the method path (cmd) if present in path
    path = request.url.path
    if path.startswith("/api/method/"):
        form_dict["cmd"] = path[len("/api/method/"):]

    frappe.local.form_dict = form_dict

    # Set request IP
    frappe.local.request_ip = (
        headers.get("x-forwarded-for", "").split(",")[0].strip()
        or headers.get("x-real-ip")
        or (request.client.host if request.client else None)
        or "127.0.0.1"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Session setup
# ─────────────────────────────────────────────────────────────────────────────


def _setup_session(request: Request) -> None:
    """Set up the user session from JWT cookie or Authorization header."""
    import frappe.auth

    try:
        frappe.auth.validate_auth()
    except Exception:
        # Continue as Guest if auth validation fails
        if not hasattr(frappe.local, "session") or not frappe.local.session:
            frappe.local.session = frappe.sessions.create_guest_session()
        if not frappe.local.user:
            frappe.local.user = "Guest"


# ─────────────────────────────────────────────────────────────────────────────
# Exception handling helpers
# ─────────────────────────────────────────────────────────────────────────────


def _handle_frappe_exception(exc: frappe.FrappeException) -> JSONResponse:
    """Map a Frappe exception to a FastAPI JSONResponse."""
    status_code = _get_status_code(exc)
    message = str(exc) or frappe._("An error occurred")
    return _error_response(status_code, message, exc_type=type(exc).__name__)


def _get_status_code(exc: Exception) -> int:
    """Get the HTTP status code for a Frappe exception."""
    for exc_type, code in EXCEPTION_STATUS_CODES.items():
        if isinstance(exc, exc_type):
            return code
    return 500


def _error_response(
    status_code: int,
    message: str,
    exc_type: str = "",
) -> JSONResponse:
    """Build a JSON error response in Frappe format.

    Original Frappe returns::

        {
            "exc_type": "PermissionError",
            "message": "...",
            "exception": "..."
        }
    """
    content: dict[str, Any] = {"message": message}
    if exc_type:
        content["exc_type"] = exc_type
    if status_code >= 500:
        content["exception"] = message
    return JSONResponse(content=content, status_code=status_code)


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI exception handlers
# ─────────────────────────────────────────────────────────────────────────────


def register_exception_handlers(app: FastAPI) -> None:
    """Register error handlers for Frappe exception types on the app."""

    @app.exception_handler(frappe.DoesNotExistError)
    async def doesnotexist_handler(request: Request, exc: frappe.DoesNotExistError):
        return _handle_frappe_exception(exc)

    @app.exception_handler(frappe.PermissionError)
    async def permission_handler(request: Request, exc: frappe.PermissionError):
        return _handle_frappe_exception(exc)

    @app.exception_handler(frappe.ValidationError)
    async def validation_handler(request: Request, exc: frappe.ValidationError):
        return _handle_frappe_exception(exc)

    @app.exception_handler(frappe.AuthenticationError)
    async def auth_handler(request: Request, exc: frappe.AuthenticationError):
        return _handle_frappe_exception(exc)

    @app.exception_handler(frappe.SessionExpiredError)
    async def session_expired_handler(request: Request, exc: frappe.SessionExpiredError):
        return _handle_frappe_exception(exc)

    @app.exception_handler(frappe.RateLimitExceededError)
    async def rate_limit_handler(request: Request, exc: frappe.RateLimitExceededError):
        status_code = _get_status_code(exc)
        message = str(exc) or frappe._("Rate limit exceeded")
        response = _error_response(status_code, message, exc_type=type(exc).__name__)
        response.headers["Retry-After"] = "60"
        return response

    @app.exception_handler(frappe.DuplicateEntryError)
    async def duplicate_handler(request: Request, exc: frappe.DuplicateEntryError):
        return _handle_frappe_exception(exc)

    @app.exception_handler(frappe.FrappeException)
    async def frappe_exception_handler(request: Request, exc: frappe.FrappeException):
        return _handle_frappe_exception(exc)

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        if frappe.conf and frappe.conf.get("developer_mode"):
            tb = traceback.format_exc()
            return _error_response(500, f"{exc}\n\n{tb}", exc_type=type(exc).__name__)
        return _error_response(500, frappe._("Internal Server Error"), exc_type=type(exc).__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Route definitions
# ─────────────────────────────────────────────────────────────────────────────


def build_api_router() -> APIRouter:
    """Create the APIRouter with all Frappe endpoints.

    This router is mounted under ``/api`` in the main application.
    """
    router = APIRouter(prefix="/api")

    # ── Health check ──────────────────────────────────────────────────────
    @router.get("/method/health")
    async def health_check():
        """Health check endpoint."""
        db_ok = False
        try:
            if hasattr(frappe, "local") and frappe.local.db:
                frappe.local.db.sql("SELECT 1")
                db_ok = True
        except Exception:
            pass
        return {
            "message": {
                "status": "ok" if db_ok else "degraded",
                "site": getattr(frappe.local, "site", None),
                "version": frappe.__version__,
            }
        }

    # ── RPC endpoints ─────────────────────────────────────────────────────
    @router.get("/method/{method_path:path}")
    @router.post("/method/{method_path:path}")
    @router.put("/method/{method_path:path}")
    @router.delete("/method/{method_path:path}")
    @guest_rate_limit()
    async def method_get(request: Request, method_path: str):
        """Handle GET/POST/PUT/DELETE /api/method/{method_path}."""
        result = handle_rpc_request(method_path)
        return result

    # ── Logout ────────────────────────────────────────────────────────────
    @router.post("/method/logout")
    async def method_logout():
        """Log out the current user."""
        result = logout()
        response = JSONResponse({"message": result})
        response.delete_cookie(key="sid")
        return response

    # ── File upload ───────────────────────────────────────────────────────
    @router.post("/method/upload_file")
    async def method_upload_file(request: Request):
        """Handle multipart file uploads."""
        content_type = request.headers.get("content-type", "")
        if "multipart/form-data" not in content_type:
            raise HTTPException(status_code=400, detail="Expected multipart/form-data")

        form = await request.form()
        file_field = None
        filename = None
        for key, value in form.multi_items():
            if hasattr(value, "file") or hasattr(value, "read"):
                file_field = value
                filename = value.filename
                break

        if file_field is None:
            raise HTTPException(status_code=400, detail="No file provided")

        filedata = await file_field.read()
        is_private = (form.get("is_private") or "0") in ("1", "true", "True")
        doctype = form.get("doctype") or None
        docname = form.get("docname") or None
        folder = form.get("folder") or "Home"
        docfield = form.get("docfield") or None

        result = upload_file(
            filename=filename or "upload",
            filedata=filedata,
            doctype=doctype,
            docname=docname,
            folder=folder,
            is_private=is_private,
            docfield=docfield,
        )
        return {"message": result}

    # ── Document method runner ────────────────────────────────────────────
    @router.post("/method/frappe.handler.run_doc_method")
    @router.get("/method/frappe.handler.run_doc_method")
    async def method_run_doc_method(request: Request):
        """Run a whitelisted method on a document.

        Expected form parameters:
          - doctype: DocType name
          - name: Document name
          - method: Method to run
          - Additional args passed to the method
        """
        form_dict = frappe.local.form_dict or _dict()
        doctype = form_dict.get("doctype")
        name = form_dict.get("name")
        method = form_dict.get("method")

        if not doctype or not name or not method:
            raise HTTPException(
                status_code=400,
                detail="doctype, name, and method are required",
            )

        # Build kwargs from form_dict, excluding metadata keys
        kwargs = {
            k: v
            for k, v in form_dict.items()
            if k not in ("cmd", "doctype", "name", "method")
        }

        result = run_doc_method(doctype, name, method, **kwargs)
        return result

    # ── REST resource endpoints ───────────────────────────────────────────
    @router.get("/resource/{doctype}")
    @guest_rate_limit()
    async def resource_list(doctype: str):
        """List documents: GET /api/resource/{doctype}"""
        return handle_resource_request(doctype)

    @router.post("/resource/{doctype}")
    async def resource_create(doctype: str):
        """Create document: POST /api/resource/{doctype}"""
        return handle_resource_request(doctype)

    @router.get("/resource/{doctype}/{name:path}")
    @guest_rate_limit()
    async def resource_get(doctype: str, name: str):
        """Get document: GET /api/resource/{doctype}/{name}"""
        return handle_resource_request(doctype, name)

    @router.put("/resource/{doctype}/{name:path}")
    async def resource_update(doctype: str, name: str):
        """Update document: PUT /api/resource/{doctype}/{name}"""
        return handle_resource_request(doctype, name)

    @router.patch("/resource/{doctype}/{name:path}")
    async def resource_patch(doctype: str, name: str):
        """Patch document: PATCH /api/resource/{doctype}/{name}"""
        return handle_resource_request(doctype, name)

    @router.delete("/resource/{doctype}/{name:path}")
    async def resource_delete(doctype: str, name: str):
        """Delete document: DELETE /api/resource/{doctype}/{name}"""
        return handle_resource_request(doctype, name)

    return router


# ─────────────────────────────────────────────────────────────────────────────
# WebSocket route
# ─────────────────────────────────────────────────────────────────────────────


def _register_websocket_route(app: FastAPI) -> None:
    """Register the WebSocket endpoint for real-time communication."""

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        """WebSocket endpoint for real-time communication."""
        from frappe.realtime.websocket import manager
        import uuid

        sid = str(uuid.uuid4())
        await manager.connect(websocket, sid)

        try:
            while True:
                # Receive and handle messages
                data = await websocket.receive_text()
                message = json.loads(data)

                action = message.get("action")
                room = message.get("room")

                if action == "subscribe" and room:
                    await manager.subscribe(sid, room)
                elif action == "unsubscribe" and room:
                    await manager.unsubscribe(sid, room)
                elif action == "ping":
                    await manager.send_to(sid, "pong", {})

        except WebSocketDisconnect:
            await manager.disconnect(sid)
        except Exception as e:
            logger.error("WebSocket error: %s", e)
            await manager.disconnect(sid)


# ─────────────────────────────────────────────────────────────────────────────
# Static files
# ─────────────────────────────────────────────────────────────────────────────


def _mount_static_files(app: FastAPI) -> None:
    """Mount static file directories for the default site.

    Public files are served from ``sites/{site}/public/``.
    """
    site_public = os.path.join(SITES_PATH, DEFAULT_SITE, "public")
    if os.path.isdir(site_public):
        app.mount("/public", StaticFiles(directory=site_public), name="public_static")

    # Also mount common assets
    assets_dir = os.path.join(site_public, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


# ─────────────────────────────────────────────────────────────────────────────
# Application factory
# ─────────────────────────────────────────────────────────────────────────────


def get_application(
    site: str | None = None,
    sites_path: str | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application instance.

    This is the main entry point for the ASGI server (uvicorn, gunicorn, etc.).

    Usage::

        from frappe.app import get_application
        app = get_application()

        # Then run with:
        # uvicorn frappe.app:app --reload

    :param site: Default site name (overrides env var).
    :param sites_path: Path to the sites directory.
    :returns: Configured ``FastAPI`` instance.
    """
    global DEFAULT_SITE, SITES_PATH

    if site:
        DEFAULT_SITE = site
    if sites_path:
        SITES_PATH = sites_path

    app = FastAPI(
        title="Frappe Framework",
        version=frappe.__version__,
        docs_url="/api/docs" if os.environ.get("DEVELOPER_MODE") else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if os.environ.get("DEVELOPER_MODE") else None,
    )

    # 1. Register Frappe request lifecycle middleware first
    app.add_middleware(FrappeRequestMiddleware)

    # 2. Register CORS middleware from site config
    _setup_cors(app)

    # 3. Register exception handlers
    register_exception_handlers(app)

    # 4. Register API routes
    api_router = build_api_router()
    app.include_router(api_router)

    # 5. Register WebSocket endpoint
    _register_websocket_route(app)

    # 6. Mount static files
    _mount_static_files(app)

    # 7. Root handler (optional — can serve a welcome page or redirect)
    @app.get("/")
    async def root():
        return {
            "message": "Frappe Framework",
            "version": frappe.__version__,
            "site": DEFAULT_SITE,
        }

    # 8. Catch-all for frappe.webui or other SPA routing
    @app.get("/{path:path}")
    async def catch_all(path: str, request: Request):
        """Serve index.html for SPA routing, or return 404."""
        # Don't interfere with API routes
        if path.startswith("api/") or path.startswith("public/") or path.startswith("assets/"):
            raise HTTPException(status_code=404, detail="Not found")

        index_html = os.path.join(SITES_PATH, DEFAULT_SITE, "public", "index.html")
        if os.path.isfile(index_html):
            return FileResponse(index_html)

        return JSONResponse(
            status_code=404,
            content={"message": frappe._("Not found"), "path": path},
        )

    return app


# ─────────────────────────────────────────────────────────────────────────────
# CORS setup
# ─────────────────────────────────────────────────────────────────────────────


def _setup_cors(app: FastAPI) -> None:
    """Configure CORS from site configuration.

    Looks for ``allow_cors`` in site_config.json. If not set, allows
    common development origins when ``developer_mode`` is enabled.
    """
    origins: list[str] = []

    try:
        # We need a minimal init to read config without DB
        frappe.init(DEFAULT_SITE, sites_path=SITES_PATH)
        config = frappe.local.conf or _dict()
        allow_cors = config.get("allow_cors")
        if allow_cors:
            if isinstance(allow_cors, str):
                origins = [o.strip() for o in allow_cors.split(",")]
            elif isinstance(allow_cors, list):
                origins = list(allow_cors)
        if config.get("developer_mode"):
            origins.extend(["http://localhost:8080", "http://127.0.0.1:8080"])
        frappe.destroy()
    except Exception:
        pass

    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["*"],
            expose_headers=["X-Frappe-Site-Name", "X-Frappe-Request-Id"],
        )


# ─────────────────────────────────────────────────────────────────────────────
# Module-level app instance (for uvicorn - reload convenience)
# ─────────────────────────────────────────────────────────────────────────────

# Lazy-loaded application instance
_app_instance: FastAPI | None = None


def app() -> FastAPI:
    """Return the global application instance, creating it on first call.

    This allows uvicorn to use ``frappe.app:app`` directly::

        uvicorn frappe.app:app --host 0.0.0.0 --port 8000
    """
    global _app_instance
    if _app_instance is None:
        _app_instance = get_application()
    return _app_instance
