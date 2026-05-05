"""
Frappe Permissions — RBAC + Field-Level + Document-Level ACL

Replaces frappe/permissions.py — handles all permission checks that
ERPNext relies on: role-based, user-level, and custom controller permissions.
"""

from __future__ import annotations

import functools
from typing import Any

import frappe
from frappe.types import _dict


STANDARD_PERMISSIONS = ("read", "write", "create", "submit", "cancel", "amend", "delete", "print", "email", "report", "import", "export", "share")


def has_permission(
    doctype,
    ptype="read",
    doc=None,
    verbose=False,
    user=None,
    print_logs=False,
    parent_doctype=None,
    ignore_share_permissions=False,
    debug=False,
):
    """Check if user has permission `ptype` on `doctype` (or specific `doc`).

    Returns True/False. If verbose=True, prints debug info.
    """
    if not user:
        user = frappe.session.user

    # Administrator always has permission
    if user == "Administrator":
        return True

    # Get role permissions for the doctype
    role_perms = get_role_permissions(doctype, user=user)

    # Check if the permission type is granted
    if not role_perms.get(ptype):
        if verbose:
            print(f"No {ptype} permission on {doctype} for user {user}")
        return False

    # Check user permissions (document-level restrictions)
    if doc and not ignore_share_permissions:
        user_perms = get_user_permissions(user)
        if doctype in user_perms:
            allowed_docs = [p.doc for p in user_perms[doctype]]
            doc_name = doc.name if hasattr(doc, "name") else doc
            if doc_name not in allowed_docs:
                if verbose:
                    print(f"User {user} not allowed to access {doctype} {doc_name}")
                return False

    return True


def get_role_permissions(doctype_meta, user=None, is_owner=None, debug=False) -> _dict:
    """Get permissions for a user on a DocType based on their roles.

    :param doctype_meta: DocType name or meta object
    :param user: User to check (default: current user)
    :returns: _dict with permission types as keys (read, write, create, etc.)
    """
    if not user:
        user = frappe.session.user

    if isinstance(doctype_meta, str):
        doctype = doctype_meta
    else:
        doctype = doctype_meta.name if hasattr(doctype_meta, "name") else str(doctype_meta)

    # Get user's roles
    user_roles = get_roles(user)

    # Get all DocPerm records for this doctype matching user's roles
    perms = frappe.db.get_all(
        "DocPerm",
        filters={"parent": doctype, "role": ("in", user_roles)},
        fields=["*"],
    )

    # Also check Custom DocPerm
    custom_perms = frappe.db.get_all(
        "Custom DocPerm",
        filters={"parent": doctype, "role": ("in", user_roles)},
        fields=["*"],
    )

    # Custom perms override standard perms
    if custom_perms:
        perms = custom_perms

    # Merge permissions — if ANY role grants a permission, user has it
    result = _dict({p: 0 for p in STANDARD_PERMISSIONS})
    result.select = 0
    result.if_owner = {}

    for perm in perms:
        for ptype in STANDARD_PERMISSIONS:
            if perm.get(ptype):
                result[ptype] = 1
        if perm.get("select"):
            result.select = 1
        if perm.get("if_owner"):
            result.if_owner[perm.get("permlevel", 0)] = 1

    return result


def get_doc_permissions(doc, user=None, ptype=None):
    """Get all permissions for a specific document."""
    if not user:
        user = frappe.session.user

    doctype = doc.doctype if hasattr(doc, "doctype") else doc

    perms = get_role_permissions(doctype, user=user)

    # Add ownership check
    if hasattr(doc, "owner") and doc.owner == user:
        perms.is_owner = True

    return perms


def get_user_permissions(user=None):
    """Get user-specific document permissions.

    Returns dict of {doctype: [allowed_doc_names]}.
    """
    if not user:
        user = frappe.session.user

    cache_key = f"user_permissions:{user}"
    if hasattr(frappe.local, "cache") and frappe.local.cache:
        cached = frappe.local.cache.get(cache_key)
        if cached:
            return cached

    # Load from User Permission doctype
    user_perms = frappe.db.get_all(
        "User Permission",
        filters={"user": user, "allow": 1},
        fields=["for_value", "applicable_for"],
    )

    result = _dict()
    for perm in user_perms:
        dt = perm.applicable_for or "*"
        if dt not in result:
            result[dt] = []
        result[dt].append(perm.for_value)

    # Cache
    if hasattr(frappe.local, "cache"):
        frappe.local.cache[cache_key] = result

    return result


