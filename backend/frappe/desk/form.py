from __future__ import annotations

import json
from typing import Any

import frappe


def getdoc(doctype: str, name: str, user: str | None = None) -> dict[str, Any]:
    """Load a document with all metadata for the form view.

    Returns the document data along with its metadata, permissions,
    linked documents info, and other form rendering context.

    Args:
        doctype: DocType of the document.
        name: Document name/ID.
        user: User loading the document (defaults to current user).

    Returns:
        Dict with 'docs', 'docinfo', 'permissions', '_link_title'.
    """
    if not user:
        user = frappe.session.user

    # Check permission
    if not frappe.has_permission(doctype, "read", user=user):
        frappe.throw(f"Not permitted to read {doctype}", frappe.PermissionError)

    # Load the document
    doc = frappe.get_doc(doctype, name)

    # Build permissions
    permissions = {
        "read": frappe.has_permission(doctype, "read", doc=doc, user=user),
        "write": frappe.has_permission(doctype, "write", doc=doc, user=user),
        "create": frappe.has_permission(doctype, "create", user=user),
        "delete": frappe.has_permission(doctype, "delete", doc=doc, user=user),
        "submit": doc.docstatus == 0 and frappe.has_permission(doctype, "submit", doc=doc, user=user),
        "cancel": doc.docstatus == 1 and frappe.has_permission(doctype, "cancel", doc=doc, user=user),
        "amend": doc.docstatus == 2 and frappe.has_permission(doctype, "amend", doc=doc, user=user),
        "print": True,
        "email": True,
    }

    # Get doc info (comments, attachments, etc.)
    docinfo = get_docinfo(doctype, name)

    # Get linked docs for Link fields
    link_titles = _get_link_titles(doc)

    return {
        "docs": [doc.as_dict()],
        "docinfo": docinfo,
        "permissions": permissions,
        "_link_title": link_titles,
    }


def get_docinfo(doctype: str, name: str) -> dict[str, Any]:
    """Get additional info for a document.

    Collects comments, attachments, versions, share info, and
    assignments for a document to display in the form sidebar.

    Args:
        doctype: DocType of the document.
        name: Document name.

    Returns:
        Dict with comments, attachments, versions, shares, assignments.
    """
    return {
        "comments": _get_comments(doctype, name),
        "attachments": _get_attachments(doctype, name),
        "versions": _get_versions(doctype, name),
        "assignments": _get_assignments(doctype, name),
        "shares": _get_shares(doctype, name),
        "permissions": _get_doc_permissions(doctype, name),
        "views": _get_views(doctype, name),
        "energy_point_logs": _get_energy_point_logs(doctype, name),
    }


def save_inline_edit(
    doctype: str,
    name: str,
    fieldname: str,
    value: Any,
) -> dict[str, Any]:
    """Save a single field inline edit.

    Updates a single field value on a document, useful for
    spreadsheet-style inline editing in list views.

    Args:
        doctype: DocType of the document.
        name: Document name.
        fieldname: Field being edited.
        value: New value.

    Returns:
        Updated document as dict.
    """
    # Check permission
    if not frappe.has_permission(doctype, "write"):
        frappe.throw(f"Not permitted to edit {doctype}", frappe.PermissionError)

    doc = frappe.get_doc(doctype, name)

    # Validate the field exists
    meta = frappe.get_meta(doctype)
    fieldnames = {f.fieldname for f in meta.fields} if hasattr(meta, "fields") else set()

    if fieldname not in fieldnames and fieldname not in ("name", "docstatus"):
        frappe.throw(f"Field {fieldname} not found in {doctype}")

    doc.set(fieldname, value)
    doc.save(ignore_permissions=False, ignore_version=False)

    return doc.as_dict()


