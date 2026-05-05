"""
Frappe Boot — Boot Info for Frontend

Replaces frappe/boot.py — provides the initial data payload sent to
the frontend when the page loads. Includes user info, permissions,
system settings, and other metadata needed by the Desk UI.
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe.types import _dict


def get_bootinfo():
    """Get the complete boot info for the current user.

    This is the big dict sent to the frontend on page load.
    Contains user info, permissions, doctypes, languages, etc.
    """
    bootinfo = _dict(
        {
            "usr": frappe.session.user,
            "lang": frappe.local.lang or "en",
            "version": frappe.__version__,
            "server_date": frappe.utils.nowdate(),
            "server_time": frappe.utils.nowtime(),
            "server_datetime": frappe.utils.now(),
            "timezone": frappe.utils.get_system_timezone(),
            "time_zone": frappe.utils.get_system_timezone(),
            "user": get_user_info(),
            "home_folder": "/",
            "has_website_permissions": False,
            "notification_settings": {},
            "is_first_startup": False,
            "desk_theme": "Light",
            "announcement": None,
            "success_action": get_success_action(),
            "currency": get_currency(),
            "system_settings": get_system_settings_dict(),
            "modules": get_modules(),
            "domains": frappe.get_active_domains(),
            "read_only_mode": frappe.conf.read_only or False,
            "developer_mode": frappe.conf.developer_mode or False,
            "setup_complete": frappe.is_setup_complete(),
            "csrf_token": frappe.sessions.get_csrf_token(),
            "calendar_defaults": get_calendar_defaults(),
        }
    )

    # Add language info
    bootinfo.lang_dict = get_lang_dict()

    # Add route history
    bootinfo.route_history = get_route_history()

    return bootinfo


def get_user_info():
    """Get info about the current user."""
    user = frappe.session.user

    info = _dict(
        {
            "name": user,
            "email": user,
            "full_name": frappe.db.get_value("User", user, "full_name") or user,
            "user_type": frappe.db.get_value("User", user, "user_type") or "System User",
            "roles": frappe.get_roles(),
            "defaults": frappe.defaults.get_defaults(),
            "can_create": get_can_create(),
            "can_read": get_can_read(),
            "can_write": get_can_write(),
            "can_cancel": get_can_cancel(),
            "can_delete": get_can_delete(),
            "can_get_report": [],
            "can_import": [],
            "can_export": [],
            "can_print": [],
            "can_email": [],
            "can_set_user_permissions": has_user_permission_doctypes(),
        }
    )

    # Add user image
    info.image = frappe.db.get_value("User", user, "user_image") or None

    return info


def get_system_settings_dict() -> dict[str, Any]:
    """Get system settings as a dict."""
    try:
        settings = frappe.get_single("System Settings")
        return {
            "date_format": settings.date_format or "yyyy-mm-dd",
            "time_format": settings.time_format or "HH:mm:ss",
            "first_day_of_the_week": settings.first_day_of_the_week or "Sunday",
            "number_format": settings.number_format or "#,###.##",
            "float_precision": settings.float_precision or 3,
            "currency_precision": settings.currency_precision or 2,
            "rounding_method": settings.rounding_method or "Banker's Rounding",
            "session_expiry": settings.session_expiry or "06:00:00",
            "logout_on_password_change": settings.logout_on_password_change or 1,
            "allow_consecutive_login_attempts": settings.allow_consecutive_login_attempts or 3,
            "allow_login_using_mobile_number": settings.allow_login_using_mobile_number or 0,
            "allow_login_using_user_name": settings.allow_login_using_user_name or 0,
            "disable_browser_autocomplete": settings.disable_browser_autocomplete or 0,
            "deny_multiple_sessions": settings.deny_multiple_sessions or 0,
        }
    except Exception:
        return {
            "date_format": "yyyy-mm-dd",
            "time_format": "HH:mm:ss",
            "first_day_of_the_week": "Sunday",
            "number_format": "#,###.##",
            "float_precision": 3,
            "currency_precision": 2,
        }


def get_modules():
    """Get list of modules accessible to the user."""
    modules = []
    try:
        all_modules = frappe.db.get_all(
            "Module Def",
            fields=["name", "module_name", "app_name"],
            order_by="module_name",
        )
        for mod in all_modules:
            modules.append(
                {
                    "name": mod.name,
                    "label": mod.module_name or mod.name,
                    "app": mod.app_name or "frappe",
                }
            )
    except Exception:
        pass
    return modules


def get_can_create():
    """Get list of DocTypes the user can create."""
    if frappe.session.user == "Administrator":
        return [d.name for d in frappe.get_all("DocType", filters={"issingle": 0, "istable": 0})]

    can_create = []
    for dt in frappe.get_all("DocType", filters={"issingle": 0, "istable": 0}, pluck="name"):
        if frappe.has_permission(dt, "create"):
            can_create.append(dt)
    return can_create


def get_can_read():
    """Get list of DocTypes the user can read."""
    return frappe.permissions.get_doctypes_with_read()


def get_can_write():
    """Get list of DocTypes the user can write."""
    can_write = []
    for dt in frappe.get_all("DocType", pluck="name"):
        if frappe.has_permission(dt, "write"):
            can_write.append(dt)
    return can_write


def get_can_cancel():
    """Get list of DocTypes the user can cancel."""
    can_cancel = []
    for dt in frappe.get_all("DocType", pluck="name"):
        if frappe.has_permission(dt, "cancel"):
            can_cancel.append(dt)
    return can_cancel


def get_can_delete():
    """Get list of DocTypes the user can delete."""
    can_delete = []
    for dt in frappe.get_all("DocType", pluck="name"):
        if frappe.has_permission(dt, "delete"):
            can_delete.append(dt)
    return can_delete


def get_can_export():
    """Get list of DocTypes the user can export."""
    can_export = []
    for dt in frappe.get_all("DocType", pluck="name"):
        if frappe.has_permission(dt, "export"):
            can_export.append(dt)
    return can_export


def has_user_permission_doctypes():
    """Get DocTypes for which user can set user permissions."""
    if frappe.session.user == "Administrator":
        return [d.name for d in frappe.get_all("DocType")]
    return []


def get_calendar_defaults():
    """Get default calendar settings."""
    return {
        "first_day": frappe.defaults.get_global_default("calendar_first_day") or "Sunday",
    }


def get_success_action():
    """Get success action configuration."""
    return {}


def get_currency():
    """Get default currency info."""
    try:
        currency = frappe.db.get_single_value("Global Defaults", "default_currency")
        if currency:
            return {
                "name": currency,
                "fraction": frappe.db.get_value("Currency", currency, "fraction_units") or 100,
                "symbol": frappe.db.get_value("Currency", currency, "symbol") or currency,
            }
    except Exception:
        pass
    return {"name": "USD", "fraction": 100, "symbol": "$"}


def get_lang_dict():
    """Get available languages."""
    return {
        "en": "English",
    }


def get_route_history():
    """Get recent route history for the user."""
    try:
        return frappe.get_all(
            "Route History",
            filters={"user": frappe.session.user},
            fields=["route", "creation"],
            order_by="creation desc",
            limit=20,
        )
    except Exception:
        return []


def get_boot_assets_json():
    """Get boot assets manifest."""
    return {}


def get_unseen_notes():
    """Get notes the user hasn't seen."""
    try:
        return frappe.get_all(
            "Note",
            filters={
                "notify_on_login": 1,
                "name": ("not in", frappe.get_all(
                    "Note Seen By",
                    filters={"user": frappe.session.user},
                    pluck="parent",
                )),
            },
            fields=["name", "title", "content", "public"],
        )
    except Exception:
        return []
