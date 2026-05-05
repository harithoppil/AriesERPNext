"""
Frappe Meta Module

Handles DocType metadata — cached objects that describe the fields,
permissions, and properties of a DocType. Meta objects are themselves
documents (of type "DocType") and are cached for performance.

The meta system provides:
- Field definitions (fieldname, fieldtype, options, etc.)
- Permission definitions (DocPerm records)
- DocType properties (issingle, istable, is_submittable, etc.)
- Field lookups by name or type
- Table field definitions for child tables

Example:
    meta = get_meta("Sales Order")
    print(meta.fields)
    print(meta.get_field("customer"))
    print(meta.get_table_fields())
"""

from __future__ import annotations

import functools
import json
import logging
from typing import Any, Optional

import frappe
from frappe.types import _dict

logger = logging.getLogger("frappe.model.meta")

# ─── Meta Cache ──────────────────────────────────────────────────────────────

_meta_cache: dict[str, "Meta"] = {}


class Meta:
    """Metadata for a DocType.

    Contains all the field definitions, permissions, and properties
    that define a DocType's behavior. Meta objects are cached.

    Attributes:
        name: DocType name
        fields: List of field definitions
        permissions: List of permission definitions
        autoname: Naming rule
        issingle: Whether this is a single DocType
        istable: Whether this is a table (child) DocType
        is_submittable: Whether documents can be submitted
        is_tree: Whether this uses the nested set model
    """

    def __init__(self, doctype: str):
        """Load metadata for a DocType.

        :param doctype: DocType name
        """
        self.name = doctype
        self.doctype = "DocType"

        # Load from database or use defaults
        meta_dict = self._load_meta(doctype)

        # Set attributes from loaded data
        self.__dict__.update(meta_dict)

        # Ensure required attributes
        if not hasattr(self, "fields"):
            self.fields = []
        if not hasattr(self, "permissions"):
            self.permissions = []
        if not hasattr(self, "autoname"):
            self.autoname = ""
        if not hasattr(self, "issingle"):
            self.issingle = 0
        if not hasattr(self, "istable"):
            self.istable = 0
        if not hasattr(self, "is_submittable"):
            self.is_submittable = 0
        if not hasattr(self, "is_tree"):
            self.is_tree = 0
        if not hasattr(self, "editable_grid"):
            self.editable_grid = 1
        if not hasattr(self, "track_changes"):
            self.track_changes = 1
        if not hasattr(self, "module"):
            self.module = "Core"
        if not hasattr(self, "icon"):
            self.icon = ""
        if not hasattr(self, "title_field"):
            self.title_field = "name"

    def _load_meta(self, doctype: str) -> dict:
        """Load metadata from database.

        :param doctype: DocType name
        :return: Dict of metadata properties
        """
        try:
            # Try to get from DocType document
            result = frappe.db.sql(
                "SELECT * FROM `tabDocType` WHERE `name` = ?",
                (doctype,),
                as_dict=True,
            )

            if result:
                meta_dict = dict(result[0])

                # Load fields
                meta_dict["fields"] = self._load_fields(doctype)

                # Load permissions
                meta_dict["permissions"] = self._load_permissions(doctype)

                # Load actions
                meta_dict["actions"] = self._load_actions(doctype)

                # Convert numeric flags
                for key in ["issingle", "istable", "is_submittable", "is_tree",
                           "editable_grid", "track_changes", "custom",
                           "read_only", "in_create", "beta"]:
                    if key in meta_dict:
                        meta_dict[key] = int(meta_dict[key] or 0)

                return meta_dict

        except Exception as e:
            logger.debug(f"Could not load meta for {doctype} from DB: {e}")

        # Return default meta for non-existent doctypes
        return self._default_meta(doctype)

    def _load_fields(self, doctype: str) -> list[dict]:
        """Load field definitions for a DocType.

        :param doctype: DocType name
        :return: List of field dicts
        """
        try:
            fields = frappe.db.sql(
                """
                SELECT * FROM `tabDocField`
                WHERE `parent` = ? AND `parenttype` = 'DocType'
                ORDER BY `idx` ASC
                """,
                (doctype,),
                as_dict=True,
            )
            return [dict(f) for f in fields] if fields else []
        except Exception as e:
            logger.debug(f"Could not load fields for {doctype}: {e}")
            return []

    def _load_permissions(self, doctype: str) -> list[dict]:
        """Load permission definitions for a DocType.

        :param doctype: DocType name
        :return: List of permission dicts
        """
        try:
            perms = frappe.db.sql(
                """
                SELECT * FROM `tabDocPerm`
                WHERE `parent` = ? AND `parenttype` = 'DocType'
                ORDER BY `idx` ASC
                """,
                (doctype,),
                as_dict=True,
            )
            return [dict(p) for p in perms] if perms else []
        except Exception as e:
            logger.debug(f"Could not load permissions for {doctype}: {e}")
            return []

    def _load_actions(self, doctype: str) -> list[dict]:
        """Load action definitions for a DocType.

        :param doctype: DocType name
        :return: List of action dicts
        """
        try:
            actions = frappe.db.sql(
                """
                SELECT * FROM `tabDocType Action`
                WHERE `parent` = ? AND `parenttype` = 'DocType'
                ORDER BY `idx` ASC
                """,
                (doctype,),
                as_dict=True,
            )
            return [dict(a) for a in actions] if actions else []
        except Exception as e:
            logger.debug(f"Could not load actions for {doctype}: {e}")
            return []

    def _default_meta(self, doctype: str) -> dict:
        """Create default metadata for a DocType that doesn't exist in DB.

        :param doctype: DocType name
        :return: Default metadata dict
        """
        return {
            "name": doctype,
            "doctype": "DocType",
            "fields": [],
            "permissions": [],
            "actions": [],
            "autoname": "",
            "issingle": 0,
            "istable": 0,
            "is_submittable": 0,
            "is_tree": 0,
            "editable_grid": 1,
            "track_changes": 1,
            "module": "Core",
            "icon": "",
            "title_field": "name",
        }

    def get_field(self, fieldname: str) -> Optional[_dict]:
        """Get a field definition by fieldname.

        :param fieldname: Field name
        :return: Field dict or None
        """
        for field in self.fields:
            if field.get("fieldname") == fieldname:
                return _dict(field)
        return None

    def get_fields_by_type(self, fieldtype: str) -> list[_dict]:
        """Get all fields of a specific type.

        :param fieldtype: Field type (e.g., 'Link', 'Table', 'Data')
        :return: List of field dicts
        """
        return [_dict(f) for f in self.fields if f.get("fieldtype") == fieldtype]

    def get_table_fields(self, include_virtual: bool = False) -> list[_dict]:
        """Get all table (child table) field definitions.

        :param include_virtual: Include virtual child tables
        :return: List of field dicts with fieldtype='Table'
        """
        result = []
        for f in self.fields:
            if f.get("fieldtype") in ("Table", "Table MultiSelect"):
                if include_virtual or not f.get("is_virtual"):
                    result.append(_dict(f))
        return result

    def get_link_fields(self) -> list[_dict]:
        """Get all Link field definitions.

        :return: List of field dicts with fieldtype='Link'
        """
        return self.get_fields_by_type("Link")

    def get_mandatory_fields(self) -> list[_dict]:
        """Get all mandatory (required) field definitions.

        :return: List of field dicts with reqd=1
        """
        return [_dict(f) for f in self.fields if f.get("reqd")]

    def get_unique_fields(self) -> list[_dict]:
        """Get all unique field definitions.

        :return: List of field dicts with unique=1
        """
        return [_dict(f) for f in self.fields if f.get("unique")]

    def has_field(self, fieldname: str) -> bool:
        """Check if a field exists.

        :param fieldname: Field name
        :return: True if field exists
        """
        return any(f.get("fieldname") == fieldname for f in self.fields)

    def get_fieldnames(self) -> list[str]:
        """Get all fieldnames defined in this DocType.

        :return: List of fieldnames
        """
        return [f.get("fieldname") for f in self.fields if f.get("fieldname")]

    def get_valid_columns(self) -> list[str]:
        """Get all valid column names (fieldnames + standard fields).

        :return: List of column names
        """
        from frappe.model import DEFAULT_FIELDS
        columns = list(DEFAULT_FIELDS)
        columns.extend(self.get_fieldnames())
        return columns

    @property
    def title_field(self) -> str:
        """Get the title field for this DocType."""
        if hasattr(self, "_title_field"):
            return self._title_field
        # Try to find title field
        for f in self.fields:
            if f.get("fieldtype") in ("Data", "Text", "Read Only") and not f.get("options"):
                self._title_field = f.get("fieldname", "name")
                return self._title_field
        self._title_field = "name"
        return self._title_field

    @title_field.setter
    def title_field(self, value):
        self._title_field = value

    @property
    def is_virtual(self) -> bool:
        """Check if this is a virtual DocType."""
        return bool(getattr(self, "is_virtual", 0))

    def get_masked_fields(self) -> list[_dict]:
        """Get fields that should have masked values.

        :return: List of field dicts
        """
        # Password fields are masked
        return self.get_fields_by_type("Password")

    def get_search_fields(self) -> list[str]:
        """Get fields that should be included in search.

        :return: List of fieldnames
        """
        search_fields = []
        for f in self.fields:
            if f.get("in_standard_filter") or f.get("search_index"):
                fieldname = f.get("fieldname")
                if fieldname:
                    search_fields.append(fieldname)
        return search_fields or ["name"]

    def as_dict(self) -> _dict:
        """Convert meta to a _dict.

        :return: _dict representation
        """
        return _dict(self.__dict__)

    def __repr__(self):
        return f"Meta({self.name})"


