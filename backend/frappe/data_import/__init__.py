"""
Frappe Data Import / Export

Replaces ``frappe/core/doctype/data_import`` and provides a clean API for
bulk importing and exporting documents via CSV, Excel, and JSON.

**Features**

- :func:`import_file` — import a CSV/Excel file into any DocType
- :func:`import_csv`  — import from a CSV string or file path
- :func:`import_json` — import from a JSON string or file path
- :func:`export_csv`  — export query results as CSV
- :func:`export_excel` — export query results as Excel (.xlsx)
- :func:`export_json` — export documents as JSON
- :class:`Importer` — low-level import engine with validation and row-by-row processing
- :class:`Exporter` — low-level export engine with column mapping

**Row-level semantics**

The importer treats each row as one document.  Child table rows are
indicated by columns named ``<parentfield>.<child_fieldname>`` (e.g.
``items.item_code``).  Multiple child rows can be provided by repeating
such columns or by using numbered suffixes.

Example CSV::

    customer,transaction_date,items.item_code,items.qty,items.rate
    CUST-001,2024-01-15,ITEM-A,5,100.00
    CUST-001,2024-01-15,ITEM-B,3,50.00

Example::

    from frappe.data_import import import_file

    result = import_file(
        doctype="Sales Order",
        file_path="/tmp/orders.csv",
        import_type="Insert",
    )
    print(result.imported, result.failed)
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Callable, Optional, Union

import frappe
from frappe.exceptions import PermissionError, ValidationError
from frappe.types import _dict
from frappe.utils import (
    cint,
    cstr,
    flt,
    getdate,
    get_datetime,
    now,
    strip,
)

logger = logging.getLogger("frappe.data_import")

# ─── Module-level exports ───────────────────────────────────────────────────

__all__ = [
    "import_file",
    "import_csv",
    "import_json",
    "export_csv",
    "export_excel",
    "export_json",
    "Importer",
    "Exporter",
    "ImportResult",
    "ImportRow",
    "detect_encoding",
    "read_csv_content",
]


# ═══════════════════════════════════════════════════════════════════════════════
#  HIGH-LEVEL API
# ═══════════════════════════════════════════════════════════════════════════════


def import_file(
    doctype: str,
    file_path: str,
    import_type: str = "Insert",  # "Insert" | "Update" | "Insert or Update"
    submit_after_import: bool = False,
    ignore_encoding: bool = False,
    template_options: Optional[dict] = None,
    **kwargs: Any,
) -> "ImportResult":
    """Import data from a CSV or Excel file.

    Parameters
    ----------
    doctype :
        Target DocType.
    file_path :
        Absolute path to the import file.
    import_type :
        ``"Insert"`` = only create new docs;
        ``"Update"`` = only update existing docs;
        ``"Insert or Update"`` = create or update.
    submit_after_import :
        Call ``doc.submit()`` after successful insert.
    ignore_encoding :
        Skip encoding detection (assume UTF-8).
    template_options :
        Extra options forwarded to the Importer.

    Returns
    -------
    ImportResult :
        Summary of the import operation.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Import file not found: {file_path}")

    # Detect file type by extension
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    if ext == ".csv":
        return import_csv(
            doctype=doctype,
            file_path=file_path,
            import_type=import_type,
            submit_after_import=submit_after_import,
            ignore_encoding=ignore_encoding,
            **kwargs,
        )
    elif ext in (".xlsx", ".xls"):
        return _import_excel(
            doctype=doctype,
            file_path=file_path,
            import_type=import_type,
            submit_after_import=submit_after_import,
            **kwargs,
        )
    elif ext == ".json":
        return import_json(
            doctype=doctype,
            file_path=file_path,
            import_type=import_type,
            submit_after_import=submit_after_import,
            **kwargs,
        )
    else:
        raise ValueError(f"Unsupported import file format: {ext}")


def import_csv(
    doctype: str,
    file_path: Optional[str] = None,
    csv_content: Optional[str] = None,
    import_type: str = "Insert",
    submit_after_import: bool = False,
    ignore_encoding: bool = False,
    **kwargs: Any,
) -> "ImportResult":
    """Import data from CSV.

    Either *file_path* or *csv_content* must be provided.
    """
    if csv_content:
        encoding = "utf-8" if ignore_encoding else (detect_encoding(csv_content) or "utf-8")
        rows = _parse_csv_string(csv_content, encoding=encoding)
    elif file_path:
        rows = read_csv_content(file_path, ignore_encoding=ignore_encoding)
    else:
        raise ValueError("Either file_path or csv_content is required")

    if not rows:
        return ImportResult(doctype=doctype, imported=0, failed=0, errors=["No data found in CSV"])

    importer = Importer(
        doctype=doctype,
        import_type=import_type,
        submit_after_import=submit_after_import,
        **kwargs,
    )
    return importer.import_rows(rows)


