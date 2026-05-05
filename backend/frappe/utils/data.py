"""
frappe.utils.data — Core utility functions for the Frappe framework.

This module provides the most heavily-used functions in ERPNext:
  • Type conversion: cint, cstr, flt, sbool, to_bool, parse_json, …
  • Date/time: now, nowdate, today, getdate, add_days, date_diff, …
  • String/text: strip_html, sanitize_html, bold, money_in_words, …
  • Validation: validate_email_address, validate_phone_number, …
  • Networking: get_url, get_host_name, …

Every function is designed to be safe (never raise on bad input unless
explicitly documented) and to behave identically to the original Frappe
implementation.
"""

from __future__ import annotations

import datetime
import hashlib
import inspect
import json
import math
import os
import random
import re
import string
import sys
import traceback
import typing
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from html.parser import HTMLParser
from typing import Any, Optional, Union, List, Tuple

# dateutil is used for timezone support
from dateutil import parser as dateutil_parser
from dateutil.relativedelta import relativedelta

# ---------------------------------------------------------------------------
# Frappe internal imports — may be missing during early bootstrap, so guard
# ---------------------------------------------------------------------------
try:
    import frappe
    from frappe import _
except Exception:
    # When frappe itself isn't available (e.g. tests / standalone usage),
    # define a minimal fallback for the translation helper.
    frappe = None  # type: ignore[assignment]

    def _(text: str, lang: str | None = None) -> str:  # noqa: D401
        return text


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

class _dict(dict):
    """dict subclass allowing attribute-style access."""

    def __getattr__(self, key: str) -> Any:
        try:
            return self[key]
        except KeyError:
            raise AttributeError(f"'_dict' object has no attribute '{key}'")

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value

    def __delattr__(self, key: str) -> None:
        try:
            del self[key]
        except KeyError:
            raise AttributeError(f"'_dict' object has no attribute '{key}'")


def getdate_week_start(date: datetime.date) -> datetime.date:
    """Return the Monday of the week containing *date*."""
    return date - datetime.timedelta(days=date.weekday())


# =====================================================================
# 1. Type conversion
# =====================================================================


def cint(s: Any, default: int = 0) -> int:
    """Convert *s* to int, returning *default* on any error.

    Decimal strings are converted via ``float`` first so that
    ``cint("1.5")`` truncates to ``1`` rather than failing.

    Examples::
        cint("1.5") -> 1        # truncates
        cint("")    -> 0
        cint(None)  -> 0
        cint("abc") -> 0
    """
    try:
        if s is None:
            return default
        if isinstance(s, int):
            return s
        if isinstance(s, float):
            return int(s)
        # For strings (and everything else), go through float so that
        # "1.5", "2.0", "-3.7" etc. are handled gracefully.
        return int(float(str(s).strip()))
    except Exception:
        return default


def cstr(s: Any, default: str = "") -> str:
    """Convert *s* to str, returning *default* on ``None`` or error."""
    if s is None:
        return default
    if isinstance(s, str):
        return s
    try:
        return str(s)
    except Exception:
        return default


def flt(s: Any, precision: int | None = None) -> float:
    """Convert *s* to float, returning ``0.0`` on ``None``/empty/error.

    Uses :class:`decimal.Decimal` internally for precision arithmetic,
    then converts back to ``float``.

    Examples::
        flt("1.234", 2) -> 1.23
        flt(None)       -> 0.0
        flt("")         -> 0.0
    """
    try:
        if s is None or s == "":
            return 0.0
        if isinstance(s, Decimal):
            result = float(s)
        elif isinstance(s, float):
            result = s
        else:
            result = float(Decimal(str(s)))
    except Exception:
        return 0.0

    if precision is not None and isinstance(precision, int):
        multiplier = 10 ** precision
        result = math.floor(result * multiplier + 0.5) / multiplier
    return result


def sbool(v: Any) -> bool:
    """Smart boolean conversion.

    Accepts strings such as ``"1"``, ``"yes"``, ``"true"`` (case-insensitive)
    as ``True`` and ``"0"``, ``"no"``, ``"false"`` as ``False``.
    Falls back to Python truthiness for other types.
    """
    if isinstance(v, str):
        lv = v.strip().lower()
        if lv in ("1", "yes", "true", "on"):
            return True
        if lv in ("0", "no", "false", "off", ""):
            return False
    return bool(v)


def to_bool(val: Any) -> bool:
    """Alias / stricter bool conversion.

    ``1``, ``"1"``, ``"Yes"`` → ``True``.
    ``0``, ``"0"``, ``"No"``, ``None``, ``""`` → ``False``.
    """
    if val is None or val == "":
        return False
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        return val.strip().lower() in ("1", "yes", "true", "on")
    return bool(val)


def parse_json(val: Any) -> Any:
    """Parse a JSON string; return the original value if it is not a string.

    Also handles values that are already decoded (dict / list).
    """
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return val
    return val


def encode(val: Any, encoding: str = "utf-8") -> str:
    """Return *val* as a string, decoding bytes if necessary."""
    if isinstance(val, bytes):
        return val.decode(encoding)
    return str(val)


def as_unicode(text: Any, encoding: str = "utf-8") -> str:
    """Ensure *text* is a ``str`` (Python 3 unicode)."""
    if isinstance(text, bytes):
        return text.decode(encoding)
    return str(text) if text is not None else ""


def safe_encode(val: Any, encoding: str = "utf-8") -> bytes:
    """Encode *val* to ``bytes`` safely."""
    if isinstance(val, bytes):
        return val
    if isinstance(val, str):
        return val.encode(encoding)
    return str(val).encode(encoding)


def safe_decode(val: Any, encoding: str = "utf-8") -> str:
    """Decode *val* to ``str`` safely."""
    if isinstance(val, str):
        return val
    if isinstance(val, bytes):
        try:
            return val.decode(encoding)
        except UnicodeDecodeError:
            return val.decode(encoding, errors="replace")
    return str(val)


# =====================================================================
# 2. Date / Time
# =====================================================================


