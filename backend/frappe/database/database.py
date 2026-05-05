"""Base Database class - drop-in replacement for Frappe's Database.

This module implements the ~1620-line Database base class that ERPNext calls
into via frappe.db.*.  Subclasses (SQLiteDatabase) provide the dialect-specific
implementation of the abstract / overridable hooks.

Design decisions
----------------
- The base class contains all business logic: CRUD helpers, query builders,
  caching, defaults/globals, etc.
- Dialect-specific pieces (connection handling, parameter style, type
  conversion, SQL translation) live in subclasses.
- We use ``sqlite3`` (stdlib) for synchronous work and ``aiosqlite`` only
  where async is required by design (connection pool).
- All public method signatures match the original Frappe API exactly so
  existing ERPNext code requires zero changes.
"""
from __future__ import annotations

import functools
import hashlib
import json
import logging
import os
import re
import threading
import time
import traceback
import warnings
from collections import OrderedDict
from contextlib import contextmanager
from datetime import date, datetime, time as dt_time, timedelta
from typing import Any, Callable, Iterator, Sequence, overload

# ---------------------------------------------------------------------------
# Frappe internal imports  (these modules are part of the replacement tree)
# ---------------------------------------------------------------------------
from frappe.types import _dict
from frappe.exceptions import (
	DoesNotExistError,
	ValidationError,
	IntegrityError,
	DatabaseError,
	SQLError,
	OperationalError,
)

logger = logging.getLogger("frappe.database")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SINGLE_TYPES = ("Read Only", "Attach", "Attach Image", "HTML", "Table", "Table MultiSelect")

# Regex used to strip SQL_CALC_FOUND_ROWS / FOUND_ROWS() when translating
# MariaDB patterns to SQLite.
RE_SQL_CALC_FOUND_ROWS = re.compile(r"\bSQL_CALC_FOUND_ROWS\b", re.IGNORECASE)
RE_FOUND_ROWS = re.compile(r"SELECT\s+FOUND_ROWS\s*\(\s*\)", re.IGNORECASE)
RE_LIMIT_FOR_UPDATE = re.compile(r"\s+FOR\s+UPDATE\s*$", re.IGNORECASE)
RE_BACKTICK = re.compile(r"`")

# Regex to detect query type for log_touched_tables
RE_QUERY_TYPE = re.compile(
	 r"^\s*(SELECT|INSERT|UPDATE|DELETE|REPLACE|CREATE|ALTER|DROP|TRUNCATE)",
	 re.IGNORECASE,
)

# Pattern to match dict-style filters in fieldnames
RE_DICT_FILTER = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*):(.*)$")

