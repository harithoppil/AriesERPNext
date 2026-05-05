"""
Frappe API — REST API Endpoints

Replaces frappe/api.py — provides auto-generated CRUD REST endpoints for all
DocTypes and dispatches RPC calls to whitelisted methods.

URL patterns::

    /api/method/{module.path.method}     ->  handle_rpc_request
    /api/resource/{doctype}              ->  list / create
    /api/resource/{doctype}/{name}       ->  get / update / delete

Response format::

    {"message": <result>, "docs": [...]}
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import frappe
from frappe.types import _dict
from frappe.handler import handle_whitelist_method, run_doc_method


# ─────────────────────────────────────────────────────────────────────────────
# RPC method dispatcher  (/api/method/...)
# ─────────────────────────────────────────────────────────────────────────────


def handle_rpc_request(method_path: str) -> dict[str, Any]:
    """Handle a call to ``/api/method/<method_path>``.

    *method_path* is a dotted Python path such as
    ``frappe.auth.get_logged_user`` or ``erpnext.projects.doctype.task.task.get_list``.

    The handler:
      1. Validates that the method is whitelisted.
      2. Parses arguments from the current request (form_dict).
      3. Executes the method.
      4. Returns the result in the standard Frappe envelope.

    :param method_path: Dotted module path to the callable.
    :returns: ``{"message": result, "docs": [...]}``
    :raises frappe.PermissionError: If the method is not whitelisted.
    :raises frappe.DoesNotExistError: If the method cannot be resolved.
    """
    if not method_path:
        frappe.throw(frappe._("Method path is required"), frappe.ValidationError)

    # Block paths that look like filesystem traversal
    if ".." in method_path or method_path.startswith("/"):
        frappe.throw(frappe._("Invalid method path"), frappe.ValidationError)

    # Replace slashes with dots (some clients send paths with /)
    method_path = method_path.replace("/", ".")

    result = handle_whitelist_method(method_path)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# REST resource handlers  (/api/resource/...)
# ─────────────────────────────────────────────────────────────────────────────


def handle_resource_list(doctype: str) -> dict[str, Any]:
    """Handle LIST /api/resource/{doctype}.

    Query parameters (all optional):
      - fields: JSON list of field names
      - filters: JSON dict or list of filters
      - order_by: e.g. ``creation desc``
      - limit_start / limit_page_length: pagination
      - parent: parent DocType (for child tables)
    """
    _check_doctype_permission(doctype, "read")

    form_dict = frappe.local.form_dict or _dict()

    fields = _safe_json_load(form_dict.get("fields"), list)
    if fields is None:
        fields = ["name"]

    filters = _safe_json_load(form_dict.get("filters"), (dict, list))
    order_by = form_dict.get("order_by", form_dict.get("orderby", "modified desc"))
    start = _to_int(form_dict.get("limit_start", 0))
    page_length = _to_int(form_dict.get("limit_page_length", 20))
    parent = form_dict.get("parent")

    result = frappe.client.get_list(
        doctype,
        fields=fields,
        filters=filters,
        order_by=order_by,
        start=start,
        page_length=page_length,
        parent=parent,
    )

    return {"message": result, "docs": result}


def handle_resource_create(doctype: str) -> dict[str, Any]:
    """Handle CREATE (POST) /api/resource/{doctype}.

    The request body is the document data including the ``doctype`` key.
    """
    _check_doctype_permission(doctype, "create")

    form_dict = frappe.local.form_dict or _dict()
    data = dict(form_dict)
    data.setdefault("doctype", doctype)

    # Remove metadata keys that should not be part of the document
    for key in ("cmd", "limit_start", "limit_page_length", "order_by", "fields", "filters"):
        data.pop(key, None)

    result = frappe.client.insert(data)
    return {"message": result, "docs": [result]}


def handle_resource_get(doctype: str, name: str) -> dict[str, Any]:
    """Handle GET /api/resource/{doctype}/{name}."""
    _check_doctype_permission(doctype, "read")

    result = frappe.client.get(doctype, name=name)
    return {"message": result, "docs": [result]}


def handle_resource_update(doctype: str, name: str) -> dict[str, Any]:
    """Handle UPDATE (PUT/PATCH) /api/resource/{doctype}/{name}.

    The request body contains the fields to update.
    """
    _check_doctype_permission(doctype, "write")

    if not frappe.db.exists(doctype, name):
        frappe.throw(
            frappe._("{0} {1} not found").format(doctype, name),
            frappe.DoesNotExistError,
        )

    form_dict = frappe.local.form_dict or _dict()
    data = dict(form_dict)
    data["doctype"] = doctype
    data["name"] = name

    # Remove metadata keys
    for key in ("cmd", "doctype_pre", "name_pre", "limit_start", "limit_page_length"):
        data.pop(key, None)

    result = frappe.client.save(data)
    return {"message": result, "docs": [result]}


def handle_resource_delete(doctype: str, name: str) -> dict[str, Any]:
    """Handle DELETE /api/resource/{doctype}/{name}."""
    _check_doctype_permission(doctype, "delete")

    if not frappe.db.exists(doctype, name):
        frappe.throw(
            frappe._("{0} {1} not found").format(doctype, name),
            frappe.DoesNotExistError,
        )

    frappe.client.delete(doctype, name)
    return {"message": "ok", "docs": []}


def handle_resource_request(doctype: str, name: str | None = None) -> dict[str, Any]:
    """Dispatch a resource request based on HTTP method.

    This is the top-level dispatcher used by the HTTP layer. It branches to
    the appropriate sub-handler (list, create, get, update, delete) based on
    the HTTP method and whether *name* is provided.

    :param doctype: DocType being accessed.
    :param name: Document name (optional; if absent, operates on collection).
    :returns: Standard Frappe response envelope.
    """
    method = _get_request_method()

    if name is None:
        if method in ("GET", "HEAD"):
            return handle_resource_list(doctype)
        elif method == "POST":
            return handle_resource_create(doctype)
        else:
            frappe.throw(
                frappe._("Method {0} not allowed on collection").format(method),
                frappe.PermissionError,
            )
    else:
        if method in ("GET", "HEAD"):
            return handle_resource_get(doctype, name)
        elif method in ("PUT", "PATCH"):
            return handle_resource_update(doctype, name)
        elif method == "DELETE":
            return handle_resource_delete(doctype, name)
        else:
            frappe.throw(
                frappe._("Method {0} not allowed on document").format(method),
                frappe.PermissionError,
            )

    # Should never reach here, but return a safe default
    return {"message": None, "docs": []}


# ─────────────────────────────────────────────────────────────────────────────
# Permission helpers
# ─────────────────────────────────────────────────────────────────────────────


def _check_doctype_permission(doctype: str, ptype: str = "read") -> None:
    """Verify the current user has *ptype* permission on *doctype*.

    Raises ``PermissionError`` if not allowed.
    """
    if not frappe.has_permission(doctype, ptype=ptype):
        frappe.throw(
            frappe._("No {0} permission on {1}").format(ptype, doctype),
            frappe.PermissionError,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Internal utilities
# ─────────────────────────────────────────────────────────────────────────────


def _get_request_method() -> str:
    """Return the HTTP method of the current request (upper-case)."""
    try:
        req = frappe.local.request
        if req is not None and hasattr(req, "method"):
            return req.method.upper()
    except Exception:
        pass
    return "GET"


def _safe_json_load(value: Any, expected_types: type | tuple[type, ...]) -> Any:
    """Safely load a JSON string, returning the raw value if it is already
    the expected type or if parsing fails.

    :param value: The value to parse (string or already-parsed object).
    :param expected_types: Type(s) to accept without parsing.
    """
    if value is None:
        return None
    if isinstance(value, expected_types):
        return value
    if isinstance(value, str):
        import json

        try:
            parsed = json.loads(value)
            if isinstance(parsed, expected_types):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    return None


def _to_int(value: Any, default: int = 0) -> int:
    """Coerce *value* to int, returning *default* on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