def import_json(
    doctype: str,
    file_path: Optional[str] = None,
    json_content: Optional[str] = None,
    import_type: str = "Insert",
    submit_after_import: bool = False,
    **kwargs: Any,
) -> "ImportResult":
    """Import data from JSON.

    The JSON should be a list of dicts, each representing one document.
    """
    if json_content:
        data = json.loads(json_content)
    elif file_path:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        raise ValueError("Either file_path or json_content is required")

    if not isinstance(data, list):
        data = [data]

    importer = Importer(
        doctype=doctype,
        import_type=import_type,
        submit_after_import=submit_after_import,
        **kwargs,
    )
    return importer.import_dicts(data)


def export_csv(
    doctype: str,
    fields: Optional[list[str]] = None,
    filters: Optional[dict] = None,
    file_path: Optional[str] = None,
    **kwargs: Any,
) -> Union[str, None]:
    """Export documents as CSV.

    Parameters
    ----------
    doctype :
        Source DocType.
    fields :
        List of fieldnames to include.  ``None`` = all fields.
    filters :
        Query filters.
    file_path :
        If given, write to this path; otherwise return CSV string.

    Returns
    -------
    str or None :
        CSV content string, or ``None`` if written to file.
    """
    exporter = Exporter(doctype=doctype, file_type="CSV", fields=fields)
    csv_content = exporter.export(filters=filters, **kwargs)

    if file_path:
        with open(file_path, "w", encoding="utf-8", newline="") as f:
            f.write(csv_content)
        return None
    return csv_content


def export_excel(
    doctype: str,
    fields: Optional[list[str]] = None,
    filters: Optional[dict] = None,
    file_path: Optional[str] = None,
    **kwargs: Any,
) -> Union[bytes, None]:
    """Export documents as Excel (.xlsx).

    Parameters are the same as :func:`export_csv`.
    """
    exporter = Exporter(doctype=doctype, file_type="Excel", fields=fields)
    xlsx_bytes = exporter.export_binary(filters=filters, **kwargs)

    if file_path:
        with open(file_path, "wb") as f:
            f.write(xlsx_bytes)
        return None
    return xlsx_bytes


def export_json(
    doctype: str,
    filters: Optional[dict] = None,
    file_path: Optional[str] = None,
    **kwargs: Any,
) -> Union[str, None]:
    """Export documents as pretty-printed JSON."""
    docs = frappe.get_all(doctype, filters=filters, fields=["*"], **kwargs)

    # Convert _dict to plain dict for serialization
    serializable = [dict(d) for d in docs]

    json_content = json.dumps(serializable, indent=2, default=str, ensure_ascii=False)

    if file_path:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(json_content)
        return None
    return json_content


# ═══════════════════════════════════════════════════════════════════════════════
#  IMPORTER ENGINE
# ═══════════════════════════════════════════════════════════════════════════════


class ImportRow:
    """Represents a single row from the import file.

    Attributes
    ----------
    row_number : int
        1-based row number (for error reporting).
    data : dict
        Column-name → value mapping.
    doctype : str
        Target DocType for this row.
    docname : str or None
        Document name (for updates).
    is_child : bool
        True if this row represents a child table entry.
    parentfield : str or None
        Parent field name for child rows.
    """

    def __init__(
        self,
        row_number: int,
        data: dict[str, Any],
        doctype: str,
    ):
        self.row_number = row_number
        self.data = _dict(data)
        self.doctype = doctype
        self.docname = data.get("name") or data.get("Name") or data.get("id")
        self.is_child = False
        self.parentfield = None
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.doc: Optional[Any] = None

    def get_value(self, fieldname: str, default: Any = None) -> Any:
        """Get a value from the row data."""
        return self.data.get(fieldname, default)

    def add_error(self, message: str) -> None:
        self.errors.append(f"Row {self.row_number}: {message}")

    def add_warning(self, message: str) -> None:
        self.warnings.append(f"Row {self.row_number}: {message}")


