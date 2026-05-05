from __future__ import annotations

import json
from typing import Any

import frappe
from frappe.types import _dict


def get_list_data(
    doctype: str,
    fields: list[str] | None = None,
    filters: dict[str, Any] | list[list] | None = None,
    order_by: str | None = None,
    start: int = 0,
    page_length: int = 20,
    with_comment_count: bool = False,
    group_by: str | None = None,
) -> dict[str, Any]:
    """Get list view data with metadata.

    Returns data in the format expected by DataTables/DataGrid:
    {keys: [field_names], values: [[row1_values], [row2_values]], ...}

    Args:
        doctype: DocType to query.
        fields: List of field names to retrieve.
        filters: Filters to apply (dict or list format).
        order_by: ORDER BY clause (e.g., 'modified desc').
        start: Offset for pagination.
        page_length: Number of rows per page.
        with_comment_count: Include comment count for each row.
        group_by: GROUP BY field.

    Returns:
        Dict with 'keys', 'values', 'columns', and metadata.
    """
    # Default fields if not specified
    if not fields:
        fields = ["name"]
        # Add common fields from meta
        try:
            meta = frappe.get_meta(doctype)
            std_fields = ["name", "owner", "creation", "modified", "modified_by", "docstatus"]
            for f in std_fields:
                fields.append(f)
        except Exception:
            fields = ["name", "owner", "creation", "modified"]

    # Build the query
    query_parts = _build_list_query(
        doctype=doctype,
        fields=fields,
        filters=filters,
        order_by=order_by,
        start=start,
        page_length=page_length,
        group_by=group_by,
    )

    # Execute query
    try:
        results = frappe.db.sql(
            query_parts.query,
            query_parts.params,
            as_dict=False,
        )
    except Exception as e:
        frappe.log_error(f"List query failed for {doctype}: {e}")
        return {
            "keys": fields,
            "values": [],
            "columns": _build_columns_meta(doctype, fields),
            "start": start,
            "page_length": page_length,
            "total_count": 0,
        }

    # Get total count for pagination
    total_count = get_count(doctype, filters=filters)

    # Build columns metadata
    columns_meta = _build_columns_meta(doctype, fields)

    return {
        "keys": fields,
        "values": results,
        "columns": columns_meta,
        "start": start,
        "page_length": page_length,
        "total_count": total_count,
    }


def get_count(
    doctype: str,
    filters: dict[str, Any] | list[list] | None = None,
) -> int:
    """Get count for list view pagination.

    Args:
        doctype: DocType to count.
        filters: Filters to apply.

    Returns:
        Total count of matching records.
    """
    conditions = ""
    params: list[Any] = []

    if filters:
        cond_result = get_filters_cond(doctype, filters, conditions)
        conditions = cond_result["conditions"]
        params = cond_result["params"]

    # Add user permission conditions
    match_cond = get_match_cond(doctype)
    if match_cond:
        conditions = f"{conditions} AND {match_cond}" if conditions else f"WHERE {match_cond}"

    query = f"SELECT COUNT(*) FROM `tab{doctype}` {conditions}"

    try:
        result = frappe.db.sql(query, params)
        return result[0][0] if result else 0
    except Exception:
        return 0


