from __future__ import annotations

import datetime
import re
from decimal import Decimal
from typing import Any, Callable, Optional

import frappe
from frappe.types import _dict


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NUMBER_FORMATS: dict[str, str] = {
    "#,###.##": "{value:,.2f}",
    "#.###,##": "{value:.2f}".replace(".", "|").replace(",", ".").replace("|", ","),
    "#,###": "{value:,.0f}",
    "#,##,###.##": "{value:,.2f}",  # Indian numbering
    "#,###.###": "{value:,.3f}",
    "#.########": "{value:.8f}",
}

DATE_FORMAT_MAP: dict[str, str] = {
    "yyyy-mm-dd": "%Y-%m-%d",
    "dd-mm-yyyy": "%d-%m-%Y",
    "dd/mm/yyyy": "%d/%m/%Y",
    "mm/dd/yyyy": "%m/%d/%Y",
    "mm-dd-yyyy": "%m-%d-%Y",
    "yyyy/mm/dd": "%Y/%m/%d",
    "dd.mm.yyyy": "%d.%m.%Y",
    "dd-MMM-yyyy": "%d-%b-%Y",
    "MMM dd, yyyy": "%b %d, %Y",
    "MMMM dd, yyyy": "%B %d, %Y",
    "dd MMMM, yyyy": "%d %B, %Y",
}

CURRENCY_SYMBOLS: dict[str, str] = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "INR": "₹",
    "JPY": "¥",
    "CNY": "¥",
    "KRW": "₩",
    "RUB": "₽",
    "BRL": "R$",
    "CAD": "C$",
    "AUD": "A$",
}


# ---------------------------------------------------------------------------
# Main value formatter
# ---------------------------------------------------------------------------


def format_value(
    value: Any,
    df: dict[str, Any] | _dict,
    doc: Optional[Any] = None,
    currency: Optional[str] = None,
    translated: bool = False,
    format_args: Optional[dict] = None,
) -> str:
    """Format a field value according to its fieldtype.

    *df* is a dict (or ``_dict``) containing at minimum a
    ``fieldtype`` key.  Common additional keys: ``options``,
    ``fieldname``, ``label``.

    Args:
        value: The raw value to format.
        df: Field definition dict with ``fieldtype`` and optionally
            ``options``.
        doc: The parent document (for context-dependent formatting).
        currency: Currency code (for Currency fields).
        translated: Whether to return translated labels.
        format_args: Extra formatting parameters.

    Returns:
        Formatted string representation of *value*.
    """
    if value is None:
        return ""

    fieldtype = df.get("fieldtype", "Data") if isinstance(df, (dict, _dict)) else "Data"
    options = df.get("options", "") if isinstance(df, (dict, _dict)) else ""

    # Formatters dispatch table
    dispatch: dict[str, Callable] = {
        "Currency": lambda v: format_currency(v, currency or options or frappe.defaults.get_defaults().get("currency")),
        "Float": lambda v: _format_float(v, df),
        "Int": lambda v: _format_int(v),
        "Integer": lambda v: _format_int(v),
        "Percent": lambda v: format_percent(v),
        "Date": lambda v: format_date(v),
        "Datetime": lambda v: _format_datetime(v),
        "Time": lambda v: _format_time(v),
        "Link": lambda v: _format_link(v, options),
        "Select": lambda v: _format_select(v, options),
        "Check": lambda v: "Yes" if v else "No",
        "Text Editor": lambda v: str(v) if v else "",
        "Text": lambda v: str(v) if v else "",
        "Long Text": lambda v: str(v) if v else "",
        "Small Text": lambda v: str(v) if v else "",
        "Code": lambda v: str(v) if v else "",
        "Markdown Editor": lambda v: str(v) if v else "",
        "HTML Editor": lambda v: str(v) if v else "",
        "Color": lambda v: _format_color(v),
        "Barcode": lambda v: str(v) if v else "",
        "JSON": lambda v: _format_json(v),
        "Rating": lambda v: _format_rating(v),
        "Duration": lambda v: _format_duration(v),
        "Password": lambda v: "*" * min(len(str(v)), 8) if v else "",
        "Phone": lambda v: _format_phone(v),
        "Icon": lambda v: str(v) if v else "",
        "Attach": lambda v: _format_attach(v),
        "Attach Image": lambda v: _format_attach(v),
        "Geolocation": lambda v: _format_geolocation(v),
    }

    formatter = dispatch.get(fieldtype)
    if formatter:
        try:
            return formatter(value)
        except Exception:
            return str(value) if value is not None else ""

    # Default fallback
    return str(value) if value is not None else ""


