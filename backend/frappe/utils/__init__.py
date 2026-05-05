"""
frappe.utils — Core utility layer for the Frappe framework.

This is the most heavily-used module in ERPNext.  It exports safe
type-conversion helpers (cint, cstr, flt), date/time utilities
(now, nowdate, add_days, date_diff), text helpers (strip_html,
sanitize_html, bold), validation routines, and more.

Every function is designed to be forgiving — bad input returns a
sensible default rather than raising.
"""

from __future__ import annotations

import datetime
import os
import sys
import traceback
from typing import Any

# ---------------------------------------------------------------------------
# Re-export EVERYTHING from frappe.utils.data so that callers can simply do::
#   from frappe.utils import cint, flt, nowdate
# ---------------------------------------------------------------------------

from frappe.utils.data import (  # noqa: F401
    # Type conversion
    cint,
    cstr,
    flt,
    sbool,
    parse_json,
    encode,
    as_unicode,
    safe_encode,
    safe_decode,
    to_bool,
    # Date / time
    now,
    nowdate,
    nowtime,
    today,
    getdate,
    get_datetime,
    get_datetime_in_timezone,
    now_datetime,
    add_days,
    add_months,
    date_diff,
    time_diff,
    time_diff_in_seconds,
    time_diff_in_hours,
    add_to_date,
    get_last_day,
    get_first_day,
    get_quarter_start,
    get_quarter_ending,
    get_year_start,
    get_year_ending,
    get_week_starting_date,
    get_week_ending_date,
    get_timespan_date_range,
    format_date,
    formatdate,
    format_time,
    format_datetime,
    get_user_date_format,
    get_user_time_format,
    get_system_timezone,
    get_datetime_str,
    get_date_str,
    get_time_str,
    global_date_format,
    pretty_date,
    rounded,
    # String / text
    strip,
    strip_html,
    sanitize_html,
    is_html,
    markdown_to_html,
    to_markdown,
    bold,
    capitalize,
    random_string,
    has_common,
    comma_sep,
    comma_and,
    new_line_sep,
    unique,
    money_in_words,
    to_csv,
    # Networking
    get_url,
    get_host_name,
    get_link_to_form,
    get_html_format,
    # Validation
    validate_email_address,
    validate_phone_number,
    validate_name,
    validate_url,
    validate_json_string,
    # Error / debug
    get_traceback,
    get_fullname,
    get_user_info,
    split_emails,
    # Table / serialization
    get_table_name,
    getdate_str,
    fmt_money,
    fmt_date,
    fmt_datetime,
    get_timedelta,
    to_json,
    groupby_dict,
    # Internal helpers
    create_folder,
    _dict,
)


# ---------------------------------------------------------------------------
# __init__-level implementations
# ---------------------------------------------------------------------------


def get_traceback() -> str:
    """Return the current exception traceback as a formatted string.

    Safe to call even outside an ``except`` block — returns ``""``.
    """
    exc_type, exc_value, exc_tb = sys.exc_info()
    if exc_type is None:
        return ""
    return "".join(traceback.format_exception(exc_type, exc_value, exc_tb))


def get_fullname(user: str | None = None) -> str:
    """Return the full name of *user* (defaults to current session user).

    Falls back to the raw user name when the database is unreachable.
    """
    try:
        import frappe

        if not user:
            user = frappe.session.user if hasattr(frappe, "session") else "Guest"
        fullname = frappe.db.get_value("User", user, "full_name")
        if fullname:
            return fullname
    except Exception:
        pass
    return user or "Guest"


def get_user_info(user: str | None = None) -> "_dict":
    """Return a ``_dict`` with basic profile info for *user*.

    Keys: ``name``, ``email``, ``first_name``, ``last_name``,
    ``full_name``, ``user_image``.
    """
    try:
        import frappe

        if not user:
            user = frappe.session.user if hasattr(frappe, "session") else "Guest"
        user_doc = frappe.db.get_value(
            "User",
            user,
            ["name", "email", "first_name", "last_name", "full_name", "user_image"],
            as_dict=True,
        )
        if user_doc:
            return _dict(user_doc)
    except Exception:
        pass
    if not user:
        user = "Guest"
    return _dict(
        name=user,
        email=user,
        first_name=user,
        last_name="",
        full_name=user,
        user_image="",
    )


def create_folder(path: str, with_init: bool = False) -> None:
    """Create directory *path* recursively.

    When *with_init* is ``True`` an empty ``__init__.py`` is also
    created inside the leaf directory.
    """
    os.makedirs(path, exist_ok=True)
    if with_init:
        init_file = os.path.join(path, "__init__.py")
        if not os.path.exists(init_file):
            with open(init_file, "w", encoding="utf-8"):
                pass