def get_sidebar_stats(
    doctype: str,
    filters: dict[str, Any] | list[list] | None = None,
) -> list[dict[str, Any]]:
    """Get sidebar filter statistics.

    Returns counts grouped by common filterable fields for the
    sidebar filter panel in list views.

    Args:
        doctype: DocType to analyze.
        filters: Base filters to apply.

    Returns:
        List of stat dicts with 'field', 'label', and 'stats'.
    """
    stats: list[dict] = []

    # Get filterable fields from meta
    try:
        meta = frappe.get_meta(doctype)
        filterable_fields = []

        for field in meta.fields if hasattr(meta, "fields") else []:
            if getattr(field, "in_list_filter", 0) or getattr(field, "fieldtype", "") in (
                "Select", "Link", "Data", "Check", "Status"
            ):
                filterable_fields.append(field)

        # Build base conditions
        base_conditions = ""
        base_params: list[Any] = []
        if filters:
            cond_result = get_filters_cond(doctype, filters, base_conditions)
            base_conditions = cond_result["conditions"]
            base_params = cond_result["params"]

        match_cond = get_match_cond(doctype)
        if match_cond:
            prefix = "AND" if base_conditions else "WHERE"
            base_conditions = f"{base_conditions} {prefix} {match_cond}" if base_conditions else f"WHERE {match_cond}"

        # Get stats for each filterable field
        for field in filterable_fields[:10]:  # Limit to top 10
            fieldname = getattr(field, "fieldname", "")
            label = getattr(field, "label", fieldname)
            fieldtype = getattr(field, "fieldtype", "")

            if fieldtype == "Select":
                options = getattr(field, "options", "").split("\n")
                field_stats = []
                for opt in options[:20]:  # Limit options
                    if not opt:
                        continue
                    where_clause = f"`{fieldname}` = ?"
                    params = base_params + [opt]
                    full_conditions = base_conditions
                    if full_conditions:
                        full_conditions += f" AND {where_clause}"
                    else:
                        full_conditions = f"WHERE {where_clause}"

                    count_result = frappe.db.sql(
                        f"SELECT COUNT(*) FROM `tab{doctype}` {full_conditions}",
                        params,
                    )
                    count_val = count_result[0][0] if count_result else 0
                    if count_val > 0:
                        field_stats.append({"label": opt, "value": opt, "count": count_val})

                if field_stats:
                    stats.append({
                        "field": fieldname,
                        "label": label,
                        "stats": field_stats,
                    })

            elif fieldtype in ("Link", "Data"):
                # Get top distinct values
                try:
                    distinct_values = frappe.db.sql(
                        f"""
                        SELECT `{fieldname}`, COUNT(*) as count
                        FROM `tab{doctype}`
                        {base_conditions}
                        GROUP BY `{fieldname}`
                        ORDER BY count DESC
                        LIMIT 20
                        """,
                        base_params,
                    )
                    if distinct_values:
                        field_stats = [
                            {"label": str(v[0]) if v[0] else "Not Set", "value": v[0] or "", "count": v[1]}
                            for v in distinct_values
                        ]
                        stats.append({
                            "field": fieldname,
                            "label": label,
                            "stats": field_stats,
                        })
                except Exception:
                    pass

    except Exception:
        pass

    return stats


def get_filters_cond(
    doctype: str,
    filters: dict[str, Any] | list[list] | None,
    conditions: str = "",
) -> dict[str, Any]:
    """Convert filters to SQL conditions.

    Supports dict format: {"status": "Open"}
    Supports list format: [["status", "=", "Open"], ["priority", "in", ["High", "Urgent"]]]

    Args:
        doctype: DocType (for validation).
        filters: Filters to convert.
        conditions: Existing conditions string to append to.

    Returns:
        Dict with 'conditions' (WHERE clause string) and 'params' (list).
    """
    params: list[Any] = []

    if not filters:
        return {"conditions": conditions, "params": params}

    conditions_list: list[str] = [conditions] if conditions else []

    if isinstance(filters, dict):
        for key, value in filters.items():
            if key == "name":
                conditions_list.append(f"`name` = ?")
                params.append(value)
            elif isinstance(value, (list, tuple)):
                # Operator included in value: [">", "2023-01-01"]
                op, operand = value[0], value[1]
                op_upper = str(op).upper()

                if op_upper == "IN" and isinstance(operand, (list, tuple)):
                    placeholders = ", ".join(["?"] * len(operand))
                    conditions_list.append(f"`{key}` IN ({placeholders})")
                    params.extend(operand)
                elif op_upper == "BETWEEN" and isinstance(operand, (list, tuple)) and len(operand) == 2:
                    conditions_list.append(f"`{key}` BETWEEN ? AND ?")
                    params.extend(operand)
                elif op_upper == "LIKE":
                    conditions_list.append(f"`{key}` LIKE ?")
                    params.append(f"%{operand}%")
                elif op_upper in ("NOT LIKE", "NOT IN", "NOT NULL", "IS NULL", "IS NOT NULL"):
                    if "NULL" in op_upper:
                        conditions_list.append(f"`{key}` {op_upper}")
                    else:
                        conditions_list.append(f"`{key}` {op_upper} ?")
                        params.append(operand)
                else:
                    conditions_list.append(f"`{key}` {op} ?")
                    params.append(operand)
            elif value is None:
                conditions_list.append(f"`{key}` IS NULL")
            else:
                conditions_list.append(f"`{key}` = ?")
                params.append(value)

    elif isinstance(filters, list):
        for f in filters:
            if isinstance(f, (list, tuple)) and len(f) >= 3:
                field, op, value = f[0], f[1], f[2]
                op_upper = str(op).upper()

                if op_upper == "IN" and isinstance(value, (list, tuple)):
                    placeholders = ", ".join(["?"] * len(value))
                    conditions_list.append(f"`{field}` IN ({placeholders})")
                    params.extend(value)
                elif op_upper == "BETWEEN" and isinstance(value, (list, tuple)) and len(value) == 2:
                    conditions_list.append(f"`{field}` BETWEEN ? AND ?")
                    params.extend(value)
                elif op_upper == "LIKE":
                    conditions_list.append(f"`{field}` LIKE ?")
                    params.append(f"%{value}%")
                elif op_upper in ("NOT IN", "NOT LIKE", "NOT NULL", "IS NULL", "IS NOT NULL"):
                    if "NULL" in op_upper:
                        conditions_list.append(f"`{field}` {op_upper}")
                    else:
                        conditions_list.append(f"`{field}` {op_upper} ?")
                        params.append(value)
                elif value is None:
                    conditions_list.append(f"`{field}` IS NULL")
                else:
                    conditions_list.append(f"`{field}` {op} ?")
                    params.append(value)
            elif isinstance(f, dict):
                # Nested dict filters
                inner_result = get_filters_cond(doctype, f, "")
                if inner_result["conditions"]:
                    conditions_list.append(inner_result["conditions"].replace("WHERE ", ""))
                    params.extend(inner_result["params"])

    # Combine conditions
    non_empty = [c for c in conditions_list if c.strip()]
    if non_empty:
        combined = " AND ".join(f"({c})" for c in non_empty)
        result_conditions = f"WHERE {combined}"
    else:
        result_conditions = ""

    return {"conditions": result_conditions, "params": params}


