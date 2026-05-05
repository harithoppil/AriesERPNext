"""
Frappe Client — Client-Side API

Replaces frappe/client.py — provides CRUD operations for client-side code.
These are called from the frontend via HTTP API endpoints.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.types import _dict


def get_list(
    doctype: str,
    fields: list[str] | None = None,
    filters: dict | list | None = None,
    order_by: str = "modified desc",
    start: int = 0,
    page_length: int = 20,
    parent: str | None = None,
) -> list[_dict]:
    """Get a list of documents."""
    return frappe.get_list(
        doctype,
        fields=fields,
        filters=filters,
        order_by=order_by,
        limit_start=start,
        limit_page_length=page_length,
        parent_doctype=parent,
    )


def get_count(
    doctype: str,
    filters: dict | list | None = None,
    debug: bool = False,
    cache: bool = False,
) -> int:
    """Get count of documents matching filters."""
    return frappe.db.count(doctype, filters=filters, debug=debug, cache=cache)


def get(doctype: str, name: str | None = None, filters: dict | None = None, parent: str | None = None) -> _dict:
    """Get a single document."""
    if filters and not name:
        result = frappe.get_list(doctype, filters=filters, limit_page_length=1)
        if result:
            name = result[0].name
        else:
            frappe.throw(frappe._("Document not found"), frappe.DoesNotExistError)

    doc = frappe.get_doc(doctype, name)
    return doc.as_dict()


def get_value(
    doctype: str,
    fieldname: str | list[str],
    filters: dict | str | None = None,
    as_dict: bool = True,
    debug: bool = False,
    parent: str | None = None,
) -> Any:
    """Get a field value from a document."""
    return frappe.db.get_value(doctype, filters, fieldname, as_dict=as_dict, debug=debug)


def get_single_value(doctype: str, field: str) -> Any:
    """Get a value from a Single DocType."""
    return frappe.db.get_single_value(doctype, field)


def set_value(
    doctype: str,
    name: str | int,
    fieldname: str | dict[str, Any],
    value: Any | None = None,
):
    """Set a field value on a document.

    Can be called as:
    - set_value("Doctype", "name", "field", "value")
    - set_value("Doctype", "name", {"field1": "value1", "field2": "value2"})
    """
    if isinstance(fieldname, dict):
        doc = frappe.get_doc(doctype, name)
        for field, val in fieldname.items():
            doc.set(field, val)
        doc.save()
    else:
        frappe.db.set_value(doctype, name, fieldname, value)


def insert(doc: str | dict[str, Any] | None = None, **kwargs) -> _dict:
    """Insert a new document.

    Can be called as:
    - insert({"doctype": "Doctype", "field": "value"})
    - insert('{"doctype": "Doctype", "field": "value"}')
    """
    if isinstance(doc, str):
        doc = frappe.parse_json(doc)

    if not doc:
        doc = kwargs

    if isinstance(doc, dict):
        doc = frappe.get_doc(doc)

    doc.insert()
    return doc.as_dict()


def insert_many(docs: str | list[dict[str, Any]] | None = None) -> list[_dict]:
    """Insert multiple documents."""
    if isinstance(docs, str):
        docs = frappe.parse_json(docs)

    if not isinstance(docs, list):
        frappe.throw(frappe._("Expected a list of documents"))

    results = []
    for doc_data in docs:
        doc = frappe.get_doc(doc_data)
        doc.insert()
        results.append(doc.as_dict())

    return results


def save(doc: str | dict[str, Any]) -> _dict:
    """Save a document (update if exists, insert if new)."""
    if isinstance(doc, str):
        doc = frappe.parse_json(doc)

    if not isinstance(doc, dict):
        frappe.throw(frappe._("Expected a document dict"))

    if doc.get("name") and frappe.db.exists(doc["doctype"], doc["name"]):
        existing = frappe.get_doc(doc["doctype"], doc["name"])
        for field, value in doc.items():
            if field not in ("doctype", "name"):
                existing.set(field, value)
        existing.save()
        return existing.as_dict()
    else:
        new_doc = frappe.get_doc(doc)
        new_doc.insert()
        return new_doc.as_dict()


def rename_doc(
    doctype: str,
    old_name: str | int,
    new_name: str | int,
    merge: bool = False,
) -> str:
    """Rename a document."""
    return frappe.rename_doc(doctype, old_name, new_name, merge=merge)


def submit(doc: str | dict[str, Any]) -> _dict:
    """Submit a document."""
    if isinstance(doc, str):
        doc = frappe.parse_json(doc)

    if isinstance(doc, dict):
        doc = frappe.get_doc(doc["doctype"], doc["name"])

    doc.submit()
    return doc.as_dict()


def cancel(doctype: str, name: str | int) -> _dict:
    """Cancel a document."""
    doc = frappe.get_doc(doctype, name)
    doc.cancel()
    return doc.as_dict()


def delete(doctype: str, name: str | int) -> None:
    """Delete a document."""
    frappe.delete_doc(doctype, name)


def bulk_update(docs: str) -> None:
    """Bulk update documents from a JSON string."""
    if isinstance(docs, str):
        docs = frappe.parse_json(docs)

    if not isinstance(docs, list):
        frappe.throw(frappe._("Expected a list of documents"))

    for doc_data in docs:
        save(doc_data)


def has_permission(doctype: str, docname: str | int, perm_type: str = "read") -> bool:
    """Check if user has permission on a document."""
    doc = frappe.get_doc(doctype, docname)
    return frappe.has_permission(doctype, ptype=perm_type, doc=doc)


def get_doc_permissions(doctype: str, docname: str | int) -> _dict:
    """Get all permissions for a document."""
    doc = frappe.get_doc(doctype, docname)
    return frappe.permissions.get_doc_permissions(doc)


def get_password(doctype: str, name: str | int, fieldname: str) -> str:
    """Get a decrypted password field value."""
    from frappe.utils.password import get_decrypted_password

    return get_decrypted_password(doctype, name, fieldname)


def get_time_zone() -> str:
    """Get the system time zone."""
    return frappe.utils.get_system_timezone()


def attach_file(
    filename: str | None = None,
    filedata: str | None = None,
    doctype: str | None = None,
    docname: str | None = None,
    folder: str = "Home",
    decode_base64: bool = False,
    is_private: bool = False,
    docfield: str | None = None,
) -> _dict:
    """Attach a file to a document."""
    from frappe.utils.file_manager import save_file

    file_doc = save_file(
        filename,
        filedata,
        doctype,
        docname,
        folder=folder,
        decode=decode_base64,
        is_private=is_private,
        df=docfield,
    )
    return file_doc.as_dict()


def is_document_amended(doctype: str, docname: str | int) -> bool:
    """Check if a document has been amended."""
    return frappe.db.exists(doctype, {"amended_from": docname})