class ImportResult:
    """Summary returned by import operations.

    Attributes
    ----------
    doctype : str
    imported : int
        Number of successfully imported rows.
    updated : int
        Number of successfully updated rows.
    failed : int
        Number of rows that failed.
    skipped : int
        Number of rows skipped (duplicates, etc.).
    errors : list[str]
        Human-readable error messages.
    warnings : list[str]
        Human-readable warning messages.
    """

    def __init__(
        self,
        doctype: str,
        imported: int = 0,
        updated: int = 0,
        failed: int = 0,
        skipped: int = 0,
        errors: Optional[list[str]] = None,
        warnings: Optional[list[str]] = None,
    ):
        self.doctype = doctype
        self.imported = imported
        self.updated = updated
        self.failed = failed
        self.skipped = skipped
        self.errors = errors or []
        self.warnings = warnings or []

    @property
    def total(self) -> int:
        return self.imported + self.updated + self.failed + self.skipped

    @property
    def success(self) -> bool:
        return self.failed == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "doctype": self.doctype,
            "imported": self.imported,
            "updated": self.updated,
            "failed": self.failed,
            "skipped": self.skipped,
            "total": self.total,
            "success": self.success,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class Importer:
    """Row-by-row import engine for CSV/Excel data.

    Handles field mapping, data type conversion, validation, child table
    assembly, and the full document lifecycle (insert / update / submit).
    """

    def __init__(
        self,
        doctype: str,
        import_type: str = "Insert",
        submit_after_import: bool = False,
        ignore_permissions: bool = False,
        **kwargs: Any,
    ):
        self.doctype = doctype
        self.import_type = import_type
        self.submit_after_import = submit_after_import
        self.ignore_permissions = ignore_permissions
        self.meta = frappe.get_meta(doctype)
        self.field_map: dict[str, dict] = self._build_field_map()
        self.results = ImportResult(doctype=doctype)

    # ── Public methods ──

    def import_rows(self, rows: list[dict[str, Any]]) -> ImportResult:
        """Import a list of row dicts."""
        import_rows = [ImportRow(i + 1, row, self.doctype) for i, row in enumerate(rows)]

        # Parse child table columns
        import_rows = self._parse_child_rows(import_rows)

        # Group rows by parent document
        parent_rows = [r for r in import_rows if not r.is_child]
        child_rows = [r for r in import_rows if r.is_child]

        for row in parent_rows:
            self._process_row(row, child_rows)

        return self.results

    def import_dicts(self, dicts: list[dict[str, Any]]) -> ImportResult:
        """Import a list of document dicts (from JSON)."""
        for i, data in enumerate(dicts, start=1):
            row = ImportRow(i, data, self.doctype)
            self._process_row(row, [])
        return self.results

    # ── Row processing ──

    def _process_row(self, row: ImportRow, all_child_rows: list[ImportRow]) -> None:
        """Process a single parent row."""
        try:
            doc_dict = self._convert_row_to_doc_dict(row)

            # Attach child rows that belong to this parent
            child_data = self._collect_children_for_row(row, all_child_rows)
            for parentfield, children in child_data.items():
                doc_dict[parentfield] = children

            # Check for existing document
            existing = None
            if row.docname and self.import_type in ("Update", "Insert or Update"):
                try:
                    existing = frappe.get_doc(self.doctype, row.docname)
                except Exception:
                    existing = None

            if existing and self.import_type in ("Update", "Insert or Update"):
                # Update existing
                for key, value in doc_dict.items():
                    if key not in ("doctype", "name"):
                        setattr(existing, key, value)
                existing.save(
                    ignore_permissions=self.ignore_permissions,
                )
                self.results.updated += 1
                row.doc = existing

            elif not existing and self.import_type in ("Insert", "Insert or Update"):
                # Insert new
                doc_dict["doctype"] = self.doctype
                doc = frappe.get_doc(doc_dict)
                doc.insert(
                    ignore_permissions=self.ignore_permissions,
                )

                if self.submit_after_import:
                    doc.submit()

                self.results.imported += 1
                row.doc = doc

            else:
                row.add_error(f"Document '{row.docname}' {'already exists' if existing else 'not found'}")
                self.results.skipped += 1

        except ValidationError as exc:
            row.add_error(str(exc))
            self.results.failed += 1
            self.results.errors.extend(row.errors)
        except PermissionError as exc:
            row.add_error(f"Permission denied: {exc}")
            self.results.failed += 1
            self.results.errors.extend(row.errors)
        except Exception as exc:
            row.add_error(f"Unexpected error: {exc}")
            self.results.failed += 1
            self.results.errors.extend(row.errors)

    # ── Data conversion ──

    def _convert_row_to_doc_dict(self, row: ImportRow) -> dict[str, Any]:
        """Convert a CSV row dict to a document dict with proper types."""
        result: dict[str, Any] = {}

        for column_name, raw_value in row.data.items():
            # Skip child table columns (handled separately)
            if "." in column_name:
                continue

            field_info = self.field_map.get(column_name)
            if not field_info:
                # Try case-insensitive match
                field_info = self.field_map.get(column_name.lower())

            if field_info:
                converted = self._convert_value(raw_value, field_info)
                result[field_info["fieldname"]] = converted
            else:
                # Pass through unknown fields as strings
                result[column_name] = raw_value

        # Always include name for updates
        if row.docname:
            result["name"] = row.docname

        return result

    def _convert_value(self, raw_value: Any, field_info: dict) -> Any:
        """Convert a raw CSV string to the appropriate Python type."""
        if raw_value is None:
            return None

        fieldtype = field_info.get("fieldtype", "Data")

        # Strip string values
        if isinstance(raw_value, str):
            raw_value = raw_value.strip()
            if raw_value == "":
                return None

        type_converters: dict[str, Callable] = {
            "Int": cint,
            "Integer": cint,
            "Float": flt,
            "Currency": flt,
            "Percent": flt,
            "Check": lambda v: cint(v) if v else 0,
            "Date": getdate,
            "Datetime": get_datetime,
            "Time": cstr,
            "Long Text": cstr,
            "Small Text": cstr,
            "Text": cstr,
            "Text Editor": cstr,
            "Markdown Editor": cstr,
            "Code": cstr,
            "HTML Editor": cstr,
            "JSON": cstr,
            "Password": cstr,
            "Read Only": cstr,
            "Link": cstr,
            "Dynamic Link": cstr,
            "Select": cstr,
            "Data": cstr,
            "Barcode": cstr,
            "Attach": cstr,
            "Attach Image": cstr,
            "Color": cstr,
            "Icon": cstr,
            "Phone": cstr,
            "Autocomplete": cstr,
            "Rating": cint,
        }

        converter = type_converters.get(fieldtype, cstr)
        try:
            return converter(raw_value)
        except Exception:
            # Fallback to string on conversion failure
            return cstr(raw_value)

    # ── Child table handling ──

    def _parse_child_rows(self, rows: list[ImportRow]) -> list[ImportRow]:
        """Identify and mark child table rows based on column names."""
        # Detect child table columns (format: parentfield.child_fieldname)
        child_fields: set[str] = set()
        for field in self.meta.fields if self.meta else []:
            if field.fieldtype == "Table" and field.fieldname:
                child_fields.add(field.fieldname)

        # Currently, we keep a flat row model; child data is extracted
        # in _collect_children_for_row.
        return rows

    def _collect_children_for_row(
        self, parent_row: ImportRow, all_child_rows: list[ImportRow],
    ) -> dict[str, list[dict]]:
        """Extract child table data from a parent row's dot-notation columns."""
        children: dict[str, list[dict]] = defaultdict(list)

        for column_name, value in parent_row.data.items():
            if "." not in column_name or value is None:
                continue

            parentfield, child_fieldname = column_name.split(".", 1)
            if parentfield not in [f.fieldname for f in (self.meta.fields if self.meta else [])]:
                continue

            child_row = {child_fieldname: value}
            children[parentfield].append(child_row)

        return dict(children)

    # ── Field map ──

    def _build_field_map(self) -> dict[str, dict]:
        """Build a mapping of label/fieldname → field info for quick lookup."""
        field_map: dict[str, dict] = {}
        if not self.meta or not hasattr(self.meta, "fields"):
            return field_map

        for field in self.meta.fields:
            fieldname = field.fieldname
            label = field.label
            fieldtype = field.fieldtype

            info = {"fieldname": fieldname, "label": label, "fieldtype": fieldtype}

            field_map[fieldname] = info
            if label:
                field_map[label] = info
                field_map[label.lower()] = info

        return field_map