# ─── Module Functions ────────────────────────────────────────────────────────


def get_meta(doctype: str, cached: bool = True) -> Meta:
    """Get metadata for a DocType.

    Meta objects are cached for performance. Use cached=False to
    force a fresh load from the database.

    :param doctype: DocType name
    :param cached: Use cached meta if available
    :return: Meta object
    """
    if cached and doctype in _meta_cache:
        return _meta_cache[doctype]

    meta = Meta(doctype)

    if cached:
        _meta_cache[doctype] = meta

    return meta


def clear_meta_cache(doctype: str = None) -> None:
    """Clear cached meta for a DocType or all DocTypes.

    :param doctype: Specific DocType to clear, or None for all
    """
    global _meta_cache
    if doctype:
        _meta_cache.pop(doctype, None)
    else:
        _meta_cache.clear()


def get_field_precision(meta_field: dict, doc=None, currency: str = None) -> int:
    """Get the precision (decimal places) for a numeric field.

    :param meta_field: Field definition dict
    :param doc: Document (for currency-based precision)
    :param currency: Currency code
    :return: Number of decimal places
    """
    # Check for field-specific precision
    precision = meta_field.get("precision")
    if precision is not None:
        return int(precision)

    fieldtype = meta_field.get("fieldtype", "")

    # Field-type defaults
    if fieldtype == "Currency":
        # Use currency precision if available
        if currency:
            # In a full implementation, this would look up currency precision
            return 2
        return 2
    elif fieldtype == "Float":
        return 6
    elif fieldtype in ("Int", "Check"):
        return 0
    elif fieldtype == "Percent":
        return 2

    # Default
    return 3


def get_table_columns(doctype: str) -> list[str]:
    """Get actual database columns for a DocType's table.

    :param doctype: DocType name
    :return: List of column names
    """
    return frappe.db.get_table_columns(doctype)


def has_field(doctype: str, fieldname: str) -> bool:
    """Check if a DocType has a specific field.

    :param doctype: DocType name
    :param fieldname: Field name
    :return: True if field exists
    """
    meta = get_meta(doctype)
    return meta.has_field(fieldname)
