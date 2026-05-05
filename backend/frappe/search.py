from __future__ import annotations

import re
from typing import Any

import frappe
from frappe.types import _dict


def search_link(
    doctype: str,
    txt: str,
    filters: dict | list | None = None,
    page_start: int = 0,
    page_len: int = 20,
    columns: list[str] | None = None,
) -> list[dict]:
    """Search for links (used in Link fields).

    Performs a LIKE search on the DocType's name (and title field if available)
    returning matching results for Link field autocomplete.

    Args:
        doctype: Target DocType to search.
        txt: Search text entered by user.
        filters: Additional filters to apply.
        page_start: Offset for pagination.
        page_len: Number of results to return.
        columns: Additional columns to include in description.

    Returns:
        List of dicts with 'value' (name) and 'description' keys.
    """
    if not txt:
        txt = ""

    # Sanitize the search text to prevent injection
    txt = sanitise_dt(txt)

    # Build the search condition
    search_txt = f"%{txt}%"

    # Get title field for the doctype
    title_field = get_title_field(doctype)

    # Build fields to select
    select_fields = ["name"]
    if title_field and title_field != "name":
        select_fields.append(title_field)

    # Build the query conditions
    conditions = []
    params: list[Any] = []

    # Search on name and title field
    if title_field and title_field != "name":
        conditions.append(f"(`name` LIKE ? OR `{title_field}` LIKE ?)")
        params.extend([search_txt, search_txt])
    else:
        conditions.append("`name` LIKE ?")
        params.append(search_txt)

    # Apply additional filters
    filter_clause = ""
    if filters:
        if isinstance(filters, dict):
            for key, value in filters.items():
                conditions.append(f"`{key}` = ?")
                params.append(value)
        elif isinstance(filters, list):
            for f in filters:
                if isinstance(f, (list, tuple)) and len(f) >= 3:
                    field, op, value = f[0], f[1], f[2]
                    if op == "=":
                        conditions.append(f"`{field}` = ?")
                        params.append(value)
                    elif op.lower() == "like":
                        conditions.append(f"`{field}` LIKE ?")
                        params.append(f"%{value}%")
                    elif op.lower() == "in":
                        placeholders = ", ".join(["?"] * len(value))
                        conditions.append(f"`{field}` IN ({placeholders})")
                        params.extend(value)

    if conditions:
        filter_clause = "WHERE " + " AND ".join(conditions)

    # Build query
    fields_str = ", ".join([f"`{f}`" for f in select_fields])
    query = f"""
        SELECT {fields_str}
        FROM `tab{doctype}`
        {filter_clause}
        ORDER BY
            CASE WHEN `name` LIKE ? THEN 0 ELSE 1 END,
            CASE WHEN `name` = ? THEN 0 ELSE 1 END,
            `name`
        LIMIT ? OFFSET ?
    """
    params.extend([f"{txt}%", txt, page_len, page_start])

    results = frappe.db.sql(query, params, as_dict=True)

    # Format results
    out = []
    for r in results:
        value = r.name
        description_parts = []
        for f in select_fields:
            if r.get(f):
                description_parts.append(str(r[f]))
        description = " — ".join(description_parts) if len(description_parts) > 1 else value
        out.append({"value": value, "description": description})

    return out


def search_widget(
    doctype: str,
    txt: str,
    query: str | None = None,
    searchfield: str = "name",
    start: int = 0,
    page_len: int = 20,
    filters: dict | list | None = None,
    filter_fields: list[str] | None = None,
    as_dict: bool = False,
    reference_doctype: str | None = None,
) -> list:
    """Main search widget (Awesome Bar backend).

    Handles general search across DocTypes with support for custom queries,
    filters, and permission checks.

    Args:
        doctype: Target DocType to search.
        txt: Search text.
        query: Optional custom query path (e.g., 'frappe.core...').
        searchfield: Field to search on (default: 'name').
        start: Offset for pagination.
        page_len: Number of results to return.
        filters: Additional filters to apply.
        filter_fields: Fields to include in filter UI.
        as_dict: Return results as dicts instead of lists.
        reference_doctype: DocType for permission reference.

    Returns:
        List of search results, either as dicts or lists.
    """
    if not txt:
        txt = ""

    # Check permission on reference doctype if provided
    check_doctype = reference_doctype or doctype
    if not frappe.has_permission(check_doctype, "read"):
        return []

    # If a custom query is provided, try to execute it
    if query:
        try:
            # Parse query path like "frappe.controllers.queries.item_query"
            parts = query.split(".")
            module_path = ".".join(parts[:-1])
            function_name = parts[-1]
            module = frappe.get_module(module_path)
            query_fn = getattr(module, function_name)
            return query_fn(
                doctype=doctype,
                txt=txt,
                searchfield=searchfield,
                start=start,
                page_len=page_len,
                filters=filters,
                as_dict=as_dict,
            )
        except Exception:
            # Fall through to default search
            pass

    # Default search: search_link with filters
    results = search_link(
        doctype=doctype,
        txt=txt,
        filters=filters,
        page_start=start,
        page_len=page_len,
    )

    if as_dict:
        return results

    # Return as list of values for backward compatibility
    return [r["value"] for r in results]


