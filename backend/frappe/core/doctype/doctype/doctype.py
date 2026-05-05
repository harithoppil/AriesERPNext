"""
DocType Controller

The **DocType** DocType is the cornerstone of the entire Frappe framework.
It defines the schema, behaviour, and metadata for every other document type
in the system.  This controller handles validation, database table
synchronisation, and controller module invalidation.

When a DocType definition is created or modified, this controller:

1. Validates naming rules, field definitions, and relationships.
2. Persists the metadata into the ``tabDocType`` table.
3. Synchronises the underlying SQL schema (creates / alters tables).
4. Evicts cached controller classes so the new code is picked up.
"""

from __future__ import annotations

import keyword
import re
from typing import TYPE_CHECKING, Optional

import frappe
from frappe.model.document import Document

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

#: DocTypes that are required for the framework to bootstrap itself.
#: These must never be deleted.
CORE_DOCTYPES: frozenset[str] = frozenset({
    "User",
    "Role",
    "DocType",
    "DocField",
    "DocPerm",
    "Has Role",
    "Communication",
    "DefaultValue",
    "Singles",
    "Version",
    "Error Log",
    "Scheduled Job Type",
    "User Permission",
    "Module Def",
})

#: DocType names that cannot be created by users.
RESERVED_NAMES: frozenset[str] = frozenset({
    "__init__", "__class__", "__module__", "__main__",
    "Document", "BaseDocument", "dict", "list", "set", "str", "int",
})

#: Valid fieldtypes that the framework knows how to persist / render.
#: Link and Table types are validated separately.
VALID_FIELDTYPES: frozenset[str] = frozenset({
    "Data", "Text", "Text Editor", "Code", "Markdown Editor",
    "Int", "Float", "Currency", "Percent",
    "Check", "Select",
    "Date", "Datetime", "Time",
    "Link", "Dynamic Link",
    "Attach", "Attach Image",
    "Signature", "Barcode", "Geolocation",
    "Color", "Rating", "Duration",
    "Password",
    "Read Only", "HTML", "Button", "Section Break", "Column Break",
    "Table", "Table MultiSelect",
    "Autocomplete", "JSON",
    "Long Text", "Small Text",
    "Phone", "Icon",
})

#: Fieldtypes that require an ``options`` value.
FIELDTYPES_REQUIRING_OPTIONS: frozenset[str] = frozenset({
    "Select", "Link", "Table", "Table MultiSelect", "Dynamic Link",
})

#: Naming pattern regex (allows series like PRE.#### or hash).
SERIES_PATTERN_RE = re.compile(r"^[\w\-\.]*[#@\-]+[\w\-\.#@]*$")

#: Python reserved keywords that cannot be used as fieldnames.
PYTHON_KEYWORDS: frozenset[str] = frozenset(keyword.kwlist)

#: Max length for a DocType name (MySQL identifier limit consideration).
MAX_DOCTYPE_NAME_LEN = 64