def add_comment(
    doctype: str,
    name: str,
    content: str,
    comment_by: str | None = None,
    comment_email: str | None = None,
) -> dict[str, Any]:
    """Add a comment to a document.

    Args:
        doctype: DocType of the document.
        name: Document name.
        content: Comment text.
        comment_by: Name of commenter.
        comment_email: Email of commenter.

    Returns:
        Created comment as dict.
    """
    if not comment_email:
        comment_email = frappe.session.user
    if not comment_by:
        comment_by = frappe.get_value("User", comment_email, "full_name") or comment_email

    comment = frappe.get_doc(
        {
            "doctype": "Comment",
            "comment_type": "Comment",
            "reference_doctype": doctype,
            "reference_name": name,
            "content": content,
            "comment_by": comment_by,
            "comment_email": comment_email,
        }
    )
    comment.insert(ignore_permissions=True)

    return comment.as_dict()


def delete_comment(comment_name: str) -> None:
    """Delete a comment.

    Args:
        comment_name: Name of the comment to delete.
    """
    frappe.delete_doc("Comment", comment_name, ignore_permissions=True)


def get_linked_docs(
    doctype: str,
    name: str,
    linkinfo: dict[str, Any] | None = None,
) -> dict[str, list[dict]]:
    """Get documents linked to the given document.

    Args:
        doctype: DocType of the document.
        name: Document name.
        linkinfo: Optional mapping of link field info.

    Returns:
        Dict mapping DocType to list of linked document dicts.
    """
    linked: dict[str, list[dict]] = {}

    if not linkinfo:
        # Discover link fields automatically
        linkinfo = _discover_link_fields(doctype)

    for linked_dt, fields in linkinfo.items():
        try:
            filters = {}
            for field in fields:
                filters[field] = name

            results = frappe.db.get_all(
                linked_dt,
                filters=filters,
                fields=["name"],
                limit=50,
            )
            if results:
                linked[linked_dt] = results
        except Exception:
            continue

    return linked


def get_perm(doctype: str, docname: str | None = None) -> dict[str, Any]:
    """Get permissions for a DocType.

    Args:
        doctype: DocType name.
        docname: Optional document name for doc-level permissions.

    Returns:
        Permission dict.
    """
    user = frappe.session.user

    return {
        "read": frappe.has_permission(doctype, "read", docname=docname, user=user),
        "write": frappe.has_permission(doctype, "write", docname=docname, user=user),
        "create": frappe.has_permission(doctype, "create", user=user),
        "delete": frappe.has_permission(doctype, "delete", docname=docname, user=user),
        "submit": frappe.has_permission(doctype, "submit", docname=docname, user=user),
        "cancel": frappe.has_permission(doctype, "cancel", docname=docname, user=user),
        "amend": frappe.has_permission(doctype, "amend", docname=docname, user=user),
        "print": True,
        "email": True,
        "report": True,
        "import": frappe.has_permission(doctype, "import", user=user),
        "export": frappe.has_permission(doctype, "export", user=user),
    }


def run_method(
    doctype: str,
    name: str,
    method: str,
    args: dict[str, Any] | None = None,
) -> Any:
    """Run a controller method on a document.

    Args:
        doctype: DocType of the document.
        name: Document name.
        method: Method name to call.
        args: Optional arguments to pass.

    Returns:
        Method return value.
    """
    doc = frappe.get_doc(doctype, name)

    if not hasattr(doc, method):
        frappe.throw(f"Method {method} not found on {doctype}")

    fn = getattr(doc, method)
    if args:
        return fn(**args)
    return fn()


# --- Internal helpers ---


def _get_comments(doctype: str, name: str) -> list[dict[str, Any]]:
    """Get comments for a document."""
    try:
        return frappe.db.get_all(
            "Comment",
            filters={
                "reference_doctype": doctype,
                "reference_name": name,
                "comment_type": ("in", ["Comment", "Workflow"]),
            },
            fields=["name", "content", "comment_by", "comment_email", "creation", "modified"],
            order_by="creation desc",
        )
    except Exception:
        return []


def _get_attachments(doctype: str, name: str) -> list[dict[str, Any]]:
    """Get file attachments for a document."""
    try:
        return frappe.db.get_all(
            "File",
            filters={
                "attached_to_doctype": doctype,
                "attached_to_name": name,
                "is_folder": 0,
            },
            fields=["name", "file_name", "file_url", "file_size", "is_private"],
            order_by="creation desc",
        )
    except Exception:
        return []