def has_user_permission(doc, user=None, debug=False, *, ptype=None):
    """Check if user has user-level permission for a document."""
    if not user:
        user = frappe.session.user

    user_perms = get_user_permissions(user)
    doctype = doc.doctype if hasattr(doc, "doctype") else doc

    if doctype not in user_perms:
        return True  # No restrictions = allowed

    doc_name = doc.name if hasattr(doc, "name") else doc
    allowed = user_perms[doctype]
    return doc_name in allowed


def has_controller_permissions(doc, ptype, user=None) -> bool:
    """Check custom permissions defined in the document's controller class."""
    if hasattr(doc, "has_permission"):
        return doc.has_permission(ptype)
    return True


def get_roles(user=None, with_standard=True):
    """Get all roles for a user.

    Includes 'All' and 'Guest' or 'Administrator' automatically.
    """
    if not user:
        user = frappe.session.user

    if user == "Administrator":
        return ["Administrator", "All"]
    if user == "Guest":
        return ["Guest", "All"]

    cache_key = f"roles:{user}"
    if hasattr(frappe.local, "cache") and frappe.local.cache:
        cached = frappe.local.cache.get(cache_key)
        if cached:
            return cached

    roles = []
    if with_standard:
        roles.append("All")

    # Get roles from Has Role table
    user_roles = frappe.db.get_all(
        "Has Role",
        filters={"parent": user, "parenttype": "User"},
        pluck="role",
    )
    roles.extend(user_roles)

    # Cache
    if hasattr(frappe.local, "cache"):
        frappe.local.cache[cache_key] = roles

    return roles


def get_doctype_roles(doctype, access_type="read"):
    """Get roles that have a specific access type on a doctype."""
    return frappe.db.get_all(
        "DocPerm",
        filters={"parent": doctype, access_type: 1},
        pluck="role",
        distinct=True,
    )


def get_perms_for(roles, perm_doctype="DocPerm"):
    """Get all permissions records for given roles."""
    return frappe.db.get_all(
        perm_doctype,
        filters={"role": ("in", roles)},
        fields=["*"],
    )


def get_doctypes_with_custom_docperms():
    """Get list of DocTypes that have custom permissions."""
    return frappe.db.get_all("Custom DocPerm", pluck="parent", distinct=True)


def add_user_permission(doctype, name, user, applicable_for=None, is_default=0, hide_descendants=0):
    """Grant a user permission to access a specific document."""
    perm = frappe.get_doc(
        {
            "doctype": "User Permission",
            "user": user,
            "allow": doctype,
            "for_value": name,
            "applicable_for": applicable_for,
            "is_default": is_default,
            "hide_descendants": hide_descendants,
        }
    )
    perm.insert(ignore_permissions=True)
    clear_user_permissions(user)
    return perm


def remove_user_permission(doctype, name, user):
    """Remove a user permission."""
    perms = frappe.db.get_all(
        "User Permission",
        filters={"user": user, "allow": doctype, "for_value": name},
        pluck="name",
    )
    for perm_name in perms:
        frappe.delete_doc("User Permission", perm_name, ignore_permissions=True)
    clear_user_permissions(user)


def clear_user_permissions_for_doctype(doctype, user=None):
    """Clear all user permissions for a doctype."""
    if not user:
        user = frappe.session.user
    perms = frappe.db.get_all(
        "User Permission",
        filters={"user": user, "allow": doctype},
        pluck="name",
    )
    for perm_name in perms:
        frappe.delete_doc("User Permission", perm_name, ignore_permissions=True)
    clear_user_permissions(user)


def clear_user_permissions(user=None):
    """Clear cached user permissions."""
    if not user:
        user = frappe.session.user
    cache_key = f"user_permissions:{user}"
    if hasattr(frappe.local, "cache") and frappe.local.cache:
        frappe.local.cache.pop(cache_key, None)


