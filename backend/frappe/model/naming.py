"""
Frappe Document Naming Module

Handles automatic name generation for documents. Supports multiple strategies:
- Naming series (e.g., PO-00001, INV-2024-00001)
- Field-based naming (using document field values)
- Hash-based naming (random hash)
- UUID-based naming
- Autoincrement
- Expression-based naming with date placeholders

Example naming series:
    "PO-.#####"           -> PO-00001, PO-00002
    "SINV-.YY.-.####"     -> SINV-24-0001
    "REC-.YYYY.-{field}"  -> REC-2024-customer_name
"""

from __future__ import annotations

import datetime
import hashlib
import logging
import re
import time
from typing import TYPE_CHECKING, Optional

import frappe
from frappe.exceptions import InvalidNamingSeriesError, NameError, ValidationError

if TYPE_CHECKING:
    from frappe.model.document import Document

logger = logging.getLogger("frappe.model.naming")

# ─── Constants ───────────────────────────────────────────────────────────────

NAMING_SERIES_PATTERN = re.compile(r"^[\w\- \/.#{}]+$", re.UNICODE)
BRACED_PARAMS_PATTERN = re.compile(r"(\{[\w | #]+\})")

# ─── Naming Series Class ─────────────────────────────────────────────────────


class NamingSeries:
    """Represents and validates a naming series pattern.

    Usage:
        series = NamingSeries("PO-.#####")
        name = series.generate_next_name(doc)
    """

    __slots__ = ("series",)

    def __init__(self, series: str):
        """Initialize with a series pattern.

        :param series: Series pattern like "PO-.#####" or "INV-.YY.-.####"
        """
        self.series = series

        # Add default number part if missing
        if "#" not in self.series:
            self.series += ".#####"

    def validate(self):
        """Validate the naming series pattern."""
        if "." not in self.series:
            raise InvalidNamingSeriesError(
                f"Invalid naming series {self.series}: dot (.) missing"
            )

        if not NAMING_SERIES_PATTERN.match(self.series):
            raise InvalidNamingSeriesError(
                f"Special characters except '-', '#', '.', '/' not allowed in naming series {self.series}"
            )

        if "#" in self.series and ".#" not in self.series:
            raise InvalidNamingSeriesError(
                f"Invalid naming series {self.series}: dot (.) missing before the numeric placeholders"
            )

    def generate_next_name(self, doc: "Document", *, ignore_validate=False) -> str:
        """Generate the next name in the series.

        :param doc: Document to generate name for
        :param ignore_validate: Skip validation
        :return: Generated name
        """
        if not ignore_validate:
            self.validate()

        parts = self.series.split(".")
        return parse_naming_series(parts, doc=doc)

    def get_prefix(self) -> str:
        """Get the series prefix (the part before the number).

        Used to maintain counters in the database.
        e.g., 'SINV-.YY.-.####' has prefix 'SINV-22-' for year 2022.
        """
        prefix = None

        def fake_counter_backend(partial_series, digits):
            nonlocal prefix
            prefix = partial_series
            return "#" * digits

        parse_naming_series(self.series, number_generator=fake_counter_backend)

        if prefix is None:
            raise InvalidNamingSeriesError(f"Invalid Naming Series: {self.series}")

        return prefix

    def get_preview(self, doc=None) -> list[str]:
        """Generate preview of naming series without using DB counters.

        :param doc: Document for field references
        :return: List of sample names
        """
        generated_names = []
        for count in range(1, 4):

            def fake_counter(_prefix, digits):
                return str(count).zfill(digits)

            generated_names.append(
                parse_naming_series(self.series, doc=doc, number_generator=fake_counter)
            )

        return generated_names

    def update_counter(self, new_count: int) -> None:
        """Update the series counter in the database.

        :param new_count: New counter value
        """
        prefix = self.get_prefix()

        # Initialize if not present
        if frappe.db.get_value("Series", prefix, "name", order_by=None) is None:
            frappe.db.sql(
                "INSERT INTO `tabSeries` (`name`, `current`) VALUES (?, ?)",
                (prefix, 0),
            )

        frappe.db.sql(
            "UPDATE `tabSeries` SET `current` = ? WHERE `name` = ?",
            (new_count, prefix),
        )

    def get_current_value(self) -> int:
        """Get current counter value from database.

        :return: Current counter value
        """
        prefix = self.get_prefix()
        result = frappe.db.get_value("Series", prefix, "current", order_by=None)
        return int(result) if result else 0


# ─── Core Naming Functions ───────────────────────────────────────────────────


