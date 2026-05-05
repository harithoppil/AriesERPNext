"""
frappe.utils.error — Error logging utilities.

Provides ``log_error``, the canonical way to persist an exception or
informational message to the ``tabError Log`` table, plus helper
routines for formatting error pages / messages.
"""

from __future__ import annotations

import datetime
import traceback
from typing import Any


# ---------------------------------------------------------------------------
# Default error page HTML — shown when a request crashes and no custom
# handler has been registered.
# ---------------------------------------------------------------------------

_DEFAULT_ERROR_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Error</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                           Roboto, Oxygen, Ubuntu, Cantarell, "Open Sans",
                           "Helvetica Neue", sans-serif;
               margin: 40px; background: #f5f7fa; color: #36414c; }}
        .error-box {{ background: #fff; border: 1px solid #d1d8dd;
                      border-radius: 4px; padding: 30px; max-width: 800px;
                      margin: 0 auto; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
        h2 {{ color: #ff5858; margin-top: 0; }}
        pre {{ background: #f0f4f7; padding: 15px; border-radius: 3px;
              overflow-x: auto; font-size: 13px; }}
        .footer {{ text-align: center; margin-top: 20px; color: #8d99a6;
                  font-size: 12px; }}
    </style>
</head>
<body>
    <div class="error-box">
        <h2>Server Error</h2>
        <p>{message}</p>
        {traceback_html}
    </div>
    <div class="footer">Frappe Framework</div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def log_error(
    title: str | None = None,
    message: str | None = None,
    reference_doctype: str | None = None,
    reference_name: str | None = None,
) -> None:
    """Persist an error to ``tabError Log``.

    Parameters
    ----------
    title:
        Short headline for the error (e.g. ``"Payment Entry validation"``).
    message:
        Detailed message or traceback.  When omitted and an exception is
        active, the current traceback is captured automatically.
    reference_doctype:
        Optional DocType that caused the error.
    reference_name:
        Optional document name that caused the error.
    """
    # Capture traceback automatically when no explicit message is given
    if message is None:
        message = _capture_traceback()

    # Defaults
    title = title or "Error"
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

    # Build the record
    error_record = {
        "doctype": "Error Log",
        "error": message,
        "method": title,
        "reference_doctype": reference_doctype or "",
        "reference_name": reference_name or "",
        "creation": now,
    }

    # Persist — try the database first, fall back to stderr
    try:
        import frappe

        doc = frappe.get_doc(error_record)
        doc.insert(ignore_permissions=True)

        # Commit so the error survives even if the calling transaction
        # is eventually rolled back.
        frappe.db.commit()
    except Exception:
        # If the framework isn't bootstrapped yet, print to stderr
        import sys

        print(f"[ERROR LOG] {title}", file=sys.stderr)
        print(f"  Time : {now}", file=sys.stderr)
        if reference_doctype:
            print(f"  Doc  : {reference_doctype} / {reference_name}", file=sys.stderr)
        print(message, file=sys.stderr)


def get_default_error_message() -> str:
    """Return a generic, safe error message for display to end users.

    This avoids leaking internal details (paths, SQL, etc.).
    """
    return (
        "There was an error processing your request. "
        "Our team has been notified. Please try again later."
    )


def get_error_html(
    message: str | None = None, include_traceback: bool = False
) -> str:
    """Render a full HTML error page.

    Parameters
    ----------
    message:
        User-visible message.  Defaults to :func:`get_default_error_message`.
    include_traceback:
        If ``True``, embed the current exception traceback in the page
        (useful in development, **never** in production).
    """
    message = message or get_default_error_message()

    traceback_html = ""
    if include_traceback:
        tb = _capture_traceback()
        if tb:
            traceback_html = f"<h3>Traceback</h3><pre>{_escape_html(tb)}</pre>"

    return _DEFAULT_ERROR_TEMPLATE.format(
        message=_escape_html(message),
        traceback_html=traceback_html,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _capture_traceback() -> str:
    """Return the current exception traceback, or ``""`` if none is active."""
    import sys

    exc_type, exc_value, exc_tb = sys.exc_info()
    if exc_type is None:
        return ""
    return "".join(traceback.format_exception(exc_type, exc_value, exc_tb))


def _escape_html(text: str) -> str:
    """Escape ``&``, ``<``, ``>`` for safe insertion into HTML."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
