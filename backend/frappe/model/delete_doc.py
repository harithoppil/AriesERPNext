"""
Frappe Document Deletion Module

Handles safe deletion of documents with proper lifecycle hooks,
cascade deletion of child tables, and link validation.

The deletion process:
1. Load the document
2. Check permissions
3. Run before_delete hook
4. Delete child table rows
5. Delete the document
6. Run on_delete (on_trash) hook
7. Update link counts

Example:
    delete_doc("Sales Order", "SO-00001")
    delete_doc("Sales Order", "SO-00001", force=True)  # Bypass restrictions
"""

from __future__ import annotations

import logging
from typing import Optional

import frappe
from frappe.exceptions import DoesNotExistError, PermissionError, ValidationError

logger = logging.getLogger("frappe.model.delete_doc")


def delete_doc(
    doctype: str,
    name: str,
    force: bool = False,
    ignore_doctypes: Optional[list] = None,
    for_reload: bool = False,
    ignore_permissions: bool = False,
    flags: Optional[dict] = None,
    ignore_on_trash: bool = False,
    ignore_missing: bool = True,
    delete_permanently: bool = False,
) -> None:
    """Delete a document and all its related data.

    :param doctype: DocType of the document to delete
    :param name: Name of the document to delete
    :param force: Delete even if linked documents exist
    :param ignore_doctypes: List of DocTypes to skip during link checking
    :param for_reload: Internal flag for document reload operations
    :param ignore_permissions: Skip permission checks
    :param flags: Additional flags to set on the document
    :param ignore_on_trash: Skip the on_trash lifecycle hook
    :param ignore_missing: Don't raise error if document doesn't exist
    :param delete_permanently: Hard delete (skip trash) - not implemented

    :raises DoesNotExistError: If document doesn't exist and ignore_missing is False
    :raises PermissionError: If user lacks delete permission
    """
    ignore_doctypes = ignore_doctypes or []

    # Load the document
    try:
        doc = frappe.get_doc(doctype, name)
    except DoesNotExistError:
        if ignore_missing:
            logger.debug(f"Document {doctype}/{name} not found, skipping deletion")
            return
        raise

    # Set flags if provided
    if flags:
        for key, value in flags.items():
            doc.flags[key] = value

    # Set force flag
    if force:
        doc.flags.force_delete = True

    # Check permissions
    if not ignore_permissions and not doc.has_permission("delete"):
        raise PermissionError(
            f"Not allowed to delete {doctype}: {name}"
        )

    # Check if document is locked (unless forced)
    if not force:
        doc.check_if_locked()

    # Run before_delete hook
    if not ignore_on_trash:
        doc.run_method("before_delete")

    # Check for linked documents (unless forced or ignore_doctypes)
    if not force:
        _check_linked_documents(doc, ignore_doctypes or [])

    # Delete child table rows
    _delete_child_tables(doc, ignore_doctypes)

    # Delete the document itself using direct SQL
    table = f"`tab{doc.doctype}`"
    frappe.db.sql(f"DELETE FROM {table} WHERE `name` = ?", (doc.name,))

    # Run on_delete/on_trash hook
    if not ignore_on_trash:
        doc.run_method("on_delete")
        doc.run_method("on_trash")

    # Update link counts
    _update_link_counts(doc)

    # Clear caches
    frappe.clear_document_cache(doctype, name)

    logger.info(f"Deleted {doctype}: {name}")