def set_new_name(doc: "Document") -> None:
    """Set the name for a new document based on naming rules.

    Rules (in order of priority):
    1. If amended doc, set amended name suffix
    2. If autoincrement is configured, get next sequence value
    3. If UUID is configured, generate UUID
    4. If custom 'autoname' method exists, call it
    5. If autoname property is set in meta, use it
    6. Fall back to hash-based naming

    :param doc: Document to name
    """
    from frappe.model.document import Document

    # Run before_naming hook
    doc.run_method("before_naming")

    meta = frappe.get_meta(doc.doctype)
    autoname = (getattr(meta, "autoname", None) or "") if meta else ""

    # Preserve explicitly-provided name unless autoname forces a specific pattern
    # (prompt/uuid let user specify; hash/field/naming_series override)
    if autoname and autoname.lower() not in ("prompt", "uuid"):
        # Only clear if autoname is explicitly configured to override
        if autoname.lower() in ("hash",):
            doc.name = None
    elif not autoname:
        # No autoname configured — respect user-provided name, only clear if not set
        if not doc.name:
            doc.name = None

    # Check for autoincrement
    if is_autoincremented(doc.doctype, meta):
        doc.name = frappe.db.get_next_sequence_val(doc.doctype)
        return

    # UUID naming
    if autoname == "UUID":
        import uuid
        doc.name = str(doc.name) if doc.name else str(uuid.uuid4())
        return

    # Amended from naming
    if getattr(doc, "amended_from", None):
        _set_amended_name(doc)
        if doc.name:
            return

    # Single doctypes use the doctype name
    if meta and getattr(meta, "issingle", False):
        doc.name = doc.doctype
        return

    # Try custom autoname method
    if not doc.name:
        doc.run_method("autoname")

    # Try naming from meta options
    if not doc.name and autoname:
        set_name_from_naming_options(autoname, doc)

    # Fall back to hash
    if not doc.name:
        doc.name = make_autoname("hash", doc.doctype)

    # Validate the final name
    doc.name = validate_name(doc.doctype, doc.name)


def set_name_from_naming_options(autoname: str, doc: "Document") -> Optional[str]:
    """Set document name from autoname configuration.

    Handles formats like:
    - "field:fieldname" - use field value
    - "naming_series:" - use naming series
    - "PO-.#####" - direct series pattern
    - "hash" - random hash
    - "uuid" - UUID
    - "format:PO-{field1}-{field2}" - format string

    :param autoname: Autoname configuration string
    :param doc: Document to name
    :return: Generated name or None
    """
    autoname = autoname or ""

    # Field-based naming
    if autoname.startswith("field:"):
        fieldname = autoname.split(":", 1)[1]
        doc.name = cstr(doc.get(fieldname)).strip()
        return doc.name

    # Format-based naming
    if autoname.startswith("format:"):
        format_str = autoname.split(":", 1)[1]
        doc.name = _format_from_template(format_str, doc)
        return doc.name

    # Prompt - user must supply name
    if autoname.lower() == "prompt":
        if not doc.name:
            raise NameError(f"Name is required for {doc.doctype}")
        return doc.name

    # UUID
    if autoname.lower() == "uuid":
        import uuid
        doc.name = str(doc.name) if doc.name else str(uuid.uuid4())
        return doc.name

    # Hash
    if autoname.lower() == "hash":
        doc.name = make_autoname("hash", doc.doctype)
        return doc.name

    # Naming series field reference
    if autoname.startswith("naming_series:"):
        set_name_by_naming_series(doc)
        return doc.name

    # Direct naming series pattern
    if "." in autoname or "#" in autoname:
        series = NamingSeries(autoname)
        doc.name = series.generate_next_name(doc)
        return doc.name

    return None


def set_name_by_naming_series(doc: "Document") -> None:
    """Set name using the document's naming_series field.

    Looks for a 'naming_series' field on the document and uses its value
    as the naming series pattern.

    :param doc: Document to name
    """
    naming_series = doc.get("naming_series")
    if not naming_series:
        # Try to get default from meta
        meta = frappe.get_meta(doc.doctype)
        if meta:
            for field in getattr(meta, "fields", []):
                if field.get("fieldname") == "naming_series":
                    options = field.get("options", "").split("\n")
                    if options and options[0]:
                        naming_series = options[0].strip()
                        break

    if not naming_series:
        raise InvalidNamingSeriesError(
            f"Naming series not found for {doc.doctype}"
        )

    series = NamingSeries(naming_series)
    doc.name = series.generate_next_name(doc)