def get_match_cond(doctype: str, ignore_permissions: bool = False) -> str:
    """Get user permission match conditions.

    Builds SQL conditions based on the current user's permissions
    to restrict data visibility.

    Args:
        doctype: DocType to check permissions for.
        ignore_permissions: If True, return empty (no restrictions).

    Returns:
        SQL condition string (without WHERE/AND prefix).
    """
    user = frappe.session.user

    if ignore_permissions or user == "Administrator":
        return ""

    return build_match_conditions(doctype, user, ignore_permissions)


def build_match_conditions(
    doctype: str,
    user: str | None = None,
    ignore_permissions: bool = False,
) -> str:
    """Build match conditions from user permissions.

    Constructs SQL conditions based on User Permission records
    that apply to the current user.

    Args:
        doctype: DocType to check.
        user: User to build conditions for (defaults to current user).
        ignore_permissions: If True, return empty.

    Returns:
        SQL condition string (without WHERE/AND prefix).
    """
    if ignore_permissions:
        return ""

    if not user:
        user = frappe.session.user

    if user == "Administrator":
        return ""

    conditions: list[str] = []

    try:
        # Get user permissions
        user_permissions = frappe.db.get_all(
            "User Permission",
            filters={"user": user, "allow": doctype, "applicable_for": ("in", ["", doctype])},
            fields=["for_value", "is_default"],
        )

        if user_permissions:
            values = [up.for_value for up in user_permissions]
            if values:
                placeholders = ", ".join(["?"] * len(values))
                # Check both 'name' and owner field if applicable
                conditions.append(f"(`name` IN ({placeholders}) OR `owner` = ?)")

        # Check if user has role-based restrictions via DocPerm
        docperms = frappe.db.get_all(
            "DocPerm",
            filters={"parent": doctype},
            fields=["role", "if_owner"],
        )

        # Check if "if_owner" restriction applies
        owner_restricted = any(
            dp.if_owner
            for dp in docperms
            if dp.role in frappe.get_roles(user)
        )

        if owner_restricted:
            conditions.append(f"`owner` = ?")

    except Exception:
        pass

    if not conditions:
        return ""

    return " AND ".join(f"({c})" for c in conditions)


def get(doctype: str, name: str | None = None, filters: dict | None = None) -> dict[str, Any] | None:
    """Get a single document as a dict.

    Convenience method to fetch a document by name or filters.

    Args:
        doctype: DocType to query.
        name: Document name.
        filters: Alternative filter dict.

    Returns:
        Document dict, or None if not found.
    """
    if name:
        try:
            doc = frappe.get_doc(doctype, name)
            return doc.as_dict()
        except Exception:
            return None
    elif filters:
        try:
            results = frappe.db.get_all(
                doctype,
                filters=filters,
                limit=1,
            )
            if results:
                doc = frappe.get_doc(doctype, results[0].name)
                return doc.as_dict()
        except Exception:
            return None
    return None


def get_meta_fields(doctype: str) -> list[dict[str, Any]]:
    """Get metadata about fields for a DocType.

    Returns field metadata needed for list view column rendering
    and filter configuration.

    Args:
        doctype: DocType to get metadata for.

    Returns:
        List of field metadata dicts.
    """
    try:
        meta = frappe.get_meta(doctype)
        fields: list[dict] = []
        for field in meta.fields if hasattr(meta, "fields") else []:
            fields.append({
                "fieldname": getattr(field, "fieldname", ""),
                "fieldtype": getattr(field, "fieldtype", ""),
                "label": getattr(field, "label", ""),
                "options": getattr(field, "options", ""),
                "width": getattr(field, "width", ""),
                "reqd": getattr(field, "reqd", 0),
                "hidden": getattr(field, "hidden", 0),
                "read_only": getattr(field, "read_only", 0),
                "default": getattr(field, "default", None),
            })
        return fields
    except Exception:
        return []