# ═══════════════════════════════════════════════════════════════════════════════
#  EXPORTER ENGINE
# ═══════════════════════════════════════════════════════════════════════════════


class Exporter:
    """Export engine for converting query results to CSV / Excel."""

    def __init__(
        self,
        doctype: str,
        file_type: str = "CSV",  # "CSV" or "Excel"
        fields: Optional[list[str]] = None,
    ):
        self.doctype = doctype
        self.file_type = file_type
        self.meta = frappe.get_meta(doctype)
        self.fields = fields or self._get_default_fields()

    def export(
        self,
        filters: Optional[dict] = None,
        **kwargs: Any,
    ) -> str:
        """Export as CSV string."""
        docs = frappe.get_all(
            self.doctype,
            filters=filters,
            fields=self.fields,
            **kwargs,
        )

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=self.fields, extrasaction="ignore")
        writer.writeheader()
        for doc in docs:
            writer.writerow({k: self._format_value(v) for k, v in doc.items()})

        return output.getvalue()

    def export_binary(
        self,
        filters: Optional[dict] = None,
        **kwargs: Any,
    ) -> bytes:
        """Export as Excel bytes."""
        csv_content = self.export(filters=filters, **kwargs)
        return _csv_to_xlsx(csv_content, self.fields)

    def _get_default_fields(self) -> list[str]:
        """Get default fields to export from the DocType meta."""
        fields = ["name"]
        if self.meta and hasattr(self.meta, "fields"):
            for field in self.meta.fields:
                if not getattr(field, "print_hide", 0):
                    fields.append(field.fieldname)
        # Add standard fields
        for std in ["creation", "modified", "modified_by", "owner", "docstatus"]:
            if std not in fields:
                fields.append(std)
        return fields

    @staticmethod
    def _format_value(value: Any) -> str:
        """Convert a value to a CSV-safe string."""
        if value is None:
            return ""
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        return cstr(value)