def _check_linked_documents(doc, ignore_doctypes: list) -> None:
    """Check if other documents link to this document.

    :param doc: Document being deleted
    :param ignore_doctypes: DocTypes to skip
    :raises ValidationError: If linked documents exist
    """
    meta = frappe.get_meta(doc.doctype)
    if not meta:
        return

    # Get link fields that reference this DocType
    link_fields = _get_link_fields(doc.doctype)

    for link_doctype, link_fieldname in link_fields:
        if link_doctype in ignore_doctypes:
            continue
        if link_doctype == doc.doctype:
            continue

        try:
            count = frappe.db.count(
                link_doctype,
                filters={link_fieldname: doc.name},
            )
            if count > 0:
                raise ValidationError(
                    f"Cannot delete {doc.doctype} '{doc.name}' because "
                    f"{count} {link_doctype}(s) are linked to it via {link_fieldname}"
                )
        except Exception as e:
            if isinstance(e, ValidationError):
                raise
            # Table might not exist, skip
            logger.debug(f"Could not check links in {link_doctype}: {e}")
            continue


def _get_link_fields(doctype: str) -> list[tuple[str, str]]:
    """Get all (DocType, fieldname) pairs that link to the given DocType.

    :param doctype: Target DocType
    :return: List of (link_doctype, link_fieldname) tuples
    """
    result = []

    try:
        # Query DocField for fields that link to this DocType
        link_fields = frappe.db.sql(
            """
            SELECT `parent`, `fieldname`
            FROM `tabDocField`
            WHERE `options` = ? AND `fieldtype` = 'Link'
            """,
            (doctype,),
            as_dict=True,
        )

        for lf in link_fields:
            result.append((lf["parent"], lf["fieldname"]))
    except Exception as e:
        logger.debug(f"Could not get link fields for {doctype}: {e}")

    return result


def _delete_child_tables(doc, ignore_doctypes: list) -> None:
    """Delete all child table rows for a document.

    :param doc: Parent document
    :param ignore_doctypes: Child DocTypes to skip
    """
    meta = frappe.get_meta(doc.doctype)
    if not meta:
        return

    for field in getattr(meta, "fields", []):
        if field.get("fieldtype") != "Table":
            continue

        child_doctype = field.get("options")
        if not child_doctype or child_doctype in ignore_doctypes:
            continue

        try:
            # Delete all child rows
            frappe.db.sql(
                f"DELETE FROM `tab{child_doctype}` "
                "WHERE `parent` = ? AND `parenttype` = ? AND `parentfield` = ?",
                (doc.name, doc.doctype, field.get("fieldname")),
            )
            logger.debug(
                f"Deleted child rows from {child_doctype} for {doc.doctype}/{doc.name}"
            )
        except Exception as e:
            logger.warning(f"Could not delete child table {child_doctype}: {e}")





def _update_link_counts(doc) -> None:
    """Update link count references after deletion.

    :param doc: Deleted document
    """
    # In a full implementation, this would update link count caches
    pass


def delete_all(
    doctype: str,
    filters: Optional[dict] = None,
    force: bool = False,
    ignore_permissions: bool = False,
) -> int:
    """Delete all documents matching filters.

    :param doctype: DocType to delete from
    :param filters: Filters to match documents
    :param force: Force delete
    :param ignore_permissions: Skip permission checks
    :return: Number of documents deleted
    """
    names = frappe.db.get_all(
        doctype,
        filters=filters or {},
        fields=["name"],
        limit_page_length=0,
    )

    count = 0
    for row in names:
        try:
            delete_doc(
                doctype,
                row["name"],
                force=force,
                ignore_permissions=ignore_permissions,
            )
            count += 1
        except Exception as e:
            logger.error(f"Failed to delete {doctype}/{row['name']}: {e}")

    return count


def bulk_delete(doctype: str, names: list, **kwargs) -> tuple[int, list[str]]:
    """Delete multiple documents efficiently.

    :param doctype: DocType
    :param names: List of document names to delete
    :param kwargs: Additional arguments passed to delete_doc
    :return: (number_deleted, list_of_failed_names)
    """
    deleted = 0
    failed = []

    for name in names:
        try:
            delete_doc(doctype, name, **kwargs)
            deleted += 1
        except Exception as e:
            logger.error(f"Failed to delete {doctype}/{name}: {e}")
            failed.append(name)

    return deleted, failed