def now() -> str:
    """Current local date-time as ``"YYYY-MM-DD HH:MM:SS"``."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def nowdate() -> str:
    """Current local date as ``"YYYY-MM-DD"``."""
    return datetime.date.today().strftime("%Y-%m-%d")


def nowtime() -> str:
    """Current local time as ``"HH:MM:SS"``."""
    return datetime.datetime.now().strftime("%H:%M:%S")


def today() -> str:
    """Current local date as ``"YYYY-MM-DD"``."""
    return nowdate()


def now_datetime() -> datetime.datetime:
    """Current local date-time as a :class:`datetime.datetime` object."""
    return datetime.datetime.now()


def get_system_timezone() -> str:
    """Return the system timezone name.

    Tries ``frappe.local.timezone`` first, then falls back to
    ``dateutil.tz.tzlocal()`` name, finally ``"UTC"``.
    """
    try:
        if frappe and hasattr(frappe, "local") and frappe.local.timezone:
            return frappe.local.timezone
    except Exception:
        pass
    try:
        import tzlocal
        return str(tzlocal.get_localzone())
    except Exception:
        pass
    try:
        from dateutil.tz import tzlocal as _tzlocal
        return str(_tzlocal())
    except Exception:
        return "UTC"


def getdate(string_date: Any = None) -> datetime.date:
    """Parse *string_date* into a :class:`datetime.date`.

    * ``None`` or ``""`` → today.
    * Already a :class:`~datetime.date` / :class:`~datetime.datetime` → returned as-is (or `.date()`).
    * String → parsed via :mod:`dateutil`.

    Raises :class:`ValueError` on unparseable strings.
    """
    if string_date is None or string_date == "":
        return datetime.date.today()
    if isinstance(string_date, datetime.datetime):
        return string_date.date()
    if isinstance(string_date, datetime.date):
        return string_date
    if isinstance(string_date, str):
        string_date = string_date.strip()
        # Try common formats first for speed
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m-%d-%Y", "%Y/%m/%d", "%d/%m/%Y"):
            try:
                return datetime.datetime.strptime(string_date, fmt).date()
            except ValueError:
                continue
        return dateutil_parser.parse(string_date).date()
    raise ValueError(f"Cannot convert {string_date!r} to date")


def get_datetime(datetime_str: Any = None) -> datetime.datetime:
    """Parse *datetime_str* into a :class:`datetime.datetime`.

    * ``None`` or ``""`` → now.
    * Already a :class:`~datetime.datetime` → returned as-is.
    * :class:`~datetime.date` → midnight of that date.
    * String → parsed via :mod:`dateutil`.
    """
    if datetime_str is None or datetime_str == "":
        return datetime.datetime.now()
    if isinstance(datetime_str, datetime.datetime):
        return datetime_str
    if isinstance(datetime_str, datetime.date):
        return datetime.datetime.combine(datetime_str, datetime.time())
    if isinstance(datetime_str, str):
        datetime_str = datetime_str.strip()
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%d-%m-%Y %H:%M:%S",
            "%Y-%m-%d",
            "%d-%m-%Y",
            "%m-%d-%Y",
        ):
            try:
                return datetime.datetime.strptime(datetime_str, fmt)
            except ValueError:
                continue
        return dateutil_parser.parse(datetime_str)
    raise ValueError(f"Cannot convert {datetime_str!r} to datetime")


def get_datetime_in_timezone(datetime_str: str, timezone: str) -> datetime.datetime:
    """Parse *datetime_str* and localise it to *timezone*."""
    import pytz

    dt = get_datetime(datetime_str)
    if dt.tzinfo is None:
        tz = pytz.timezone(timezone)
        dt = tz.localize(dt)
    return dt


def add_days(date: Any, days: int | float) -> str:
    """Add *days* to *date* and return ``YYYY-MM-DD`` string."""
    d = getdate(date)
    result = d + datetime.timedelta(days=days)
    return result.strftime("%Y-%m-%d")


def add_months(date: Any, months: int) -> str:
    """Add *months* to *date* and return ``YYYY-MM-DD`` string.

    Uses :class:`dateutil.relativedelta` so month-end wrapping is sane.
    """
    d = getdate(date)
    result = d + relativedelta(months=months)
    return result.strftime("%Y-%m-%d")


def date_diff(string_ed_date: Any, string_st_date: Any) -> int:
    """Return ``(ed_date - st_date)`` in days."""
    return (getdate(string_ed_date) - getdate(string_st_date)).days


def time_diff(string_ed_date: Any, string_st_date: Any) -> datetime.timedelta:
    """Return ``ed - st`` as a :class:`datetime.timedelta`."""
    return get_datetime(string_ed_date) - get_datetime(string_st_date)


def time_diff_in_seconds(string_ed_date: Any, string_st_date: Any) -> float:
    """Return ``ed - st`` in seconds."""
    return time_diff(string_ed_date, string_st_date).total_seconds()


def time_diff_in_hours(string_ed_date: Any, string_st_date: Any) -> float:
    """Return ``ed - st`` in hours."""
    return time_diff_in_seconds(string_ed_date, string_st_date) / 3600.0


def add_to_date(
    date: Any,
    years: int = 0,
    months: int = 0,
    weeks: int = 0,
    days: int = 0,
    hours: int = 0,
    minutes: int = 0,
    seconds: int = 0,
    as_string: bool = False,
    as_datetime: bool = False,
) -> str | datetime.datetime | datetime.date:
    """Add arbitrary relative deltas to *date*.

    Parameters
    ----------
    as_string:
        If ``True``, return a formatted string (``YYYY-MM-DD`` or
        ``YYYY-MM-DD HH:MM:SS`` when any time component is non-zero).
    as_datetime:
        If ``True``, return a :class:`datetime.datetime` object.
    """
    dt = get_datetime(date)
    result = dt + relativedelta(
        years=years,
        months=months,
        weeks=weeks,
        days=days,
        hours=hours,
        minutes=minutes,
        seconds=seconds,
    )
    if as_datetime:
        return result
    if as_string:
        if hours or minutes or seconds:
            return result.strftime("%Y-%m-%d %H:%M:%S")
        return result.strftime("%Y-%m-%d")
    if hours or minutes or seconds:
        return result
    return result.date()


def get_last_day(dt: Any) -> datetime.date:
    """Return the last day of the month containing *dt*."""
    d = getdate(dt)
    next_month = d.replace(day=28) + datetime.timedelta(days=4)
    return next_month.replace(day=1) - datetime.timedelta(days=1)


def get_first_day(
    dt: Any, d_years: int = 0, d_months: int = 0, as_str: bool = False
) -> str | datetime.date:
    """Return the first day of the month containing *dt* (plus offsets)."""
    d = getdate(dt)
    d = d + relativedelta(years=d_years, months=d_months)
    result = d.replace(day=1)
    if as_str:
        return result.strftime("%Y-%m-%d")
    return result


def get_quarter_start(dt: Any) -> datetime.date:
    """Return the first day of the quarter containing *dt*."""
    d = getdate(dt)
    quarter_month = ((d.month - 1) // 3) * 3 + 1
    return datetime.date(d.year, quarter_month, 1)


def get_quarter_ending(dt: Any) -> datetime.date:
    """Return the last day of the quarter containing *dt*."""
    d = getdate(dt)
    quarter_month = ((d.month - 1) // 3) * 3 + 3
    return get_last_day(datetime.date(d.year, quarter_month, 1))


def get_year_start(dt: Any) -> datetime.date:
    """Return January 1st of the year containing *dt*."""
    d = getdate(dt)
    return datetime.date(d.year, 1, 1)


def get_year_ending(dt: Any) -> datetime.date:
    """Return December 31st of the year containing *dt*."""
    d = getdate(dt)
    return datetime.date(d.year, 12, 31)


def get_week_starting_date(date: Any) -> str:
    """Return the Monday of the week containing *date* (as string)."""
    d = getdate(date)
    monday = d - datetime.timedelta(days=d.weekday())
    return monday.strftime("%Y-%m-%d")


def get_week_ending_date(date: Any) -> str:
    """Return the Sunday of the week containing *date* (as string)."""
    d = getdate(date)
    sunday = d + datetime.timedelta(days=6 - d.weekday())
    return sunday.strftime("%Y-%m-%d")


def get_timespan_date_range(timespan: str) -> Tuple[str, str] | None:
    """Return ``(start_date, end_date)`` strings for named *timespan*.

    Supported values (case-insensitive):
    ``last_week``, "this_week", "next_week",
    "last_month", "this_month", "next_month",
    "last_quarter", "this_quarter", "next_quarter",
    "last_year", "this_year", "next_year",
    "yesterday", "today", "tomorrow",
    "last_7_days", "last_14_days", "last_30_days",
    "all".
    """
    today_date = datetime.date.today()
    ts = (timespan or "").lower().strip()

    if ts == "last_week":
        start = today_date - datetime.timedelta(days=today_date.weekday() + 7)
        end = start + datetime.timedelta(days=6)
    elif ts == "this_week":
        start = today_date - datetime.timedelta(days=today_date.weekday())
        end = start + datetime.timedelta(days=6)
    elif ts == "next_week":
        start = today_date + datetime.timedelta(days=7 - today_date.weekday())
        end = start + datetime.timedelta(days=6)
    elif ts == "last_month":
        first_this = today_date.replace(day=1)
        end = first_this - datetime.timedelta(days=1)
        start = end.replace(day=1)
    elif ts == "this_month":
        start = today_date.replace(day=1)
        end = get_last_day(today_date)
    elif ts == "next_month":
        first_next = get_last_day(today_date) + datetime.timedelta(days=1)
        start = first_next
        end = get_last_day(first_next)
    elif ts == "last_quarter":
        qstart = get_quarter_start(today_date)
        end = qstart - datetime.timedelta(days=1)
        start = get_quarter_start(end)
    elif ts == "this_quarter":
        start = get_quarter_start(today_date)
        end = get_quarter_ending(today_date)
    elif ts == "next_quarter":
        qend = get_quarter_ending(today_date)
        start = qend + datetime.timedelta(days=1)
        end = get_quarter_ending(start)
    elif ts == "last_year":
        start = datetime.date(today_date.year - 1, 1, 1)
        end = datetime.date(today_date.year - 1, 12, 31)
    elif ts == "this_year":
        start = datetime.date(today_date.year, 1, 1)
        end = datetime.date(today_date.year, 12, 31)
    elif ts == "next_year":
        start = datetime.date(today_date.year + 1, 1, 1)
        end = datetime.date(today_date.year + 1, 12, 31)
    elif ts == "yesterday":
        start = end = today_date - datetime.timedelta(days=1)
    elif ts == "today":
        start = end = today_date
    elif ts == "tomorrow":
        start = end = today_date + datetime.timedelta(days=1)
    elif ts == "last_7_days":
        end = today_date
        start = today_date - datetime.timedelta(days=6)
    elif ts == "last_14_days":
        end = today_date
        start = today_date - datetime.timedelta(days=13)
    elif ts == "last_30_days":
        end = today_date
        start = today_date - datetime.timedelta(days=29)
    elif ts == "all":
        return ("0001-01-01", "9999-12-31")
    else:
        return None

    return (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))


# -- format helpers --------------------------------------------------------


def get_user_date_format() -> str:
    """Return the authenticated user's preferred date format."""
    try:
        if frappe and hasattr(frappe, "db"):
            user = frappe.session.user if hasattr(frappe, "session") else "Guest"
            if user and user != "Guest":
                fmt = frappe.db.get_value("User", user, "date_format")
                if fmt:
                    return fmt
    except Exception:
        pass
    return "%Y-%m-%d"