def make_autoname(key: str, doctype: str = "", doc=None) -> str:
    """Generate an automatic name based on the key pattern.

    :param key: Pattern key ("hash", "uuid", or naming series)
    :param doctype: DocType name
    :param doc: Document (for field references)
    :return: Generated name
    """
    if key == "hash":
        return _generate_hash_name(doctype)

    if key == "uuid":
        import uuid
        return str(uuid.uuid4())

    if key == "autoincrement":
        return str(frappe.db.get_next_sequence_val(doctype))

    # Treat as naming series
    if "." in key or "#" in key:
        parts = key.split(".")
        return parse_naming_series(parts, doc=doc)

    # Simple prefix with counter
    if doctype:
        counter = frappe.db.get_next_sequence_val(doctype)
        return f"{key}{counter:05d}"

    return _generate_hash_name(doctype)


def parse_naming_series(
    parts: list,
    doc=None,
    number_generator=None,
) -> str:
    """Parse a naming series into a document name.

    Handles placeholders:
    - '#' digits: numeric counter
    - 'YY', 'YYYY': year
    - 'MM': month
    - 'DD': day
    - '{fieldname}': document field value
    - '.': separator (ignored in output)

    :param parts: Series parts split by '.'
    :param doc: Document for field references
    :param number_generator: Optional callback(prefix, digits) -> str for custom counter
    :return: Parsed name
    """
    now = datetime.datetime.now()
    result_parts = []
    number_part_encountered = False
    prefix_so_far = ""

    for part in parts:
        if not part:
            continue

        # Handle numeric placeholders (####)
        if "#" in part:
            number_part_encountered = True
            digits = part.count("#")
            prefix_so_far += "." if prefix_so_far else ""

            if number_generator:
                result_parts.append(number_generator(prefix_so_far, digits))
            else:
                # Use database counter
                counter = _get_series_counter(prefix_so_far, digits)
                result_parts.append(str(counter).zfill(digits))

        # Handle year/month/day placeholders
        elif part == "YYYY":
            result_parts.append(str(now.year))
        elif part == "YY":
            result_parts.append(str(now.year)[-2:])
        elif part == "MM":
            result_parts.append(f"{now.month:02d}")
        elif part == "DD":
            result_parts.append(f"{now.day:02d}")
        elif part == "WW":
            result_parts.append(f"{now.isocalendar()[1]:02d}")
        elif part == "FY":
            result_parts.append(_get_fiscal_year(now))
        elif part == "TIMESTAMP":
            result_parts.append(str(int(time.time())))

        # Handle {fieldname} references
        elif part.startswith("{") and part.endswith("}"):
            fieldname = part[1:-1].strip()
            if doc:
                value = cstr(doc.get(fieldname, "")).strip()
                result_parts.append(value)
            else:
                result_parts.append("")

        # Regular literal part
        else:
            if result_parts:
                result_parts.append(part)
            else:
                result_parts.append(part)

        if not number_part_encountered:
            prefix_so_far = "".join(result_parts)

    return "".join(result_parts)


def validate_name(
    doctype: str,
    name: str,
    case: Optional[str] = None,
    merge: bool = False,
) -> str:
    """Validate and return a cleaned document name.

    :param doctype: DocType name
    :param name: Proposed name
    :param case: Case enforcement ('Title Case', 'UPPERCASE', 'lowercase')
    :param merge: Whether this is a merge operation
    :return: Validated name
    :raises NameError: If name is invalid
    """
    if not name:
        raise NameError(f"Name cannot be empty for {doctype}")

    name = str(name).strip()

    # Maximum length check
    if len(name) > 255:
        raise NameError(f"Name exceeds maximum length of 255 characters: {name[:50]}...")

    # Check for invalid characters
    invalid_chars = re.findall(r'[<>"/\\]', name)
    if invalid_chars:
        raise NameError(
            f"Name cannot contain characters: {', '.join(set(invalid_chars))}"
        )

    # Case conversion
    if case == "Title Case":
        name = name.title()
    elif case == "UPPERCASE":
        name = name.upper()
    elif case == "lowercase":
        name = name.lower()

    return name


def revert_series_if_last(key: str, name: str, doc=None) -> None:
    """Revert a series counter if the given name was the last one generated.

    Used when a document is deleted to potentially reclaim the number.

    :param key: Series key
    :param name: Document name that was deleted
    :param doc: Document (optional)
    """
    try:
        series = NamingSeries(key)
        prefix = series.get_prefix()

        # Extract the numeric part from the name
        current_value = series.get_current_value()

        # Check if this name used the current counter value
        import re as re_mod
        numeric_part = re_mod.search(r"(\d+)", name)
        if numeric_part:
            name_number = int(numeric_part.group(1))
            if name_number == current_value:
                # Revert counter
                series.update_counter(current_value - 1)
    except Exception:
        # Don't fail if series revert doesn't work
        logger.warning(f"Failed to revert series {key} for name {name}")
        pass