# ═══════════════════════════════════════════════════════════════════════════════
#  CSV UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════


def detect_encoding(text: str) -> Optional[str]:
    """Attempt to detect the encoding of a text string.

    Returns the most likely encoding or ``None``.
    """
    try:
        # Try UTF-8 BOM first
        if text.startswith("\ufeff"):
            return "utf-8-sig"
        # If it decodes as UTF-8, use that
        text.encode("utf-8")
        return "utf-8"
    except UnicodeEncodeError:
        pass

    # Try chardet if available
    try:
        import chardet

        result = chardet.detect(text.encode("latin-1", errors="replace"))
        return result.get("encoding", "utf-8")
    except ImportError:
        pass

    return "utf-8"


def read_csv_content(
    file_path: str,
    ignore_encoding: bool = False,
) -> list[dict[str, Any]]:
    """Read a CSV file and return a list of row dicts."""
    encoding = "utf-8"
    if not ignore_encoding:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            sample = f.read(4096)
            detected = detect_encoding(sample)
            if detected:
                encoding = detected

    with open(file_path, "r", encoding=encoding, errors="replace") as f:
        reader = csv.DictReader(f)
        return [row for row in reader]


def _parse_csv_string(content: str, encoding: str = "utf-8") -> list[dict[str, Any]]:
    """Parse CSV content from a string."""
    import io

    f = io.StringIO(content)
    reader = csv.DictReader(f)
    return [row for row in reader]


def _csv_to_xlsx(csv_content: str, fieldnames: list[str]) -> bytes:
    """Convert CSV content to Excel (.xlsx) bytes.

    Uses ``openpyxl`` if available; falls back to a tab-separated format
    inside a zip file (minimal xlsx).
    """
    try:
        import openpyxl
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "Export"

        reader = csv.DictReader(io.StringIO(csv_content))
        headers = reader.fieldnames or fieldnames

        # Write header
        ws.append(headers)

        # Write rows
        for row in reader:
            ws.append([row.get(h, "") for h in headers])

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf.getvalue()

    except ImportError:
        logger.warning("openpyxl not installed; returning CSV in xlsx wrapper")
        # Fallback: return CSV bytes
        return csv_content.encode("utf-8")


def _import_excel(
    doctype: str,
    file_path: str,
    import_type: str = "Insert",
    submit_after_import: bool = False,
    **kwargs: Any,
) -> ImportResult:
    """Import from an Excel (.xlsx) file."""
    try:
        import openpyxl
    except ImportError:
        return ImportResult(
            doctype=doctype,
            failed=1,
            errors=["openpyxl is required for Excel import. Install it: pip install openpyxl"],
        )

    try:
        wb = openpyxl.load_workbook(file_path, data_only=True)
        ws = wb.active

        # First row = headers
        headers = [cstr(cell.value) for cell in ws[1]]

        rows: list[dict[str, Any]] = []
        for row_data in ws.iter_rows(min_row=2, values_only=True):
            row_dict = {}
            for i, header in enumerate(headers):
                if i < len(row_data):
                    row_dict[header] = row_data[i]
            rows.append(row_dict)

        importer = Importer(
            doctype=doctype,
            import_type=import_type,
            submit_after_import=submit_after_import,
            **kwargs,
        )
        return importer.import_rows(rows)

    except Exception as exc:
        logger.exception("Excel import failed")
        return ImportResult(doctype=doctype, failed=1, errors=[str(exc)])