# Compile a regex to extract table names from queries
RE_TAB_PREFIX = re.compile(r"\btab([A-Z][a-zA-Z0-9_ ]+)\b")
RE_FROM_TABLE = re.compile(r"\bFROM\s+`?(tab[A-Z][a-zA-Z0-9_ ]+)`?", re.IGNORECASE)
RE_INTO_TABLE = re.compile(r"\bINTO\s+`?(tab[A-Z][a-zA-Z0-9_ ]+)`?", re.IGNORECASE)
RE_UPDATE_TABLE = re.compile(r"\bUPDATE\s+`?(tab[A-Z][a-zA-Z0-9_ ]+)`?", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _QueryCache:
	"""Simple thread-safe LRU cache for get_value / exists calls."""

	def __init__(self, maxsize: int = 500):
		self._maxsize = maxsize
		self._cache: OrderedDict[str, Any] = OrderedDict()
		self._lock = threading.RLock()

	def _key(self, *parts) -> str:
		return hashlib.sha256(
			json.dumps(parts, sort_keys=True, default=str).encode()
		).hexdigest()

	def get(self, *parts):
		key = self._key(*parts)
		with self._lock:
			if key in self._cache:
				self._cache.move_to_end(key)
				return self._cache[key]
			return _UNSET

	def set(self, value, *parts):
		key = self._key(*parts)
		with self._lock:
			if key in self._cache:
				self._cache.move_to_end(key)
			else:
				if len(self._cache) >= self._maxsize:
					self._cache.popitem(last=False)
				self._cache[key] = value

	def clear(self):
		with self._lock:
			self._cache.clear()

	def invalidate_doctype(self, doctype: str):
		"""Remove all entries that mention *doctype*."""
		with self._lock:
			keys = [
				k for k, v in self._cache.items()
				if doctype.lower() in str(v).lower()
			]
			for k in keys:
				self._cache.pop(k, None)


_UNSET = object()


class Empty:
	"""Sentinel used internally to distinguish "no value" from None."""


_empty = Empty()


class LazyEncoder(json.JSONEncoder):
	"""JSON encoder that handles date/time objects."""

	def default(self, o: Any) -> Any:
		if isinstance(o, (datetime, date, dt_time)):
			return o.isoformat()
		if isinstance(o, timedelta):
			return str(o)
		if isinstance(o, set):
			return list(o)
		if isinstance(o, bytes):
			return o.decode("utf-8", errors="replace")
		return super().default(o)


def _to_serializable(value: Any) -> Any:
	"""Convert a Python value to something SQLite can store / compare."""
	if value is None:
		return None
	if isinstance(value, (bool, int, float, str)):
		return value
	if isinstance(value, (datetime, date, dt_time, timedelta)):
		return value.isoformat() if hasattr(value, "isoformat") else str(value)
	if isinstance(value, (list, dict, tuple, set)):
		return json.dumps(value, cls=LazyEncoder)
	return str(value)


def _cast_result(value: Any, target_type: str | None = None) -> Any:
	"""Cast a raw DB value back toward the original Python type."""
	if value is None:
		return None
	if target_type == "Check" and isinstance(value, (int, float)):
		return bool(value)
	if target_type == "Int" and isinstance(value, str):
		try:
			return int(value)
		except ValueError:
			return value
	if target_type == "Float" and isinstance(value, str):
		try:
			return float(value)
		except ValueError:
			return value
	if isinstance(value, str):
		# Try to detect JSON
		if value.startswith("[") or value.startswith("{"):
			try:
				return json.loads(value)
			except (json.JSONDecodeError, ValueError):
				pass
	return value


def _parse_date(value: Any) -> date | None:
	"""Parse a date string back into a date object."""
	if value is None:
		return None
	if isinstance(value, date) and not isinstance(value, datetime):
		return value
	if isinstance(value, datetime):
		return value.date()
	if isinstance(value, str):
		for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
			try:
				return datetime.strptime(value, fmt).date()
			except ValueError:
				continue
	return None


def _parse_datetime(value: Any) -> datetime | None:
	"""Parse a datetime string back into a datetime object."""
	if value is None:
		return None
	if isinstance(value, datetime):
		return value
	if isinstance(value, date) and not isinstance(value, datetime):
		return datetime(value.year, value.month, value.day)
	if isinstance(value, str):
		for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
			try:
				return datetime.strptime(value, fmt)
			except ValueError:
				continue
	return None


def _make_in_placeholder(values: Sequence) -> str:
	"""Build the correct parameter placeholder for IN clauses."""
	return ",".join("?" for _ in values)


def _scrub_table_name(doctype: str) -> str:
	"""Convert a DocType to the SQL table name (tabDoctype)."""
	if doctype.startswith("tab"):
		return doctype
	# Frappe convention: prefix with "tab"
	return f"tab{doctype}"


def _unscrub_table_name(table: str) -> str:
	"""Convert tabDoctype back to the DocType name."""
	if table.startswith("tab"):
		return table[3:]
	return table


def _parse_field_expression(fieldname: str | list | tuple) -> list[str]:
	"""Convert a fieldname argument into a list of column strings."""
	if isinstance(fieldname, str):
		return [f.strip() for f in fieldname.split(",") if f.strip()]
	return list(fieldname)


def _is_single_doctype(db: "Database", doctype: str) -> bool:
	"""Check whether *doctype* is a Single type (stored in tabSingles)."""
	try:
		result = db.sql(
			"SELECT issingle FROM `tabDocType` WHERE name=? LIMIT 1",
			(doctype,),
		)
		return bool(result and result[0][0])
	except Exception:
		return False


def _now() -> str:
	"""Current UTC datetime in Frappe format."""
	return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")


def _sql_escape(value: str, percent: bool = True) -> str:
	"""Escape a string for safe use in SQL LIKE / comparison."""
	s = str(value).replace("\\", "\\\\").replace("'", "\\'").replace("\"", '\\"')
	if percent:
		s = s.replace("%", "\\%").replace("_", "\\_")
	return s


# ---------------------------------------------------------------------------
# Database base class
# ---------------------------------------------------------------------------

class Database:
	# ================================================================
	# 1. Core connection
	# ================================================================

	def __init__(
		self,
		host: str | None,
		port: int | None,
		user: str | None,
		password: str | None,
		database: str | None,
		**kwargs,
	):
		self.host = host
		self.port = port
		self.user = user
		self.password = password
		self.database = database or ":memory:"
		self.kwargs = kwargs

		# Connection state (subclasses must override)
		self._conn: Any = None
		self._cursor: Any = None
		self._lock = threading.RLock()
		self._in_transaction: bool = False
		self._savepoints: list[str] = []
		self._read_only_mode: bool = False

		# Query cache
		self.query_cache = _QueryCache(maxsize=kwargs.get("cache_size", 500))

		# Touched tables tracking (for cache invalidation)
		self.touched_tables: set[str] = set()

		# Debug / profiling
		self._queries: list[dict] = []
		self._debug: bool = kwargs.get("debug", False)

		# Dialect info (filled by subclasses)
		self.dialect: str = "unknown"
		self.param_style: str = "?"

	def connect(self) -> None:
		"""Open the database connection.  Subclasses must implement."""
		raise NotImplementedError

	def close(self) -> None:
		"""Close the database connection and free resources."""
		with self._lock:
			try:
				if self._cursor:
					self._cursor.close()
					self._cursor = None
				if self._conn:
					self._conn.close()
					self._conn = None
			except Exception:
				logger.debug("Error closing DB connection", exc_info=True)
		self._in_transaction = False
		self._savepoints.clear()

	# ------------------------------------------------------------------
	# SQL execution
	# ------------------------------------------------------------------

	def sql(
		self,
		query: str,
		values: Sequence | dict | Any = (),
		as_dict: bool = False,
		as_list: bool = False,
		pluck: bool = False,
		debug: bool = False,
		ignore_ddl: bool = False,
		auto_commit: bool = True,
		update: dict | None = None,
		explain: bool = False,
		run: bool = True,
		page_length: int = 20,
		**kwargs,
	) -> list | tuple | None:
		"""Execute a SQL query and return the results.

		Parameters mirror the original Frappe ``sql()`` exactly.

		Returns
		-------
		list | tuple | None
			- *as_dict=True* → list of _dict rows.
			- *as_list=True* → list of list rows.
			- *pluck=True*   → list of single scalar values.
			- default        → list of tuple rows.
			- For INSERT/UPDATE/DELETE without RETURNING → None or lastrowid.
		"""
		# Translates query from MariaDB syntax to local dialect.
		translated = self._translate_query(query)
		if explain:
			translated = f"EXPLAIN QUERY PLAN {translated}"
		if debug or self._debug:
			self._log_query(translated, values)
		if not run:
			return self.mogrify(translated, values)

		try:
			cursor = self._execute(translated, values)
		except Exception as exc:
			self._handle_execution_error(exc, translated, ignore_ddl)
			return [] if ignore_ddl else None

		# Detect query type for touched-tables tracking
		self.log_touched_tables(translated, None)

		# Auto-commit for write operations (must happen before fetchall since INSERT/UPDATE/DELETE may not support it)
		# Skip auto-commit when inside an explicit transaction — caller will commit/rollback
		if auto_commit and not self._in_transaction:
			self.commit()

		# Fetch results
		if cursor is None:
			return None

		try:
			rows = cursor.fetchall()
		except Exception:
			# INSERT / UPDATE / DELETE / DDL may not support fetchall
			return None

		if not rows:
			return [] if (as_dict or as_list or pluck) else None

		# Build description if available
		description = getattr(cursor, "description", None) or []
		columns = [desc[0] for desc in description] if description else []

		return self._format_results(
			rows, columns, as_dict=as_dict, as_list=as_list,
			pluck=pluck, update=update,
		)

	# -- dialect hooks (subclass overrides) ------------------------

	def _translate_query(self, query: str) -> str:
		"""Translate MariaDB-specific syntax to the target dialect.

		Subclasses override this.  Base implementation performs the
		generic rewrites that are safe for every backend.
		"""
		# Strip SQL_CALC_FOUND_ROWS (MariaDB-only)
		query = RE_SQL_CALC_FOUND_ROWS.sub("", query)
		# Strip FOUND_ROWS() calls – we don't emulate them
		query = RE_FOUND_ROWS.sub("SELECT 0", query)
		# Strip FOR UPDATE (SQLite does not support it)
		query = RE_LIMIT_FOR_UPDATE.sub("", query)
		# Convert IFNULL → COALESCE (SQLite compatible)
		query = self._rewrite_ifnull(query)
		return query

	def _rewrite_ifnull(self, query: str) -> str:
		"""Replace IFNULL(...) with COALESCE(...)."""
		# Simple textual replacement; complex nested cases are handled
		# by the SQLite layer if needed.
		return re.sub(r"\bIFNULL\b", "COALESCE", query, flags=re.IGNORECASE)

	def _execute(self, query: str, values: Any):
		"""Run a query and return the cursor object.

		Subclasses must implement this.
		"""
		raise NotImplementedError

	def _handle_execution_error(self, exc: Exception, query: str, ignore_ddl: bool) -> None:
		"""Decide whether to swallow or re-raise *exc*."""
		if ignore_ddl and self._is_ddl_error(exc):
			logger.debug("Ignoring DDL error: %s", exc)
			return
		raise DatabaseError(f"{exc}\nQuery: {query}") from exc

	def _is_ddl_error(self, exc: Exception) -> bool:
		"""Return True if *exc* is a benign DDL failure (table exists, etc.)."""
		msg = str(exc).lower()
		return any(
			k in msg
			for k in (
				"already exists", "duplicate column", "unknown column",
				"does not exist", "can't drop",
			)
		)

	# -- result formatting ------------------------------------------

	def _format_results(
		self,
		rows: list,
		columns: list[str],
		*,
		as_dict: bool,
		as_list: bool,
		pluck: bool,
		update: dict | None,
	) -> list:
		"""Convert raw rows into the requested output shape."""
		if pluck:
			if not columns:
				return [r[0] for r in rows]
			col = columns[0]
			return [self._cast_row_value(r[0]) for r in rows]

		if as_dict:
			result = []
			for row in rows:
				d = _dict()
				for i, col in enumerate(columns):
					d[col] = self._cast_row_value(row[i])
				if update:
					d.update(update)
				result.append(d)
			return result

		if as_list:
			return [list(row) for row in rows]

		# Default: tuple rows
		return list(rows)

	def _cast_row_value(self, value: Any) -> Any:
		"""Cast a single DB cell value."""
		return _cast_result(value)

	# -- query logging ----------------------------------------------

	def _log_query(self, query: str, values: Any):
		"""Record a query for debugging."""
		entry = {
			"query": query,
			"values": values,
			"time": time.monotonic(),
			"stack": traceback.format_stack(limit=5),
		}
		self._queries.append(entry)
		logger.debug("SQL: %s | values: %s", query, values)

	# ================================================================
	# 2. CRUD operations
	# ================================================================

	def get(
		self,
		doctype: str,
		filters: dict | str | None = None,
		as_dict: bool = True,
		cache: bool = False,
	) -> _dict | None:
		"""Fetch a single document by filters.

		Equivalent to ``get_doc`` at the DB layer – returns the full row.
		"""
		if cache:
			cached = self.query_cache.get("get", doctype, filters, as_dict)
			if cached is not _UNSET:
				return cached

		if isinstance(filters, str):
			filters = {"name": filters}
		filters = filters or {}

		result = self.get_all(
			doctype,
			filters=filters,
			limit=1,
			as_dict=as_dict,
		)
		if result:
			value = result[0]
			if cache:
				self.query_cache.set(value, "get", doctype, filters, as_dict)
			return value
		return None

	# ------------------------------------------------------------------
	# get_value / get_values
	# ------------------------------------------------------------------

	def get_value(
		self,
		doctype: str,
		filters: Any = None,
		fieldname: str = "name",
		ignore: Any = None,
		as_dict: bool = False,
		debug: bool = False,
		order_by: str = "modified",
		for_update: bool = False,
		*,
		pluck: bool = False,
		distinct: bool = False,
		cache: bool = False,
	) -> Any:
		"""Return a single value (or dict) matching *filters*.

		This is one of the most heavily-called methods in ERPNext.
		"""
		if cache:
			cached = self.query_cache.get(
				"get_value", doctype, filters, fieldname, as_dict, order_by,
			)
			if cached is not _UNSET:
				return cached

		# Handle single doctypes
		if _is_single_doctype(self, doctype) or doctype in ("DocType",):
			if self._is_single(doctype):
				return self._get_value_single(
					doctype, filters, fieldname, as_dict, debug,
				)

		result = self.get_values(
			doctype,
			filters=filters,
			fieldname=fieldname,
			ignore=ignore,
			as_dict=as_dict,
			debug=debug,
			order_by=order_by,
			pluck=pluck,
			distinct=distinct,
			limit=1,
			cache=cache,
		)
		if not result:
			return None

		if pluck:
			value = result[0] if result else None
		elif as_dict:
			value = result[0] if result else None
		else:
			# result is a list of tuples; for a single fieldname return scalar
			value = result[0][0] if result else None

		if cache:
			self.query_cache.set(
				value, "get_value", doctype, filters, fieldname, as_dict, order_by,
			)
		return value

	def _get_value_single(
		self,
		doctype: str,
		filters: Any,
		fieldname: str,
		as_dict: bool,
		debug: bool,
	) -> Any:
		"""get_value helper for Single doctypes (stored in tabSingles)."""
		fields = _parse_field_expression(fieldname)
		result = self.get_values_from_single(
			fields, filters, doctype, as_dict=as_dict, debug=debug,
		)
		if not result:
			return _dict() if as_dict else None
		if as_dict:
			return result[0]
		# Return the value of the first requested field
		return result[0].get(fields[0]) if isinstance(result[0], dict) else result[0][0]

	def get_values(
		self,
		doctype: str,
		filters: Any = None,
		fieldname: str = "name",
		ignore: Any = None,
		as_dict: bool = True,
		debug: bool = False,
		order_by: str = "modified",
		update: dict | None = None,
		*,
		pluck: bool = False,
		distinct: bool = False,
		limit: int | None = None,
		cache: bool = False,
	) -> list | None:
		"""Return multiple values matching *filters*."""
		if cache and limit == 1:
			cached = self.query_cache.get(
				"get_values", doctype, filters, fieldname, as_dict, order_by,
			)
			if cached is not _UNSET:
				return cached

		if self._is_single(doctype):
			fields = _parse_field_expression(fieldname)
			return self.get_values_from_single(
				fields, filters, doctype, as_dict=as_dict, debug=debug,
				update=update, pluck=pluck, distinct=distinct,
			)

		table = _scrub_table_name(doctype)
		fields = _parse_field_expression(fieldname)
		field_sql = self._build_field_clause(fields, distinct)
		where_sql, where_vals = self._build_where_clause(filters, table)

		query = f"SELECT {field_sql} FROM `{table}` {where_sql}"
		if order_by:
			query += f" ORDER BY {order_by}"
		if limit is not None:
			query += f" LIMIT {int(limit)}"

		result = self.sql(
			query, tuple(where_vals),
			as_dict=as_dict, debug=debug, update=update,
			pluck=pluck,
		)
		if cache and limit == 1 and result is not None:
			self.query_cache.set(
				result, "get_values", doctype, filters, fieldname, as_dict, order_by,
			)
		return result if result is not None else []

	def _build_field_clause(self, fields: list[str], distinct: bool) -> str:
		"""Build the SELECT field list."""
		prefix = "DISTINCT " if distinct else ""
		if not fields:
			return prefix + "*"
		escaped = []
		for f in fields:
			f = f.strip()
			if f == "*":
				escaped.append("*")
			else:
				escaped.append(f"`{f.strip('`')}`")
		return prefix + ", ".join(escaped)

	def _build_where_clause(
		self,
		filters: Any,
		table: str,
	) -> tuple[str, list]:
		"""Build WHERE clause from filters dict/list.

		Returns (sql_fragment, values).
		"""
		if filters is None:
			return "", []
		if isinstance(filters, str):
			# Name-based filter
			return " WHERE `name` = ?", [filters]
		if isinstance(filters, (list, tuple)) and len(filters) == 3:
			# [field, operator, value] triplet
			field, operator, value = filters
			op_map = {
				"=": "=", "!=": "!=", "<>": "!=",
				">": ">", "<": "<", ">=": ">=", "<=": "<=",
				"like": "LIKE", "not like": "NOT LIKE",
				"in": "IN", "not in": "NOT IN",
				"is": "IS", "is not": "IS NOT",
				"between": "BETWEEN",
			}
			sql_op = op_map.get(operator.lower(), "=")
			if sql_op in ("IN", "NOT IN"):
				if not isinstance(value, (list, tuple)):
					value = [value]
				placeholders = _make_in_placeholder(value)
				return f" WHERE `{field}` {sql_op} ({placeholders})", list(value)
			if sql_op == "BETWEEN":
				return f" WHERE `{field}` BETWEEN ? AND ?", [value[0], value[1]]
			return f" WHERE `{field}` {sql_op} ?", [value]
		if isinstance(filters, dict):
			if not filters:
				return "", []
			clauses: list[str] = []
			values: list[Any] = []
			for key, val in filters.items():
				if val is None:
					clauses.append(f"`{key}` IS NULL")
				elif isinstance(val, (list, tuple)):
					placeholders = _make_in_placeholder(val)
					clauses.append(f"`{key}` IN ({placeholders})")
					values.extend(val)
				else:
					clauses.append(f"`{key}` = ?")
					values.append(val)
			return " WHERE " + " AND ".join(clauses), values
		# Fallback – raw SQL string (dangerous but Frappe allows it)
		return f" WHERE {filters}", []

	# -- single doctype helpers -------------------------------------

	def get_values_from_single(
		self,
		fields: list[str],
		filters: Any,
		doctype: str,
		as_dict: bool = False,
		debug: bool = False,
		update: dict | None = None,
		*,
		pluck: bool = False,
		distinct: bool = False,
		for_update: bool = False,
	) -> list:
		"""Read values from the tabSingles table for a Single doctype."""
		if not fields:
			fields = ["*"]
		# Singles are stored as (doctype, field, value) in tabSingles
		if len(fields) == 1 and fields[0] == "*":
			rows = self.sql(
				"SELECT field, value FROM `tabSingles` WHERE doctype=?",
				(doctype,),
				as_dict=False,
				debug=debug,
			)
			if as_dict:
				d = _dict()
				for row in rows or []:
					d[row[0]] = row[1]
				if update:
					d.update(update)
				return [d]
			return rows or []

		placeholders = ",".join("?" for _ in fields)
		rows = self.sql(
			f"SELECT field, value FROM `tabSingles` "
			f"WHERE doctype=? AND field IN ({placeholders})",
			(doctype, *fields),
			as_dict=False,
			debug=debug,
		)
		if as_dict:
			d = _dict()
			for row in rows or []:
				d[row[0]] = row[1]
			if update:
				d.update(update)
			return [d]
		return rows or []

	def get_singles_dict(
		self,
		doctype: str,
		debug: bool = False,
		*,
		for_update: bool = False,
		cast: bool = False,
	) -> _dict:
		"""Return all (field → value) pairs for a Single doctype."""
		rows = self.sql(
			"SELECT field, value FROM `tabSingles` WHERE doctype=?",
			(doctype,),
			as_dict=False,
			debug=debug,
		)
		result = _dict()
		for row in rows or []:
			value = row[1]
			if cast:
				value = _cast_result(value)
			result[row[0]] = value
		return result

	def set_single_value(
		self,
		doctype: str,
		field: str,
		value: Any,
		**kwargs,
	) -> None:
		"""Set a field value for a Single doctype."""
		debug = kwargs.get("debug", False)
		# Upsert: delete existing then insert
		self.sql(
			"DELETE FROM `tabSingles` WHERE doctype=? AND field=?",
			(doctype, field),
			debug=debug,
		)
		self.sql(
			"INSERT INTO `tabSingles` (doctype, field, value) VALUES (?, ?, ?)",
			(doctype, field, _to_serializable(value)),
			debug=debug,
		)
		self.query_cache.invalidate_doctype(doctype)

	def get_single_value(
		self,
		doctype: str,
		fieldname: str,
		cache: bool = False,
	) -> Any:
		"""Return a single value from a Single doctype."""
		if cache:
			cached = self.query_cache.get("single_value", doctype, fieldname)
			if cached is not _UNSET:
				return cached

		rows = self.sql(
			"SELECT value FROM `tabSingles` "
			"WHERE doctype=? AND field=? LIMIT 1",
			(doctype, fieldname),
			as_dict=False,
		)
		value = rows[0][0] if rows else None
		value = _cast_result(value)
		if cache:
			self.query_cache.set(value, "single_value", doctype, fieldname)
		return value

	def _is_single(self, doctype: str) -> bool:
		"""Fast check whether *doctype* is a Single type."""
		if not doctype or doctype.startswith("__"):
			return False
		try:
			result = self.sql(
				"SELECT issingle FROM `tabDocType` WHERE name=? LIMIT 1",
				(doctype,),
				as_dict=False,
			)
			return bool(result and result[0][0])
		except Exception:
			return False

	# -- set_value / bulk_update ------------------------------------

	def set_value(
		self,
		doctype: str,
		name: str | None,
		fieldname: str | dict,
		value: Any = None,
		**kwargs,
	) -> None:
		"""Update field(s) for document(s) matching *name*.

		*fieldname* can be a dict of {field: value} to update multiple fields
		at once.  If *name* is None or a dict, it is treated as a filter.
		"""
		debug = kwargs.get("debug", False)
		table = _scrub_table_name(doctype)

		if isinstance(fieldname, dict):
			updates = {k: _to_serializable(v) for k, v in fieldname.items()}
		else:
			if value is None and isinstance(name, dict):
				# set_value(doctype, filters, fieldname, value)
				pass
			updates = {fieldname: _to_serializable(value)}

		# Build SET clause
		set_clauses = []
		set_values = []
		for f, v in updates.items():
			set_clauses.append(f"`{f}` = ?")
			set_values.append(v)

		# Build WHERE
		if name is None:
			where_sql, where_vals = "", []
		elif isinstance(name, dict):
			where_sql, where_vals = self._build_where_clause(name, table)
		elif isinstance(name, (list, tuple)):
			placeholders = _make_in_placeholder(name)
			where_sql = f" WHERE `name` IN ({placeholders})"
			where_vals = list(name)
		else:
			where_sql = " WHERE `name` = ?"
			where_vals = [name]

		query = f"UPDATE `{table}` SET {', '.join(set_clauses)}{where_sql}"
		self.sql(query, tuple(set_values + where_vals), debug=debug)
		self.query_cache.invalidate_doctype(doctype)

	def bulk_update(
		self,
		doctype: str,
		docs: list[dict],
		field: str,
		**kwargs,
	) -> None:
		"""Update *field* for multiple documents efficiently."""
		debug = kwargs.get("debug", False)
		table = _scrub_table_name(doctype)
		for doc in docs:
			if "name" not in doc:
				continue
			self.sql(
				f"UPDATE `{table}` SET `{field}` = ? WHERE `name` = ?",
				(_to_serializable(doc[field]), doc["name"]),
				debug=debug,
			)
		self.query_cache.invalidate_doctype(doctype)

	# ================================================================
	# 3. Query builders
	# ================================================================

	def get_all(
		self,
		*args,
		**kwargs,
	) -> list:
		"""Fetch all documents (bypasses user permissions)."""
		return self._get_list_impl(*args, **kwargs)

	def get_list(
		self,
		*args,
		**kwargs,
	) -> list:
		"""Fetch documents (respects user permissions – noop in base layer)."""
		return self._get_list_impl(*args, **kwargs)

	def _get_list_impl(
		self,
		doctype: str,
		fields: list[str] | str = None,
		filters: Any = None,
		or_filters: list[dict] | None = None,
		docstatus: list[int] | None = None,
		group_by: str | None = None,
		order_by: str = "modified DESC",
		limit_start: int = 0,
		limit_page_length: int | None = None,
		as_list: bool = False,
		as_dict: bool = True,
		debug: bool = False,
		ignore_permissions: bool = True,
		user: str | None = None,
		with_comment_count: bool = False,
		join: str | None = None,
		left_join: str | None = None,
		join_on: str | None = None,
		distinct: bool = False,
		cache: bool = False,
		page_length: int | None = None,
		limit: int | None = None,
		start: int | None = None,
		**extra,
	) -> list:
		"""Internal implementation for get_list / get_all."""
		# Resolve limit aliases
		if page_length is not None:
			limit_page_length = page_length
		if limit is not None:
			limit_page_length = limit
		if start is not None:
			limit_start = start
		if limit_page_length is None:
			limit_page_length = 20

		if cache:
			cached = self.query_cache.get(
				"get_list", doctype, fields, filters, order_by,
				limit_start, limit_page_length,
			)
			if cached is not _UNSET:
				return cached

		table = _scrub_table_name(doctype)
		if isinstance(fields, str):
			fields = [fields]
		if not fields:
			fields = ["*"]

		field_sql = self._build_field_clause(fields, distinct)
		where_sql, where_vals = self._build_where_clause(filters, table)

		# Or-filters
		or_sql, or_vals = "", []
		if or_filters:
			parts = []
			for d in or_filters:
				for k, v in d.items():
					if v is None:
						parts.append(f"`{k}` IS NULL")
					elif isinstance(v, (list, tuple)):
						ph = _make_in_placeholder(v)
						parts.append(f"`{k}` IN ({ph})")
						or_vals.extend(v)
					else:
						parts.append(f"`{k}` = ?")
						or_vals.append(v)
			if parts:
				or_fragment = " OR ".join(parts)
				if where_sql:
					where_sql += f" AND ({or_fragment})"
					where_vals.extend(or_vals)
				else:
					where_sql = f" WHERE ({or_fragment})"
					where_vals = or_vals

		# Docstatus filter
		if docstatus is not None:
			ph = _make_in_placeholder(docstatus)
			ds_filter = f"`docstatus` IN ({ph})"
			if where_sql:
				where_sql += f" AND {ds_filter}"
				where_vals.extend(docstatus)
			else:
				where_sql = f" WHERE {ds_filter}"
				where_vals = list(docstatus)

		query = f"SELECT {field_sql} FROM `{table}` {where_sql}"
		if group_by:
			query += f" GROUP BY {group_by}"
		if order_by:
			query += f" ORDER BY {order_by}"
		if limit_page_length:
			query += f" LIMIT {int(limit_page_length)} OFFSET {int(limit_start)}"

		result = self.sql(
			query, tuple(where_vals),
			as_dict=as_dict, as_list=as_list, debug=debug,
		)
		if cache:
			self.query_cache.set(
				result, "get_list", doctype, fields, filters, order_by,
				limit_start, limit_page_length,
			)
		return result if result is not None else []

	# ------------------------------------------------------------------
	# exists / count / delete / truncate
	# ------------------------------------------------------------------

	def exists(
		self,
		dt: str,
		dn: str | None = None,
		cache: bool = False,
		*,
		debug: bool = False,
	) -> str | None:
		"""Return the document name if a document exists, else None."""
		# Normalize arguments: exists(doctype, name) or exists(dict)
		if isinstance(dt, dict):
			doctype = dt.get("doctype")
			dn = dt.get("name")
		else:
			doctype = dt

		if cache:
			cached = self.query_cache.get("exists", doctype, dn)
			if cached is not _UNSET:
				return cached

		if not doctype:
			return None

		table = _scrub_table_name(doctype)
		if dn is not None:
			rows = self.sql(
				f"SELECT `name` FROM `{table}` WHERE `name` = ? LIMIT 1",
				(dn,),
				as_dict=False,
				debug=debug,
			)
		else:
			# Just check if any row exists
			rows = self.sql(
				f"SELECT `name` FROM `{table}` LIMIT 1",
				as_dict=False,
				debug=debug,
			)
		value = (rows[0][0] if rows else None)
		if cache:
			self.query_cache.set(value, "exists", doctype, dn)
		return value

	def count(
		self,
		dt: str,
		filters: Any = None,
		debug: bool = False,
		cache: bool = False,
		distinct: bool = True,
	) -> int:
		"""Return the number of documents matching *filters*."""
		if cache:
			cached = self.query_cache.get("count", dt, filters)
			if cached is not _UNSET:
				return cached

		table = _scrub_table_name(dt)
		where_sql, where_vals = self._build_where_clause(filters, table)
		query = f"SELECT COUNT(*) FROM `{table}`{where_sql}"
		rows = self.sql(query, tuple(where_vals), as_dict=False, debug=debug)
		result = rows[0][0] if rows else 0
		if cache:
			self.query_cache.set(result, "count", dt, filters)
		return int(result) if result else 0

	def delete(
		self,
		doctype: str,
		filters: Any = None,
		debug: bool = False,
		**kwargs,
	) -> None:
		"""Delete document(s) matching *filters*."""
		table = _scrub_table_name(doctype)
		if filters is None:
			# Delete all – dangerous, but matches Frappe API
			self.sql(f"DELETE FROM `{table}`", debug=debug)
		else:
			where_sql, where_vals = self._build_where_clause(filters, table)
			self.sql(
				f"DELETE FROM `{table}`{where_sql}",
				tuple(where_vals),
				debug=debug,
			)
		self.query_cache.invalidate_doctype(doctype)

	def truncate(self, doctype: str) -> None:
		"""Remove all rows from a table (DDL)."""
		table = _scrub_table_name(doctype)
		self.sql_ddl(f"DELETE FROM `{table}`")
		# Also reset the SQLite sequence if it exists
		try:
			self.sql_ddl(f"DELETE FROM sqlite_sequence WHERE name='{table}'")
		except Exception:
			pass
		self.query_cache.invalidate_doctype(doctype)

	# ================================================================
	# 4. Schema introspection
	# ================================================================

	def table_exists(self, doctype: str, cached: bool = True) -> bool:
		"""Return True if the table for *doctype* exists."""
		table = _scrub_table_name(doctype)
		if cached:
			cached_tables = getattr(self, "_cached_tables", None)
			if cached_tables is not None:
				return table in cached_tables
		rows = self.sql(
			"SELECT name FROM sqlite_master WHERE type='table' AND name=?",
			(table,),
			as_dict=False,
		)
		return bool(rows)

	def field_exists(self, dt: str, fn: str) -> bool:
		"""Return True if field *fn* exists in doctype *dt*."""
		return fn in self.get_table_columns(dt)

	def has_table(self, doctype: str) -> bool:
		"""Alias for table_exists."""
		return self.table_exists(doctype, cached=False)

	def get_tables(self, cached: bool = True) -> list:
		"""Return a list of all tab* tables in the database."""
		if cached:
			cached_tables = getattr(self, "_cached_tables", None)
			if cached_tables is not None:
				return list(cached_tables)
		rows = self.sql(
			"SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'tab%'",
			as_dict=False,
		)
		tables = [r[0] for r in (rows or [])]
		self._cached_tables = set(tables)
		return tables

	def a_row_exists(self, doctype: str) -> bool:
		"""Return True if at least one row exists in the table."""
		table = _scrub_table_name(doctype)
		try:
			rows = self.sql(
				f"SELECT 1 FROM `{table}` LIMIT 1",
				as_dict=False,
			)
			return bool(rows)
		except Exception:
			return False

	def get_db_table_columns(self, table: str) -> list[str]:
		"""Return column names for a raw SQL table name."""
		try:
			rows = self.sql(
				f"PRAGMA table_info(`{table}`)",
				as_dict=False,
			)
			return [r[1] for r in (rows or [])]
		except Exception:
			return []

	def get_table_columns(self, doctype: str) -> list[str]:
		"""Return column names for a DocType table."""
		table = _scrub_table_name(doctype)
		return self.get_db_table_columns(table)

	def has_column(self, doctype: str, column: str) -> bool:
		"""Return True if *column* exists in *doctype*."""
		return column in self.get_table_columns(doctype)

	def has_index(self, table_name: str, index_name: str) -> bool:
		"""Return True if the named index exists on the table."""
		try:
			rows = self.sql(
				f"PRAGMA index_list(`{table_name}`)",
				as_dict=False,
			)
			names = [r[1] for r in (rows or [])]
			return index_name in names
		except Exception:
			return False

	def add_index(
		self,
		doctype: str,
		fields: list[str],
		index_name: str | None = None,
	) -> None:
		"""Create a non-unique index on *fields*."""
		table = _scrub_table_name(doctype)
		if not index_name:
			index_name = f"{table}_{'_'.join(fields)}_index"
		field_sql = ", ".join(f"`{f}`" for f in fields)
		self.sql_ddl(
			f"CREATE INDEX IF NOT EXISTS `{index_name}` ON `{table}` ({field_sql})"
		)

	def add_unique(
		self,
		doctype: str,
		fields: list[str],
		constraint_name: str | None = None,
	) -> None:
		"""Add a UNIQUE constraint on *fields*."""
		table = _scrub_table_name(doctype)
		if not constraint_name:
			constraint_name = f"{table}_{'_'.join(fields)}_unique"
		field_sql = ", ".join(f"`{f}`" for f in fields)
		self.sql_ddl(
			f"CREATE UNIQUE INDEX IF NOT EXISTS `{constraint_name}` "
			f"ON `{table}` ({field_sql})"
		)

	# ================================================================
	# 5. Defaults / globals
	# ================================================================

	def set_global(self, key: str, val: str | None, user: str = "__global") -> None:
		"""Set a global default value (stored in tabDefaultValue)."""
		self.delete(
			"DefaultValue",
			{"defkey": key, "parent": user},
		)
		if val is not None:
			self.sql(
				"""INSERT INTO `tabDefaultValue`
				(name, defkey, defvalue, parent, parenttype, parentfield)
				VALUES (?, ?, ?, ?, 'User Default', 'system_defaults')""",
				(f"{user}-{key}", key, str(val), user),
			)

	def get_global(self, key: str, user: str = "__global") -> str | None:
		"""Get a global default value."""
		rows = self.sql(
			"SELECT defvalue FROM `tabDefaultValue` "
			"WHERE defkey=? AND parent=? LIMIT 1",
			(key, user),
			as_dict=False,
		)
		return rows[0][0] if rows else None

	def get_default(self, key: str, parent: str = "__default") -> Any:
		"""Get a default value for *key*."""
		rows = self.sql(
			"SELECT defvalue FROM `tabDefaultValue` "
			"WHERE defkey=? AND parent=? LIMIT 1",
			(key, parent),
			as_dict=False,
		)
		return _cast_result(rows[0][0]) if rows else None

	def set_default(
		self,
		key: str,
		val: Any,
		parent: str = "__default",
		parenttype: str | None = None,
	) -> None:
		"""Set (overwrite) a default value."""
		self.sql(
			"DELETE FROM `tabDefaultValue` WHERE defkey=? AND parent=?",
			(key, parent),
		)
		self.add_default(key, val, parent, parenttype)

	def add_default(
		self,
		key: str,
		val: Any,
		parent: str = "__default",
		parenttype: str | None = None,
	) -> None:
		"""Add a default value (does not delete existing)."""
		parenttype = parenttype or "__default"
		import uuid
		self.sql(
			"""INSERT INTO `tabDefaultValue`
			(name, defkey, defvalue, parent, parenttype)
			VALUES (?, ?, ?, ?, ?)""",
			(f"{parent}-{key}-{uuid.uuid4().hex[:8]}", key, _to_serializable(val), parent, parenttype),
		)

	def get_defaults(self, key: str | None = None, parent: str = "__default") -> dict | list:
		"""Return defaults as dict (if *key* is None) or list of values."""
		if key is None:
			rows = self.sql(
				"SELECT defkey, defvalue FROM `tabDefaultValue` WHERE parent=?",
				(parent,),
				as_dict=False,
			)
			return {r[0]: _cast_result(r[1]) for r in (rows or [])}
		rows = self.sql(
			"SELECT defvalue FROM `tabDefaultValue` WHERE defkey=? AND parent=?",
			(key, parent),
			as_dict=False,
		)
		return [_cast_result(r[0]) for r in (rows or [])]

	def get_system_setting(self, key: str) -> str | None:
		"""Read a value from System Settings (Single doctype)."""
		return self.get_single_value("System Settings", key)

	# ================================================================
	# 6. Transactions
	# ================================================================

	def begin(self, *, read_only: bool = False) -> None:
		"""Start a transaction."""
		with self._lock:
			if not self._in_transaction:
				self._execute_raw("BEGIN")
				self._in_transaction = True
				self._read_only_mode = read_only
			self.touched_tables.clear()

	def commit(self, *, chain: bool = False) -> None:
		"""Commit the current transaction."""
		with self._lock:
			if self._in_transaction:
				self._execute_raw("COMMIT")
				self._in_transaction = False
				self._savepoints.clear()
				self.query_cache.clear()
			if chain:
				self.begin()

	def rollback(self, *, save_point: str | None = None, chain: bool = False) -> None:
		"""Rollback the current transaction or to a named savepoint."""
		with self._lock:
			if save_point:
				self._execute_raw(f"ROLLBACK TO SAVEPOINT `{save_point}`")
				# Prune savepoints newer than the one we rolled back to
				if save_point in self._savepoints:
					idx = self._savepoints.index(save_point)
					self._savepoints = self._savepoints[: idx + 1]
			elif self._in_transaction:
				self._execute_raw("ROLLBACK")
				self._in_transaction = False
				self._savepoints.clear()
				self.query_cache.clear()
		if chain:
			self.begin()

	def savepoint(self, save_point: str) -> None:
		"""Create a named savepoint."""
		with self._lock:
			self._execute_raw(f"SAVEPOINT `{save_point}`")
			self._savepoints.append(save_point)

	def release_savepoint(self, save_point: str) -> None:
		"""Release a named savepoint."""
		with self._lock:
			self._execute_raw(f"RELEASE SAVEPOINT `{save_point}`")
			if save_point in self._savepoints:
				self._savepoints.remove(save_point)

	# -- raw execution helpers (subclass implements) ----------------

	def _execute_raw(self, sql: str) -> None:
		"""Execute a raw SQL statement without parameterization."""
		raise NotImplementedError

	# ================================================================
	# 7. DDL
	# ================================================================

	def sql_ddl(self, query: str, debug: bool = False) -> None:
		"""Execute a DDL statement (ignores benign errors)."""
		self.sql(query, debug=debug, ignore_ddl=True)

	def get_descendants(self, doctype: str, name: str) -> list[str]:
		"""Return all descendant names from the closure table."""
		rows = self.sql(
			f"SELECT descendant FROM `tab{doctype} Tree` WHERE ancestor=? ORDER BY idx",
			(name,),
			as_dict=False,
			pluck=True,
		)
		return rows or []

	# ================================================================
	# 8. Utilities
	# ================================================================

	def escape(self, s: str, percent: bool = True) -> str:
		"""Escape a string for safe SQL interpolation."""
		return _sql_escape(s, percent)

	def mogrify(self, query: str, values: Any) -> str:
		"""Return the query with values bound (for debugging)."""
		if not values:
			return query
		if isinstance(values, dict):
			# Named parameters
			for k, v in values.items():
				placeholder = f":{k}" if not self.param_style == "format" else f"%({k})s"
				query = query.replace(placeholder, repr(_to_serializable(v)))
			return query
		# Positional
		if isinstance(values, (list, tuple)):
			parts = query.split("?")
			if len(parts) - 1 == len(values):
				result = parts[0]
				for i, val in enumerate(values):
					result += repr(_to_serializable(val)) + parts[i + 1]
				return result
		# Fallback – manual replacement
		for val in values if isinstance(values, (list, tuple)) else [values]:
			query = query.replace("?", repr(_to_serializable(val)), 1)
		return query

	def get_creation_count(self, doctype: str, minutes: int) -> int:
		"""Count documents created in the last *minutes*."""
		table = _scrub_table_name(doctype)
		cutoff = (datetime.utcnow() - timedelta(minutes=minutes)).strftime(
			"%Y-%m-%d %H:%M:%S"
		)
		rows = self.sql(
			f"SELECT COUNT(*) FROM `{table}` WHERE creation >= ?",
			(cutoff,),
			as_dict=False,
		)
		return int(rows[0][0]) if rows else 0

	def get_database_size(self) -> int:
		"""Return the database file size in bytes."""
		if self.database and self.database != ":memory:":
			try:
				return os.path.getsize(self.database)
			except OSError:
				return 0
		# For :memory: try page_count * page_size
		try:
			page_count = self.sql("PRAGMA page_count", as_dict=False)
			page_size = self.sql("PRAGMA page_size", as_dict=False)
			if page_count and page_size:
				return int(page_count[0][0]) * int(page_size[0][0])
		except Exception:
			pass
		return 0

	def get_last_created(self, doctype: str) -> Any:
		"""Return the creation timestamp of the most recent document."""
		table = _scrub_table_name(doctype)
		rows = self.sql(
			f"SELECT MAX(creation) FROM `{table}`",
			as_dict=False,
		)
		return rows[0][0] if rows and rows[0][0] else None

	def log_touched_tables(self, query: str, query_type: str | None) -> None:
		"""Record which tables were touched by *query* for cache invalidation."""
		if query_type is None:
			match = RE_QUERY_TYPE.match(query)
			if match:
				query_type = match.group(1).upper()
		if query_type not in ("INSERT", "UPDATE", "DELETE", "REPLACE"):
			return
		# Extract table names
		for pattern in (RE_FROM_TABLE, RE_INTO_TABLE, RE_UPDATE_TABLE):
			m = pattern.search(query)
			if m:
				self.touched_tables.add(m.group(1))

	# ================================================================
	# 9. Formatting
	# ================================================================

	def format_date(self, date_value: date | str | None) -> str:
		"""Format a date for SQL."""
		if date_value is None:
			return "NULL"
		if isinstance(date_value, str):
			return f"'{date_value}'"
		return f"'{date_value.strftime('%Y-%m-%d')}'"

	def format_datetime(self, datetime_value: datetime | str | None) -> str:
		"""Format a datetime for SQL."""
		if datetime_value is None:
			return "NULL"
		if isinstance(datetime_value, str):
			return f"'{datetime_value}'"
		return f"'{datetime_value.strftime('%Y-%m-%d %H:%M:%S.%f')}'"

	# ================================================================
	# 10. Context manager support
	# ================================================================

	@contextmanager
	def transaction(self, read_only: bool = False):
		"""Context manager for transactions."""
		self.begin(read_only=read_only)
		try:
			yield self
			self.commit()
		except Exception:
			self.rollback()
			raise

	# ================================================================
	# 11. Magic / dunder
	# ================================================================

	def __enter__(self):
		self.connect()
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		if exc_type:
			self.rollback()
		else:
			self.commit()
		self.close()

	def __repr__(self) -> str:
		return (
			f"<{self.__class__.__name__} dialect={self.dialect} "
			f"db={self.database!r}>"
		)