# ─── Helper Functions ────────────────────────────────────────────────────────


def _generate_hash_name(doctype: str = "", length: int = 10) -> str:
    """Generate a hash-based name.

    :param doctype: DocType (used for additional entropy)
    :param length: Hash length
    :return: Hex hash string
    """
    import hashlib
    import time

    hash_input = f"{doctype}:{time.time()}:{id(object())}"
    return hashlib.sha256(hash_input.encode()).hexdigest()[:length]


def _get_series_counter(prefix: str, digits: int) -> int:
    """Get the next counter value for a naming series prefix.

    Uses the tabSeries table to maintain counters.

    :param prefix: Series prefix
    :param digits: Number of digits
    :return: Next counter value
    """
    try:
        # Try to get current value
        current = frappe.db.get_value("Series", prefix, "current", order_by=None)

        if current is None:
            # Initialize series
            frappe.db.sql(
                "INSERT OR IGNORE INTO `tabSeries` (`name`, `current`) VALUES (?, ?)",
                (prefix, 0),
            )
            current = 0
        else:
            current = int(current)

        # Increment and update
        next_value = current + 1
        frappe.db.sql(
            "UPDATE `tabSeries` SET `current` = ? WHERE `name` = ?",
            (next_value, prefix),
        )

        return next_value
    except Exception:
        # Fallback: use timestamp
        import time
        return int(time.time()) % (10 ** digits)


def _set_amended_name(doc: "Document") -> None:
    """Set name for an amended document.

    Appends '-1', '-2', etc. to the original document name.

    :param doc: Document being amended
    """
    amended_from = doc.amended_from
    if not amended_from:
        return

    # Check if there's already an amendment
    import re as re_mod
    match = re_mod.search(r"-([\d]+)$", amended_from)
    if match:
        # Increment the amendment number
        base = amended_from[: match.start()]
        num = int(match.group(1)) + 1
        doc.name = f"{base}-{num}"
    else:
        # First amendment
        doc.name = f"{amended_from}-1"


def _format_from_template(template: str, doc: "Document") -> str:
    """Generate name from a format template.

    Replaces {fieldname} placeholders with document field values.

    :param template: Format string like "PO-{customer}-{transaction_date}"
    :param doc: Document to get values from
    :return: Formatted name
    """
    import re as re_mod

    def replace_field(match):
        fieldname = match.group(1)
        value = cstr(doc.get(fieldname, "")).strip()
        # Sanitize value for use in name
        value = re_mod.sub(r'[<>"/\\]', "", value)
        return value

    return re_mod.sub(r"\\{([^}]+)\\}", replace_field, template)


def _get_fiscal_year(now: datetime.datetime) -> str:
    """Get fiscal year string.

    :param now: Current datetime
    :return: Fiscal year string like "2024-25"
    """
    year = now.year
    return f"{year}-{(year + 1) % 100:02d}"


def is_autoincremented(doctype: str, meta=None) -> bool:
    """Check if a DocType uses autoincrement naming.

    :param doctype: DocType name
    :param meta: Meta object (optional)
    :return: True if autoincrement
    """
    if meta:
        autoname = getattr(meta, "autoname", "")
        if autoname and autoname.lower() == "autoincrement":
            return True
    return False


def append_number_if_name_exists(
    doctype: str,
    name: str,
    fieldname: str = "name",
    separator: str = "-",
    filters: Optional[dict] = None,
) -> str:
    """Append a number to name if it already exists.

    :param doctype: DocType name
    :param name: Proposed name
    :param fieldname: Field to check for existence
    :param separator: Separator between name and number
    :param filters: Additional filters
    :return: Unique name
    """
    original_name = name
    count = 1

    check_filters = {fieldname: name}
    if filters:
        check_filters.update(filters)

    while frappe.db.exists(doctype, check_filters):
        name = f"{original_name}{separator}{count}"
        check_filters[fieldname] = name
        count += 1

    return name


def get_default_naming_series(doctype: str) -> Optional[str]:
    """Get the default naming series for a DocType.

    :param doctype: DocType name
    :return: Default series or None
    """
    meta = frappe.get_meta(doctype)
    if not meta:
        return None

    for field in getattr(meta, "fields", []):
        if field.get("fieldname") == "naming_series":
            options = field.get("options", "").split("\n")
            return options[0].strip() if options else None

    return None


def cstr(val: Any) -> str:
    """Convert value to string, handling None.

    :param val: Value to convert
    :return: String representation
    """
    if val is None:
        return ""
    return str(val)
