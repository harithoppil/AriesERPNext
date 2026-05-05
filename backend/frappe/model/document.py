"""
Frappe Document Model

THE core class of the entire framework. Every ERPNext business object
inherits from Document — Sales Order, Purchase Order, Item, Customer, etc.

Provides:
- Loading/saving from/to database
- Complete lifecycle hooks (validate, before_save, on_submit, etc.)
- Child table management
- Dirty tracking and partial updates
- Permission checking
- Pydantic-based validation and serialization

Example:
    so = get_doc("Sales Order", "SO-00001")
    so.status = "To Deliver"
    so.save()
    so.submit()

    new_so = new_doc("Sales Order")
    new_so.customer = "CUST-001"
    new_so.append("items", {"item_code": "ITEM-001", "qty": 5})
    new_so.insert()
"""

from __future__ import annotations

import copy
import datetime
import json
import logging
from collections.abc import Generator, Iterable
from typing import Any, Callable, Optional, Union

import frappe
from frappe.exceptions import (
    DoesNotExistError,
    DuplicateEntryError,
    MandatoryError,
    PermissionError,
    TimestampMismatchError,
    ValidationError,
)
from frappe.model.meta import get_meta
from frappe.model.naming import set_new_name, validate_name
from frappe.types import _dict
from frappe.utils import cint, cstr, flt, get_datetime, get_table_name, now

logger = logging.getLogger("frappe.model.document")

# ─── Document Cache ──────────────────────────────────────────────────────────

_document_object_cache: dict[str, "Document"] = {}
_document_value_cache: dict[str, Any] = {}


# ─── Module-Level Functions ─────────────────────────────────────────────────


def get_doc(*args, **kwargs) -> "Document":
    """Return a Document object. This is the primary way to load or create documents.

    Multiple calling conventions are supported:

    1. Load from database by doctype and name::

        doc = get_doc("Sales Order", "SO-00001")

    2. Load from a dict (creates new document)::

        doc = get_doc({"doctype": "Sales Order", "customer": "CUST-001"})

    3. Create new with keyword arguments::

        doc = get_doc(doctype="Sales Order", customer="CUST-001")

    4. Load a single DocType::

        doc = get_doc("System Settings")

    5. Pass an existing Document (returns as-is)::

        doc = get_doc(existing_doc)

    :param args: Positional arguments (doctype, name)
    :param kwargs: Keyword arguments for creating documents
    :return: Document instance
    :raises ValueError: If arguments are invalid
    :raises DoesNotExistError: If document not found
    """
    if not args and kwargs:
        # New document from kwargs
        if "doctype" not in kwargs:
            raise ValueError('"doctype" is required when creating from kwargs')
        return _create_document(kwargs["doctype"], kwargs)

    if len(args) == 1:
        arg = args[0]
        if isinstance(arg, Document):
            # Already a Document
            return arg
        if isinstance(arg, dict):
            # From dict
            if "doctype" not in arg:
                raise ValueError('"doctype" is a required key in dict')
            return _create_document(arg["doctype"], arg)
        if isinstance(arg, str):
            # Single doctype or just doctype name
            return _create_document(arg, {}, load_from_db=True)

    if len(args) >= 2:
        doctype = args[0]
        name = args[1]
        if isinstance(doctype, str):
            return _create_document(doctype, {"name": name}, load_from_db=True)

    raise ValueError(f"Invalid arguments for get_doc: args={args}, kwargs={kwargs}")


def get_cached_doc(*args, **kwargs) -> "Document":
    """Get a document from cache or load from database.

    Documents are cached by (doctype, name) key for performance.
    Use clear_document_cache() to invalidate.

    :param args: Same as get_doc
    :param kwargs: Same as get_doc
    :return: Document instance (cached or freshly loaded)
    """
    # Determine doctype and name from arguments
    doctype, name = _extract_doctype_name(args, kwargs)

    if doctype and name:
        cache_key = get_document_cache_key(doctype, name)
        if cache_key in _document_object_cache:
            return _document_object_cache[cache_key]

    doc = get_doc(*args, **kwargs)

    if doc.doctype and doc.name:
        cache_key = get_document_cache_key(doc.doctype, doc.name)
        _document_object_cache[cache_key] = doc

    return doc


def new_doc(
    doctype: str,
    parent_doc: Optional["Document"] = None,
    parentfield: Optional[str] = None,
    **kwargs,
) -> "Document":
    """Create a new, unsaved document of the given DocType.

    :param doctype: DocType to create
    :param parent_doc: Parent document (for child table rows)
    :param parentfield: Parent field name (for child table rows)
    :param kwargs: Additional field values
    :return: New Document instance (not yet saved)

    Example::

        doc = new_doc("Sales Order")
        doc.customer = "CUST-001"
        doc.insert()
    """
    data = {"doctype": doctype, **kwargs}

    if parent_doc:
        data["parent"] = parent_doc.name
        data["parenttype"] = parent_doc.doctype
    if parentfield:
        data["parentfield"] = parentfield

    doc = _create_document(doctype, data)
    doc.__islocal = True
    doc.__unsaved = True

    return doc


def get_single(doctype: str) -> "Document":
    """Get a single DocType document.

    Single DocTypes store their values in the tabSingles table.
    They have exactly one instance per site.

    :param doctype: Single DocType name
    :return: Document instance
    """
    doc = _create_document(doctype, {}, load_from_db=True)
    return doc


def get_single_value(doctype: str, fieldname: str) -> Any:
    """Get a single field value from a single DocType.

    :param doctype: Single DocType name
    :param fieldname: Field to retrieve
    :return: Field value or None
    """
    cache_key = f"_single_value:{doctype}:{fieldname}"
    if cache_key in _document_value_cache:
        return _document_value_cache[cache_key]

    try:
        result = frappe.db.sql(
            """
            SELECT `value` FROM `tabSingles`
            WHERE `doctype` = ? AND `field` = ?
            """,
            (doctype, fieldname),
        )
        value = result[0][0] if result else None
    except Exception:
        value = None

    _document_value_cache[cache_key] = value
    return value


def get_last_doc(doctype: str, **kwargs) -> "Document":
    """Get the most recently modified document of a DocType.

    :param doctype: DocType to query
    :param kwargs: Additional filters
    :return: Latest Document instance
    :raises DoesNotExistError: If no documents exist
    """
    filters = kwargs.get("filters", {})
    order_by = kwargs.get("order_by", "modified desc")

    result = frappe.db.get_all(
        doctype,
        filters=filters,
        fields=["name"],
        order_by=order_by,
        limit_page_length=1,
    )

    if not result:
        raise DoesNotExistError(f"No {doctype} found", doctype=doctype)

    return get_doc(doctype, result[0]["name"])


