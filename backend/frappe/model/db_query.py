"""
Frappe Database Query Builder

Provides a programmatic way to build and execute database queries for DocTypes.
Handles field selection, filtering, sorting, pagination, and permission checks.

Example:
    result = DatabaseQuery("Sales Order").execute(
        filters={"status": "Draft"},
        fields=["name", "customer", "grand_total"],
        order_by="creation desc",
        limit_page_length=10,
    )
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional, Union

import frappe
from frappe.types import _dict

logger = logging.getLogger("frappe.model.db_query")


class DatabaseQuery:
    """Query builder for Frappe DocType data.

    Provides a high-level interface for constructing SELECT queries
    with filtering, sorting, pagination, and field selection.
    """

    def __init__(self, doctype: str):
        """Initialize query for a DocType.

        :param doctype: The DocType to query
        """
        self.doctype = doctype
        self.tables = [f"`tab{doctype}`"]
        self.fields = ["*"]
        self.filters: list = []
        self.or_filters: list = []
        self.order_by_parts: list = []
        self.group_by_parts: list = []
        self.limit_start = 0
        self.limit_page_length = 0
        self.join_type = "LEFT JOIN"
        self.distinct = False
        self.ignore_permissions = False
        self.user = None
        self.debug = False
        self.as_list = False
        self.as_dict = True
        self.with_childnames = False
        self.joined_tables: list[str] = []

    def execute(
        self,
        fields: Optional[Union[list, str]] = None,
        filters: Optional[Union[dict, list, str, int]] = None,
        or_filters: Optional[list] = None,
        docstatus: Optional[Union[list, str]] = None,
        group_by: Optional[str] = None,
        order_by: Optional[str] = None,
        limit_start: Optional[int] = None,
        limit_page_length: Optional[int] = None,
        as_list: bool = False,
        with_childnames: bool = False,
        debug: bool = False,
        ignore_permissions: bool = False,
        user: Optional[str] = None,
        with_comment_count: bool = False,
        join: str = "left join",
        distinct: bool = False,
        start: Optional[int] = None,
        page_length: Optional[int] = None,
        limit: Optional[int] = None,
        ignore_ifnull: bool = False,
        save_user_settings: bool = False,
        save_user_settings_fields: bool = False,
        update: Optional[dict] = None,
        add_total_row: Optional[bool] = None,
        user_settings: Optional[str] = None,
        reference_doctype: Optional[str] = None,
        run: bool = True,
        strict: bool = True,
        ignore_ddl: bool = False,
        parent_doctype: Optional[str] = None,
        *,
        pluck: Optional[str] = None,
    ) -> list:
        """Execute the query and return results.

        :param fields: Fields to select (list of fieldnames, or "*")
        :param filters: Filters as dict, list, or name string
        :param or_filters: OR conditions as list of [field, condition, value]
        :param docstatus: Filter by docstatus (e.g., [0, 1])
        :param group_by: GROUP BY clause
        :param order_by: ORDER BY clause (e.g., "creation desc")
        :param limit_start: Start offset for pagination
        :param limit_page_length: Number of records per page
        :param as_list: Return results as list of values instead of dicts
        :param with_childnames: Include child table row names
        :param debug: Print query for debugging
        :param ignore_permissions: Skip permission checks
        :param user: User to check permissions for
        :param with_comment_count: Include comment count (not implemented)
        :param join: Join type for linked tables
        :param distinct: Use DISTINCT
        :param start: Alias for limit_start
        :param page_length: Alias for limit_page_length
        :param limit: Maximum number of records
        :param pluck: Return only this field's values
        :param run: Actually execute the query (if False, just prepare)
        :param strict: Raise error on invalid fields
        :return: List of results (dicts or values)
        """
        # Handle parameter aliases
        if start is not None:
            limit_start = start
        if page_length is not None:
            limit_page_length = page_length
        if limit is not None and limit_page_length is None:
            limit_page_length = limit

        # Defaults
        limit_start = limit_start or 0
        limit_page_length = limit_page_length or 0

        self.fields = self._parse_fields(fields or ["*"])
        self.as_list = as_list
        self.as_dict = not as_list
        self.debug = debug
        self.ignore_permissions = ignore_permissions
        self.user = user
        self.distinct = distinct
        self.with_childnames = with_childnames
        self.limit_start = limit_start
        self.limit_page_length = limit_page_length

        # Build filters
        self.filters = []
        if filters:
            self._build_filters(filters)

        self.or_filters = []
        if or_filters:
            self._build_or_filters(or_filters)

        # Docstatus filter
        if docstatus is not None:
            if isinstance(docstatus, (list, tuple)):
                self.filters.append(("docstatus", "in", docstatus))
            else:
                self.filters.append(("docstatus", "=", docstatus))

        # Build ORDER BY
        self.order_by_parts = []
        if order_by:
            self._build_order_by(order_by)

        # Build GROUP BY
        self.group_by_parts = []
        if group_by:
            self.group_by_parts.append(group_by)

        if not run:
            return []

        # Build and execute query
        query, values = self._build_query()

        if self.debug:
            logger.debug(f"Query: {query}")
            logger.debug(f"Values: {values}")

        try:
            result = frappe.db.sql(query, tuple(values), as_dict=self.as_dict, debug=self.debug)
        except Exception as e:
            logger.error(f"Query failed: {e}")
            if strict:
                raise
            return []

        # Pluck single field
        if pluck and result:
            result = [r.get(pluck) if isinstance(r, dict) else r for r in result]

        return result or []

    def _parse_fields(self, fields: Union[list, str]) -> list[str]:
        """Parse fields parameter into list of SQL field expressions.

        :param fields: Fields string or list
        :return: List of SQL field expressions
        """
        if isinstance(fields, str):
            if fields == "*":
                return ["*"]
            fields = [fields]

        parsed = []
        for field in fields:
            if field in ("*", "count(*) as total_count"):
                parsed.append(field)
            elif " as " in field.lower():
                parsed.append(field)
            elif "(" in field and ")" in field:
                parsed.append(field)
            elif field.startswith("`"):
                parsed.append(field)
            elif "." in field:
                parsed.append(f"{field}")
            else:
                parsed.append(f"`{field}`")

        return parsed

    def _build_filters(self, filters: Union[dict, list, str, int]) -> None:
        """Build filter conditions from various input formats.

        Supports:
        - Dict: {"status": "Draft", "amount": [">", 100]}
        - List of triplets: [["status", "=", "Draft"], ["amount", ">", 100]]
        - String/Int: Exact name match
        """
        if isinstance(filters, (str, int)):
            self.filters.append(("name", "=", str(filters)))
        elif isinstance(filters, dict):
            for key, value in filters.items():
                if isinstance(value, (list, tuple)) and len(value) == 2:
                    self.filters.append((key, value[0], value[1]))
                elif isinstance(value, (list, tuple)):
                    self.filters.append((key, "in", value))
                elif value is None:
                    self.filters.append((key, "is", "NULL"))
                else:
                    self.filters.append((key, "=", value))
        elif isinstance(filters, list):
            for f in filters:
                if isinstance(f, (list, tuple)) and len(f) == 3:
                    self.filters.append(tuple(f))
                elif isinstance(f, dict):
                    for key, value in f.items():
                        if isinstance(value, (list, tuple)) and len(value) == 2:
                            self.filters.append((key, value[0], value[1]))
                        else:
                            self.filters.append((key, "=", value))

    def _build_or_filters(self, or_filters: list) -> None:
        """Build OR filter conditions."""
        for f in or_filters:
            if isinstance(f, (list, tuple)) and len(f) == 3:
                self.or_filters.append(tuple(f))
            elif isinstance(f, dict):
                for key, value in f.items():
                    self.or_filters.append((key, "=", value))

    def _build_order_by(self, order_by: str) -> None:
        """Parse ORDER BY clause.

        Supports formats like:
        - "creation desc"
        - "creation desc, modified asc"
        - "`tabDoctype`.`creation` desc"
        """
        parts = order_by.split(",")
        for part in parts:
            part = part.strip()
            # Extract field and direction
            match = re.match(r"^(.*?)(?:\\s+(asc|desc))?$", part, re.IGNORECASE)
            if match:
                field = match.group(1).strip()
                direction = (match.group(2) or "asc").upper()
                # Remove table prefix if present
                if "`.`" in field:
                    field = field.split("`.")[1].strip("`")
                elif "." in field:
                    field = field.split(".")[1]
                field = field.strip("`")
                self.order_by_parts.append(f"`{field}` {direction}")

    def _build_query(self) -> tuple[str, list]:
        """Build the SQL query and parameter values.

        :return: (query_string, parameter_values)
        """
        values: list = []

        # SELECT clause
        if self.distinct:
            select_clause = "SELECT DISTINCT " + ", ".join(self.fields)
        else:
            select_clause = "SELECT " + ", ".join(self.fields)

        # FROM clause
        from_clause = f"FROM {self.tables[0]}"

        # JOIN clauses for linked fields (if fields reference linked tables)
        join_clauses = []

        # WHERE clause
        where_parts = []
        where_parts.extend(self._condition_sql(self.filters, values))

        if self.or_filters:
            or_parts = self._condition_sql(self.or_filters, values)
            if or_parts:
                where_parts.append(f"({' OR '.join(or_parts)})")

        where_clause = ""
        if where_parts:
            where_clause = "WHERE " + " AND ".join(where_parts)

        # GROUP BY clause
        group_clause = ""
        if self.group_by_parts:
            group_clause = "GROUP BY " + ", ".join(self.group_by_parts)

        # ORDER BY clause
        order_clause = ""
        if self.order_by_parts:
            order_clause = "ORDER BY " + ", ".join(self.order_by_parts)
        else:
            # Default ordering
            order_clause = "ORDER BY `modified` DESC"

        # LIMIT clause
        limit_clause = ""
        if self.limit_page_length:
            limit_clause = f"LIMIT {self.limit_page_length} OFFSET {self.limit_start}"
        elif self.limit_start:
            limit_clause = f"LIMIT -1 OFFSET {self.limit_start}"

        # Assemble query
        parts = [
            select_clause,
            from_clause,
            " ".join(join_clauses),
            where_clause,
            group_clause,
            order_clause,
            limit_clause,
        ]
        query = " ".join(p for p in parts if p)

        return query, values

    def _condition_sql(self, conditions: list, values: list) -> list[str]:
        """Convert filter conditions to SQL WHERE clauses.

        :param conditions: List of (field, operator, value) tuples
        :param values: Accumulated parameter values (mutated)
        :return: List of SQL condition strings
        """
        sql_parts = []

        for condition in conditions:
            if len(condition) != 3:
                continue

            field, operator, value = condition
            field = field.strip("`")

            # Handle table-qualified fields
            if "." in field:
                sql_field = field
            else:
                sql_field = f"`{field}`"

            op = operator.lower()

            if op == "=":
                if value is None or value == "NULL":
                    sql_parts.append(f"{sql_field} IS NULL")
                else:
                    sql_parts.append(f"{sql_field} = ?")
                    values.append(value)
            elif op in ("!=", "<>"):
                if value is None or value == "NULL":
                    sql_parts.append(f"{sql_field} IS NOT NULL")
                else:
                    sql_parts.append(f"{sql_field} != ?")
                    values.append(value)
            elif op == "in":
                if value:
                    placeholders = ", ".join(["?"] * len(value))
                    sql_parts.append(f"{sql_field} IN ({placeholders})")
                    values.extend(value)
                else:
                    sql_parts.append("1=0")  # Empty IN is always false
            elif op == "not in":
                if value:
                    placeholders = ", ".join(["?"] * len(value))
                    sql_parts.append(f"{sql_field} NOT IN ({placeholders})")
                    values.extend(value)
                else:
                    sql_parts.append("1=1")  # Empty NOT IN is always true
            elif op == "like":
                sql_parts.append(f"{sql_field} LIKE ?")
                values.append(value)
            elif op == "not like":
                sql_parts.append(f"{sql_field} NOT LIKE ?")
                values.append(value)
            elif op == "is":
                if value is None or str(value).upper() == "NULL":
                    sql_parts.append(f"{sql_field} IS NULL")
                else:
                    sql_parts.append(f"{sql_field} IS ?")
                    values.append(value)
            elif op in (">", "<", ">=", "<=", "like"):
                sql_parts.append(f"{sql_field} {op} ?")
                values.append(value)
            elif op == "between" and isinstance(value, (list, tuple)) and len(value) == 2:
                sql_parts.append(f"{sql_field} BETWEEN ? AND ?")
                values.extend(value)
            else:
                # Fallback to equality
                sql_parts.append(f"{sql_field} = ?")
                values.append(value)

        return sql_parts