def get_user_time_format() -> str:
    """Return the authenticated user's preferred time format."""
    try:
        if frappe and hasattr(frappe, "db"):
            user = frappe.session.user if hasattr(frappe, "session") else "Guest"
            if user and user != "Guest":
                fmt = frappe.db.get_value("User", user, "time_format")
                if fmt:
                    return fmt
    except Exception:
        pass
    return "%H:%M:%S"


def format_date(string_date: Any = None, format_string: str | None = None) -> str:
    """Format *string_date* for display.

    If *format_string* is omitted the user's preferred format is used.
    """
    d = getdate(string_date)
    if not format_string:
        format_string = get_user_date_format()
    return d.strftime(format_string)


def format_time(txt: Any) -> str:
    """Format a time value for display."""
    if isinstance(txt, datetime.time):
        return txt.strftime(get_user_time_format())
    if isinstance(txt, datetime.timedelta):
        total_seconds = int(txt.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    if isinstance(txt, str):
        try:
            t = datetime.datetime.strptime(txt.strip(), "%H:%M:%S").time()
            return t.strftime(get_user_time_format())
        except ValueError:
            pass
    return cstr(txt)


def format_datetime(datetime_string: Any, format_string: str | None = None) -> str:
    """Format a datetime for display."""
    dt = get_datetime(datetime_string)
    if not format_string:
        format_string = f"{get_user_date_format()} {get_user_time_format()}"
    return dt.strftime(format_string)


def formatdate(string_date: Any = None, format_string: str | None = None) -> str:
    """Alias for :func:`format_date`."""
    return format_date(string_date, format_string)


def get_datetime_str(datetime_obj: Any) -> str:
    """``datetime`` → ``"YYYY-MM-DD HH:MM:SS"``."""
    if isinstance(datetime_obj, str):
        return datetime_obj
    return get_datetime(datetime_obj).strftime("%Y-%m-%d %H:%M:%S")


def get_date_str(date_obj: Any) -> str:
    """``date`` → ``"YYYY-MM-DD"``."""
    if isinstance(date_obj, str):
        return date_obj
    return getdate(date_obj).strftime("%Y-%m-%d")


def get_time_str(timedelta: Any) -> str:
    """Convert a :class:`datetime.timedelta` (or time-like value) to ``"HH:MM:SS"``."""
    if isinstance(timedelta, str):
        return timedelta
    if isinstance(timedelta, datetime.time):
        return timedelta.strftime("%H:%M:%S")
    if isinstance(timedelta, datetime.timedelta):
        total_seconds = int(timedelta.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return str(timedelta)


def global_date_format(date: Any, format: str = "long") -> str:
    """Return a locale-aware string such as ``"1st January, 2024"``."""
    d = getdate(date)
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(
        d.day if d.day < 20 else d.day % 10, "th"
    )
    if d.day in (11, 12, 13):
        suffix = "th"
    month_name = d.strftime("%B")
    return f"{d.day}{suffix} {month_name}, {d.year}"


def pretty_date(iso_datetime: Any, minimal: bool = False) -> str:
    """Return a human-friendly relative time string.

    Examples::
        pretty_date(now())           -> "just now"
        pretty_date(datetime - 5m)   -> "5 minutes ago"
        pretty_date(datetime - 1d)   -> "yesterday"
    """
    try:
        dt = get_datetime(iso_datetime)
    except Exception:
        return cstr(iso_datetime)

    now_dt = datetime.datetime.now()
    diff = now_dt - dt
    seconds = diff.total_seconds()

    if seconds < 10:
        return _("just now") if not minimal else _("now")
    if seconds < 60:
        return _("{0} seconds ago").format(int(seconds)) if not minimal else _("{0}s").format(int(seconds))
    minutes = seconds / 60
    if minutes < 2:
        return _("1 minute ago") if not minimal else _("1m")
    if minutes < 60:
        return _("{0} minutes ago").format(int(minutes)) if not minimal else _("{0}m").format(int(minutes))
    hours = minutes / 60
    if hours < 2:
        return _("1 hour ago") if not minimal else _("1h")
    if hours < 24:
        return _("{0} hours ago").format(int(hours)) if not minimal else _("{0}h").format(int(hours))
    days = hours / 24
    if days < 2:
        return _("yesterday") if not minimal else _("1d")
    if days < 7:
        return _("{0} days ago").format(int(days)) if not minimal else _("{0}d").format(int(days))
    weeks = days / 7
    if weeks < 2:
        return _("1 week ago") if not minimal else _("1w")
    if weeks < 4:
        return _("{0} weeks ago").format(int(weeks)) if not minimal else _("{0}w").format(int(weeks))
    months = days / 30
    if months < 2:
        return _("1 month ago") if not minimal else _("1mo")
    if months < 12:
        return _("{0} months ago").format(int(months)) if not minimal else _("{0}mo").format(int(months))
    years = days / 365
    if years < 2:
        return _("1 year ago") if not minimal else _("1y")
    return _("{0} years ago").format(int(years)) if not minimal else _("{0}y").format(int(years))


def rounded(num: Any, precision: int = 2) -> float:
    """Round *num* to *precision* decimal places (half-up)."""
    try:
        d = Decimal(str(num))
        return float(d.quantize(Decimal(10) ** -precision, rounding=ROUND_HALF_UP))
    except Exception:
        return 0.0


# =====================================================================
# 3. String / Text
# =====================================================================


def strip(val: Any, chars: str | None = None) -> str:
    """Strip whitespace (or *chars*) from *val*.

    Returns ``""`` when *val* is ``None``.
    """
    if val is None:
        return ""
    return str(val).strip(chars)


class _MLStripper(HTMLParser):
    """HTMLParser that collects only the text data."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.reset()
        self.fed: List[str] = []

    def handle_data(self, d: str) -> None:
        self.fed.append(d)

    def get_data(self) -> str:
        return "".join(self.fed)


def strip_html(text: str) -> str:
    """Remove HTML tags from *text*, returning plain text."""
    if not text:
        return ""
    s = _MLStripper()
    try:
        s.feed(str(text))
        s.close()
    except Exception:
        # Malformed HTML — fall back to regex
        return re.sub(r"<[^>]*>", "", str(text))
    return s.get_data()


# Allowed tags / attributes for sanitize_html
_SAFE_TAGS = frozenset(
    [
        "a",
        "abbr",
        "acronym",
        "b",
        "blockquote",
        "br",
        "code",
        "div",
        "em",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "i",
        "li",
        "ol",
        "p",
        "pre",
        "span",
        "strong",
        "sub",
        "sup",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "u",
        "ul",
    ]
)
_SAFE_ATTRS = frozenset(["href", "title", "class", "style", "src", "alt", "target"])


def sanitize_html(html: str, linkify: bool = False) -> str:
    """Strip dangerous HTML, keeping only a whitelist of safe tags.

    Parameters
    ----------
    linkify:
        If ``True``, convert bare URLs into clickable ``<a>`` tags.
    """
    if not html:
        return ""
    try:
        from bleach import clean

        cleaned = clean(
            html, tags=list(_SAFE_TAGS), attributes=list(_SAFE_ATTRS), strip=True
        )
    except ImportError:
        # bleach not installed — use a simple regex fallback
        cleaned = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.S | re.I)
        cleaned = re.sub(r"<style[^>]*>.*?</style>", "", cleaned, flags=re.S | re.I)
        cleaned = re.sub(
            r'<(?!/?(?:' + "|".join(_SAFE_TAGS) + r')\b)[^>]*>',
            "",
            cleaned,
            flags=re.I,
        )

    if linkify:
        try:
            from bleach import linkify as _linkify

            cleaned = _linkify(cleaned)
        except ImportError:
            # Simple regex linkify fallback
            url_pattern = re.compile(
                r'(https?://[^\s<>"]+|www\.[^\s<>"]+)',
                flags=re.I,
            )
            cleaned = url_pattern.sub(r'<a href="\1">\1</a>', cleaned)

    return cleaned


def is_html(text: str) -> bool:
    """Return ``True`` if *text* looks like HTML."""
    if not text or not isinstance(text, str):
        return False
    return bool(re.search(r"<[^>]+>", text))


def markdown_to_html(text: str) -> str:
    """Convert Markdown to HTML."""
    if not text:
        return ""
    try:
        import markdown

        return markdown.markdown(text, extensions=["tables", "fenced_code"])
    except ImportError:
        # Ultra-minimal fallback for plain text
        escaped = (
            str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        return f"<p>{escaped}</p>"


def to_markdown(text: str) -> str:
    """Convert HTML to Markdown."""
    if not text:
        return ""
    try:
        from html2text import HTML2Text

        h = HTML2Text()
        h.ignore_links = False
        return h.handle(text).strip()
    except ImportError:
        # Fallback: just strip tags
        return strip_html(text)


def bold(text: str) -> str:
    """Wrap *text* in ``<strong>`` tags."""
    return f"<strong>{text}</strong>"


def capitalize(s: str) -> str:
    """Capitalise the first character of *s* and lower-case the rest."""
    if not s:
        return ""
    return s[0].upper() + s[1:].lower()


def random_string(length: int = 10) -> str:
    """Return a random alphanumeric string of *length*."""
    return "".join(
        random.choices(string.ascii_letters + string.digits, k=length)
    )


def has_common(lst1: list, lst2: list) -> bool:
    """Return ``True`` if *lst1* and *lst2* share at least one element."""
    if not lst1 or not lst2:
        return False
    return not set(lst1).isdisjoint(lst2)


def comma_sep(s: Any, c: str = ", ") -> str:
    """Join iterable *s* with *c* (default ``", "``)."""
    if isinstance(s, str):
        return s
    if s is None:
        return ""
    try:
        return c.join(str(x) for x in s if x is not None)
    except TypeError:
        return str(s)


def comma_and(s: Any, c: str = ", ") -> str:
    """Join iterable *s* with commas and "and" before the last item."""
    if isinstance(s, str):
        return s
    if s is None:
        return ""
    items = [str(x) for x in s if x is not None]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + ", and " + items[-1]


def new_line_sep(s: Any) -> str:
    """Join iterable *s* with newline characters."""
    if isinstance(s, str):
        return s
    if s is None:
        return ""
    try:
        return "\n".join(str(x) for x in s if x is not None)
    except TypeError:
        return str(s)


def unique(seq: Any) -> list:
    """Return a list with duplicate values removed, preserving order."""
    if seq is None:
        return []
    seen: set = set()
    result: list = []
    for item in seq:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


# ---------------------------------------------------------------------------
# Number-to-words helpers (used by money_in_words)
# ---------------------------------------------------------------------------

_ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen",
    "Sixteen", "Seventeen", "Eighteen", "Nineteen",
]
_TENS = [
    "", "", "Twenty", "Thirty", "Forty", "Fifty",
    "Sixty", "Seventy", "Eighty", "Ninety",
]


def _num_to_words(num: int) -> str:
    """Convert a non-negative integer (< 1e12) to English words."""
    if num == 0:
        return "Zero"

    def _convert_less_than_thousand(n: int) -> str:
        if n == 0:
            return ""
        if n < 20:
            return _ONES[n]
        if n < 100:
            return _TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else "")
        return (
            _ONES[n // 100]
            + " Hundred"
            + (" and " + _convert_less_than_thousand(n % 100) if n % 100 else "")
        )

    parts: list[str] = []
    billions = num // 1_000_000_000
    millions = (num // 1_000_000) % 1_000
    thousands = (num // 1_000) % 1_000
    remainder = num % 1_000

    if billions:
        parts.append(_convert_less_than_thousand(billions) + " Billion")
    if millions:
        parts.append(_convert_less_than_thousand(millions) + " Million")
    if thousands:
        parts.append(_convert_less_than_thousand(thousands) + " Thousand")
    if remainder:
        parts.append(_convert_less_than_thousand(remainder))

    # Handle "and" between last two parts when there are multiple parts
    if len(parts) > 1 and remainder and remainder < 100:
        return " and ".join(parts)
    return " ".join(parts)


def money_in_words(
    number: float | int | str,
    main_currency: str | None = None,
    fraction_currency: str | None = None,
) -> str:
    """Convert a monetary amount to words.

    Examples::
        money_in_words(123.45, "USD", "Cent")
        -> "One Hundred And Twenty Three USD and Forty Five Cent Only"
    """
    try:
        number = float(number)
    except (ValueError, TypeError):
        return ""

    main_currency = main_currency or ""
    fraction_currency = fraction_currency or ""

    # Split into main and fraction parts
    main_part = int(number)
    fraction_part = int(round((number - main_part) * 100))

    # Determine "and" usage
    in_million = True  # Original Frappe uses in_million flag; default True

    main_words = _num_to_words(abs(main_part))

    out: str = ""
    if main_words == "Zero":
        out = f"Zero {main_currency}"
    else:
        out = f"{main_words} {main_currency}"

    if fraction_part:
        fraction_words = _num_to_words(fraction_part)
        out += f" and {fraction_words} {fraction_currency}"

    if number < 0:
        out = f"Negative {out}"

    return out + " Only"


def to_csv(data: list[list[Any]] | list[dict[str, Any]]) -> str:
    """Convert tabular *data* to a CSV string."""
    import csv
    import io

    output = io.StringIO()
    if data and isinstance(data[0], dict):
        if not data:
            return ""
        writer = csv.DictWriter(output, fieldnames=list(data[0].keys()))
        writer.writeheader()
        writer.writerows(data)
    else:
        writer = csv.writer(output)
        writer.writerows(data)
    return output.getvalue()


# =====================================================================
# 4. Networking / URL helpers
# =====================================================================


def get_url(uri: str | None = None, full_address: bool = False) -> str:
    """Build a URL from ``frappe.conf.host_name``.

    Parameters
    ----------
    uri:
        Path to append (e.g. ``"/app/sales-order"``).
    full_address:
        If ``True``, always prepend the scheme + host.
    """
    host = get_host_name()
    if not host:
        host = "localhost"

    # Ensure scheme
    if not host.startswith(("http://", "https://")):
        try:
            ssl = frappe.local.conf.get("ssl_certificate") if frappe else False
        except Exception:
            ssl = False
        scheme = "https" if ssl else "http"
        host = f"{scheme}://{host}"

    if uri:
        host = host.rstrip("/") + "/" + uri.lstrip("/")
    return host


def get_host_name() -> str:
    """Return the configured host name."""
    try:
        if frappe and hasattr(frappe, "local") and hasattr(frappe.local, "conf"):
            return cstr(frappe.local.conf.get("host_name", ""))
    except Exception:
        pass
    return os.environ.get("FRAPPE_HOST_NAME", "localhost")


def get_link_to_form(doctype: str, name: str, label: str | None = None) -> str:
    """Return an HTML link to a form / document."""
    display = label or name
    return f'<a href="/app/{doctype.lower().replace(" ", "-")}/{name}">{display}</a>'


def get_html_format(print_path: str) -> str | None:
    """Read an HTML print-format file at *print_path*.

    Returns ``None`` if the file does not exist.
    """
    if not print_path:
        return None
    path = os.path.abspath(print_path)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return None


# =====================================================================
# 5. Validation
# =====================================================================

# Simple e-mail regex (same pattern used historically by Frappe)
_EMAIL_RE = re.compile(
    r"([a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+\.[a-zA-Z0-9._-]+)"
)
# More robust pattern
_EMAIL_RE_STRICT = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*$"
)


def validate_email_address(
    email_str: str, throw: bool = False
) -> str | list[str] | bool:
    """Validate (and optionally split) e-mail address(es).

    Accepts comma-separated addresses.  Returns:
    * a single string when one valid address is given,
    * a list of strings when multiple valid addresses are given,
    * ``False`` when validation fails and *throw* is ``False``.

    Raises ``frappe.ValidationError`` when validation fails and *throw* is ``True``.
    """
    if not email_str or not isinstance(email_str, str):
        if throw:
            raise ValueError("Invalid Email Address")
        return False

    emails = [e.strip() for e in email_str.split(",") if e.strip()]
    valid: list[str] = []
    for email in emails:
        if "@" not in email or "." not in email.split("@")[-1]:
            if throw:
                raise ValueError(f"Invalid Email Address: {email}")
            return False
        # More strict check
        if not _EMAIL_RE_STRICT.match(email):
            if throw:
                raise ValueError(f"Invalid Email Address: {email}")
            return False
        valid.append(email.lower())

    if len(valid) == 1:
        return valid[0]
    return valid


_PHONE_RE = re.compile(r"^[\d\s\+\-\(\)\.]+$")


def validate_phone_number(phone_number: str, throw: bool = False) -> str | bool:
    """Validate a phone number.

    Returns the cleaned number on success, ``False`` on failure.
    """
    if not phone_number or not isinstance(phone_number, str):
        if throw:
            raise ValueError("Invalid Phone Number")
        return False
    cleaned = phone_number.strip()
    if not _PHONE_RE.match(cleaned):
        if throw:
            raise ValueError(f"Invalid Phone Number: {phone_number}")
        return False
    return cleaned


def validate_name(name: str, throw: bool = False) -> bool:
    """Validate a person / company name.

    Rejects names containing HTML tags or dangerous characters.
    """
    if not name or not isinstance(name, str):
        if throw:
            raise ValueError("Invalid Name")
        return False
    stripped = name.strip()
    if not stripped:
        if throw:
            raise ValueError("Invalid Name")
        return False
    # Reject HTML
    if re.search(r"<[^>]+>", stripped):
        if throw:
            raise ValueError("Name cannot contain HTML")
        return False
    return True


_URL_RE = re.compile(
    r"^(https?|ftp)://"  # scheme
    r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+"
    r"[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?|"  # domain
    r"localhost|"  # localhost
    r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # or ip
    r"(?::\d+)?"  # optional port
    r"(?:/?|[/?]\S+)$",
    re.IGNORECASE,
)


def validate_url(url: str, throw: bool = False) -> bool:
    """Validate a URL string."""
    if not url or not isinstance(url, str):
        if throw:
            raise ValueError("Invalid URL")
        return False
    if _URL_RE.match(url.strip()):
        return True
    if throw:
        raise ValueError(f"Invalid URL: {url}")
    return False


def validate_json_string(string: str) -> bool:
    """Return ``True`` if *string* is valid JSON."""
    if not string:
        return False
    try:
        json.loads(string)
        return True
    except Exception:
        return False


# =====================================================================
# 6. Error / Debug helpers
# =====================================================================


def get_traceback() -> str:
    """Return the current exception's traceback as a string.

    Safe to call even when no exception is active — returns ``""``.
    """
    exc_type, exc_value, exc_tb = sys.exc_info()
    if exc_type is None:
        return ""
    return "".join(traceback.format_exception(exc_type, exc_value, exc_tb))


def get_fullname(user: str | None = None) -> str:
    """Return the full name of *user* (or the current user)."""
    try:
        if frappe and hasattr(frappe, "db"):
            if not user:
                user = frappe.session.user if hasattr(frappe, "session") else "Guest"
            fullname = frappe.db.get_value("User", user, "full_name")
            if fullname:
                return fullname
    except Exception:
        pass
    if not user:
        return "Guest"
    return user


def get_user_info(user: str | None = None) -> "_dict":
    """Return a ``_dict`` with basic info about *user*."""
    try:
        if frappe and hasattr(frappe, "db"):
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


# =====================================================================
# 7. E-mail splitting
# =====================================================================


def split_emails(email_str: str) -> list[str]:
    """Split a comma/semicolon-separated e-mail string into a clean list."""
    if not email_str:
        return []
    return [
        e.strip().lower()
        for e in re.split(r"[,;]", email_str)
        if e.strip()
    ]


# =====================================================================
# 8. Aliases / compatibility
# =====================================================================


def create_folder(path: str, with_init: bool = False) -> None:
    """Create *path* (and any missing parents)."""
    os.makedirs(path, exist_ok=True)
    if with_init:
        init_file = os.path.join(path, "__init__.py")
        if not os.path.exists(init_file):
            with open(init_file, "w", encoding="utf-8"):
                pass


# =====================================================================
# 9. Table / serialization helpers
# =====================================================================


def get_table_name(doctype: str, wrap_in_backticks: bool = False) -> str:
    """Get SQL table name for a DocType.

    :param doctype: DocType name
    :param wrap_in_backticks: Wrap in backticks
    :return: Table name like 'tabSales Order' or '`tabSales Order`'
    """
    name = f"tab{doctype}"
    if wrap_in_backticks:
        return f"`{name}`"
    return name


def getdate_str(date_obj=None) -> str:
    """Convert date to string in YYYY-MM-DD format."""
    if date_obj is None:
        date_obj = datetime.date.today()
    if isinstance(date_obj, datetime.datetime):
        date_obj = date_obj.date()
    return date_obj.strftime("%Y-%m-%d")


def fmt_money(amount: float, precision: int = 2) -> str:
    """Format amount as currency string."""
    return f"{amount:,.{precision}f}"


def fmt_date(date_obj) -> str:
    """Format date for display."""
    if isinstance(date_obj, str):
        date_obj = getdate(date_obj)
    if isinstance(date_obj, datetime.datetime):
        date_obj = date_obj.date()
    return date_obj.strftime("%d-%m-%Y")


def fmt_datetime(dt_obj) -> str:
    """Format datetime for display."""
    if isinstance(dt_obj, str):
        dt_obj = get_datetime(dt_obj)
    return dt_obj.strftime("%d-%m-%Y %H:%M")


def get_timedelta(time_str=None) -> datetime.timedelta:
    """Convert string to timedelta."""
    if time_str is None:
        return datetime.timedelta()
    if isinstance(time_str, datetime.timedelta):
        return time_str
    if isinstance(time_str, str):
        parts = time_str.split(":")
        if len(parts) == 3:
            return datetime.timedelta(
                hours=int(parts[0]), minutes=int(parts[1]), seconds=int(parts[2])
            )
        elif len(parts) == 2:
            return datetime.timedelta(hours=int(parts[0]), minutes=int(parts[1]))
    return datetime.timedelta()


def to_json(data: Any) -> str:
    """Convert Python object to JSON string."""
    import json
    from datetime import date, datetime, timedelta

    def default_serializer(obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, timedelta):
            return str(obj)
        if isinstance(obj, set):
            return list(obj)
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    return json.dumps(data, default=default_serializer, ensure_ascii=False)


def groupby_dict(seq: list, key) -> dict:
    """Group a list of dicts by a key function."""
    result: dict = {}
    for item in seq:
        k = key(item) if callable(key) else item.get(key)
        result.setdefault(k, []).append(item)
    return result


# =====================================================================
# 10. Additional Date/Time Functions
# =====================================================================


def add_years(date: Any, years: int) -> str:
    """Add *years* to *date* and return ``YYYY-MM-DD`` string.

    Examples::
        add_years("2024-01-15", 1) -> "2025-01-15"
        add_years("2024-01-15", -1) -> "2023-01-15"
    """
    return add_to_date(date, years=years, as_string=True)


def get_month_diff(d1: Any, d2: Any) -> int:
    """Return the difference in whole months between *d1* and *d2*.

    The result is positive when *d1* > *d2*.
    Uses :class:`dateutil.relativedelta` for accurate month-boundary calculation.

    Examples::
        get_month_diff("2024-03-15", "2024-01-15") -> 2
        get_month_diff("2024-01-15", "2024-03-15") -> -2
    """
    dt1 = getdate(d1)
    dt2 = getdate(d2)
    rd = relativedelta(dt1, dt2)
    return rd.years * 12 + rd.months


def time_diff_in_minutes(string_ed_date: Any, string_st_date: Any) -> float:
    """Return ``ed - st`` in minutes."""
    return time_diff_in_seconds(string_ed_date, string_st_date) / 60.0


def time_diff_in_days(string_ed_date: Any, string_st_date: Any) -> float:
    """Return ``ed - st`` in days."""
    return time_diff_in_seconds(string_ed_date, string_st_date) / 86400.0


def format_duration(seconds: int | float, hide_days: bool = False) -> str:
    """Format *seconds* into a human-readable duration string.

    Parameters
    ----------
    seconds:
        Total number of seconds.
    hide_days:
        If ``True``, express everything in hours (e.g. ``"27h 30m"``).

    Examples::
        format_duration(9000)       -> "2h 30m"
        format_duration(189000)     -> "2d 4h 30m"
        format_duration(189000, True) -> "52h 30m"
    """
    try:
        seconds = int(seconds)
    except (ValueError, TypeError):
        return ""

    if seconds < 0:
        return ""

    if hide_days:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        parts = []
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        if secs and not parts:
            parts.append(f"{secs}s")
        return " ".join(parts) if parts else "0s"

    days = seconds // 86400
    remainder = seconds % 86400
    hours = remainder // 3600
    minutes = (remainder % 3600) // 60
    secs = remainder % 60

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs and not parts:
        parts.append(f"{secs}s")

    return " ".join(parts) if parts else "0s"


def get_user_time_zone() -> str:
    """Return the user's configured time zone.

    Falls back to ``frappe.local.conf.time_zone``, then ``"UTC"``.
    """
    try:
        if frappe and hasattr(frappe, "local") and hasattr(frappe.local, "conf"):
            tz = frappe.local.conf.get("time_zone")
            if tz:
                return tz
    except Exception:
        pass
    return "UTC"


get_time_zone = get_user_time_zone  # Alias


def convert_utc_to_user_timezone(utc_timestamp: Any) -> datetime.datetime:
    """Convert a UTC datetime to the user's local time zone.

    Parameters
    ----------
    utc_timestamp:
        A datetime (naive or UTC-aware) or a string parsable by
        :func:`get_datetime`.

    Returns
    -------
    datetime.datetime
        A **naive** datetime shifted to the user's time zone.
    """
    import pytz

    dt = get_datetime(utc_timestamp)
    user_tz = get_user_time_zone()

    # If naive, assume it's UTC
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)

    target_tz = pytz.timezone(user_tz)
    local_dt = dt.astimezone(target_tz)
    return local_dt.replace(tzinfo=None)


# =====================================================================
# 11. Additional String/Encoding Functions
# =====================================================================


def to_encoded(txt: str, encoding: str = "utf-8") -> bytes:
    """Encode *txt* to ``bytes`` using *encoding*.

    Returns the original value if it is already ``bytes``.
    """
    if isinstance(txt, bytes):
        return txt
    return str(txt).encode(encoding)


def decode_dict(d: Any, encoding: str = "utf-8") -> Any:
    """Recursively decode ``bytes`` → ``str`` inside *d*.

    Walks dicts, lists and tuples.  Leaves everything else untouched.
    """
    if isinstance(d, bytes):
        return d.decode(encoding)
    if isinstance(d, dict):
        return {decode_dict(k, encoding): decode_dict(v, encoding) for k, v in d.items()}
    if isinstance(d, list):
        return [decode_dict(i, encoding) for i in d]
    if isinstance(d, tuple):
        return tuple(decode_dict(i, encoding) for i in d)
    return d


def is_json(text: str) -> bool:
    """Return ``True`` if *text* is a valid JSON string."""
    if not text or not isinstance(text, str):
        return False
    try:
        json.loads(text)
        return True
    except Exception:
        return False


def get_hash(text: str, encoding: str = "utf-8") -> str:
    """Return the SHA-256 hex digest of *text*."""
    if isinstance(text, str):
        text = text.encode(encoding)
    return hashlib.sha256(text).hexdigest()


def sha256_hash(input: str) -> str:
    """Return the SHA-256 hex digest of *input*."""
    return get_hash(input)


def md5_hash(input: str) -> str:
    """Return the MD5 hex digest of *input*."""
    if isinstance(input, str):
        input = input.encode("utf-8")
    return hashlib.md5(input).hexdigest()


# =====================================================================
# 12. Additional Number/Validation Functions
# =====================================================================


def floor(num: Any) -> int:
    """Return the mathematical floor of *num*.

    Returns ``0`` on ``None`` / unparseable input.
    """
    try:
        return math.floor(float(num))
    except (ValueError, TypeError):
        return 0


def ceil(num: Any) -> int:
    """Return the mathematical ceiling of *num*.

    Returns ``0`` on ``None`` / unparseable input.
    """
    try:
        return math.ceil(float(num))
    except (ValueError, TypeError):
        return 0


def remainder(numerator: Any, denominator: Any, precision: int = 2) -> float:
    """Return the safe remainder of *numerator* / *denominator*.

    Returns ``0.0`` when *denominator* is ``0`` or unparseable.
    """
    try:
        n = float(numerator)
        d = float(denominator)
        if d == 0:
            return 0.0
        result = n % d
        return rounded(result, precision)
    except (ValueError, TypeError):
        return 0.0


def safe_div(numerator: Any, denominator: Any, default: float = 0.0) -> float:
    """Return *numerator* / *denominator*, or *default* if division is unsafe.

    "Unsafe" means *denominator* is ``0``, ``None``, or unparseable.
    """
    try:
        n = float(numerator)
        d = float(denominator)
        if d == 0:
            return default
        return n / d
    except (ValueError, TypeError):
        return default


def get_number_format_info(format: str) -> Tuple[str, str, int]:
    """Parse a number-format pattern and return metadata.

    Parameters
    ----------
    format:
        A pattern such as ``"#,##0.##"`` or ``"#.###,##"``.

    Returns
    -------
    tuple
        ``(thousands_separator, decimal_point, precision)``

    Examples::
        get_number_format_info("#,##0.##")  -> (",", ".", 2)
        get_number_format_info("#.###,##")  -> (".", ",", 2)
        get_number_format_info("#,##0")     -> (",", ".", 0)
    """
    if not format or not isinstance(format, str):
        return (",", ".", 2)

    last_dot = format.rfind(".")
    last_comma = format.rfind(",")

    if last_dot == -1 and last_comma == -1:
        return (",", ".", 0)

    # Determine rightmost separator
    if last_dot > last_comma:
        pos, sep = last_dot, "."
    else:
        pos, sep = last_comma, ","

    after = format[pos + 1 :]

    # Check if ``after`` looks like fractional digits (1–6 #/0 chars).
    # Heuristic: exactly "##0" after a separator is a thousands group
    # (e.g. ``#,##0``) rather than a fractional part.
    is_frac = False
    if after and all(c in "#0" for c in after) and 1 <= len(after) <= 6:
        if not (len(after) == 3 and after[0] == "#" and after[1] == "#" and after[2] == "0"):
            is_frac = True

    if is_frac:
        thousands_sep = "," if sep == "." else "."
        return (thousands_sep, sep, len(after))

    # No fractional part detected
    if "," in format and "." in format:
        return (",", ".", 0) if last_dot > last_comma else (".", ",", 0)
    elif "," in format:
        return (",", ".", 0)
    elif "." in format:
        return (".", ",", 0)
    return (",", ".", 0)


def number_format_string(
    number: float | int | str,
    format: str = "#,##0.##",
    precision: int = 2,
) -> str:
    """Format *number* according to a custom pattern.

    Parameters
    ----------
    number:
        The value to format.
    format:
        Pattern such as ``"#,##0.##"`` (US) or ``"#.###,##"`` (European).
    precision:
        Decimal places (overrides the pattern when > 0).

    Examples::
        number_format_string(1234.5, "#,##0.00") -> "1,234.50"
        number_format_string(1234.5, "#.###,##") -> "1.234,50"
    """
    try:
        num = float(number)
    except (ValueError, TypeError):
        return str(number)

    thousands_sep, decimal_point, fmt_precision = get_number_format_info(format)
    if precision is not None:
        fmt_precision = precision

    # Build the format spec
    if fmt_precision > 0:
        fmt = f"{{:,.{fmt_precision}f}}"
    else:
        fmt = "{:,.0f}"

    # Python's default uses comma as thousands and dot as decimal
    result = fmt.format(num)

    # Convert to the target separators if different from defaults
    if thousands_sep != "," or decimal_point != ".":
        # First replace the default separators with placeholders
        result = result.replace(",", "\x00")  # placeholder for thousands
        result = result.replace(".", decimal_point)
        result = result.replace("\x00", thousands_sep)

    return result


def parse_number(number: str, precision: int | None = None) -> float:
    """Parse a formatted numeric string back to ``float``.

    Handles both ``","`` and ``"."`` as thousands/decimal separators
    by stripping thousands separators and converting the decimal point
    to ``"."``.

    Parameters
    ----------
    number:
        Formatted number like ``"1,234.56"`` or ``"1.234,56"``.
    precision:
        If given, round the result to this many decimal places.

    Examples::
        parse_number("1,234.56") -> 1234.56
        parse_number("1.234,56") -> 1234.56
    """
    if not number or not isinstance(number, str):
        return flt(number, precision)

    s = number.strip()
    if not s:
        return 0.0

    # Detect format: if comma is the last separator, it's the decimal point
    last_comma = s.rfind(",")
    last_dot = s.rfind(".")

    if last_comma > last_dot:
        # European format: 1.234,56
        s = s.replace(".", "").replace(",", ".")
    else:
        # US format: 1,234.56
        s = s.replace(",", "")

    try:
        result = float(s)
    except (ValueError, TypeError):
        return 0.0

    if precision is not None:
        result = rounded(result, precision)

    return result


def fmt_money(
    amount: float | int | str | None,
    precision: int | None = None,
    currency: str | None = None,
    format: str | None = None,
) -> str:
    """Format *amount* as a currency string.

    Parameters
    ----------
    amount:
        Numeric value.  ``None`` → ``""``.
    precision:
        Decimal places.  Falls back to the currency's precision or ``2``.
    currency:
        Currency code (e.g. ``"USD"``, ``"EUR"``).
    format:
        Number format pattern (e.g. ``"#,##0.##"``).

    Examples::
        fmt_money(1234.5)                -> "1,234.50"
        fmt_money(1234.5, currency="USD") -> "$ 1,234.50"
    """
    if amount is None or amount == "":
        return ""

    try:
        amount = float(amount)
    except (ValueError, TypeError):
        return str(amount)

    # Determine precision
    if precision is None:
        precision = 2

    # Determine number format
    if not format:
        format = "#,##0.##"

    # Format the number
    result = number_format_string(amount, format, precision)

    # Add currency symbol if provided
    if currency:
        result = f"{currency} {result}"

    return result


# =====================================================================
# 13. Additional URL/Web Functions
# =====================================================================


def get_request_site_address(full_address: bool = False) -> str:
    """Return the current request's site address.

    This is an alias for :func:`get_url` that mirrors the original
    Frappe internal naming.
    """
    return get_url(full_address=full_address)


def get_request_url() -> str:
    """Return the full URL of the current HTTP request.

    Tries ``frappe.local.request.url`` first, then falls back to
    :func:`get_url`.
    """
    try:
        if frappe and hasattr(frappe, "local") and hasattr(frappe.local, "request"):
            req_url = frappe.local.request.url
            if req_url:
                return req_url
    except Exception:
        pass
    return get_url()


def url_encode_json(json_obj: Any) -> str:
    """URL-safe base64-encode a JSON-serialisable object.

    Examples::
        url_encode_json({"key": "value"})
        -> "eyJrZXkiOiAidmFsdWUifQ=="
    """
    import base64

    s = json.dumps(json_obj, ensure_ascii=False, default=str)
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("utf-8")


def get_formatted_email(user: str) -> str:
    """Return ``"Full Name <email@example.com>"`` for *user*.

    Falls back to just the e-mail address if the full name cannot be
    determined.
    """
    fullname = get_user_fullname(user)
    email = user
    try:
        if frappe and hasattr(frappe, "db"):
            email = frappe.db.get_value("User", user, "email") or user
    except Exception:
        pass
    if fullname and fullname != user:
        return f"{fullname} <{email}>"
    return email


def get_user_fullname(user: str | None = None) -> str:
    """Return the full name of *user* (or the current user).

    Falls back to :func:`get_fullname` which queries the ``User`` DocType.
    """
    return get_fullname(user)


def get_domain(url: str) -> str:
    """Extract the domain / host name from *url*.

    Examples::
        get_domain("https://example.com/path") -> "example.com"
        get_domain("http://localhost:8000")    -> "localhost"
    """
    if not url:
        return ""
    from urllib.parse import urlparse

    parsed = urlparse(url.strip())
    return parsed.netloc or parsed.path.split("/")[0]


def quote_urls(text: str) -> str:
    """Convert bare URLs in *text* to clickable HTML ``<a>`` tags.

    URLs starting with ``http://``, ``https://``, or ``www.`` are
    recognised.

    Examples::
        quote_urls("Visit https://example.com today")
        -> "Visit <a href=\"https://example.com\">https://example.com</a> today"
    """
    if not text:
        return ""
    url_pattern = re.compile(
        r'(https?://[^\s<>"\']+|www\.[^\s<>"\']+)',
        flags=re.I,
    )

    def _replace(match: re.Match) -> str:
        url = match.group(1)
        href = url if url.startswith("http") else f"http://{url}"
        return f'<a href="{href}">{url}</a>'

    return url_pattern.sub(_replace, text)


def get_site_url(site: str) -> str:
    """Return the base URL for *site*.

    Reads ``host_name`` from the site configuration.
    """
    try:
        if frappe and hasattr(frappe, "local") and hasattr(frappe.local, "conf"):
            host = frappe.local.conf.get("host_name", "localhost")
            scheme = "https" if frappe.local.conf.get("ssl_certificate") else "http"
            return f"{scheme}://{host}"
    except Exception:
        pass
    return f"http://{site}"


# =====================================================================
# 14. Data-Structure Functions
# =====================================================================


def flatten(lst: list) -> list:
    """Flatten a nested list (one level deep).

    Non-list elements are kept as-is.

    Examples::
        flatten([[1, 2], [3, 4]])       -> [1, 2, 3, 4]
        flatten([[1, 2], 3, [4, 5]])    -> [1, 2, 3, 4, 5]
    """
    if not lst:
        return []
    result: list = []
    for item in lst:
        if isinstance(item, list):
            result.extend(item)
        else:
            result.append(item)
    return result


def get_file_timestamp(filename: str) -> float | None:
    """Return the last-modification timestamp of *filename*.

    Returns ``None`` if the file does not exist.
    """
    if not filename or not os.path.exists(filename):
        return None
    try:
        return os.path.getmtime(filename)
    except OSError:
        return None


def compare(val1: Any, condition: str, val2: Any) -> bool:
    """Compare *val1* and *val2* using *condition*.

    Supported operators:
    ``"="``, ``"!="``, ``"<"``, ``">"``, ``"<="``, ``">="``,
    ``"in"``, ``"not in"``, ``"like"``.

    The ``"like"`` operator performs a case-insensitive substring
    search when both operands are strings.

    Examples::
        compare(5, ">", 3)            -> True
        compare("abc", "like", "b")   -> True
        compare(5, "in", [1, 5, 10])  -> True
    """
    condition = (condition or "").strip().lower()

    if condition == "=":
        return val1 == val2
    if condition == "!=":
        return val1 != val2
    if condition == "<":
        try:
            return float(val1) < float(val2)
        except (ValueError, TypeError):
            return val1 < val2
    if condition == ">":
        try:
            return float(val1) > float(val2)
        except (ValueError, TypeError):
            return val1 > val2
    if condition == "<=":
        try:
            return float(val1) <= float(val2)
        except (ValueError, TypeError):
            return val1 <= val2
    if condition == ">=":
        try:
            return float(val1) >= float(val2)
        except (ValueError, TypeError):
            return val1 >= val2
    if condition == "in":
        try:
            return val1 in val2
        except Exception:
            return False
    if condition == "not in":
        try:
            return val1 not in val2
        except Exception:
            return True
    if condition == "like":
        if isinstance(val1, str) and isinstance(val2, str):
            return val2.lower() in val1.lower()
        try:
            return val2 in val1
        except Exception:
            return False

    # Unknown condition → equality fallback
    return val1 == val2


def filter_dict(input_dict: dict, filter_fn: Any) -> dict:
    """Return a new dict containing only items where *filter_fn* is truthy.

    *filter_fn* can be:
    * a callable ``(key, value) -> bool``,
    * a callable ``(value) -> bool``,
    * a dict of ``{key: expected_value}`` for exact matching.

    Examples::
        filter_dict({"a": 1, "b": 2}, lambda k, v: v > 1)
        -> {"b": 2}
    """
    if not input_dict:
        return {}

    result: dict = {}

    # If filter_fn is a dict, use it as exact match on keys
    if isinstance(filter_fn, dict):
        for key, value in input_dict.items():
            if key in filter_fn and filter_fn[key] == value:
                result[key] = value
        return result

    if callable(filter_fn):
        sig = inspect.signature(filter_fn)
        n_params = len(sig.parameters)
        for key, value in input_dict.items():
            try:
                if n_params >= 2:
                    if filter_fn(key, value):
                        result[key] = value
                else:
                    if filter_fn(value):
                        result[key] = value
            except Exception:
                pass
        return result

    return input_dict


def dictify(arg: Any) -> dict:
    """Convert *arg* into a ``dict``.

    * Already a dict → returned as-is.
    * List / tuple of pairs → ``dict(arg)``.
    * ``None`` → empty dict.
    * Anything else → ``{"value": arg}``.
    """
    if arg is None:
        return {}
    if isinstance(arg, dict):
        return arg
    if isinstance(arg, (list, tuple)):
        try:
            return dict(arg)
        except (ValueError, TypeError):
            return {"value": arg}
    return {"value": arg}


def get_max_if_not_none(val1: Any, val2: Any) -> Any:
    """Return ``max(val1, val2)`` ignoring ``None`` values.

    If both are ``None``, returns ``None``.
    """
    if val1 is None and val2 is None:
        return None
    if val1 is None:
        return val2
    if val2 is None:
        return val1
    try:
        return max(val1, val2)
    except TypeError:
        return val1 if val1 > val2 else val2


def get_min_if_not_none(val1: Any, val2: Any) -> Any:
    """Return ``min(val1, val2)`` ignoring ``None`` values.

    If both are ``None``, returns ``None``.
    """
    if val1 is None and val2 is None:
        return None
    if val1 is None:
        return val2
    if val2 is None:
        return val1
    try:
        return min(val1, val2)
    except TypeError:
        return val1 if val1 < val2 else val2


def get_abbr(string: str, max_len: int = 2) -> str:
    """Return an abbreviation of *string*.

    Takes the first letter of each whitespace-separated word, up to
    *max_len* characters.

    Examples::
        get_abbr("Sales Order")     -> "SO"
        get_abbr("Purchase Invoice") -> "PI"
        get_abbr("Request for Quotation", 3) -> "RFQ"
    """
    if not string:
        return ""
    words = string.strip().split()
    abbr = "".join(w[0].upper() for w in words if w)
    return abbr[:max_len] if max_len else abbr


def get_descendants(
    root_label: str,
    tree_list: list[dict],
    sort_key: str = "name",
) -> list[str]:
    """Return all descendants of *root_label* in a flat tree.

    Each item in *tree_list* is expected to have at least:
    * ``sort_key`` – the node identifier,
    * ``"parent"`` – the parent node's identifier (``""`` or ``None`` for roots).

    The result includes the root itself.

    Parameters
    ----------
    root_label:
        The identifier of the root node to start from.
    tree_list:
        Flat list of node dicts.
    sort_key:
        Dict key that holds the node identifier.

    Examples::
        tree = [
            {"name": "All", "parent": ""},
            {"name": "A", "parent": "All"},
            {"name": "B", "parent": "A"},
        ]
        get_descendants("All", tree) -> ["All", "A", "B"]
    """
    if not tree_list:
        return [root_label] if root_label else []

    # Build a parent → children mapping
    children_map: dict[str, list[dict]] = {}
    node_map: dict[str, dict] = {}

    for node in tree_list:
        label = node.get(sort_key, "")
        parent = node.get("parent") or ""
        node_map[label] = node
        children_map.setdefault(parent, []).append(node)

    result: list[str] = []
    queue = [root_label]
    visited: set[str] = set()

    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        result.append(current)
        for child in children_map.get(current, []):
            child_label = child.get(sort_key, "")
            if child_label and child_label not in visited:
                queue.append(child_label)

    return result


# =====================================================================
# 15. Other Utility Functions
# =====================================================================


def get_file_extension(filename: str) -> str:
    """Return the lower-case file extension of *filename*.

    Returns ``""`` if there is no extension.

    Examples::
        get_file_extension("document.pdf") -> "pdf"
        get_file_extension("archive.tar.gz") -> "gz"
    """
    if not filename or not isinstance(filename, str):
        return ""
    return os.path.splitext(filename)[1].lstrip(".").lower()


def get_content_hash(content: str | bytes) -> str:
    """Return the SHA-256 hex digest of *content*.

    Strings are UTF-8 encoded before hashing.
    """
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def get_build_version() -> str:
    """Return the framework version string.

    Tries ``frappe.__version__`` first, then returns a default.
    """
    try:
        if frappe and hasattr(frappe, "__version__"):
            return frappe.__version__
    except Exception:
        pass
    try:
        import importlib.metadata as _im

        return _im.version("frappe")
    except Exception:
        pass
    return "15.0.0"


def call_hook_method(hook: str, *args: Any, **kwargs: Any) -> list[Any]:
    """Call every function registered under *hook* and return results.

    Hooks are defined in the ``hooks.py`` of installed apps.  Each
    hook value can be a dotted path ``"module.path.function"`` or a
    callable.

    Parameters
    ----------
    hook:
        The hook name (e.g. ``"after_insert"``).
    *args, **kwargs:
        Forwarded to each hook function.

    Returns
    -------
    list:
        Return values from each invoked function.
    """
    results: list[Any] = []
    try:
        if frappe and hasattr(frappe, "get_hooks"):
            hook_fns = frappe.get_hooks(hook)
            for fn_ref in hook_fns:
                try:
                    if callable(fn_ref):
                        results.append(fn_ref(*args, **kwargs))
                    elif isinstance(fn_ref, str):
                        # Resolve dotted path
                        module_path, fn_name = fn_ref.rsplit(".", 1)
                        mod = __import__(module_path, fromlist=[fn_name])
                        fn = getattr(mod, fn_name)
                        results.append(fn(*args, **kwargs))
                except Exception:
                    # Individual hook failures should not stop others
                    pass
    except Exception:
        pass
    return results


def get_path(*path: str) -> str:
    """Join path components with ``os.path.join``.

    Examples::
        get_path("sites", "site1.local", "private")
        -> "sites/site1.local/private"
    """
    return os.path.join(*path)


def get_url_to_form(doctype: str, name: str) -> str:
    """Return the full desk URL to a document form.

    Example::
        get_url_to_form("Sales Order", "SO-001")
        -> "https://example.com/app/sales-order/SO-001"
    """
    return get_url(
        uri=f"/app/{doctype.lower().replace(' ', '-')}/{name}",
        full_address=True,
    )


def get_url_to_list(doctype: str) -> str:
    """Return the full desk URL to a DocType list view.

    Example::
        get_url_to_list("Sales Order")
        -> "https://example.com/app/sales-order"
    """
    return get_url(
        uri=f"/app/{doctype.lower().replace(' ', '-')}",
        full_address=True,
    )


def get_url_to_report(
    name: str,
    report_type: str | None = None,
    doctype: str | None = None,
) -> str:
    """Return the full desk URL to a report.

    Parameters
    ----------
    name:
        Report name.
    report_type:
        One of ``"Report Builder"``, ``"Query Report"``, ``"Script Report"``.
    doctype:
        Associated DocType (for Report Builder reports).

    Example::
        get_url_to_report("Sales Order Trends")
        -> "https://example.com/app/query-report/Sales%20Order%20Trends"
    """
    from urllib.parse import quote

    encoded_name = quote(name)

    if report_type == "Report Builder" and doctype:
        return get_url(
            uri=f"/app/{doctype.lower().replace(' ', '-')}/view/report/{encoded_name}",
            full_address=True,
        )

    return get_url(
        uri=f"/app/query-report/{encoded_name}",
        full_address=True,
    )


def get_backups_path() -> str:
    """Return the absolute path to the site's private backups folder.

    Pattern: ``sites/{site_name}/private/backups``
    """
    try:
        if frappe and hasattr(frappe, "local"):
            site_path = frappe.local.site
            if site_path:
                return os.path.join(site_path, "private", "backups")
    except Exception:
        pass
    # Fallback: try to construct from current working directory
    return os.path.join("sites", "site1.local", "private", "backups")