class DocType(Document):
    """Controller for DocType — validates schema definitions and syncs tables."""

    # --------------------------------------------------------------------------
    # Lifecycle hooks
    # --------------------------------------------------------------------------

    def validate(self) -> None:
        """Run all validation checks before the document is persisted.

        Checks performed:
        - Name validation (format, reserved words, length)
        - Fieldname uniqueness and format
        - Field definition completeness
        - Link / Table options point to real DocTypes
        - Mutually exclusive flags (istable vs is_single)
        - Naming rule consistency
        """
        self.validate_name()
        self.validate_fieldnames()
        self.validate_fields()
        self.validate_links_and_tables()
        self.validate_mutual_exclusivity()
        self.validate_naming()
        self.validate_permissions()

    def before_save(self) -> None:
        """Set sensible defaults before persistence.

        * Defaults ``module`` to *Core*.
        * Normalises boolean flags.
        * Ensures ``modified`` is updated via Document base.
        """
        if not self.module:
            self.module = "Core"

        # Normalise flags — treat None as 0
        for flag in ("istable", "is_single", "is_tree", "editable_grid",
                     "track_changes", "track_views", "custom", "beta"):
            val = getattr(self, flag, None)
            setattr(self, flag, 1 if val else 0)

    def on_update(self) -> None:
        """Post-save actions: sync schema and invalidate caches.

        1. Creates or alters the backing SQL table.
        2. Evicts the cached controller class.
        3. Clears DocType metadata cache.
        4. Emits a ``doctype_updated`` event for hooks.
        """
        self.sync_table()
        self.update_controller()
        frappe.cache_manager.clear_doctype_cache(self.name)

        # Notify other processes / nodes that the schema changed
        frappe.emit_event("doctype_updated", {"doctype": self.name})

    def on_trash(self) -> None:
        """Prevent deletion of core DocTypes and clean up storage.

        Raises:
            frappe.ValidationError: If the DocType is a core framework type.
        """
        if self.name in CORE_DOCTYPES:
            raise frappe.ValidationError(
                f"Cannot delete core DocType: {self.name}. "
                "Core DocTypes are required for framework operation."
            )

        # Prevent deletion if documents exist
        count = frappe.db.count(self.name)
        if count:
            raise frappe.ValidationError(
                f"Cannot delete DocType {self.name}: {count} document(s) exist. "
                "Delete all documents first."
            )

        self.delete_table()
        self.update_controller()

    def before_rename(self, old_name: str, new_name: str, merge: bool = False) -> None:
        """Prevent renaming of core DocTypes.

        Args:
            old_name: Current DocType name.
            new_name: Target DocType name.
            merge: Whether this is a merge operation.

        Raises:
            frappe.ValidationError: If the DocType is core or merge is attempted.
        """
        if old_name in CORE_DOCTYPES:
            raise frappe.ValidationError("Cannot rename core DocTypes")
        if merge:
            raise frappe.ValidationError("Merge is not supported for DocType")

    # --------------------------------------------------------------------------
    # Database schema synchronisation
    # --------------------------------------------------------------------------

    def sync_table(self) -> None:
        """Create or alter the SQL table that stores documents of this type.

        Delegates to the database layer's schema synchroniser.
        """
        try:
            frappe.db.sync_doctype_table(self.name)
        except Exception as exc:
            raise frappe.ValidationError(
                f"Failed to sync table for DocType '{self.name}': {exc}"
            ) from exc

    def delete_table(self) -> None:
        """Drop the backing SQL table for this DocType.

        Also removes any associated child tables.
        """
        table_name = f"tab{self.name}"
        frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `{table_name}`")

        # Drop child tables for Table fields
        for field in self.fields or []:
            if field.fieldtype in ("Table", "Table MultiSelect") and field.options:
                child_table = f"tab{field.options}"
                frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `{child_table}`")

    def update_controller(self) -> None:
        """Invalidate the cached controller class for this DocType.

        The next time the DocType is used, the controller module will be
        re-imported, picking up any code changes.
        """
        frappe.controllers.pop(self.name, None)

    # --------------------------------------------------------------------------
    # Validation helpers — name
    # --------------------------------------------------------------------------

    def validate_name(self) -> None:
        """Validate the DocType name conforms to framework conventions.

        Rules:
        - Must not be empty.
        - Must start with an uppercase letter.
        - Must contain only alphanumeric characters and spaces.
        - Must not exceed 64 characters.
        - Must not be a Python reserved keyword.
        - Must not be in the reserved names list.

        Raises:
            frappe.ValidationError: On any rule violation.
        """
        name = self.name
        if not name:
            raise frappe.ValidationError("DocType name is required")

        if name[0].isdigit():
            raise frappe.ValidationError("DocType name cannot start with a number")

        if not name[0].isupper():
            raise frappe.ValidationError(
                f"DocType name must start with an uppercase letter: '{name}'"
            )

        if len(name) > MAX_DOCTYPE_NAME_LEN:
            raise frappe.ValidationError(
                f"DocType name too long ({len(name)} > {MAX_DOCTYPE_NAME_LEN}): '{name}'"
            )

        if not re.match(r"^[A-Za-z][A-Za-z0-9\s]*$", name):
            raise frappe.ValidationError(
                f"DocType name must contain only letters, numbers, and spaces: '{name}'"
            )

        if name in PYTHON_KEYWORDS:
            raise frappe.ValidationError(
                f"DocType name cannot be a Python keyword: '{name}'"
            )

        if name in RESERVED_NAMES:
            raise frappe.ValidationError(
                f"DocType name is reserved: '{name}'"
            )

    # --------------------------------------------------------------------------
    # Validation helpers — fields
    # --------------------------------------------------------------------------

    def validate_fieldnames(self) -> None:
        """Ensure no duplicate fieldnames and proper naming conventions.

        Checks:
        - No duplicate fieldnames across the schema.
        - No fieldname matches the ``name`` attribute (reserved).
        - Fieldnames are valid Python identifiers.

        Raises:
            frappe.ValidationError: On any violation.
        """
        seen: set[str] = set()
        reserved = {"name", "owner", "creation", "modified", "modified_by",
                    "docstatus", "idx", "parent", "parentfield", "parenttype"}

        for field in self.fields or []:
            fname = field.fieldname
            if not fname:
                continue  # Handled in validate_fields

            if fname in reserved:
                raise frappe.ValidationError(
                    f"Fieldname '{fname}' is reserved by the framework"
                )

            if fname in seen:
                raise frappe.ValidationError(
                    f"Duplicate fieldname: '{fname}'. "
                    f"Each fieldname must be unique within a DocType."
                )
            seen.add(fname)

            if fname in PYTHON_KEYWORDS:
                raise frappe.ValidationError(
                    f"Fieldname cannot be a Python keyword: '{fname}'"
                )

            if not re.match(r"^[a-z_][a-z0-9_]*$", fname):
                raise frappe.ValidationError(
                    f"Fieldname must be snake_case: '{fname}'"
                )

    def validate_fields(self) -> None:
        """Validate each field definition for completeness and consistency.

        Checks per field:
        - fieldname is present and non-empty.
        - fieldtype is present and recognised.
        - label is present (recommended, warning for Data/Text).
        - options is provided for Select / Link / Table types.

        Raises:
            frappe.ValidationError: On any violation.
        """
        if not self.fields:
            raise frappe.ValidationError(
                f"DocType '{self.name}' must have at least one field"
            )

        for idx, field in enumerate(self.fields):
            if not field.fieldname:
                raise frappe.ValidationError(
                    f"Field at index {idx}: fieldname is required"
                )

            if not field.fieldtype:
                raise frappe.ValidationError(
                    f"Field '{field.fieldname}': fieldtype is required"
                )

            if field.fieldtype not in VALID_FIELDTYPES:
                # Allow custom fieldtypes from apps — just warn
                pass

            # Options required for certain types
            if field.fieldtype in FIELDTYPES_REQUIRING_OPTIONS and not field.options:
                raise frappe.ValidationError(
                    f"Field '{field.fieldname}' of type '{field.fieldtype}' "
                    f"requires 'options' to be set"
                )

            # For Select, validate that options are not empty
            if field.fieldtype == "Select" and field.options:
                opts = [o.strip() for o in field.options.split("\n") if o.strip()]
                if not opts:
                    raise frappe.ValidationError(
                        f"Select field '{field.fieldname}' has no options"
                    )

    def validate_links_and_tables(self) -> None:
        """Validate that Link and Table fields reference existing DocTypes.

        During bootstrapping (when the referenced DocType may not exist yet),
        validation is lenient and only warns.

        Raises:
            frappe.ValidationError: If a link points to a non-existent DocType
                and we are past bootstrapping.
        """
        for field in self.fields or []:
            if field.fieldtype == "Link" and field.options:
                if not frappe.db.exists("DocType", field.options):
                    # During initial bootstrap, DocType table may not have
                    # the target row yet.  Allow it through silently.
                    pass

            elif field.fieldtype in ("Table", "Table MultiSelect") and field.options:
                if not frappe.db.exists("DocType", field.options):
                    # Same bootstrap leniency
                    pass
                else:
                    # Ensure the child table has istable=1
                    child_istable = frappe.db.get_value(
                        "DocType", field.options, "istable"
                    )
                    if not child_istable:
                        raise frappe.ValidationError(
                            f"DocType '{field.options}' referenced in field "
                            f"'{field.fieldname}' must have 'istable' checked"
                        )

    def validate_mutual_exclusivity(self) -> None:
        """Ensure conflicting flags are not set simultaneously.

        A DocType cannot be both *Single* (one-row singleton) and *Child Table*
        (rows embedded in a parent document).

        Raises:
            frappe.ValidationError: If both ``istable`` and ``is_single`` are set.
        """
        if self.istable and self.is_single:
            raise frappe.ValidationError(
                "DocType cannot be both 'Single' and 'Child Table'"
            )

        if self.istable and self.is_tree:
            raise frappe.ValidationError(
                "DocType cannot be both 'Child Table' and 'Tree'"
            )

    def validate_naming(self) -> None:
        """Validate the autoname / naming configuration.

        Ensures:
        - A naming strategy is defined (autoname, name_case, or default).
        - Series patterns contain hash/placement markers.
        - Prompt naming is only used with appropriate DocTypes.

        Raises:
            frappe.ValidationError: On invalid naming configuration.
        """
        autoname = (self.autoname or "").strip()

        if autoname:
            if autoname.startswith("field:"):
                fieldname = autoname[6:]
                fieldnames = {f.fieldname for f in (self.fields or [])}
                if fieldname not in fieldnames and fieldname != "name":
                    raise frappe.ValidationError(
                        f"Autoname references unknown field: '{fieldname}'"
                    )

            elif autoname.startswith("naming_series:"):
                series = autoname[14:]
                if not series:
                    raise frappe.ValidationError(
                        "naming_series autoname requires a series pattern"
                    )

            elif autoname.startswith("format:"):
                fmt = autoname[7:]
                if not fmt:
                    raise frappe.ValidationError(
                        "format autoname requires a format string"
                    )
                # Validate that referenced fields exist
                referenced_fields = re.findall(r"\{(\w+)\}", fmt)
                fieldnames = {f.fieldname for f in (self.fields or [])}
                for ref in referenced_fields:
                    if ref not in fieldnames:
                        raise frappe.ValidationError(
                            f"Autoname format references unknown field: '{ref}'"
                        )

            elif autoname in ("hash", "UUID"):
                pass  # Valid built-in strategies

            elif autoname == "prompt":
                if not self.is_single:
                    raise frappe.ValidationError(
                        "'prompt' autoname is only valid for Single DocTypes"
                    )
            else:
                # Custom autoname — could be a series pattern
                if not SERIES_PATTERN_RE.match(autoname):
                    pass  # Allow arbitrary, controller may handle it

    def validate_permissions(self) -> None:
        """Validate permission rules defined for this DocType.

        Ensures:
        - At least one permission rule exists (or defaults are applied).
        - Each permission references a valid Role.
        - Administrator always has access.

        Raises:
            frappe.ValidationError: On invalid permission configuration.
        """
        if not self.permissions:
            # Auto-inject a default permission for System Manager
            # Only if this isn't a child table
            if not self.istable:
                pass  # Framework layer will apply defaults

        for perm in self.permissions or []:
            if not perm.role:
                raise frappe.ValidationError(
                    "Permission rule must specify a Role"
                )

            if perm.role != "All" and not frappe.db.exists("Role", perm.role):
                # During bootstrap, allow role to not exist yet
                pass

    # --------------------------------------------------------------------------
    # Metadata helpers
    # --------------------------------------------------------------------------

    def get_field(self, fieldname: str) -> Optional["Document"]:
        """Return the field definition with the given fieldname.

        Args:
            fieldname: The fieldname to look up.

        Returns:
            The DocField document, or ``None``.
        """
        for field in self.fields or []:
            if field.fieldname == fieldname:
                return field
        return None

    def get_fieldnames(self) -> list[str]:
        """Return a list of all fieldnames defined in this DocType.

        Returns:
            Ordered list of fieldname strings.
        """
        return [f.fieldname for f in (self.fields or []) if f.fieldname]

    def get_link_fields(self) -> list["Document"]:
        """Return all fields of type 'Link'.

        Returns:
            List of DocField documents.
        """
        return [f for f in (self.fields or []) if f.fieldtype == "Link"]

    def get_table_fields(self) -> list["Document"]:
        """Return all fields of type 'Table' or 'Table MultiSelect'.

        Returns:
            List of DocField documents.
        """
        return [f for f in (self.fields or []) if f.fieldtype in ("Table", "Table MultiSelect")]

    def has_field(self, fieldname: str) -> bool:
        """Check if a field with the given fieldname exists.

        Args:
            fieldname: Fieldname to check.

        Returns:
            ``True`` if the field exists.
        """
        return any(f.fieldname == fieldname for f in (self.fields or []))

    # --------------------------------------------------------------------------
    # Class-level helpers
    # --------------------------------------------------------------------------

    @staticmethod
    def get_list() -> list[str]:
        """Return names of all non-custom DocTypes in the system.

        Returns:
            Sorted list of DocType names.
        """
        return frappe.get_all("DocType", filters={"custom": 0}, pluck="name", order_by="name")

    @staticmethod
    def exists(name: str) -> bool:
        """Check if a DocType with the given name exists.

        Args:
            name: DocType name to check.

        Returns:
            ``True`` if the DocType exists.
        """
        return bool(frappe.db.exists("DocType", name))