# ---------------------------------------------------------------------------
# Column header formatter
# ---------------------------------------------------------------------------


def format_column(
    column: str,
    df: dict[str, Any] | _dict,
    data: Optional[list] = None,
) -> str:
    """Format a column header for display.

    Args:
        column: The column key/name.
        df: Field definition dict.
        data: The full dataset (for width calculation hints).

    Returns:
        Formatted column header string.
    """
    label = df.get("label", column) if isinstance(df, (dict, _dict)) else column
    if label:
        return str(label)
    return column.replace("_", " ").title()


# ---------------------------------------------------------------------------
# Date / time formatters
# ---------------------------------------------------------------------------


def format_date(
    string_date: Any = None,
    format_string: Optional[str] = None,
) -> str:
    """Format a date value for display.

    Args:
        string_date: A ``date``, ``datetime``, or ISO string.
        format_string: A Python strftime format, or a key from
            :data:`DATE_FORMAT_MAP`.

    Returns:
        Formatted date string, or ``""`` on error.
    """
    if string_date is None:
        return ""

    # Resolve Python datetime object
    if isinstance(string_date, datetime.datetime):
        dt = string_date.date()
    elif isinstance(string_date, datetime.date):
        dt = string_date
    elif isinstance(string_date, str):
        dt = _parse_date_string(string_date)
        if dt is None:
            return string_date
    else:
        return str(string_date)

    # Resolve format string
    fmt = format_string or frappe.get_system_settings("date_format") or "yyyy-mm-dd"
    fmt = DATE_FORMAT_MAP.get(fmt, fmt)

    try:
        return dt.strftime(fmt)
    except ValueError:
        return str(string_date)