def get_cached_value(
    doctype: str,
    name: str,
    fieldname: str = "name",
    as_dict: bool = False,
) -> Any:
    """Get a cached field value from a document.

    :param doctype: DocType
    :param name: Document name
    :param fieldname: Field to retrieve (or list of fields)
    :param as_dict: Return as dict
    :return: Field value(s)
    """
    cache_key = get_document_cache_key(doctype, name)

    # Check object cache first
    if cache_key in _document_object_cache:
        doc = _document_object_cache[cache_key]
        if isinstance(fieldname, (list, tuple)):
            result = {f: doc.get(f) for f in fieldname}
            return _dict(result) if as_dict else list(result.values())
        return doc.get(fieldname)

    # Fall back to DB
    return frappe.db.get_value(
        doctype, name, fieldname, as_dict=as_dict
    )


def copy_doc(doc: "Document", ignore_no_copy: bool = True) -> "Document":
    """Create a deep copy of a document.

    The new document will not have a name and will be marked as unsaved.
    Child tables are also copied.

    :param doc: Document to copy
    :param ignore_no_copy: Skip fields marked with no_copy=1
    :return: New Document instance (not yet saved)
    """
    if not isinstance(doc, Document):
        raise ValueError("copy_doc expects a Document instance")

    # Get document as dict
    doc_dict = doc.as_dict()

    # Remove name and ID fields
    doc_dict.pop("name", None)
    doc_dict.pop("__islocal", None)
    doc_dict.pop("__unsaved", None)
    doc_dict.pop("creation", None)
    doc_dict.pop("modified", None)
    doc_dict.pop("owner", None)
    doc_dict.pop("modified_by", None)
    doc_dict.pop("docstatus", 0)

    # Remove no_copy fields
    if not ignore_no_copy:
        meta = frappe.get_meta(doc.doctype)
        if meta:
            for field in meta.fields:
                if field.get("no_copy"):
                    doc_dict.pop(field.get("fieldname"), None)

    # Copy child tables - they need new names
    meta = frappe.get_meta(doc.doctype)
    if meta:
        for table_field in meta.get_table_fields():
            fieldname = table_field.get("fieldname")
            if fieldname and fieldname in doc_dict:
                for child in doc_dict[fieldname]:
                    child.pop("name", None)
                    child.pop("creation", None)
                    child.pop("modified", None)
                    child["__islocal"] = True

    new_doc = get_doc(doc_dict)
    new_doc.__islocal = True
    new_doc.__unsaved = True

    return new_doc


def can_cache_doc(*args) -> bool:
    """Check if a document can be cached.

    Documents that shouldn't be cached include:
    - New unsaved documents
    - Documents with special flags

    :param args: Arguments that would be passed to get_doc
    :return: True if the document can be cached
    """
    if not args:
        return False
    if isinstance(args[0], dict):
        return False
    if len(args) >= 2 and not args[1]:
        return False
    return True


def get_document_cache_key(doctype: str, name: str) -> str:
    """Get the cache key for a document.

    :param doctype: DocType name
    :param name: Document name
    :return: Cache key string
    """
    return f"__document_cache:{doctype}:{name}"


def _set_document_in_cache(doctype: str, name: str, doc: "Document") -> None:
    """Store a document in the cache.

    :param doctype: DocType name
    :param name: Document name
    :param doc: Document instance
    """
    cache_key = get_document_cache_key(doctype, name)
    _document_object_cache[cache_key] = doc


def clear_document_cache(doctype: str = None, name: str = None) -> None:
    """Clear cached document(s).

    :param doctype: DocType to clear, or None for all
    :param name: Specific document name, or None for all of doctype
    """
    global _document_object_cache, _document_value_cache

    if doctype is None:
        # Clear all caches
        _document_object_cache.clear()
        _document_value_cache.clear()
        return

    if name is None:
        # Clear all documents of this doctype
        keys_to_remove = [
            k for k in _document_object_cache.keys()
            if k.startswith(f"__document_cache:{doctype}:")
        ]
        for key in keys_to_remove:
            del _document_object_cache[key]

        value_keys = [
            k for k in _document_value_cache.keys()
            if k.startswith(f"_single_value:{doctype}:")
        ]
        for key in value_keys:
            del _document_value_cache[key]
    else:
        cache_key = get_document_cache_key(doctype, name)
        _document_object_cache.pop(cache_key, None)


# ─── Internal Helpers ────────────────────────────────────────────────────────


def _create_document(doctype: str, data: dict, load_from_db: bool = False) -> "Document":
    """Create a Document instance, optionally loading from DB.

    :param doctype: DocType name
    :param data: Initial data dict
    :param load_from_db: Whether to load from database
    :return: Document instance
    """
    doc = Document(doctype, **data) if not load_from_db else Document(doctype, data.get("name"))

    if load_from_db:
        doc.doctype = doctype
        doc.name = data.get("name")
        doc.load_from_db()
    else:
        # Set values from data
        for key, value in data.items():
            if key != "doctype":
                setattr(doc, key, value)
        doc.init_child_tables()

    return doc


def _extract_doctype_name(args, kwargs) -> tuple[Optional[str], Optional[str]]:
    """Extract doctype and name from get_doc arguments.

    :param args: Positional arguments
    :param kwargs: Keyword arguments
    :return: (doctype, name) tuple
    """
    if len(args) >= 2:
        return args[0], args[1]
    if len(args) == 1:
        if isinstance(args[0], str):
            return args[0], None
        if isinstance(args[0], dict):
            return args[0].get("doctype"), args[0].get("name")
    return kwargs.get("doctype"), kwargs.get("name")


# ─── Document Class ──────────────────────────────────────────────────────────


