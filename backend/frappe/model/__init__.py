"""
Frappe Model Module

Core document modeling infrastructure. Provides the Document base class,
metadata handling, naming, querying, and lifecycle management.
"""

# Field types that represent child tables
TABLE_FIELDS = ("Table", "Table MultiSelect")

# Standard fields present on all documents
STANDARD_FIELDS = [
    "name",
    "owner",
    "creation",
    "modified",
    "modified_by",
    "docstatus",
    "idx",
    "parent",
    "parenttype",
    "parentfield",
    "_user_tags",
    "_comments",
    "_assign",
    "_liked_by",
]

# Optional fields that can exist on documents
OPTIONAL_FIELDS = [
    "_user_tags",
    "_comments",
    "_assign",
    "_liked_by",
]

# Child table fields
CHILD_TABLE_FIELDS = [
    "parent",
    "parenttype",
    "parentfield",
    "idx",
]

# Default fields for metadata
DEFAULT_FIELDS = [
    "name",
    "creation",
    "modified",
    "modified_by",
    "owner",
    "docstatus",
    "idx",
]

# Datetime field types
DATETIME_FIELD_TYPES = ("Date", "Datetime", "Time")

# Numeric field types
NUMERIC_FIELD_TYPES = ("Int", "Float", "Currency", "Percent", "Check")

# Field types stored as text
TEXT_FIELD_TYPES = (
    "Data",
    "Link",
    "Dynamic Link",
    "Password",
    "Select",
    "Read Only",
    "Attach",
    "Attach Image",
    "Signature",
    "Color",
    "Barcode",
    "Geolocation",
    "HTML Editor",
    "Markdown Editor",
    "Code",
    "Text Editor",
    "Text",
    "Small Text",
    "Long Text",
    "JSON",
    "Autocomplete",
)

# Log doctypes that should not trigger certain hooks
LOG_TYPES = ("Version", "Activity Log", "Error Log", "Error Snapshot", "Access Log")


def get_permitted_fields(doctype, parenttype=None):
    """Get fields that the current user is permitted to read.

    :param doctype: DocType name
    :param parenttype: Parent DocType (for child tables)
    :return: List of permitted fieldnames
    """
    import frappe
    meta = frappe.get_meta(doctype)
    if not meta:
        return ["name"]
    return [f.get("fieldname") for f in meta.fields] + DEFAULT_FIELDS