# --- Internal helpers ---


def _build_list_query(
    doctype: str,
    fields: list[str],
    filters: dict[str, Any] | list[list] | None,
    order_by: str | None,
    start: int,
    page_length: int,
    group_by: str | None,
) -> _dict:
    """Build the SQL query parts for a list view query.

    Returns:
        _dict with 'query' (SQL string) and 'params' (list).
    """
    # Sanitize field names to prevent injection
    safe_fields = []
    for f in fields:
        # Handle function calls like COUNT(*), YEAR(creation)
        if "(" in f and ")" in f:
            safe_fields.append(f)
        elif f == "*":
            safe_fields.append("*")
        else:
            safe_fields.append(f"`{f}`")

    fields_str = ", ".join(safe_fields)

    # Build WHERE clause
    filter_result = get_filters_cond(doctype, filters, "")
    where_clause = filter_result["conditions"]
    params = list(filter_result["params"])

    # Add match conditions
    match_cond = get_match_cond(doctype)
    if match_cond:
        prefix = "AND" if where_clause else "WHERE"
        where_clause = f"{where_clause} {prefix} {match_cond}" if where_clause else f"WHERE {match_cond}"
        # Note: match_cond may contain params - for simplicity we append user
        params.append(frappe.session.user)

    # Build ORDER BY
    order_clause = ""
    if order_by:
        # Validate order_by to prevent injection
        order_parts = order_by.strip().split()
        if order_parts:
            order_field = order_parts[0]
            order_dir = order_parts[1].upper() if len(order_parts) > 1 else "ASC"
            if order_dir not in ("ASC", "DESC"):
                order_dir = "ASC"
            # Handle function-based ordering
            if "(" in order_field:
                order_clause = f"ORDER BY {order_field} {order_dir}"
            else:
                order_clause = f"ORDER BY `{order_field}` {order_dir}"
    else:
        order_clause = "ORDER BY `modified` DESC"

    # Build GROUP BY
    group_clause = ""
    if group_by:
        group_clause = f"GROUP BY `{group_by}`"

    # Build LIMIT
    limit_clause = f"LIMIT ? OFFSET ?"
    params.append(page_length)
    params.append(start)

    query = f"""
        SELECT {fields_str}
        FROM `tab{doctype}`
        {where_clause}
        {group_clause}
        {order_clause}
        {limit_clause}
    """

    return _dict(query=query, params=params)


def _build_columns_meta(doctype: str, fields: list[str]) -> list[dict[str, Any]]:
    """Build column metadata for DataTables.

    Args:
        doctype: DocType name.
        fields: Field names.

    Returns:
        List of column metadata dicts.
    """
    columns: list[dict] = []

    try:
        meta = frappe.get_meta(doctype)
        field_meta: dict[str, Any] = {}

        for f in meta.fields if hasattr(meta, "fields") else []:
            field_meta[getattr(f, "fieldname", "")] = f

        for fieldname in fields:
            if fieldname in field_meta:
                fm = field_meta[fieldname]
                columns.append({
                    "field": fieldname,
                    "label": getattr(fm, "label", fieldname),
                    "fieldtype": getattr(fm, "fieldtype", "Data"),
                    "options": getattr(fm, "options", ""),
                    "width": getattr(fm, "width", 120),
                    "align": _get_field_alignment(getattr(fm, "fieldtype", "Data")),
                })
            elif fieldname == "name":
                columns.append({
                    "field": "name",
                    "label": "ID",
                    "fieldtype": "Data",
                    "options": "",
                    "width": 150,
                    "align": "left",
                })
            else:
                columns.append({
                    "field": fieldname,
                    "label": fieldname.replace("_", " ").title(),
                    "fieldtype": "Data",
                    "options": "",
                    "width": 120,
                    "align": "left",
                })
    except Exception:
        # Fallback: basic column info
        for fieldname in fields:
            columns.append({
                "field": fieldname,
                "label": fieldname.replace("_", " ").title(),
                "fieldtype": "Data",
                "options": "",
                "width": 120,
                "align": "left",
            })

    return columns


def _get_field_alignment(fieldtype: str) -> str:
    """Determine column alignment based on field type."""
    right_aligned = {
        "Int", "Float", "Currency", "Percent", "Check",
        "Rating", "Auto Complete", "Barcode", "Duration",
    }
    center_aligned = {"Date", "Datetime", "Time", "Color"}

    if fieldtype in right_aligned:
        return "right"
    elif fieldtype in center_aligned:
        return "center"
    return "left"
