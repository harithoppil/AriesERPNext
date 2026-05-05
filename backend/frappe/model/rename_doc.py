"""
Frappe Document Rename Module

Handles renaming documents while maintaining referential integrity
by updating all Link fields across all doctypes that reference
the renamed document.

The rename process:
1. Validate the rename operation
2. Update the renamed document's name
3. Update all Link fields referencing the old name
4. Update user permissions
5. Run after_rename hook
6. Clear caches

Example:
    rename_doc("Customer", "CUST-001", "CUST-NEW-001")
    rename_doc("Item", "OLD-ITEM", "NEW-ITEM", merge=True)  # Merge two items
"""

from __future__ import annotations

import logging
from typing import Optional

import frappe
from frappe.exceptions import DoesNotExistError, NameError, PermissionError, ValidationError

logger = logging.getLogger("frappe.model.rename_doc")


def rename_doc(
    doctype: str,
    old: str,
    new: str,
    force: bool = False,
    merge: bool = False,
    ignore_if_exists: bool = False,
    show_alert: bool = True,
    rebuild_search: bool = True,
) -> str:
    """Rename a document and update all references.

    :param doctype: DocType of the document to rename
    :param old: Current name of the document
    :param new: New name for the document
    :param force: Force rename even if new name exists
    :param merge: Merge old document into existing new document
    :param ignore_if_exists: Don't raise error if new name already exists
    :param show_alert: Show an alert after renaming
    :param rebuild_search: Rebuild search index after rename
    :return: The new name

    :raises DoesNotExistError: If old document doesn't exist
    :raises NameError: If new name already exists and not merging
    :raises PermissionError: If user lacks permission
    """
    # Validate inputs
    if not old or not new:
        raise ValidationError("Both old and new names are required")

    old = str(old).strip()
    new = str(new).strip()

    if old == new:
        logger.debug(f"Rename: old and new are the same: {old}")
        return new

    # Check if old document exists
    if not frappe.db.exists(doctype, old):
        raise DoesNotExistError(f"{doctype} '{old}' does not exist", doctype=doctype)

    # Load old document
    old_doc = frappe.get_doc(doctype, old)

    # Check permissions
    if not old_doc.has_permission("write"):
        raise PermissionError(f"Not allowed to rename {doctype}: {old}")

    # Check if new name already exists
    new_exists = frappe.db.exists(doctype, new)

    if new_exists and not merge and not ignore_if_exists:
        raise NameError(
            f"{doctype} '{new}' already exists. Use merge=True to merge."
        )

    # Run before_rename hook
    old_doc.run_method("before_rename", old, new, merge)

    # If merging, delete the old document after transferring data
    is_merge = merge and new_exists

    # Get all link fields that reference this doctype
    link_fields = _get_link_fields(doctype)

    # Update the document name
    _update_document_name(doctype, old, new)

    # Update all references in link fields
    for ref_doctype, fieldname in link_fields:
        if ref_doctype == doctype:
            continue  # Skip self-references (handled above)
        try:
            _update_link_field(ref_doctype, fieldname, old, new)
        except Exception as e:
            logger.warning(
                f"Failed to update {ref_doctype}.{fieldname} from '{old}' to '{new}': {e}"
            )

    # Update dynamic link references
    _update_dynamic_links(doctype, old, new)

    # Update user permissions
    _update_user_permissions(doctype, old, new)

    # If merging, delete the old document
    if is_merge:
        try:
            frappe.delete_doc(doctype, old, force=True, ignore_on_trash=True)
        except Exception as e:
            logger.warning(f"Could not delete merged document {doctype}/{old}: {e}")

    # Clear caches
    frappe.clear_document_cache(doctype, old)
    frappe.clear_document_cache(doctype, new)

    # Reload and run after_rename hook
    try:
        new_doc = frappe.get_doc(doctype, new)
        new_doc.run_method("after_rename", old, new, merge)
    except Exception as e:
        logger.warning(f"after_rename hook failed for {doctype}/{new}: {e}")

    logger.info(f"Renamed {doctype}: '{old}' -> '{new}'")

    return new


def _get_link_fields(doctype: str) -> list[tuple[str, str]]:
    """Get all (DocType, fieldname) pairs that link to the given DocType.

    :param doctype: Target DocType
    :return: List of (link_doctype, link_fieldname) tuples
    """
    result = []

    try:
        link_fields = frappe.db.sql(
            """
            SELECT `parent` as doctype, `fieldname`
            FROM `tabDocField`
            WHERE `options` = ? AND `fieldtype` = 'Link'
            ORDER BY `parent`
            """,
            (doctype,),
            as_dict=True,
        )

        for lf in link_fields:
            result.append((lf["doctype"], lf["fieldname"]))

        # Also check Custom Field
        try:
            custom_fields = frappe.db.sql(
                """
                SELECT `dt` as doctype, `fieldname`
                FROM `tabCustom Field`
                WHERE `options` = ? AND `fieldtype` = 'Link'
                ORDER BY `dt`
                """,
                (doctype,),
                as_dict=True,
            )
            for cf in custom_fields:
                result.append((cf["doctype"], cf["fieldname"]))
        except Exception:
            pass  # Custom Field table might not exist

    except Exception as e:
        logger.debug(f"Could not get link fields for {doctype}: {e}")

    return result