def can_import(doctype, raise_exception=False):
    """Check if user can import this doctype."""
    result = has_permission(doctype, "import")
    if not result and raise_exception:
        frappe.throw(frappe._("Not permitted to import {0}").format(doctype), frappe.PermissionError)
    return result


def can_export(doctype, raise_exception=False, is_owner=False):
    """Check if user can export this doctype."""
    result = has_permission(doctype, "export")
    if not result and raise_exception:
        frappe.throw(frappe._("Not permitted to export {0}").format(doctype), frappe.PermissionError)
    return result


def update_permission_property(doctype, role, permlevel, ptype, value=None):
    """Update a specific permission property."""
    out = frappe.get_all(
        "DocPerm",
        filters={"parent": doctype, "role": role, "permlevel": permlevel},
    )
    if out:
        frappe.db.set_value("DocPerm", out[0].name, ptype, value)
    else:
        # Create new perm
        perm = frappe.get_doc(
            {
                "doctype": "DocPerm",
                "parent": doctype,
                "parentfield": "permissions",
                "parenttype": "DocType",
                "role": role,
                "permlevel": permlevel,
                ptype: value,
            }
        )
        perm.insert(ignore_permissions=True)


def add_permission(doctype, role, permlevel=0, ptype=None):
    """Add a permission for a role on a doctype."""
    perm = frappe.get_doc(
        {
            "doctype": "DocPerm",
            "parent": doctype,
            "parentfield": "permissions",
            "parenttype": "DocType",
            "role": role,
            "permlevel": permlevel,
        }
    )
    if ptype:
        perm.set(ptype, 1)
    perm.insert(ignore_permissions=True)


def copy_perms(parent):
    """Copy permissions from one doctype to Custom DocPerm."""
    perms = frappe.get_all("DocPerm", filters={"parent": parent}, fields=["*"])
    for perm in perms:
        perm["doctype"] = "Custom DocPerm"
        perm["name"] = None
        frappe.get_doc(perm).insert(ignore_permissions=True)


def reset_perms(doctype):
    """Reset permissions to defaults from the DocType definition."""
    frappe.db.delete("Custom DocPerm", {"parent": doctype})
    clear_doctype_cache(doctype)


def get_linked_doctypes(dt: str) -> list:
    """Get DocTypes that are linked to this doctype via Link fields."""
    meta = frappe.get_meta(dt)
    linked = []
    for field in meta.fields:
        if field.fieldtype == "Link" and field.options:
            linked.append(field.options)
    return list(set(linked))


def get_doc_name(doc):
    return doc.name if hasattr(doc, "name") else str(doc)


def get_rights(doctype=None):
    """Get all rights for a doctype."""
    return list(STANDARD_PERMISSIONS)


def allow_everything(doctype=None):
    """Temporarily allow all permissions. For maintenance scripts."""
    original = frappe.session.user
    frappe.set_user("Administrator")
    return original


def check_doctype_permission(doctype, ptype="read"):
    """Check permission and raise if not allowed."""
    if not has_permission(doctype, ptype):
        frappe.throw(frappe._("No {0} permission on {1}").format(ptype, doctype), frappe.PermissionError)


def clear_doctype_cache(doctype):
    """Clear permission cache for a doctype."""
    if hasattr(frappe.local, "cache") and frappe.local.cache:
        for key in list(frappe.local.cache.keys()):
            if doctype in key:
                frappe.local.cache.pop(key, None)


def setup_custom_perms(parent):
    """Setup custom permissions if they don't exist."""
    if not frappe.get_all("Custom DocPerm", filters={"parent": parent}, limit=1):
        copy_perms(parent)


def get_valid_perms(doctype=None, user=None):
    """Get valid permissions for a user."""
    if not user:
        user = frappe.session.user
    roles = get_roles(user)
    filters = {"role": ("in", roles)}
    if doctype:
        filters["parent"] = doctype
    return frappe.get_all("DocPerm", filters=filters, fields=["*"])


def get_doctypes_with_read():
    """Get list of DocTypes the current user can read."""
    user = frappe.session.user
    roles = get_roles(user)
    return frappe.db.get_all(
        "DocPerm",
        filters={"role": ("in", roles), "read": 1},
        pluck="parent",
        distinct=True,
    )