def get_names_for_mentions(search_string: str) -> list[dict]:
    """Search users for @mentions.

    Searches active User documents matching the given string,
    returning users suitable for @mention autocomplete.

    Args:
        search_string: Partial username/fullname to search.

    Returns:
        List of dicts with 'id', 'value', and 'image' keys.
    """
    if not search_string or len(search_string) < 2:
        return []

    search_pattern = f"%{search_string}%"

    results = frappe.db.sql(
        """
        SELECT name, full_name, user_image
        FROM `tabUser`
        WHERE enabled = 1
            AND user_type = 'System User'
            AND name NOT IN ('Administrator', 'Guest')
            AND (name LIKE ? OR full_name LIKE ?)
        ORDER BY full_name
        LIMIT 10
        """,
        (search_pattern, search_pattern),
        as_dict=True,
    )

    out = []
    for r in results:
        out.append(
            {
                "id": r.name,
                "value": r.full_name or r.name,
                "image": r.user_image or "",
            }
        )

    return out


def get_user_groups() -> list[dict]:
    """Get user groups for @mentions.

    Returns all active User Groups for group mentions.

    Returns:
        List of dicts with 'id', 'value', and 'image' keys.
    """
    try:
        results = frappe.db.get_all(
            "User Group",
            filters={"enabled": 1},
            fields=["name"],
            order_by="name",
            limit=100,
        )
    except Exception:
        # User Group DocType may not exist
        return []

    out = []
    for r in results:
        out.append(
            {
                "id": r.name,
                "value": r.name,
                "image": "",
            }
        )

    return out


def build_for_autosuggest(results: list, doctype: str) -> list[dict]:
    """Format results for frontend autocomplete.

    Converts raw search results into a format suitable for
    the frontend autocomplete/AwesomeBar components.

    Args:
        results: Raw search results (list of names or dicts).
        doctype: The DocType being searched.

    Returns:
        List of dicts with label, value, and description.
    """
    out = []
    for r in results:
        if isinstance(r, dict):
            label = r.get("description") or r.get("value") or r.get("name", "")
            value = r.get("value") or r.get("name", "")
        else:
            label = str(r)
            value = str(r)

        out.append(
            {
                "label": label,
                "value": value,
                "description": f"{doctype}: {label}",
            }
        )

    return out


def sanitise_dt(search_dt: str) -> str:
    """Sanitize DocType name for search.

    Removes potentially dangerous characters to prevent SQL injection
    and other injection attacks.

    Args:
        search_dt: Raw DocType name or search string.

    Returns:
        Sanitized string safe for use in queries.
    """
    if not search_dt:
        return ""
    # Remove backticks, semicolons, and other SQL-sensitive characters
    cleaned = re.sub(r"[`;\"'\\]", "", search_dt)
    # Remove any SQL comment patterns
    cleaned = re.sub(r"(--|/\*|\*/)", "", cleaned)
    return cleaned.strip()


def get_title_field(doctype: str) -> str:
    """Get the title field for a DocType (defaults to 'name').

    Looks up the DocType's meta to find the configured title_field.

    Args:
        doctype: The DocType to look up.

    Returns:
        Name of the title field, or 'name' if not configured.
    """
    try:
        meta = frappe.get_meta(doctype)
        if meta and hasattr(meta, "title_field") and meta.title_field:
            return meta.title_field
    except Exception:
        pass
    return "name"


def get_std_fields_list(doctype: str, key_fields: list[str] | None = None) -> list[str]:
    """Get standard fields to include in search.

    Returns a list of common fields that should be included when
    displaying search results for a DocType.

    Args:
        doctype: The DocType to get fields for.
        key_fields: Additional key fields to include.

    Returns:
        List of field names.
    """
    std_fields = ["name"]

    # Add title field if different from name
    title = get_title_field(doctype)
    if title and title != "name":
        std_fields.append(title)

    # Add common metadata fields
    std_fields.extend([
        "owner",
        "creation",
        "modified",
        "modified_by",
        "docstatus",
    ])

    # Merge additional key fields
    if key_fields:
        for f in key_fields:
            if f not in std_fields:
                std_fields.append(f)

    return std_fields