def _update_document_name(doctype: str, old: str, new: str) -> None:
    """Update the primary name of a document.

    :param doctype: DocType
    :param old: Old name
    :param new: New name
    """
    table = f"`tab{doctype}`"
    frappe.db.sql(
        f"UPDATE {table} SET `name` = ? WHERE `name` = ?",
        (new, old),
    )
    logger.debug(f"Updated name in {doctype}: {old} -> {new}")


def _update_link_field(
    ref_doctype: str, fieldname: str, old_value: str, new_value: str
) -> int:
    """Update all rows in a DocType where a link field matches the old value.

    :param ref_doctype: DocType containing the link field
    :param fieldname: Name of the link field
    :param old_value: Old link value
    :param new_value: New link value
    :return: Number of rows updated
    """
    try:
        table = f"`tab{ref_doctype}`"

        # Get count first
        count_result = frappe.db.sql(
            f"SELECT COUNT(*) FROM {table} WHERE `{fieldname}` = ?",
            (old_value,),
        )
        count = count_result[0][0] if count_result else 0

        if count == 0:
            return 0

        # Update
        frappe.db.sql(
            f"UPDATE {table} SET `{fieldname}` = ? WHERE `{fieldname}` = ?",
            (new_value, old_value),
        )

        logger.debug(
            f"Updated {count} rows in {ref_doctype}.{fieldname}: {old_value} -> {new_value}"
        )
        return count

    except Exception as e:
        logger.debug(f"Could not update {ref_doctype}.{fieldname}: {e}")
        return 0


def _update_dynamic_links(doctype: str, old: str, new: str) -> None:
    """Update Dynamic Link references.

    Dynamic Links store the DocType and name in separate fields.

    :param doctype: DocType being renamed
    :param old: Old name
    :param new: New name
    """
    try:
        # Find all Dynamic Link fields
        dynamic_link_fields = frappe.db.sql(
            """
            SELECT `parent` as doctype, `fieldname`, `options`
            FROM `tabDocField`
            WHERE `fieldtype` = 'Dynamic Link'
            """,
            as_dict=True,
        )

        # Group by DocType to find the link field and parent field pairs
        for dlf in dynamic_link_fields:
            ref_doctype = dlf["doctype"]
            fieldname = dlf["fieldname"]  # e.g., "link_name"
            options_field = dlf["options"]  # e.g., "link_doctype"

            try:
                table = f"`tab{ref_doctype}`"
                frappe.db.sql(
                    f"""
                    UPDATE {table}
                    SET `{fieldname}` = ?
                    WHERE `{options_field}` = ? AND `{fieldname}` = ?
                    """,
                    (new, doctype, old),
                )
            except Exception as e:
                logger.debug(
                    f"Could not update dynamic link {ref_doctype}.{fieldname}: {e}"
                )

    except Exception as e:
        logger.debug(f"Could not update dynamic links for {doctype}: {e}")


def _update_user_permissions(doctype: str, old: str, new: str) -> None:
    """Update user permissions that reference the renamed document.

    :param doctype: DocType
    :param old: Old name
    :param new: New name
    """
    try:
        frappe.db.sql(
            """
            UPDATE `tabUser Permission`
            SET `for_value` = ?
            WHERE `allow` = ? AND `for_value` = ?
            """,
            (new, doctype, old),
        )
    except Exception as e:
        logger.debug(f"Could not update user permissions for {doctype}: {e}")


def rename_field(doctype: str, old_fieldname: str, new_fieldname: str) -> None:
    """Rename a field in a DocType (admin operation).

    :param doctype: DocType
    :param old_fieldname: Current field name
    :param new_fieldname: New field name
    """
    # Update DocField
    try:
        frappe.db.sql(
            """
            UPDATE `tabDocField`
            SET `fieldname` = ?
            WHERE `parent` = ? AND `fieldname` = ?
            """,
            (new_fieldname, doctype, old_fieldname),
        )
    except Exception as e:
        logger.error(f"Could not rename field in DocField: {e}")

    # Update Custom Field
    try:
        frappe.db.sql(
            """
            UPDATE `tabCustom Field`
            SET `fieldname` = ?
            WHERE `dt` = ? AND `fieldname` = ?
            """,
            (new_fieldname, doctype, old_fieldname),
        )
    except Exception:
        pass

    # Note: Renaming the actual table column requires ALTER TABLE
    # which is not implemented here for safety
    logger.info(
        f"Renamed field in {doctype}: '{old_fieldname}' -> '{new_fieldname}'"
    )
