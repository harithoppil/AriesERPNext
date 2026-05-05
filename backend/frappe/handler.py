"""
Frappe Handler — Whitelist Method Dispatcher

Replaces frappe/handler.py — dispatches HTTP requests to whitelisted Python
functions, handles file uploads, runs document methods, and manages logout.

This module is the bridge between the HTTP layer (FastAPI) and the Frappe
Python framework. All ``/api/method/...`` calls flow through here.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import frappe
from frappe.types import _dict


# ─────────────────────────────────────────────────────────────────────────────
# Whitelist method dispatcher
# ─────────────────────────────────────────────────────────────────────────────


def handle_whitelist_method(method_string: str) -> dict[str, Any]:
    """Execute a whitelisted method identified by *method_string*.

    The method string follows the ``module.submodule.function`` pattern,
    e.g. ``frappe.auth.login`` or ``erpnext.selling.doctype.sales_order.sales_order.make_sales_order``.

    Steps:
      1. Parse ``module.method`` format.
      2. Resolve the callable via ``frappe.get_attr()``.
      3. Validate whitelist status via ``frappe.is_whitelisted()``.
      4. Check permissions for method access.
      5. Parse and validate arguments from the current request.
      6. Execute and return JSON-serialisable result.

    :raises frappe.DoesNotExistError: If the method cannot be resolved.
    :raises frappe.PermissionError: If the method is not whitelisted or the
        user lacks permission.
    :raises frappe.ValidationError: If argument parsing fails.
    """
    # 1. Resolve the method
    try:
        method = frappe.get_attr(method_string)
    except (AttributeError, ImportError) as exc:
        frappe.throw(
            frappe._("Method {0} not found").format(method_string),
            frappe.DoesNotExistError,
        )

    if not callable(method):
        frappe.throw(
            frappe._("Method {0} is not callable").format(method_string),
            frappe.ValidationError,
        )

    # 2. Validate whitelist status
    frappe.is_whitelisted(method)

    # 3. Check HTTP method is allowed
    allowed_methods = frappe.allowed_http_methods_for_whitelisted_func.get(method, ["GET", "POST"])
    current_method = _get_request_method()
    if current_method and current_method.upper() not in allowed_methods:
        frappe.throw(
            frappe._("Method {0} not allowed").format(current_method),
            frappe.PermissionError,
        )

    # 4. Parse arguments from form_dict
    args, kwargs = _parse_method_args(method)

    # 5. Execute
    try:
        response = method(*args, **kwargs)
    except frappe.FrappeException:
        raise
    except Exception as exc:
        frappe.log_error(f"Error calling {method_string}: {exc}")
        raise

    return _build_response(response)


# ─────────────────────────────────────────────────────────────────────────────
# File upload
# ─────────────────────────────────────────────────────────────────────────────


def upload_file(
    filename: str | None = None,
    filedata: bytes | str | None = None,
    doctype: str | None = None,
    docname: str | None = None,
    folder: str = "Home",
    is_private: bool = False,
    decode_base64: bool = False,
    docfield: str | None = None,
) -> _dict:
    """Handle a file upload and persist it to disk.

    Files are stored under ``sites/{site}/private/files/`` or
    ``sites/{site}/public/files/`` depending on *is_private*.

    :param filename: Original file name (e.g. ``report.pdf``).
    :param filedata: Raw file bytes or base64-encoded string.
    :param doctype: DocType to attach the file to (optional).
    :param docname: Document name to attach the file to (optional).
    :param folder: Virtual folder name (default ``Home``).
    :param is_private: Store in private files directory.
    :param decode_base64: Treat *filedata* as base64-encoded.
    :param docfield: Field name on the document for the attachment.
    :returns: _dict with ``file_url``, ``file_name``, ``file_size``, etc.
    """
    site_path = frappe.local.site_path
    if not site_path:
        frappe.throw(frappe._("Site not initialised"), frappe.ValidationError)

    # Determine storage path
    files_dir = "private/files" if is_private else "public/files"
    upload_path = os.path.join(site_path, files_dir)
    os.makedirs(upload_path, exist_ok=True)

    # Sanitise filename
    if not filename:
        filename = "upload"
    safe_filename = re.sub(r"[^\w.\-]", "_", filename)

    # Handle base64
    if decode_base64 and isinstance(filedata, str):
        try:
            filedata = base64.b64decode(filedata)
        except Exception:
            frappe.throw(frappe._("Invalid base64 data"), frappe.ValidationError)

    # Ensure bytes
    if isinstance(filedata, str):
        filedata = filedata.encode("utf-8")

    if not filedata:
        frappe.throw(frappe._("No file data provided"), frappe.ValidationError)

    # Write file
    dest_path = os.path.join(upload_path, safe_filename)
    # Handle duplicates by appending a counter
    counter = 1
    original_dest = dest_path
    while os.path.exists(dest_path):
        name, ext = os.path.splitext(original_dest)
        dest_path = f"{name}_{counter}{ext}"
        counter += 1

    with open(dest_path, "wb") as f:
        f.write(filedata)

    file_size = os.path.getsize(dest_path)
    file_url = f"/{files_dir}/{os.path.basename(dest_path)}"

    # Create File document if doctype/docname provided
    if doctype and docname:
        try:
            file_doc = frappe.get_doc(
                {
                    "doctype": "File",
                    "file_name": os.path.basename(dest_path),
                    "file_url": file_url,
                    "file_size": file_size,
                    "is_private": is_private,
                    "folder": folder,
                    "attached_to_doctype": doctype,
                    "attached_to_name": docname,
                    "attached_to_field": docfield,
                }
            )
            file_doc.insert(ignore_permissions=True)
        except Exception:
            # If File DocType doesn't exist, return metadata without DB entry
            pass

    return _dict(
        file_name=os.path.basename(dest_path),
        file_url=file_url,
        file_size=file_size,
        is_private=is_private,
        folder=folder,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Document method runner
# ─────────────────────────────────────────────────────────────────────────────


def run_doc_method(
    doctype: str,
    name: str,
    method: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Run a whitelisted method on a Document instance.

    This powers calls like::

        POST /api/method/frappe.handler.run_doc_method
        { "doctype": "Sales Order", "name": "SO-00001", "method": "submit" }

    :param doctype: DocType of the document.
    :param name: Document name (primary key).
    :param method: Method name to call on the document.
    :param kwargs: Additional arguments passed to the method.
    :raises frappe.DoesNotExistError: If the document does not exist.
    :raises frappe.PermissionError: If the method is not whitelisted.
    """
    # Load the document
    if not frappe.db.exists(doctype, name):
        frappe.throw(
            frappe._("{0} {1} not found").format(doctype, name),
            frappe.DoesNotExistError,
        )

    doc = frappe.get_doc(doctype, name)

    # Resolve the method
    if not hasattr(doc, method):
        frappe.throw(
            frappe._("Method {0} not found on {1}").format(method, doctype),
            frappe.DoesNotExistError,
        )

    doc_method: Callable = getattr(doc, method)
    if not callable(doc_method):
        frappe.throw(
            frappe._("'{0}' is not callable on {1}").format(method, doctype),
            frappe.ValidationError,
        )

    # Check whitelist status on the document method
    # Document methods that are whitelisted have the method in frappe.whitelisted
    frappe.is_whitelisted(doc_method)

    # Run the method
    result = doc_method(**kwargs)

    return _build_response(result)


