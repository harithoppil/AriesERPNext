"""
Frappe Defaults — User and Global Default Values

Replaces frappe/defaults.py — manages user-specific and global default values.
Stores key-value pairs that can be scoped per-user or globally.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.types import _dict


def set_user_default(key, value, user=None, parenttype=None):
    """Set a user default value."""
    if not user:
        user = frappe.session.user
    set_default(key, value, parent=user, parenttype=parenttype or "__default")


def add_user_default(key, value, user=None, parenttype=None):
    """Add a user default (doesn't overwrite existing)."""
    if not user:
        user = frappe.session.user
    add_default(key, value, parent=user, parenttype=parenttype or "__default")


def get_user_default(key, user=None):
    """Get a user default value.

    Checks in order:
    1. User's defaults
    2. Global defaults
    3. Return key as-is (for things like "__user" → username)
    """
    if not user:
        user = frappe.session.user

    # Check user-specific default
    user_defaults = get_defaults_for(parent=user)
    if key in user_defaults:
        values = user_defaults[key]
        if values:
            return values[0]

    # Check global default
    global_defaults = get_defaults_for(parent="__default")
    if key in global_defaults:
        values = global_defaults[key]
        if values:
            return values[0]

    # Special keys
    if key == "__user":
        return user
    if key == "__today":
        return frappe.utils.today()

    return None


def get_user_permission_default(key, defaults=None):
    """Get a default that respects user permissions."""
    if defaults is None:
        defaults = get_defaults()

    if key in defaults:
        return defaults[key][0] if defaults[key] else None

    return None


def get_user_default_as_list(key, user=None):
    """Get user default as a list."""
    if not user:
        user = frappe.session.user

    user_defaults = get_defaults_for(parent=user)
    if key in user_defaults:
        return user_defaults[key]

    global_defaults = get_defaults_for(parent="__default")
    if key in global_defaults:
        return global_defaults[key]

    return []


def is_a_user_permission_key(key):
    """Check if a key represents a user permission."""
    return key.startswith("_user_permission_")


def not_in_user_permission(key, value, user=None):
    """Check if a value is NOT in user's permissions for a key."""
    if not user:
        user = frappe.session.user

    user_perms = frappe.permissions.get_user_permissions(user)
    if key in user_perms:
        allowed = user_perms[key]
        return value not in allowed
    return True


def get_user_permissions(user=None):
    """Get user permissions as a defaults-compatible dict."""
    if not user:
        user = frappe.session.user

    perms = frappe.permissions.get_user_permissions(user)
    result = _dict()
    for doctype, docs in perms.items():
        result[f"_user_permission_{doctype}"] = docs
    return result


def get_defaults(user=None):
    """Get all defaults for a user (user + global combined)."""
    if not user:
        user = frappe.session.user

    # Start with global defaults
    result = get_defaults_for(parent="__default")

    # Override with user defaults
    user_defaults = get_defaults_for(parent=user)
    for key, values in user_defaults.items():
        result[key] = values

    # Add special defaults
    result["__user"] = [user]
    result["__today"] = [frappe.utils.today()]

    return result


def clear_user_default(key, user=None):
    """Clear a user default."""
    if not user:
        user = frappe.session.user
    clear_default(key, parent=user)


def set_global_default(key, value):
    """Set a global default value."""
    set_default(key, value, parent="__global")


def add_global_default(key, value):
    """Add a global default (doesn't overwrite)."""
    add_default(key, value, parent="__global")


def get_global_default(key):
    """Get a global default value."""
    global_defaults = get_defaults_for(parent="__global")
    if key in global_defaults:
        return global_defaults[key][0] if global_defaults[key] else None
    return None


def set_default(key, value, parent, parenttype="__default"):
    """Set a default value."""
    if value is None:
        clear_default(key, parent=parent)
        return

    # Check if default already exists
    existing = frappe.db.get_value(
        "DefaultValue",
        {"parent": parent, "defkey": key, "parenttype": parenttype},
        "name",
    )

    if existing:
        frappe.db.set_value("DefaultValue", existing, "defvalue", str(value))
    else:
        doc = frappe.get_doc(
            {
                "doctype": "DefaultValue",
                "parent": parent,
                "parenttype": parenttype,
                "defkey": key,
                "defvalue": str(value),
            }
        )
        doc.insert(ignore_permissions=True)

    # Clear cache
    _clear_cache(parent)


def add_default(key, value, parent, parenttype=None):
    """Add a default value without removing existing ones."""
    if not parenttype:
        parenttype = "__default"

    doc = frappe.get_doc(
        {
            "doctype": "DefaultValue",
            "parent": parent,
            "parenttype": parenttype,
            "defkey": key,
            "defvalue": str(value),
        }
    )
    doc.insert(ignore_permissions=True)
    _clear_cache(parent)


def clear_default(key=None, value=None, parent=None, name=None, parenttype=None):
    """Clear default values matching criteria."""
    filters = {"doctype": "DefaultValue"}
    if key:
        filters["defkey"] = key
    if value:
        filters["defvalue"] = value
    if parent:
        filters["parent"] = parent
    if name:
        filters["name"] = name
    if parenttype:
        filters["parenttype"] = parenttype

    defaults = frappe.db.get_all("DefaultValue", filters=filters, pluck="name")
    for default_name in defaults:
        frappe.delete_doc("DefaultValue", default_name, ignore_permissions=True)

    if parent:
        _clear_cache(parent)


def get_defaults_for(parent="__default"):
    """Get all defaults for a specific parent."""
    cache_key = f"defaults:{parent}"
    cached = frappe.cache.get_value(cache_key)
    if cached:
        return _dict(cached)

    defaults = frappe.db.get_all(
        "DefaultValue",
        filters={"parent": parent},
        fields=["defkey", "defvalue"],
    )

    result = _dict()
    for d in defaults:
        if d.defkey not in result:
            result[d.defkey] = []
        result[d.defkey].append(d.defvalue)

    frappe.cache.set_value(cache_key, dict(result))
    return result


def _clear_cache(parent):
    """Clear defaults cache for a parent."""
    cache_key = f"defaults:{parent}"
    frappe.cache.delete_value(cache_key)


def get_nested_default(key, user=None):
    """Get a default, checking user then global scope."""
    return get_user_default(key, user)


def get_discussion_replies(name):
    """Get discussion replies for a topic."""
    return frappe.get_all(
        "Discussion Reply",
        filters={"topic": name},
        fields=["*"],
        order_by="creation asc",
    )