class Document:
    """Base class for all Frappe documents.

    Every ERPNext document (Sales Order, Purchase Order, Item, Customer, etc.)
    inherits from this class. It provides:

    - **Loading/saving**: load_from_db, insert, save, reload
    - **Lifecycle hooks**: validate, before_save, on_submit, etc.
    - **Child table management**: append, extend, remove for child tables
    - **Dirty tracking**: has_changed, get_changed for partial updates
    - **Permission checking**: has_permission, check_permission
    - **Serialization**: as_dict, get_valid_dict, to_json

    Attributes:
        doctype: The DocType name
        name: The document name (primary key)
        owner: User who created the document
        creation: Creation timestamp
        modified: Last modification timestamp
        modified_by: User who last modified
        docstatus: 0=draft, 1=submitted, 2=cancelled
        idx: Display index for ordering
        parent: Parent document name (for child tables)
        parenttype: Parent DocType (for child tables)
        parentfield: Parent field name (for child tables)
        flags: Runtime flags (_dict)
        _doc_before_save: Previous version before save (for change tracking)
    """

    def __init__(self, *args, **kwargs):
        """Initialize a Document.

        Supports multiple calling conventions:

        1. ``Document(doctype, name)`` — load from database
        2. ``Document(doctype)`` — create new (single doctypes load from DB)
        3. ``Document(dict_data)`` — from dict (must have 'doctype')
        4. ``Document(doctype, **field_values)`` — new with field values

        :param args: Positional arguments
        :param kwargs: Field values
        """
        # Initialize core attributes
        self.doctype: Optional[str] = None
        self.name: Optional[str] = None
        self.owner: str = ""
        self.creation: Optional[str] = None
        self.modified: Optional[str] = None
        self.modified_by: str = ""
        self.docstatus: int = 0
        self.idx: int = 0
        self.parent: Optional[str] = None
        self.parenttype: Optional[str] = None
        self.parentfield: Optional[str] = None

        # Runtime attributes
        self.flags = _dict()
        self._doc_before_save: Optional[Document] = None
        self._table_fields: dict[str, str] = {}  # fieldname -> child_doctype
        self._changed: list[str] = []
        self._values: dict[str, Any] = {}  # Internal storage for non-standard fields
        self.__islocal = False
        self.__unsaved = False
        self._action: Optional[str] = None

        # Process arguments
        if args:
            first_arg = args[0]
            if isinstance(first_arg, str):
                # Document(doctype) or Document(doctype, name)
                self.doctype = first_arg
                self.name = args[1] if len(args) > 1 else None

                if self.name:
                    # Load from database
                    self.load_from_db()
                return

            elif isinstance(first_arg, dict):
                # Document(dict)
                kwargs = first_arg

        # Set from kwargs
        if kwargs:
            self.doctype = kwargs.pop("doctype", self.doctype)
            for key, value in kwargs.items():
                if hasattr(self, key) and key not in ("flags", "_values", "_table_fields"):
                    setattr(self, key, value)
                else:
                    self._values[key] = value

            self.init_child_tables()

    # ─── Property Access ─────────────────────────────────────────────────────

    def __getattr__(self, key: str) -> Any:
        """Allow attribute-style access to dynamic fields."""
        if key.startswith("_"):
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{key}'"
            )
        if key in self._values:
            return self._values[key]
        # Return None for unset fields (Frappe convention)
        return None

    def __setattr__(self, key: str, value: Any) -> None:
        """Set attribute, tracking changes for standard fields."""
        # Always set known attributes directly
        known_attrs = {
            "doctype", "name", "owner", "creation", "modified",
            "modified_by", "docstatus", "idx", "parent", "parenttype",
            "parentfield", "flags", "_doc_before_save", "_table_fields",
            "_changed", "_values", "_Document__islocal", "_Document__unsaved",
            "_action",
        }

        if key in known_attrs or key.startswith("_"):
            super().__setattr__(key, value)
        else:
            # Store in _values for dynamic fields
            old_value = self._values.get(key)
            if old_value != value:
                if key not in self._changed:
                    self._changed.append(key)
            self._values[key] = value

    def __getitem__(self, key: str) -> Any:
        """Dict-style access: doc['fieldname']."""
        return self.get(key)

    def __setitem__(self, key: str, value: Any) -> None:
        """Dict-style assignment: doc['fieldname'] = value."""
        self.set(key, value)

    def __contains__(self, key: str) -> bool:
        """Check if field exists: 'fieldname' in doc."""
        return hasattr(self, key) or key in self._values

    def __repr__(self) -> str:
        return f"Document({self.doctype}, {self.name})"

    def __str__(self) -> str:
        return f"{self.doctype}({self.name})"

    # ─── Core Loading ─────────────────────────────────────────────────────────

    def load_from_db(self) -> "Document":
        """Load document and children from database.

        Loads the main document row and all child table rows.
        Must have ``self.doctype`` and ``self.name`` set before calling.

        :return: self (for chaining)
        :raises DoesNotExistError: If document not found
        """
        if not self.doctype:
            raise ValueError("doctype must be set before load_from_db")

        # Handle single doctypes
        meta = self.meta
        if meta and getattr(meta, "issingle", False):
            self._load_single_from_db()
            return self

        if not self.name:
            raise ValueError("name must be set before load_from_db")

        # Load main document
        data = frappe.db.get_value(
            self.doctype,
            self.name,
            "*",
            as_dict=True,
            for_update=getattr(self.flags, "for_update", False),
        )

        if not data:
            raise DoesNotExistError(
                f"{self.doctype} {self.name} not found",
                doctype=self.doctype,
            )

        # Set standard fields
        self._set_from_dict(data)

        # Load child tables
        self.load_children_from_db()

        return self

    def _load_single_from_db(self) -> None:
        """Load a single DocType from tabSingles table."""
        single_values = frappe.db.get_singles_dict(self.doctype)

        if not single_values:
            # Return defaults
            self.name = self.doctype
            return

        self._set_from_dict(single_values)
        self.name = self.doctype

    def load_children_from_db(self) -> "Document":
        """Load child table rows from database.

        Queries each child table defined in the DocType meta and
        populates the corresponding attributes on this document.

        :return: self (for chaining)
        """
        if not self.name:
            return self

        self._table_fields = {}
        meta = self.meta
        if not meta:
            return self

        for table_field in meta.get_table_fields():
            fieldname = table_field.get("fieldname")
            child_doctype = table_field.get("options")

            if not fieldname or not child_doctype:
                continue

            self._table_fields[fieldname] = child_doctype

            try:
                children = frappe.db.get_values(
                    child_doctype,
                    {
                        "parent": self.name,
                        "parenttype": self.doctype,
                        "parentfield": fieldname,
                    },
                    "*",
                    as_dict=True,
                    order_by="idx asc",
                )
            except Exception as e:
                logger.debug(
                    f"Could not load child table {child_doctype} for "
                    f"{self.doctype}/{self.name}: {e}"
                )
                children = []

            # Convert child dicts to Document objects
            child_docs = []
            for child_data in children or []:
                child_doc = Document(child_doctype, **child_data)
                child_doc.__islocal = False
                child_doc.parent = self.name
                child_doc.parenttype = self.doctype
                child_doc.parentfield = fieldname
                child_docs.append(child_doc)

            self._values[fieldname] = child_docs

        return self

    # ─── CRUD Operations ─────────────────────────────────────────────────────

    def insert(
        self,
        ignore_permissions: Optional[bool] = None,
        ignore_links: Optional[bool] = None,
        ignore_if_duplicate: bool = False,
        ignore_mandatory: Optional[bool] = None,
        set_name: Optional[str] = None,
        set_child_names: bool = True,
    ) -> "Document":
        """Insert the document as a new record in the database.

        Executes the full insert lifecycle:
        1. Set defaults and timestamps
        2. Check permissions
        3. Run before_insert hook
        4. Generate name (autoname)
        5. Run validate hook
        6. Insert into database
        7. Insert child table rows
        8. Run after_insert hook
        9. Run on_update and on_change hooks

        :param ignore_permissions: Skip permission checks if True
        :param ignore_links: Skip link validation if True
        :param ignore_if_duplicate: Don't raise error on duplicate name
        :param ignore_mandatory: Skip mandatory field validation if True
        :param set_name: Explicit name to use
        :param set_child_names: Generate names for child rows
        :return: self (for chaining)
        """
        if ignore_permissions is not None:
            self.flags.ignore_permissions = ignore_permissions
        if ignore_links is not None:
            self.flags.ignore_links = ignore_links
        if ignore_mandatory is not None:
            self.flags.ignore_mandatory = ignore_mandatory

        self.__islocal = True
        self._action = "insert"

        # Set defaults
        self._set_defaults()
        self.set_user_and_timestamp()
        self.set_docstatus()

        # Check permissions
        self.check_permission("create")

        # Validate links
        if not self.flags.get("ignore_links"):
            self._validate_links()

        # Run before_insert hook
        self.run_method("before_insert")

        # Generate name
        if set_name:
            self.name = validate_name(self.doctype, set_name)
        else:
            set_new_name(self)

        # Set parent references in children
        self.set_parent_in_children()

        # Set names in children
        if set_child_names:
            self._set_child_names()

        # Run before_save hooks
        self.run_method("before_save")
        self.run_method("before_validate")

        # Validate
        if not self.flags.get("ignore_mandatory"):
            self._validate_mandatory()
        self.run_method("validate")

        # Set docstatus again (validate might have changed it)
        self.set_docstatus()

        # Insert into database
        if self.meta and getattr(self.meta, "issingle", False):
            self._update_single(self.get_valid_dict())
        else:
            self._db_insert(ignore_if_duplicate=ignore_if_duplicate)

        # Insert child table rows
        for child in self.get_all_children():
            child._db_insert()

        # Run after_insert hook
        self.run_method("after_insert")

        # Run on_update and on_change
        self.run_method("on_update")
        self.run_method("on_change")

        # Clear flags
        self.__islocal = False
        if hasattr(self, "__unsaved"):
            self.__unsaved = False

        # Update cache
        if self.name:
            cache_key = get_document_cache_key(self.doctype, self.name)
            _document_object_cache[cache_key] = self

        return self

    def save(
        self,
        ignore_permissions: Optional[bool] = None,
        ignore_version: Optional[bool] = None,
        ignore_links: Optional[bool] = None,
    ) -> "Document":
        """Save the document (insert if new, update if existing).

        This is the main method for persisting changes. It delegates to
        insert() for new documents or _save() for existing ones.

        :param ignore_permissions: Skip permission checks if True
        :param ignore_version: Skip version tracking if True
        :param ignore_links: Skip link validation if True
        :return: self (for chaining)
        """
        if self.get("__islocal") or not self.get("name"):
            return self.insert(
                ignore_permissions=ignore_permissions,
                ignore_links=ignore_links,
            )
        return self._save(
            ignore_permissions=ignore_permissions,
            ignore_version=ignore_version,
            ignore_links=ignore_links,
        )

    def _save(
        self,
        ignore_permissions: Optional[bool] = None,
        ignore_version: Optional[bool] = None,
        ignore_links: Optional[bool] = None,
    ) -> "Document":
        """Update an existing document in the database.

        Executes the full update lifecycle:
        1. Load previous version for change tracking
        2. Check permissions
        3. Run before_save and before_validate hooks
        4. Validate
        5. Update in database
        6. Update child tables
        7. Run on_update and on_change hooks

        :param ignore_permissions: Skip permission checks if True
        :param ignore_version: Skip version tracking if True
        :param ignore_links: Skip link validation if True
        :return: self (for chaining)
        """
        if ignore_permissions is not None:
            self.flags.ignore_permissions = ignore_permissions
        if ignore_links is not None:
            self.flags.ignore_links = ignore_links
        self.flags.ignore_version = ignore_version

        self._action = "update"

        # Load previous version for change tracking
        self.load_doc_before_save()

        # Check permissions
        self.check_permission("write")

        # Set timestamps
        self.set_user_and_timestamp()
        self.set_docstatus()

        # Check if latest (prevent stale updates)
        self.check_if_latest()

        # Set parent references
        self.set_parent_in_children()

        # Validate links
        if not self.flags.get("ignore_links"):
            self._validate_links()

        # Run before_save hooks
        self.run_method("before_save")
        self.run_method("before_validate")

        # Validate
        if not self.flags.get("ignore_mandatory"):
            self._validate_mandatory()
        self.run_method("validate")

        # Set docstatus again
        self.set_docstatus()

        # Update in database
        if self.meta and getattr(self.meta, "issingle", False):
            self._update_single(self.get_valid_dict())
        else:
            self._db_update()

        # Update child tables
        self._update_children()

        # Run post-save hooks
        self.run_method("on_update")
        self.run_method("on_change")

        # Clear unsaved flag
        if hasattr(self, "__unsaved"):
            self.__unsaved = False

        # Update cache
        if self.name:
            cache_key = get_document_cache_key(self.doctype, self.name)
            _document_object_cache[cache_key] = self

        return self

    def submit(self) -> "Document":
        """Submit the document (transition docstatus from 0 to 1).

        Executes:
        1. before_submit hook
        2. validate
        3. Set docstatus = 1
        4. Save
        5. on_submit hook

        :return: self (for chaining)
        """
        self._action = "submit"
        self.docstatus = 1

        # Check permission
        self.check_permission("submit")

        # Run before_submit
        self.run_method("before_submit")

        # Validate
        self.run_method("validate")

        # Save with new docstatus
        self._save()

        # Run on_submit
        self.run_method("on_submit")

        return self

    def cancel(self) -> "Document":
        """Cancel the document (transition docstatus from 1 to 2).

        Executes:
        1. before_cancel hook
        2. Set docstatus = 2
        3. Save
        4. on_cancel hook

        :return: self (for chaining)
        """
        self._action = "cancel"
        self.docstatus = 2

        # Check permission
        self.check_permission("cancel")

        # Run before_cancel
        self.run_method("before_cancel")

        # Save with new docstatus
        self._save()

        # Run on_cancel
        self.run_method("on_cancel")

        return self

    def delete(
        self,
        ignore_permissions: bool = False,
        *,
        force: bool = False,
        delete_permanently: bool = False,
    ) -> None:
        """Delete the document.

        :param ignore_permissions: Skip permission checks if True
        :param force: Force delete even if linked documents exist
        :param delete_permanently: Hard delete (skip trash)
        """
        from frappe.model.delete_doc import delete_doc as _delete_doc

        _delete_doc(
            self.doctype,
            self.name,
            force=force,
            ignore_permissions=ignore_permissions,
            delete_permanently=delete_permanently,
        )

    def reload(self) -> "Document":
        """Reload the document from database, discarding any unsaved changes.

        :return: self (for chaining)
        """
        # Clear current values (except core identity)
        self._values.clear()
        self._changed.clear()
        self._table_fields.clear()
        self._doc_before_save = None

        # Reload from DB
        return self.load_from_db()

    # ─── Database Operations ─────────────────────────────────────────────────

    def _sync_table_schema(self) -> None:
        """Sync database table schema with document fields before insert."""
        try:
            fields = []
            valid = self.get_valid_dict(ignore_nulls=True)
            for fieldname, val in valid.items():
                if val is None or fieldname in (
                    "doctype", "name", "creation", "modified", "modified_by", 
                    "owner", "docstatus", "idx", "parent", "parenttype", "parentfield",
                ):
                    continue
                fieldtype = "Data"
                if isinstance(val, bool):
                    fieldtype = "Check"
                elif isinstance(val, int):
                    fieldtype = "Int"
                elif isinstance(val, float):
                    fieldtype = "Float"
                elif isinstance(val, str) and len(val) > 255:
                    fieldtype = "Text"
                fields.append({"fieldname": fieldname, "fieldtype": fieldtype})
            if fields:
                frappe.db.sync_doctype_table(self.doctype, fields)
        except Exception as e:
            frappe.log(f"Schema sync warning: {e}")

    def _db_insert(self, ignore_if_duplicate: bool = False) -> None:
        """Insert this document into the database.

        Builds and executes an INSERT statement with all valid fields.

        :param ignore_if_duplicate: If True, don't raise on duplicate key
        """
        d = self.get_valid_dict()
        d["name"] = self.name

        # Remove parent/child table fields for non-child documents
        if not getattr(self, "parenttype", None):
            for pf in ("parent", "parenttype", "parentfield"):
                d.pop(pf, None)

        # Build INSERT statement
        fields = list(d.keys())
        placeholders = ["?"] * len(fields)
        values = [d[f] for f in fields]

        field_str = ", ".join(f"`{f}`" for f in fields)
        placeholder_str = ", ".join(placeholders)
        table = f"`tab{self.doctype}`"

        query = f"INSERT INTO {table} ({field_str}) VALUES ({placeholder_str})"

        try:
            frappe.db.sql(query, tuple(values))
        except Exception as e:
            error_msg = str(e).lower()
            # If missing column, try schema sync and retry
            if "no column named" in error_msg or "has no column" in error_msg:
                try:
                    self._sync_table_schema()
                    frappe.db.sql(query, tuple(values))
                    return
                except Exception:
                    pass
            if ignore_if_duplicate and "UNIQUE" in str(e).upper():
                logger.debug(f"Ignoring duplicate insert for {self.doctype}/{self.name}")
                return
            raise DuplicateEntryError(
                f"Failed to insert {self.doctype} '{self.name}': {e}"
            )

    def _db_update(self) -> None:
        """Update this document in the database.

        Builds and executes an UPDATE statement with all changed fields.
        """
        d = self.get_valid_dict()
        # Remove parent/child table fields for non-child documents
        if not getattr(self, "parenttype", None):
            for pf in ("parent", "parenttype", "parentfield"):
                d.pop(pf, None)
        set_fields = [f for f in d.keys() if f != "name"]
        if not set_fields:
            return

        set_clause = ", ".join(f"`{f}` = ?" for f in set_fields)
        values = [d[f] for f in set_fields] + [self.name]
        table = f"`tab{self.doctype}`"

        query = f"UPDATE {table} SET {set_clause} WHERE `name` = ?"
        frappe.db.sql(query, tuple(values))

    def _update_single(self, d: dict) -> None:
        """Update a single DocType's values in tabSingles.

        :param d: Dictionary of field values
        """
        for fieldname, value in d.items():
            if fieldname in ("name", "doctype", "creation", "modified", "owner", "modified_by"):
                continue

            # Check if record exists
            existing = frappe.db.sql(
                """
                SELECT `name` FROM `tabSingles`
                WHERE `doctype` = ? AND `field` = ?
                """,
                (self.doctype, fieldname),
            )

            if existing:
                frappe.db.sql(
                    """
                    UPDATE `tabSingles`
                    SET `value` = ?
                    WHERE `doctype` = ? AND `field` = ?
                    """,
                    (value, self.doctype, fieldname),
                )
            else:
                frappe.db.sql(
                    """
                    INSERT INTO `tabSingles` (`doctype`, `field`, `value`)
                    VALUES (?, ?, ?)
                    """,
                    (self.doctype, fieldname, value),
                )

    def _update_children(self) -> None:
        """Sync child table rows with the database.

        Compares current child rows with database rows and:
        - Inserts new rows
        - Updates existing rows
        - Deletes removed rows
        """
        meta = self.meta
        if not meta:
            return

        for table_field in meta.get_table_fields():
            fieldname = table_field.get("fieldname")
            child_doctype = table_field.get("options")

            if not fieldname or not child_doctype:
                continue

            current_children = self.get(fieldname) or []
            if not isinstance(current_children, list):
                continue

            # Get existing child names from DB
            try:
                existing = frappe.db.sql(
                    f"SELECT `name` FROM `tab{child_doctype}` "
                    "WHERE `parent` = ? AND `parenttype` = ? AND `parentfield` = ?",
                    (self.name, self.doctype, fieldname),
                    as_dict=True,
                )
                existing_names = {row["name"] for row in existing} if existing else set()
            except Exception:
                existing_names = set()

            # Process current children
            current_names = set()
            for child in current_children:
                if isinstance(child, Document):
                    child.parent = self.name
                    child.parenttype = self.doctype
                    child.parentfield = fieldname

                    if child.name and child.name in existing_names:
                        # Update existing
                        child._db_update()
                    else:
                        # Insert new
                        if not child.name:
                            child.name = self._generate_child_name(child_doctype)
                        child._db_insert()

                    if child.name:
                        current_names.add(child.name)
                elif isinstance(child, dict):
                    # Convert dict to Document and insert
                    child_doc = Document(child_doctype, **child)
                    child_doc.parent = self.name
                    child_doc.parenttype = self.doctype
                    child_doc.parentfield = fieldname
                    child_doc.name = self._generate_child_name(child_doctype)
                    child_doc._db_insert()
                    current_names.add(child_doc.name)

            # Delete removed children
            removed = existing_names - current_names
            for removed_name in removed:
                try:
                    frappe.db.delete(child_doctype, removed_name)
                except Exception as e:
                    logger.debug(f"Could not delete child {child_doctype}/{removed_name}: {e}")

    def _generate_child_name(self, child_doctype: str) -> str:
        """Generate a unique name for a child table row.

        :param child_doctype: Child DocType name
        :return: Unique name string
        """
        import hashlib
        import time

        hash_input = f"{child_doctype}:{self.name}:{time.time()}:{id(object())}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:10]

    # ─── Lifecycle Hooks ─────────────────────────────────────────────────────

    def run_method(self, method: str, *args, **kwargs) -> Any:
        """Run a method on this document if it exists.

        This is the primary mechanism for lifecycle hooks. It calls the
        method on the document if defined, otherwise returns None.

        :param method: Method name to run
        :param args: Positional arguments for the method
        :param kwargs: Keyword arguments for the method
        :return: Method return value or None
        """
        # Check for controller method
        fn = getattr(self, method, None)
        if fn and callable(fn):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                if method in ("validate", "before_save"):
                    # These methods can raise ValidationError
                    raise
                logger.warning(f"Method {method} failed on {self.doctype}/{self.name}: {e}")
                raise
        return None

    # ─── Default Hook Implementations ────────────────────────────────────────

    def autoname(self) -> None:
        """Generate the document name.

        Override in subclasses to implement custom naming logic.
        Called during insert() before the name is finalized.

        Example::

            def autoname(self):
                self.name = f"SO-{self.customer}-{self.transaction_date}"
        """
        pass

    def before_naming(self) -> None:
        """Called before the naming process begins.

        Use this to set fields that naming might depend on.
        """
        pass

    def before_insert(self) -> None:
        """Called before inserting a new document.

        Database transaction has not started yet.
        """
        pass

    def after_insert(self) -> None:
        """Called after a new document is inserted.

        Document is now in the database. Use for side effects
        like creating related documents.
        """
        pass

    def validate(self) -> None:
        """Validate the document before saving.

        Override to implement custom validation logic.
        Raise ValidationError if validation fails.

        Example::

            def validate(self):
                if self.delivery_date and self.delivery_date < self.transaction_date:
                    raise ValidationError("Delivery date cannot be before transaction date")
        """
        pass

    def before_save(self) -> None:
        """Called before saving (both insert and update)."""
        pass

    def before_validate(self) -> None:
        """Called before validation (both insert and update)."""
        pass

    def on_update(self) -> None:
        """Called after the document is updated in the database."""
        pass

    def on_submit(self) -> None:
        """Called after the document is submitted (docstatus = 1)."""
        pass

    def before_submit(self) -> None:
        """Called before the document is submitted."""
        pass

    def on_cancel(self) -> None:
        """Called after the document is cancelled (docstatus = 2)."""
        pass

    def before_cancel(self) -> None:
        """Called before the document is cancelled."""
        pass

    def on_delete(self) -> None:
        """Called after the document is deleted from the database."""
        pass

    def on_trash(self) -> None:
        """Alias for on_delete. Called after the document is deleted."""
        pass

    def on_change(self) -> None:
        """Called after any save operation (insert, update, submit, cancel).

        This is a good place for notifications and webhooks.
        """
        pass

    def before_delete(self) -> None:
        """Called before the document is deleted.

        Use this to clean up related resources.
        """
        pass

    def before_rename(self, old: str, new: str, merge: bool = False) -> None:
        """Called before the document is renamed.

        :param old: Current name
        :param new: New name
        :param merge: Whether this is a merge operation
        """
        pass

    def after_rename(self, old: str, new: str, merge: bool = False) -> None:
        """Called after the document is renamed.

        :param old: Old name
        :param new: New name
        :param merge: Whether this was a merge operation
        """
        pass

    def validate_update_after_submit(self) -> None:
        """Validate fields when updating a submitted document.

        Only certain fields should be editable after submit.
        Override to implement custom logic.
        """
        pass

    # ─── Change Tracking ─────────────────────────────────────────────────────

    def get_doc_before_save(self) -> Optional["Document"]:
        """Get the previous version of this document before the last save.

        :return: Previous Document version or None
        """
        return self._doc_before_save

    def load_doc_before_save(self) -> None:
        """Load the previous version from database for change tracking."""
        if self.name and not self._doc_before_save:
            try:
                self._doc_before_save = frappe.get_doc(self.doctype, self.name)
            except DoesNotExistError:
                self._doc_before_save = None

    def has_changed(self) -> bool:
        """Check if the document has unsaved changes.

        :return: True if any field has changed
        """
        return len(self._changed) > 0

    def get_changed(self) -> list[str]:
        """Get the list of changed field names.

        :return: List of fieldnames that have changed
        """
        return list(self._changed)

    def get_valid_dict(
        self,
        sanitize: bool = True,
        convert_dates_to_str: bool = False,
        ignore_nulls: bool = False,
        ignore_virtual: bool = False,
    ) -> dict:
        """Convert the document to a validated dictionary.

        This is the serialization format used for database operations.

        :param sanitize: Sanitize HTML content
        :param convert_dates_to_str: Convert date objects to strings
        :param ignore_nulls: Exclude None values
        :param ignore_virtual: Exclude virtual fields
        :return: Dictionary of field values
        """
        d = _dict()

        # Standard fields
        for field in ["name", "owner", "creation", "modified", "modified_by",
                       "docstatus", "idx", "parent", "parenttype", "parentfield"]:
            value = getattr(self, field, None)
            if value is not None or not ignore_nulls:
                d[field] = value

        # Dynamic fields
        for key, value in self._values.items():
            if key.startswith("_"):
                continue
            if value is None and ignore_nulls:
                continue
            if isinstance(value, list) and all(isinstance(i, Document) for i in value):
                # Child table - skip in parent dict
                continue

            # Sanitize
            if sanitize and isinstance(value, str):
                value = frappe.utils.sanitize_html(value)

            # Convert dates
            if convert_dates_to_str:
                if isinstance(value, (datetime.date, datetime.datetime)):
                    value = value.isoformat()

            d[key] = value

        return d

    # ─── Child Table Management ──────────────────────────────────────────────

    def append(self, key: str, value: Union[dict, "Document", None] = None) -> "Document":
        """Append a row to a child table.

        :param key: Child table fieldname
        :param value: Dict of field values, or a Document, or None for empty row
        :return: The appended child Document

        Example::

            doc.append("items", {
                "item_code": "ITEM-001",
                "qty": 5,
                "rate": 100.0,
            })
        """
        if value is None:
            value = {}

        # Get child DocType
        child_doctype = self._table_fields.get(key)
        if not child_doctype:
            # Try to get from meta
            meta = self.meta
            if meta:
                for tf in meta.get_table_fields():
                    if tf.get("fieldname") == key:
                        child_doctype = tf.get("options")
                        self._table_fields[key] = child_doctype
                        break

        if not child_doctype:
            raise ValueError(f"'{key}' is not a valid child table field for {self.doctype}")

        # Create child document
        if isinstance(value, Document):
            child = value
        elif isinstance(value, dict):
            child = Document(child_doctype, **value)
        else:
            raise ValueError(f"Cannot append {type(value)} to child table '{key}'")

        # Set parent references
        child.parent = self.name
        child.parenttype = self.doctype
        child.parentfield = key
        child.__islocal = True

        # Add to list
        if key not in self._values:
            self._values[key] = []
        self._values[key].append(child)

        # Mark as changed
        if key not in self._changed:
            self._changed.append(key)

        return child

    def extend(self, key: str, values: list[Union[dict, "Document"]]) -> list["Document"]:
        """Extend a child table with multiple rows.

        :param key: Child table fieldname
        :param values: List of dicts or Documents
        :return: List of appended child Documents
        """
        result = []
        for value in values:
            result.append(self.append(key, value))
        return result

    def remove(self, child: "Document") -> None:
        """Remove a child document from its parent table.

        :param child: Child Document to remove
        """
        parentfield = getattr(child, "parentfield", None)
        if not parentfield:
            raise ValueError("Child document does not have a parentfield")

        children = self._values.get(parentfield, [])
        if child in children:
            children.remove(child)
            if parentfield not in self._changed:
                self._changed.append(parentfield)

    def get_all_children(self) -> list["Document"]:
        """Get all child documents across all child tables.

        :return: List of child Documents
        """
        children = []
        meta = self.meta
        if not meta:
            return children

        for table_field in meta.get_table_fields():
            fieldname = table_field.get("fieldname")
            if fieldname and fieldname in self._values:
                table_children = self._values[fieldname]
                if isinstance(table_children, list):
                    children.extend(table_children)

        return children

    def init_child_tables(self) -> None:
        """Initialize empty child table lists based on meta.

        Called during __init__ to ensure child table attributes exist.
        """
        meta = self.meta
        if not meta:
            return

        for table_field in meta.get_table_fields():
            fieldname = table_field.get("fieldname")
            child_doctype = table_field.get("options")
            if fieldname and child_doctype:
                self._table_fields[fieldname] = child_doctype
                if fieldname not in self._values:
                    self._values[fieldname] = []

    def set_parent_in_children(self) -> None:
        """Set parent references on all child documents."""
        if not self.name:
            return

        for child in self.get_all_children():
            if hasattr(child, "parent"):
                child.parent = self.name
            if hasattr(child, "parenttype"):
                child.parenttype = self.doctype

    def _set_child_names(self) -> None:
        """Generate names for child table rows that don't have one."""
        for child in self.get_all_children():
            if not getattr(child, "name", None):
                child.name = self._generate_child_name(child.doctype)

    # ─── Validation ──────────────────────────────────────────────────────────

    def _validate(self) -> None:
        """Run validation: mandatory fields, links, data types."""
        if not self.flags.get("ignore_mandatory"):
            self._validate_mandatory()
        self._validate_links()
        self._validate_data_types()

    def _validate_mandatory(self) -> None:
        """Check that all mandatory fields have values.

        :raises MandatoryError: If a mandatory field is empty
        """
        meta = self.meta
        if not meta:
            return

        for field in meta.get_mandatory_fields():
            fieldname = field.get("fieldname")
            value = self.get(fieldname)

            # Check for empty value
            if value is None or value == "":
                label = field.get("label") or fieldname
                raise MandatoryError(f"{label} is mandatory for {self.doctype}")

    def _validate_links(self) -> None:
        """Validate that link fields reference existing documents.

        :raises LinkValidationError: If a link target doesn't exist
        """
        if self.flags.get("ignore_links"):
            return

        meta = self.meta
        if not meta:
            return

        for field in meta.get_link_fields():
            fieldname = field.get("fieldname")
            value = self.get(fieldname)

            if not value:
                continue

            options = field.get("options")
            if not options:
                continue

            # Check if referenced document exists
            try:
                exists = frappe.db.exists(options, value)
                if not exists:
                    raise frappe.exceptions.LinkValidationError(
                        f"{field.get('label') or fieldname}: "
                        f"{options} {value} does not exist"
                    )
            except frappe.exceptions.LinkValidationError:
                raise
            except Exception as e:
                # If we can't check, skip (table might not exist yet)
                logger.debug(f"Could not validate link {options}/{value}: {e}")

    def _validate_data_types(self) -> None:
        """Validate field values match their declared types."""
        meta = self.meta
        if not meta:
            return

        for field in meta.fields:
            fieldname = field.get("fieldname")
            fieldtype = field.get("fieldtype", "")
            value = self.get(fieldname)

            if value is None or value == "":
                continue

            try:
                if fieldtype == "Int":
                    cint(value)
                elif fieldtype in ("Float", "Currency", "Percent"):
                    flt(value)
                elif fieldtype == "Date":
                    if isinstance(value, str):
                        frappe.utils.getdate(value)
                elif fieldtype == "Datetime":
                    if isinstance(value, str):
                        frappe.utils.get_datetime(value)
                elif fieldtype == "Check":
                    # Should be 0 or 1
                    if value not in (0, 1, True, False):
                        cint(value)
            except (ValueError, TypeError):
                label = field.get("label") or fieldname
                raise ValidationError(
                    f"{label}: Invalid {fieldtype} value: {value}"
                )

    # ─── Permission ──────────────────────────────────────────────────────────

    def check_permission(self, permtype: str = "read", permlevel=None) -> None:
        """Raise PermissionError if the current user lacks the permission.

        :param permtype: Permission type (read, write, create, submit, cancel, delete)
        :param permlevel: Permission level (optional)
        :raises PermissionError: If permission is denied
        """
        if not self.has_permission(permtype):
            raise PermissionError(
                f"Not permitted to {permtype} {self.doctype}: {self.name}"
            )

    def has_permission(
        self,
        permtype: str = "read",
        *,
        debug: bool = False,
        user: Optional[str] = None,
    ) -> bool:
        """Check if user has permission for this document.

        :param permtype: Permission type
        :param debug: Print debug info
        :param user: User to check (defaults to current user)
        :return: True if permitted
        """
        if self.flags.get("ignore_permissions"):
            return True

        return frappe.permissions.has_permission(
            self.doctype, permtype, self, user=user, debug=debug
        )

    def check_if_locked(self) -> None:
        """Check if the document is locked by another process.

        :raises DocumentLockedError: If document is locked
        """
        # Document locking not implemented in this version
        pass

    def check_if_latest(self) -> None:
        """Check if the document has been modified by another user.

        Compares the current modified timestamp with the database.

        :raises TimestampMismatchError: If document is stale
        """
        if not self.name or self.get("__islocal"):
            return

        current_modified = frappe.db.get_value(
            self.doctype, self.name, "modified"
        )

        if current_modified and self.modified:
            if str(current_modified) != str(self.modified):
                raise TimestampMismatchError(
                    f"{self.doctype} {self.name} has been modified after you loaded it. "
                    f"Please reload and try again."
                )

    def validate_higher_perm_levels(self) -> None:
        """Validate fields at higher permission levels.

        Ensures users can only modify fields at their permission level.
        """
        # Simplified implementation - full version would check DocField permlevel
        pass

    # ─── Defaults & Timestamps ───────────────────────────────────────────────

    def _set_defaults(self) -> None:
        """Set default values for fields that are empty."""
        meta = self.meta
        if not meta:
            return

        for field in meta.fields:
            fieldname = field.get("fieldname")
            if not fieldname:
                continue

            value = self.get(fieldname)
            if value is None or value == "":
                default = field.get("default")
                if default is not None:
                    # Evaluate dynamic defaults
                    if isinstance(default, str):
                        if default == "__user":
                            default = getattr(frappe.session, "user", "Guest")
                        elif default == "Today":
                            default = frappe.utils.getdate_str()
                        elif default == "Now":
                            default = frappe.utils.now()
                    self.set(fieldname, default)

    def set_user_and_timestamp(self) -> None:
        """Set owner, creation, modified, and modified_by fields."""
        timestamp = now()
        user = getattr(frappe.session, "user", "Guest")

        if not self.owner:
            self.owner = user
        if not self.creation:
            self.creation = timestamp

        self.modified = timestamp
        self.modified_by = user

    def set_docstatus(self) -> None:
        """Ensure docstatus is an integer."""
        if self.docstatus is None:
            self.docstatus = 0
        else:
            self.docstatus = cint(self.docstatus)

    # ─── Serialization ───────────────────────────────────────────────────────

    def as_dict(
        self,
        no_nulls: bool = False,
        no_default_fields: bool = False,
        convert_dates_to_str: bool = False,
    ) -> _dict:
        """Convert the document to a dictionary.

        :param no_nulls: Exclude None values
        :param no_default_fields: Exclude standard fields
        :param convert_dates_to_str: Convert dates to strings
        :return: _dict representation
        """
        d = _dict()

        # Standard fields
        if not no_default_fields:
            for field in ["name", "owner", "creation", "modified", "modified_by",
                           "docstatus", "idx", "doctype", "parent", "parenttype", "parentfield"]:
                value = getattr(self, field, None)
                if value is not None or not no_nulls:
                    d[field] = value

        # Dynamic fields
        for key, value in self._values.items():
            if key.startswith("_"):
                continue
            if value is None and no_nulls:
                continue

            if isinstance(value, list) and all(isinstance(i, Document) for i in value):
                # Serialize child tables
                d[key] = [child.as_dict(no_nulls=no_nulls) for child in value]
            elif isinstance(value, Document):
                d[key] = value.as_dict(no_nulls=no_nulls)
            else:
                if convert_dates_to_str and isinstance(
                    value, (datetime.date, datetime.datetime)
                ):
                    value = value.isoformat()
                d[key] = value

        return d

    def to_json(self) -> str:
        """Convert the document to a JSON string.

        :return: JSON string
        """
        return frappe.utils.to_json(self.as_dict())

    def __iter__(self):
        """Iterate over field names and values."""
        d = self.as_dict()
        return iter(d.items())

    # ─── Field Access ────────────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """Get a field value.

        :param key: Field name
        :param default: Default value if field doesn't exist
        :return: Field value or default
        """
        # Check standard attributes
        if hasattr(self, key) and key not in ("_values", "flags", "meta"):
            value = getattr(self, key)
            if value is not None:
                return value

        # Check dynamic values
        return self._values.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a field value.

        :param key: Field name
        :param value: Value to set
        """
        # Track change
        old_value = self.get(key)
        if old_value != value:
            if key not in self._changed:
                self._changed.append(key)

        # Set on known attribute or in _values
        known_attrs = {
            "name", "owner", "creation", "modified", "modified_by",
            "docstatus", "idx", "parent", "parenttype", "parentfield",
        }
        if key in known_attrs:
            super().__setattr__(key, value)
        else:
            self._values[key] = value

    def get_title(self) -> str:
        """Get the title of this document.

        Uses the title_field from meta, or falls back to name.

        :return: Title string
        """
        meta = self.meta
        if meta:
            title_field = getattr(meta, "title_field", "name")
            if title_field and self.get(title_field):
                return str(self.get(title_field))
        return str(self.name or "")

    # ─── Internal Helpers ────────────────────────────────────────────────────

    def _set_from_dict(self, data: dict) -> None:
        """Set document attributes from a dictionary.

        :param data: Dictionary of field values
        """
        standard_fields = {
            "name", "owner", "creation", "modified", "modified_by",
            "docstatus", "idx", "parent", "parenttype", "parentfield",
        }

        for key, value in data.items():
            if key in ("doctype",):
                continue
            if key in standard_fields:
                setattr(self, key, value)
            else:
                self._values[key] = value

    @property
    def meta(self):
        """Get the Meta object for this document's DocType.

        :return: Meta instance
        """
        if self.doctype:
            return get_meta(self.doctype)
        return None

    def _reset_changed(self) -> None:
        """Reset the changed fields tracking."""
        self._changed = []