# ─────────────────────────────────────────────────────────────────────────────
# Logout
# ─────────────────────────────────────────────────────────────────────────────


def logout() -> str:
    """Log out the current user and clear the session.

    Returns a translatable success message.
    """
    user = frappe.session.user if hasattr(frappe, "session") else "Guest"
    frappe.sessions.clear(user=user)
    frappe.local.user = "Guest"
    frappe.local.session = frappe.sessions.create_guest_session()
    return frappe._("Logged out")


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────


def _get_request_method() -> str | None:
    """Get the HTTP method of the current request, if any."""
    try:
        req = frappe.local.request
        if req is not None and hasattr(req, "method"):
            return req.method
    except Exception:
        pass
    return None


def _parse_method_args(
    method: Callable,
) -> tuple[list[Any], dict[str, Any]]:
    """Parse positional and keyword arguments for *method* from form_dict.

    The logic follows the original Frappe handler:
      - ``frappe.local.form_dict`` contains the request parameters.
      - The ``cmd`` key (method path) is stripped out.
      - Remaining keys are matched against the method signature.
      - Lists are converted when a param has an annotation of ``list``.
    """
    form_dict = frappe.local.form_dict
    if form_dict is None:
        return [], {}

    # Work on a copy and strip internal keys
    data: dict[str, Any] = {}
    for key, value in form_dict.items():
        if key in ("cmd", "doctype", "name", "method"):
            continue
        data[key] = value

    # Try to extract positional *args if the form_dict contains an "args" key
    args: list[Any] = []
    if "args" in data:
        raw_args = data.pop("args")
        if isinstance(raw_args, str):
            try:
                parsed = json.loads(raw_args)
                if isinstance(parsed, list):
                    args = parsed
                elif isinstance(parsed, dict):
                    data.update(parsed)
            except (json.JSONDecodeError, TypeError):
                pass
        elif isinstance(raw_args, list):
            args = raw_args

    # Convert type hints for common patterns
    import inspect

    try:
        sig = inspect.signature(method)
    except (ValueError, TypeError):
        sig = None

    if sig is not None:
        for param_name, param in sig.parameters.items():
            if param_name not in data:
                continue
            value = data[param_name]
            # Handle list annotations
            if param.annotation is list or str(param.annotation).startswith("typing.List"):
                if isinstance(value, str):
                    try:
                        data[param_name] = json.loads(value)
                    except json.JSONDecodeError:
                        pass
            # Handle dict annotations
            elif param.annotation is dict or str(param.annotation).startswith("typing.Dict"):
                if isinstance(value, str):
                    try:
                        data[param_name] = json.loads(value)
                    except json.JSONDecodeError:
                        pass
            # Handle int/float annotations
            elif param.annotation is int and isinstance(value, str):
                try:
                    data[param_name] = int(value)
                except ValueError:
                    pass
            elif param.annotation is float and isinstance(value, str):
                try:
                    data[param_name] = float(value)
                except ValueError:
                    pass

    return args, data


def _build_response(result: Any) -> dict[str, Any]:
    """Wrap a method result in the standard Frappe response envelope.

    Format::

        {
            "message": <result>,
            "docs": frappe.local.response.get("docs", [])
        }
    """
    docs: list[Any] = []
    try:
        resp = frappe.local.response
        if resp is not None:
            docs = resp.get("docs", []) or []
    except Exception:
        pass

    envelope: dict[str, Any] = {"message": result, "docs": docs}

    # Merge in any keys that the method stashed on frappe.local.response
    try:
        resp = frappe.local.response
        if isinstance(resp, dict):
            for key, value in resp.items():
                if key not in envelope:
                    envelope[key] = value
    except Exception:
        pass

    return envelope