def _get_versions(doctype: str, name: str) -> list[dict[str, Any]]:
    """Get version history for a document."""
    try:
        return frappe.db.get_all(
            "Version",
            filters={
                "ref_doctype": doctype,
                "docname": name,
            },
            fields=["name", "owner", "creation", "data"],
            order_by="creation desc",
            limit=50,
        )
    except Exception:
        return []


def _get_assignments(doctype: str, name: str) -> list[dict[str, Any]]:
    """Get todo assignments for a document."""
    try:
        return frappe.db.get_all(
            "ToDo",
            filters={
                "reference_type": doctype,
                "reference_name": name,
                "status": "Open",
            },
            fields=["name", "owner", "description", "allocated_to", "assignment_rule"],
        )
    except Exception:
        return []


def _get_shares(doctype: str, name: str) -> list[dict[str, Any]]:
    """Get share records for a document."""
    try:
        return frappe.db.get_all(
            "DocShare",
            filters={
                "share_doctype": doctype,
                "share_name": name,
            },
            fields=["name", "user", "read", "write", "share", "everyone"],
        )
    except Exception:
        return []


def _get_doc_permissions(doctype: str, name: str) -> dict[str, Any]:
    """Get user permissions for a document."""
    user = frappe.session.user
    try:
        return {
            "read": frappe.has_permission(doctype, "read", docname=name, user=user),
            "write": frappe.has_permission(doctype, "write", docname=name, user=user),
            "share": frappe.has_permission(doctype, "share", docname=name, user=user),
        }
    except Exception:
        return {"read": True, "write": False, "share": False}


def _get_views(doctype: str, name: str) -> list[dict[str, Any]]:
    """Get view logs for a document."""
    try:
        return frappe.db.get_all(
            "View Log",
            filters={
                "reference_doctype": doctype,
                "reference_name": name,
            },
            fields=["name", "viewed_by", "creation"],
            order_by="creation desc",
            limit=10,
        )
    except Exception:
        return []


def _get_energy_point_logs(doctype: str, name: str) -> list[dict[str, Any]]:
    """Get energy point logs for a document."""
    try:
        return frappe.db.get_all(
            "Energy Point Log",
            filters={
                "reference_doctype": doctype,
                "reference_name": name,
            },
            fields=["name", "user", "type", "points", "reason", "creation"],
            order_by="creation desc",
        )
    except Exception:
        return []


def _get_link_titles(doc: "frappe.Document") -> dict[str, str]:
    """Get title values for Link fields on a document."""
    link_titles: dict[str, str] = {}

    try:
        meta = frappe.get_meta(doc.doctype)
        for field in meta.fields if hasattr(meta, "fields") else []:
            if getattr(field, "fieldtype", None) == "Link":
                fieldname = getattr(field, "fieldname", "")
                value = doc.get(fieldname)
                if value:
                    link_dt = getattr(field, "options", "")
                    if link_dt:
                        try:
                            title = frappe.db.get_value(link_dt, value, "title_field") or value
                            link_titles[f"{fieldname}:{value}"] = title
                        except Exception:
                            link_titles[f"{fieldname}:{value}"] = value
    except Exception:
        pass

    return link_titles


def _discover_link_fields(doctype: str) -> dict[str, list[str]]:
    """Discover fields in other doctypes that link to this doctype."""
    linkinfo: dict[str, list[str]] = {}

    try:
        # Query DocField for fields that have this doctype as options
        results = frappe.db.get_all(
            "DocField",
            filters={"fieldtype": "Link", "options": doctype},
            fields=["parent", "fieldname"],
        )
        for r in results:
            linked_dt = r["parent"]
            fieldname = r["fieldname"]
            if linked_dt not in linkinfo:
                linkinfo[linked_dt] = []
            linkinfo[linked_dt].append(fieldname)
    except Exception:
        pass

    return linkinfo