def _format_datetime(value: Any) -> str:
    """Format a datetime value for display."""
    if value is None:
        return ""

    if isinstance(value, datetime.datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    elif isinstance(value, datetime.date):
        dt = datetime.datetime.combine(value, datetime.time())
    else:
        return str(value)

    fmt = "%Y-%m-%d %H:%M:%S"
    try:
        return dt.strftime(fmt)
    except ValueError:
        return str(value)


def _format_time(value: Any) -> str:
    """Format a time value for display."""
    if value is None:
        return ""
    if isinstance(value, datetime.time):
        return value.strftime("%H:%M:%S")
    if isinstance(value, datetime.datetime):
        return value.strftime("%H:%M:%S")
    if isinstance(value, str):
        # Already a string – validate HH:MM:SS format
        if re.match(r"^\d{1,2}:\d{2}:\d{2}$", value):
            return value
        try:
            dt = datetime.datetime.fromisoformat(value)
            return dt.strftime("%H:%M:%S")
        except ValueError:
            return value
    return str(value)


# ---------------------------------------------------------------------------
# Number formatters
# ---------------------------------------------------------------------------


def format_number(
    number: Any,
    format_string: Optional[str] = None,
    precision: int = 2,
) -> str:
    """Format a number with thousand separators.

    Args:
        number: The numeric value.
        format_string: A format key from :data:`NUMBER_FORMATS` or a
            Python format string.
        precision: Decimal places (default ``2``).

    Returns:
        Formatted number string.
    """
    if number is None:
        return ""

    try:
        value = float(number)
    except (ValueError, TypeError):
        return str(number)

    fmt = format_string or frappe.get_system_settings("number_format") or "#,###.##"
    python_fmt = NUMBER_FORMATS.get(fmt)

    if python_fmt:
        # Simple mapping for common formats
        if "##" in fmt and "." in fmt:
            return f"{value:,.{precision}f}"
        return python_fmt.format(value=value)

    # Fallback: use format string directly
    try:
        return format_string.format(value)
    except (ValueError, TypeError):
        return f"{value:,.{precision}f}"


def format_currency(
    value: Any,
    currency: Optional[str] = None,
    format_string: Optional[str] = None,
) -> str:
    """Format a value as currency with symbol.

    Args:
        value: The numeric amount.
        currency: ISO 4217 currency code (e.g. ``"USD"``).
        format_string: Optional number format override.

    Returns:
        String like ``"$1,234.56"``.
    """
    if value is None:
        return ""

    try:
        amount = float(value)
    except (ValueError, TypeError):
        return str(value)

    currency = currency or frappe.get_system_settings("currency") or "USD"
    symbol = CURRENCY_SYMBOLS.get(currency, currency)
    precision = frappe.get_system_settings("currency_precision") or 2

    formatted = format_number(amount, format_string, precision=precision)
    return f"{symbol}{formatted}"


def format_percent(value: Any, precision: int = 2) -> str:
    """Format a value as a percentage.

    Args:
        value: The numeric value (e.g. ``0.25`` → ``"25.00%"``).
        precision: Decimal places.

    Returns:
        Percentage string.
    """
    if value is None:
        return ""
    try:
        num = float(value)
        return f"{num * 100:,.{precision}f}%"
    except (ValueError, TypeError):
        return str(value)


# ---------------------------------------------------------------------------
# Table formatter
# ---------------------------------------------------------------------------


def format_table(
    data: list[dict],
    fields: list[dict],
    formatters: Optional[dict[str, Callable]] = None,
) -> list[list[str]]:
    """Format a data table for display.

    Args:
        data: List of row dicts.
        fields: List of field definition dicts with ``fieldname`` and
            ``fieldtype``.
        formatters: Optional dict mapping fieldnames to custom
            formatter callables.

    Returns:
        List of formatted rows, where the first row is the header.
    """
    formatters = formatters or {}

    # Header row
    headers = [format_column(f.get("fieldname", ""), f, data) for f in fields]
    rows: list[list[str]] = [headers]

    # Data rows
    for row in data:
        formatted_row: list[str] = []
        for f in fields:
            fn = f.get("fieldname", "")
            if fn in formatters:
                formatted_row.append(formatters[fn](row.get(fn), row))
            else:
                formatted_row.append(format_value(row.get(fn), f))
        rows.append(formatted_row)

    return rows


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _format_float(value: Any, df: Optional[dict] = None) -> str:
    """Format a Float field value."""
    if value is None:
        return ""
    try:
        precision = 2
        if df:
            precision = int(df.get("precision", 2) or 2)
        return f"{float(value):,.{precision}f}"
    except (ValueError, TypeError):
        return str(value)


def _format_int(value: Any) -> str:
    """Format an Int field value."""
    if value is None:
        return ""
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return str(value)


def _format_link(value: Any, options: str) -> str:
    """Format a Link field value."""
    if not value:
        return ""
    return str(value)


def _format_select(value: Any, options: str) -> str:
    """Format a Select field value – return the selected option label."""
    if value is None:
        return ""
    return str(value)


def _format_color(value: Any) -> str:
    """Format a Color field value as a coloured preview."""
    if not value:
        return ""
    color = str(value)
    return f"■ {color}"


def _format_json(value: Any) -> str:
    """Format a JSON field value as a pretty-printed string."""
    import json
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, indent=2, default=str)
    except (TypeError, ValueError):
        return str(value)


def _format_rating(value: Any) -> str:
    """Format a Rating field as star symbols."""
    if value is None:
        return ""
    try:
        stars = int(float(value))
        return "★" * stars + "☆" * (5 - stars)
    except (ValueError, TypeError):
        return str(value)


def _format_duration(value: Any) -> str:
    """Format a Duration field (stored in seconds) as HH:MM:SS."""
    if value is None:
        return ""
    try:
        total_seconds = float(value)
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"
    except (ValueError, TypeError):
        return str(value)


def _format_phone(value: Any) -> str:
    """Format a Phone field value."""
    if not value:
        return ""
    return str(value)


def _format_attach(value: Any) -> str:
    """Format an Attach / Attach Image field value."""
    if not value:
        return ""
    return str(value)


def _format_geolocation(value: Any) -> str:
    """Format a Geolocation field value."""
    if not value:
        return ""
    from frappe.geo import format_coordinates, parse_coordinates
    parsed = parse_coordinates(value)
    if parsed:
        return format_coordinates(parsed)
    return str(value)


def _parse_date_string(value: str) -> Optional[datetime.date]:
    """Try to parse a date string in various formats.

    Returns:
        A ``datetime.date`` object, or ``None``.
    """
    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y/%m/%d",
        "%d.%m.%Y",
        "%b %d, %Y",
        "%B %d, %Y",
        "%d %B, %Y",
    ]
    for fmt in formats:
        try:
            return datetime.datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue

    # Try ISO format (may include time)
    try:
        dt = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.date()
    except ValueError:
        pass

    return None
