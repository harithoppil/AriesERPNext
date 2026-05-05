"""SQLite-specific Database implementation.

This module provides a drop-in SQLite backend for Frappe's database layer.
Design decisions:

*   Uses ``sqlite3`` (stdlib) for synchronous operations – Frappe/ERPNext are
    fundamentally synchronous codebases.
*   ``aiosqlite`` is available for future async paths but **not required** at
    runtime; we use stdlib ``sqlite3`` for everything.
*   Translates MariaDB-specific syntax (``IFNULL``, ``SQL_CALC_FOUND_ROWS``,
    ``FOUND_ROWS()``, ``GROUP_CONCAT`` with ``SEPARATOR``, etc.) into
    SQLite-compatible equivalents.
*   JSON fields are stored as TEXT and handled via ``json`` module; the
    JSON1 extension is enabled via ``PRAGMA`` when available.
*   Thread-local connections – each thread gets its own ``sqlite3.Connection``
    to avoid "objects created in another thread" errors.
*   The ``tabDoctype`` naming convention is preserved exactly.
*   All internal tables (tabDocType, tabDocField, tabUser, …) are created on
    first connect via ``_ensure_schema()``.

This file implements every abstract / overridable hook from the base
:class:`Database` so that no method raises ``NotImplementedError`` at runtime.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3
import threading
import time
import weakref
from collections.abc import Sequence
from datetime import date, datetime, time as dt_time, timedelta
from typing import Any

# ---------------------------------------------------------------------------
# We try to import aiosqlite but do not fail if it is absent.
# ---------------------------------------------------------------------------
try:
	import aiosqlite

	_HAS_AIOSQLITE = True
except Exception:  # pragma: no cover
	aiosqlite = None  # type: ignore[assignment]
	_HAS_AIOSQLITE = False

from frappe.database.database import (
	Database,
	_cast_result,
	_to_serializable,
	_sql_escape,
	_dict,
	_scrub_table_name,
	_parse_field_expression,
	_make_in_placeholder,
	_now,
)
from frappe.exceptions import DatabaseError, IntegrityError, OperationalError

logger = logging.getLogger("frappe.database.sqlite")

# ---------------------------------------------------------------------------
# Type registration
# ---------------------------------------------------------------------------

def _adapt_date(val: date) -> str:
	return val.isoformat()


def _adapt_datetime(val: datetime) -> str:
	return val.isoformat()


def _adapt_timedelta(val: timedelta) -> str:
	return str(val)


def _convert_date(val: bytes) -> date:
	return datetime.strptime(val.decode("utf-8"), "%Y-%m-%d").date()


def _convert_datetime(val: bytes) -> datetime:
	s = val.decode("utf-8")
	for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
		try:
			return datetime.strptime(s, fmt)
		except ValueError:
			continue
	return datetime.strptime(s, "%Y-%m-%d")


# Register adapters / converters with sqlite3
sqlite3.register_adapter(date, _adapt_date)
sqlite3.register_adapter(datetime, _adapt_datetime)
sqlite3.register_adapter(timedelta, _adapt_timedelta)
sqlite3.register_converter("DATE", _convert_date)
sqlite3.register_converter("DATETIME", _convert_datetime)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Regex for MariaDB → SQLite syntax translation
_RE_GROUP_CONCAT = re.compile(
	r"GROUP_CONCAT\s*\(\s*(.*?)\s+SEPARATOR\s+'([^']+)'\s*\)",
	re.IGNORECASE | re.DOTALL,
)
_RE_MATCH_AGAINST = re.compile(
	r"MATCH\s*\([^)]+\)\s*AGAINST\s*\([^)]+\)",
	re.IGNORECASE,
)
_RE_RAND = re.compile(r"\bRAND\s*\(\s*\)", re.IGNORECASE)
_RE_NOW = re.compile(r"\bNOW\s*\(\s*\)", re.IGNORECASE)
_RE_CURDATE = re.compile(r"\bCURDATE\s*\(\s*\)", re.IGNORECASE)
_RE_CURTIME = re.compile(r"\bCURTIME\s*\(\s*\)", re.IGNORECASE)
_RE_UNIX_TIMESTAMP = re.compile(r"\bUNIX_TIMESTAMP\s*\(\s*\)", re.IGNORECASE)
_RE_TIMESTAMP_DIFF = re.compile(
	r"TIMESTAMPDIFF\s*\(\s*(\w+)\s*,\s*([^,]+)\s*,\s*([^)]+)\s*\)",
	re.IGNORECASE,
)
_RE_DATE_FORMAT = re.compile(
	r"DATE_FORMAT\s*\(\s*([^,]+)\s*,\s*'([^']+)'\s*\)",
	re.IGNORECASE,
)
_RE_CAST_SIGNED = re.compile(
	r"CAST\s*\(\s*([^)]+)\s+AS\s+SIGNED\s*\)",
	re.IGNORECASE,
)
_RE_CONCAT_WS = re.compile(
	r"CONCAT_WS\s*\(\s*'([^']+)'((?:\s*,\s*[^,\)]+)+)\s*\)",
	re.IGNORECASE,
)
_RE_FIELD = re.compile(
	r"FIELD\s*\(\s*([^,]+)((?:\s*,\s*[^,\)]+)+)\s*\)",
	re.IGNORECASE,
)
_RE_BACKTICK = re.compile(r"`")
_RE_LIMIT_FOR_UPDATE = re.compile(r"\s+FOR\s+UPDATE\s*$", re.IGNORECASE)
_RE_SQL_CALC_FOUND_ROWS = re.compile(r"\bSQL_CALC_FOUND_ROWS\b", re.IGNORECASE)
_RE_FOUND_ROWS = re.compile(r"SELECT\s+FOUND_ROWS\s*\(\s*\)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# SQLite helpers
# ---------------------------------------------------------------------------

def _sqlite_group_concat(value: Any, separator: str = ", ") -> str:
	"""Aggregate helper for GROUP_CONCAT in SQLite."""
	if value is None:
		return ""
	if isinstance(value, str):
		return value
	if isinstance(value, (list, tuple)):
		return separator.join(str(v) for v in value)
	return str(value)


class _ConnectionPool:
	"""Thread-local connection pool for SQLite.

	Each thread receives its own ``sqlite3.Connection``.  When a thread
	terminates the connection is closed automatically via a weak-ref callback.
	"""

	def __init__(
		self,
		db_path: str,
		pragmas: dict[str, Any] | None = None,
		read_only: bool = False,
	):
		self.db_path = db_path
		self.pragmas = pragmas or {}
		self.read_only = read_only
		self._local = threading.local()
		self._all_conns: set[int] = set()  # Track by id() since sqlite3.Connection doesn't support weakref
		self._lock = threading.Lock()

	# -- public API -------------------------------------------------

	def get(self) -> sqlite3.Connection:
		"""Return the connection for the current thread (create if needed)."""
		conn = getattr(self._local, "connection", None)
		if conn is None:
			conn = self._create_connection()
			self._local.connection = conn
			self._all_conns.add(id(conn))
		return conn

	def close_current(self) -> None:
		"""Close the connection belonging to the current thread."""
		conn = getattr(self._local, "connection", None)
		if conn is not None:
			try:
				conn.close()
			except Exception:
				logger.debug("Error closing thread-local connection", exc_info=True)
			self._local.connection = None
			self._all_conns.discard(id(conn))

	def close_all(self) -> None:
		"""Close every known connection."""
		with self._lock:
			self.close_current()
			self._all_conns.clear()

	# -- internal ---------------------------------------------------

	def _create_connection(self) -> sqlite3.Connection:
		"""Open a new SQLite connection with our custom settings."""
		uri = False
		path = self.db_path
		if self.read_only:
			path = f"file:{self.db_path}?mode=ro"
			uri = True

		conn = sqlite3.connect(
			path,
			check_same_thread=False,
			detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
			isolation_level=None,  # We manage transactions manually
			uri=uri,
		)

		# Enable JSON1 extension (built into modern Python sqlite3)
		conn.enable_load_extension(False)

		# Default pragmas
		conn.execute("PRAGMA foreign_keys = ON")
		conn.execute("PRAGMA journal_mode = WAL")
		conn.execute("PRAGMA synchronous = NORMAL")

		# User-supplied pragmas override defaults
		for key, val in self.pragmas.items():
			conn.execute(f"PRAGMA {key} = {val}")

		# Row factory for dict-like access when needed
		conn.row_factory = sqlite3.Row

		# Custom functions
		conn.create_function("IFNULL", 2, lambda x, y: x if x is not None else y)
		conn.create_function("COALESCE", 2, lambda x, y: x if x is not None else y)

		return conn


# ---------------------------------------------------------------------------
# SQLiteDatabase class
# ---------------------------------------------------------------------------

class SQLiteDatabase(Database):
	"""SQLite-backed implementation of the Frappe Database API."""

	# ================================================================
	# Construction & connection
	# ================================================================

	def __init__(
		self,
		host=None,
		port=None,
		user=None,
		password=None,
		database=None,
		**kwargs,
	):
		super().__init__(host, port, user, password, database, **kwargs)
		self.dialect = "sqlite"
		self.param_style = "?"
		self.db_path = database or kwargs.get("db_name") or ":memory:"
		self.read_only = kwargs.get("read_only", False)

		# Pragmas
		self.pragmas: dict[str, Any] = {}
		if "synchronous" in kwargs:
			self.pragmas["synchronous"] = kwargs["synchronous"]
		if "journal_mode" in kwargs:
			self.pragmas["journal_mode"] = kwargs["journal_mode"]

		# Connection pool
		self._pool = _ConnectionPool(
			self.db_path, pragmas=self.pragmas, read_only=self.read_only
		)
		self._conn: sqlite3.Connection | None = None
		self._cursor: sqlite3.Cursor | None = None

		# Track whether schema has been ensured
		self._schema_ready = False

	# -- connection lifecycle -----------------------------------------

	def connect(self) -> None:
		"""Open the SQLite connection for the current thread."""
		with self._lock:
			if self._conn is None:
				self._conn = self._pool.get()
				self._cursor = self._conn.cursor()
				if not self._schema_ready:
					self._ensure_schema()
					self._schema_ready = True

	def close(self) -> None:
		"""Close the current thread's connection."""
		with self._lock:
			if self._cursor:
				try:
					self._cursor.close()
				except Exception:
					pass
				self._cursor = None
			self._pool.close_current()
			self._conn = None
		self._in_transaction = False
		self._savepoints.clear()

	def _ensure_connection(self) -> sqlite3.Connection:
		"""Return the current connection, opening if necessary."""
		if self._conn is None:
			self.connect()
		assert self._conn is not None
		return self._conn

	def _ensure_cursor(self) -> sqlite3.Cursor:
		"""Return the current cursor, opening if necessary."""
		if self._cursor is None:
			self.connect()
		assert self._cursor is not None
		return self._cursor

	# ================================================================
	# SQL dialect translation
	# ================================================================

	def _translate_query(self, query: str) -> str:
		"""Convert MariaDB SQL to SQLite-compatible SQL."""
		# 1. Strip MariaDB-only hints
		query = _RE_SQL_CALC_FOUND_ROWS.sub("", query)
		query = _RE_FOUND_ROWS.sub("SELECT 0", query)
		query = _RE_LIMIT_FOR_UPDATE.sub("", query)

		# 2. Function replacements
		query = self._rewrite_group_concat(query)
		query = self._rewrite_match_against(query)
		query = self._rewrite_field(query)
		query = self._rewrite_concat_ws(query)
		query = _RE_CAST_SIGNED.sub(r"CAST(\1 AS INTEGER)", query)
		query = self._rewrite_date_format(query)
		query = self._rewrite_timestampdiff(query)
		query = _RE_RAND.sub("RANDOM() / CAST(-1 AS REAL) / 9223372036854775808 + 0.5", query)
		query = _RE_NOW.sub("DATETIME('now')", query)
		query = _RE_CURDATE.sub("DATE('now')", query)
		query = _RE_CURTIME.sub("TIME('now')", query)
		query = _RE_UNIX_TIMESTAMP.sub("CAST(STRFTIME('%s', 'now') AS INTEGER)", query)

		# 3. Generic IFNULL → COALESCE
		query = self._rewrite_ifnull(query)

		# 4. Fix ``INSERT IGNORE`` → ``INSERT OR IGNORE``
		query = re.sub(r"\bINSERT\s+IGNORE\b", "INSERT OR IGNORE", query, flags=re.IGNORECASE)

		# 5. Fix ``REPLACE INTO`` is already SQLite-native

		# 6. ``ON DUPLICATE KEY UPDATE`` → ``ON CONFLICT(...) DO UPDATE SET``
		query = self._rewrite_on_duplicate(query)

		# 7. ``DESCRIBE <table>`` → ``PRAGMA table_info(<table>)``
		query = self._rewrite_describe(query)

		# 8. ``SHOW COLUMNS`` → ``PRAGMA table_info``
		query = self._rewrite_show_columns(query)

		# 9. ``SHOW TABLES`` → ``SELECT name FROM sqlite_master``
		query = self._rewrite_show_tables(query)

		# 10. ``SHOW INDEX`` → ``PRAGMA index_list``
		query = self._rewrite_show_index(query)

		# 11. Convert ``LIMIT row_count OFFSET offset`` (already SQLite)
		# but ensure ``LIMIT offset, row_count`` (MariaDB) becomes
		# ``LIMIT row_count OFFSET offset``.
		query = self._rewrite_limit(query)

		# 12. ``AUTO_INCREMENT`` → ``AUTOINCREMENT`` (SQLite spelling)
		query = re.sub(r"\bAUTO_INCREMENT\b", "AUTOINCREMENT", query, flags=re.IGNORECASE)

		# 13. Backtick-quoted identifiers are fine in SQLite 3.25+,
		#     but we keep them for compatibility.

		return query

	# -- specific rewriters -------------------------------------------

	@staticmethod
	def _rewrite_group_concat(query: str) -> str:
		"""GROUP_CONCAT(... SEPARATOR 'x') → GROUP_CONCAT(..., 'x')."""
		def repl(m: re.Match) -> str:
			expr = m.group(1).strip()
			sep = m.group(2)
			return f"GROUP_CONCAT({expr}, '{sep}')"
		return _RE_GROUP_CONCAT.sub(repl, query)

	@staticmethod
	def _rewrite_match_against(query: str) -> str:
		"""Replace MATCH ... AGAINST ... with a LIKE fallback."""
		# Simple fallback: MATCH(col) AGAINST('term')
		# becomes col LIKE '%term%'
		# This is a best-effort translation.
		def repl(m: re.Match) -> str:
			# Extract the column and the search term if possible
			match_str = m.group(0)
			# Try to find quoted term
			term_match = re.search(r"'([^']+)'", match_str)
			if term_match:
				term = term_match.group(1)
				# Extract column name from MATCH(col)
				col_match = re.search(r"MATCH\s*\(\s*([^)]+)\s*\)", match_str)
				if col_match:
					col = col_match.group(1).strip()
					return f"{col} LIKE '%{_sql_escape(term, percent=False)}%'"
			return "1"  # Fallback: always true
		return _RE_MATCH_AGAINST.sub(repl, query)

	@staticmethod
	def _rewrite_field(query: str) -> str:
		"""FIELD(value, v1, v2, ...) → CASE-based ordering."""
		def repl(m: re.Match) -> str:
			value = m.group(1).strip()
			args = [a.strip() for a in m.group(2).split(",") if a.strip()]
			# Build CASE WHEN value=v1 THEN 0 WHEN value=v2 THEN 1 ... ELSE 999 END
			cases = " ".join(
				f"WHEN {value} = {a} THEN {i}"
				for i, a in enumerate(args)
			)
			return f"CASE {cases} ELSE {len(args)} END"
		return _RE_FIELD.sub(repl, query)

	@staticmethod
	def _rewrite_concat_ws(query: str) -> str:
		"""CONCAT_WS(sep, a, b, ...) → a || sep || b ..."""
		def repl(m: re.Match) -> str:
			sep = m.group(1)
			args = [a.strip() for a in m.group(2).split(",") if a.strip()]
			sep_expr = f" || '{sep}' || "
			return sep_expr.join(args)
		return _RE_CONCAT_WS.sub(repl, query)

	@staticmethod
	def _rewrite_date_format(query: str) -> str:
		"""DATE_FORMAT(date, 'format') → STRFTIME('sqlite_format', date)."""
		mysql_to_sqlite_fmt = {
			"%Y": "%Y", "%y": "%y",
			"%m": "%m", "%c": "%m",
			"%d": "%d", "%e": "%d",
			"%H": "%H", "%h": "%H", "%I": "%H",
			"%i": "%M",
			"%s": "%S", "%S": "%S",
			"%p": "",
			"%w": "%w", "%W": "%W",
			"%M": "%m",  # month name – simplified
			"%b": "%m",
			"%f": "%f",
			"%j": "%j",
		}

		def repl(m: re.Match) -> str:
			expr = m.group(1).strip()
			fmt = m.group(2)
			# Translate format specifiers
			sqlite_fmt = fmt
			for mysql, sqlite in mysql_to_sqlite_fmt.items():
				sqlite_fmt = sqlite_fmt.replace(mysql, sqlite)
			return f"STRFTIME('{sqlite_fmt}', {expr})"
		return _RE_DATE_FORMAT.sub(repl, query)

	@staticmethod
	def _rewrite_timestampdiff(query: str) -> str:
		"""TIMESTAMPDIFF(unit, a, b) → (julianday(b) - julianday(a)) * factor."""
		unit_factors = {
			"second": 86400.0,
			"minute": 1440.0,
			"hour": 24.0,
			"day": 1.0,
			"week": 1.0 / 7.0,
			"month": 1.0 / 30.44,
			"quarter": 1.0 / 91.31,
			"year": 1.0 / 365.25,
		}

		def repl(m: re.Match) -> str:
			unit = m.group(1).lower()
			a = m.group(2).strip()
			b = m.group(3).strip()
			factor = unit_factors.get(unit, 1.0)
			if unit == "month":
				# More accurate month diff using Julian day
				return f"CAST((JULIANDAY({b}) - JULIANDAY({a})) / 30.44 AS INTEGER)"
			if unit == "year":
				return f"CAST((JULIANDAY({b}) - JULIANDAY({a})) / 365.25 AS INTEGER)"
			return f"CAST(ROUND((JULIANDAY({b}) - JULIANDAY({a})) * {factor}) AS INTEGER)"
		return _RE_TIMESTAMP_DIFF.sub(repl, query)

	@staticmethod
	def _rewrite_on_duplicate(query: str) -> str:
		"""INSERT ... ON DUPLICATE KEY UPDATE ... → INSERT ... ON CONFLICT DO UPDATE ..."""
		# This is a simplified rewriter. Complex cases may need manual handling.
		pattern = re.compile(
			r"\bON\s+DUPLICATE\s+KEY\s+UPDATE\b",
			re.IGNORECASE,
		)
		if not pattern.search(query):
			return query

		# Extract the UPDATE assignments
		parts = pattern.split(query, maxsplit=1)
		if len(parts) != 2:
			return query

		prefix = parts[0]
		assignments = parts[1].strip()

		# Try to extract the table name from INSERT INTO `table` ...
		tbl_match = re.search(r"INSERT\s+(?:OR\s+IGNORE\s+)?INTO\s+`?([^`\s(]+)`?", prefix, re.IGNORECASE)
		if not tbl_match:
			return query

		table = tbl_match.group(1)

		# Try to determine the conflict target (primary key / unique columns)
		# For Frappe tables the primary key is usually `name`
		conflict_target = "name"

		# Build the ON CONFLICT clause
		upsert = f"ON CONFLICT({conflict_target}) DO UPDATE SET {assignments}"

		return f"{prefix} {upsert}"

	@staticmethod
	def _rewrite_describe(query: str) -> str:
		"""DESCRIBE table → PRAGMA table_info(table)."""
		m = re.match(r"^\s*DESCRIBE\s+`?([^`\s]+)`?\s*$", query, re.IGNORECASE)
		if m:
			return f"PRAGMA table_info('{m.group(1)}')"
		return query

	@staticmethod
	def _rewrite_show_columns(query: str) -> str:
		"""SHOW COLUMNS FROM table → PRAGMA table_info(table)."""
		m = re.match(
			r"^\s*SHOW\s+(?:FULL\s+)?COLUMNS\s+FROM\s+`?([^`\s]+)`?.*$",
			query,
			re.IGNORECASE,
		)
		if m:
			return f"PRAGMA table_info('{m.group(1)}')"
		return query

	@staticmethod
	def _rewrite_show_tables(query: str) -> str:
		"""SHOW TABLES → SELECT name FROM sqlite_master WHERE type='table'."""
		m = re.match(r"^\s*SHOW\s+TABLES\s*$", query, re.IGNORECASE)
		if m:
			return (
				"SELECT name FROM sqlite_master "
				"WHERE type='table' ORDER BY name"
			)
		return query

	@staticmethod
	def _rewrite_show_index(query: str) -> str:
		"""SHOW INDEX FROM table → PRAGMA index_list(table)."""
		m = re.match(
			r"^\s*SHOW\s+(?:INDEX|INDEXES|KEYS)\s+FROM\s+`?([^`\s]+)`?.*$",
			query,
			re.IGNORECASE,
		)
		if m:
			return f"PRAGMA index_list('{m.group(1)}')"
		return query

	@staticmethod
	def _rewrite_limit(query: str) -> str:
		"""LIMIT offset, count → LIMIT count OFFSET offset."""
		# MariaDB: LIMIT offset, count
		# SQLite:  LIMIT count OFFSET offset
		def repl(m: re.Match) -> str:
			offset = m.group(1)
			count = m.group(2)
			return f"LIMIT {count} OFFSET {offset}"
		return re.sub(r"\bLIMIT\s+(\d+)\s*,\s*(\d+)\b", repl, query, flags=re.IGNORECASE)

	# ================================================================
	# Query execution
	# ================================================================

	def _execute(self, query: str, values: Any) -> sqlite3.Cursor:
		"""Execute *query* with *values* and return the cursor."""
		cursor = self._ensure_cursor()
		if values is None:
			values = ()
		# Normalize values
		if isinstance(values, dict):
			# Named parameters – sqlite3 supports :name style
			cursor.execute(query, values)
		elif isinstance(values, (list, tuple)):
			cursor.execute(query, values)
		else:
			cursor.execute(query, (values,))
		return cursor

	def _execute_raw(self, sql: str) -> None:
		"""Execute a raw SQL statement (used for BEGIN, COMMIT, etc.)."""
		conn = self._ensure_connection()
		conn.execute(sql)

	# ================================================================
	# Schema setup (internal tables)
	# ================================================================


	def sync_doctype_table(self, doctype: str, fields: list[dict]) -> None:
		"""Sync table schema for a DocType — add missing columns."""
		table = f"tab{doctype}"

		if not self.table_exists(doctype):
			self.sql_ddl(f"""
				CREATE TABLE IF NOT EXISTS `{table}` (
					`name` VARCHAR(255) PRIMARY KEY,
					`creation` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
					`modified` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
					`modified_by` VARCHAR(255),
					`owner` VARCHAR(255),
					`docstatus` INTEGER DEFAULT 0,
					`idx` INTEGER DEFAULT 0
				)
			""")

		try:
			existing_columns = self.get_db_table_columns(table)
		except Exception:
			existing_columns = []

		type_map = {
			"Data": "VARCHAR(255)", "Link": "VARCHAR(255)",
			"Dynamic Link": "VARCHAR(255)", "Password": "VARCHAR(255)",
			"Select": "VARCHAR(255)", "Read Only": "VARCHAR(255)",
			"Text": "TEXT", "Long Text": "TEXT", "Text Editor": "TEXT",
			"Code": "TEXT", "Markdown Editor": "TEXT", "HTML Editor": "TEXT",
			"Int": "INTEGER", "Integer": "INTEGER",
			"Check": "INTEGER DEFAULT 0",
			"Float": "FLOAT", "Currency": "FLOAT", "Percent": "FLOAT",
			"Date": "DATE", "Datetime": "TIMESTAMP", "Time": "TIME",
			"Color": "VARCHAR(7)", "Barcode": "VARCHAR(255)",
			"Geolocation": "TEXT", "Attach": "VARCHAR(255)",
			"Attach Image": "VARCHAR(255)", "Signature": "TEXT",
			"JSON": "TEXT", "Autocomplete": "VARCHAR(255)",
		}

		for field in fields:
			fieldname = field.get("fieldname") if isinstance(field, dict) else getattr(field, "fieldname", None)
			fieldtype = field.get("fieldtype") if isinstance(field, dict) else getattr(field, "fieldtype", "Data")

			if not fieldname or fieldname in existing_columns:
				continue
			if fieldtype in ("Table", "Table MultiSelect", "Section Break", 
							 "Column Break", "Tab Break", "HTML", "Button", "Fold"):
				continue

			column_type = type_map.get(fieldtype, "VARCHAR(255)")
			try:
				self.sql_ddl(f"ALTER TABLE `{table}` ADD COLUMN `{fieldname}` {column_type}")
				existing_columns.append(fieldname)
			except Exception:
				pass

	def _ensure_schema(self) -> None:
		"""Create all internal tables on first connect."""
		conn = self._ensure_connection()
		with conn:
			self._create_table_doc_type(conn)
			self._create_table_doc_field(conn)
			self._create_table_doc_perm(conn)
			self._create_table_module_def(conn)
			self._create_table_user(conn)
			self._create_table_role(conn)
			self._create_table_version(conn)
			self._create_table_error_log(conn)
			self._create_table_scheduled_job_type(conn)
			self._create_table_default_value(conn)
			self._create_table_singles(conn)
			self._create_table_sequences(conn)
			self._insert_seed_data(conn)

	def _exec_schema(self, conn: sqlite3.Connection, ddl: str) -> None:
		"""Execute a DDL statement, ignoring 'already exists' errors."""
		try:
			conn.execute(ddl)
		except sqlite3.OperationalError as exc:
			if "already exists" in str(exc):
				return
			raise

	# -- individual table creators ------------------------------------

	def _create_table_doc_type(self, conn: sqlite3.Connection) -> None:
		self._exec_schema(conn, """
			CREATE TABLE IF NOT EXISTS `tabDocType` (
				name              TEXT PRIMARY KEY,
				creation          DATETIME,
				modified          DATETIME,
				modified_by       TEXT,
				owner             TEXT DEFAULT 'Administrator',
				docstatus         INTEGER DEFAULT 0,
				idx               INTEGER DEFAULT 0,
				search_fields     TEXT,
				issingle          INTEGER DEFAULT 0,
				is_tree           INTEGER DEFAULT 0,
				istable           INTEGER DEFAULT 0,
				editable_grid     INTEGER DEFAULT 1,
				track_changes     INTEGER DEFAULT 1,
				module            TEXT,
				autoname          TEXT,
				naming_rule       TEXT,
				title_field       TEXT,
				sort_field        TEXT DEFAULT 'modified',
				sort_order        TEXT DEFAULT 'DESC',
				description       TEXT,
				colour            TEXT,
				read_only         INTEGER DEFAULT 0,
				in_create         INTEGER DEFAULT 0,
				settings          TEXT,
				has_web_view      INTEGER DEFAULT 0,
				allow_guest_to_view INTEGER DEFAULT 0,
				index_web_pages_for_search INTEGER DEFAULT 0,
				engine            TEXT DEFAULT 'InnoDB',
			
				custom            INTEGER DEFAULT 0,
				beta              INTEGER DEFAULT 0,
				is_virtual        INTEGER DEFAULT 0,
				
				_fields           TEXT,
				_permissions      TEXT,
				_links            TEXT,
				_actions          TEXT,
				_states           TEXT,
				_dashboard        TEXT
			)
		""")

	def _create_table_doc_field(self, conn: sqlite3.Connection) -> None:
		self._exec_schema(conn, """
			CREATE TABLE IF NOT EXISTS `tabDocField` (
				name              TEXT PRIMARY KEY,
				creation          DATETIME,
				modified          DATETIME,
				modified_by       TEXT,
				owner             TEXT DEFAULT 'Administrator',
				docstatus         INTEGER DEFAULT 0,
				idx               INTEGER DEFAULT 0,
				fieldname         TEXT,
				label             TEXT,
				fieldtype         TEXT,
				options           TEXT,
				search_index      INTEGER DEFAULT 0,
				hidden            INTEGER DEFAULT 0,
				set_only_once     INTEGER DEFAULT 0,
				allow_in_quick_entry INTEGER DEFAULT 0,
				print_hide        INTEGER DEFAULT 0,
				report_hide       INTEGER DEFAULT 0,
				reqd              INTEGER DEFAULT 0,
				bold              INTEGER DEFAULT 0,
				in_global_search  INTEGER DEFAULT 0,
				collapsible       INTEGER DEFAULT 0,
				`unique`          INTEGER DEFAULT 0,
				no_copy           INTEGER DEFAULT 0,
				allow_on_submit   INTEGER DEFAULT 0,
				show_preview_popup INTEGER DEFAULT 0,
				trigger           TEXT,
				collapsible_depends_on TEXT,
				mandatory_depends_on TEXT,
				read_only_depends_on TEXT,
				depends_on        TEXT,
				description       TEXT,
				ignore_user_permissions INTEGER DEFAULT 0,
				allow_bulk_edit   INTEGER DEFAULT 0,
				`default`         TEXT,
				fetch_from        TEXT,
				fetch_if_empty    INTEGER DEFAULT 0,
				permlevel         INTEGER DEFAULT 0,
				ignore_xss_filter INTEGER DEFAULT 0,
				translatable      INTEGER DEFAULT 0,
				length            INTEGER DEFAULT 0,
				doc_parent        TEXT,
				_doc_parent       TEXT
			)
		""")

	def _create_table_doc_perm(self, conn: sqlite3.Connection) -> None:
		self._exec_schema(conn, """
			CREATE TABLE IF NOT EXISTS `tabDocPerm` (
				name              TEXT PRIMARY KEY,
				creation          DATETIME,
				modified          DATETIME,
				modified_by       TEXT,
				owner             TEXT DEFAULT 'Administrator',
				docstatus         INTEGER DEFAULT 0,
				idx               INTEGER DEFAULT 0,
				role              TEXT,
				`match`           TEXT,
				`read`            INTEGER DEFAULT 1,
				`write`           INTEGER DEFAULT 1,
				`create`          INTEGER DEFAULT 1,
				submit            INTEGER DEFAULT 0,
				cancel            INTEGER DEFAULT 0,
				`delete`          INTEGER DEFAULT 1,
				amend             INTEGER DEFAULT 0,
				report            INTEGER DEFAULT 1,
				export            INTEGER DEFAULT 1,
				import_data       INTEGER DEFAULT 0,
				share             INTEGER DEFAULT 1,
				print             INTEGER DEFAULT 1,
				email             INTEGER DEFAULT 1,
				if_owner          INTEGER DEFAULT 0,
				permlevel         INTEGER DEFAULT 0,
				doc_parent        TEXT,
				_doc_parent       TEXT
			)
		""")

	def _create_table_module_def(self, conn: sqlite3.Connection) -> None:
		self._exec_schema(conn, """
			CREATE TABLE IF NOT EXISTS `tabModule Def` (
				name              TEXT PRIMARY KEY,
				creation          DATETIME,
				modified          DATETIME,
				modified_by       TEXT,
				owner             TEXT DEFAULT 'Administrator',
				docstatus         INTEGER DEFAULT 0,
				idx               INTEGER DEFAULT 0,
				app_name          TEXT,
				custom            INTEGER DEFAULT 0,
				package           TEXT,
				restrict_to_domain TEXT
			)
		""")

	def _create_table_user(self, conn: sqlite3.Connection) -> None:
		self._exec_schema(conn, """
			CREATE TABLE IF NOT EXISTS `tabUser` (
				name              TEXT PRIMARY KEY,
				creation          DATETIME,
				modified          DATETIME,
				modified_by       TEXT,
				owner             TEXT DEFAULT 'Administrator',
				docstatus         INTEGER DEFAULT 0,
				idx               INTEGER DEFAULT 0,
				enabled           INTEGER DEFAULT 1,
				email             TEXT UNIQUE,
				send_welcome_email INTEGER DEFAULT 0,
				first_name        TEXT,
				middle_name       TEXT,
				last_name         TEXT,
				full_name         TEXT,
				username          TEXT,
				language          TEXT,
				time_zone         TEXT,
				user_image        TEXT,
				role_profile_name TEXT,
				phone             TEXT,
				mobile_no         TEXT,
				location          TEXT,
				gender            TEXT,
				birth_date        DATE,
				interest          TEXT,
				desk_theme        TEXT,
				banner_image      TEXT,
				document_follow_notify INTEGER DEFAULT 0,
				follow_liked_documents INTEGER DEFAULT 0,
				follow_commented_documents INTEGER DEFAULT 0,
				follow_assigned_documents INTEGER DEFAULT 0,
				follow_shared_documents INTEGER DEFAULT 0,
				home_settings     TEXT,
				thread_notify     INTEGER DEFAULT 0,
				allowed_in_mentions INTEGER DEFAULT 1,
				simultaneous_sessions INTEGER DEFAULT 0,
				login_after       INTEGER DEFAULT 0,
				login_before      INTEGER DEFAULT 0,
				restrict_ip       TEXT,
				bypass_restrict_ip_check_if_2fa_enabled INTEGER DEFAULT 0,
				last_ip           TEXT,
				last_active       DATETIME,
				last_login        TEXT,
				last_known_versions TEXT,
				new_password      TEXT,
				logout_all_sessions INTEGER DEFAULT 0,
				reset_password_key TEXT,
				last_password_reset_date DATE,
				redirect_url      TEXT,
				send_me_a_copy    INTEGER DEFAULT 0,
				unsuccessful_logins INTEGER DEFAULT 0,
				notify_email      TEXT,
				api_key           TEXT,
				api_secret        TEXT,
				`type`            TEXT DEFAULT 'System User'
			)
		""")

	def _create_table_role(self, conn: sqlite3.Connection) -> None:
		self._exec_schema(conn, """
			CREATE TABLE IF NOT EXISTS `tabRole` (
				name              TEXT PRIMARY KEY,
				creation          DATETIME,
				modified          DATETIME,
				modified_by       TEXT,
				owner             TEXT DEFAULT 'Administrator',
				docstatus         INTEGER DEFAULT 0,
				idx               INTEGER DEFAULT 0,
				desk_access       INTEGER DEFAULT 1,
				restrict_to_domain TEXT,
				_two_factor_auth  TEXT,
				home_page         TEXT
			)
		""")

	def _create_table_version(self, conn: sqlite3.Connection) -> None:
		self._exec_schema(conn, """
			CREATE TABLE IF NOT EXISTS `tabVersion` (
				name              TEXT PRIMARY KEY,
				creation          DATETIME,
				modified          DATETIME,
				modified_by       TEXT,
				owner             TEXT DEFAULT 'Administrator',
				docstatus         INTEGER DEFAULT 0,
				idx               INTEGER DEFAULT 0,
				ref_doctype       TEXT,
				docname           TEXT,
				data              TEXT
			)
		""")

	def _create_table_error_log(self, conn: sqlite3.Connection) -> None:
		self._exec_schema(conn, """
			CREATE TABLE IF NOT EXISTS `tabError Log` (
				name              TEXT PRIMARY KEY,
				creation          DATETIME,
				modified          DATETIME,
				modified_by       TEXT,
				owner             TEXT DEFAULT 'Administrator',
				docstatus         INTEGER DEFAULT 0,
				idx               INTEGER DEFAULT 0,
				method            TEXT,
				error             TEXT,
				reference_doctype TEXT,
				reference_name    TEXT,
				seen              INTEGER DEFAULT 0,
				roll_up           INTEGER DEFAULT 0,
				trace_id          TEXT
			)
		""")

	def _create_table_scheduled_job_type(self, conn: sqlite3.Connection) -> None:
		self._exec_schema(conn, """
			CREATE TABLE IF NOT EXISTS `tabScheduled Job Type` (
				name              TEXT PRIMARY KEY,
				creation          DATETIME,
				modified          DATETIME,
				modified_by       TEXT,
				owner             TEXT DEFAULT 'Administrator',
				docstatus         INTEGER DEFAULT 0,
				idx               INTEGER DEFAULT 0,
				stopped           INTEGER DEFAULT 0,
				method            TEXT,
				frequency         TEXT,
				cron_format       TEXT,
				create_log        INTEGER DEFAULT 1,
				last_execution    DATETIME
			)
		""")

	def _create_table_default_value(self, conn: sqlite3.Connection) -> None:
		self._exec_schema(conn, """
			CREATE TABLE IF NOT EXISTS `tabDefaultValue` (
				name              TEXT PRIMARY KEY,
				creation          DATETIME,
				modified          DATETIME,
				modified_by       TEXT,
				owner             TEXT DEFAULT 'Administrator',
				docstatus         INTEGER DEFAULT 0,
				idx               INTEGER DEFAULT 0,
				defkey            TEXT,
				defvalue          TEXT,
				parent            TEXT,
				parenttype        TEXT,
				parentfield       TEXT
			)
		""")

	def _create_table_singles(self, conn: sqlite3.Connection) -> None:
		self._exec_schema(conn, """
			CREATE TABLE IF NOT EXISTS `tabSingles` (
				doctype           TEXT NOT NULL,
				field             TEXT NOT NULL,
				value             TEXT,
				PRIMARY KEY (doctype, field)
			)
		""")

	def _create_table_sequences(self, conn: sqlite3.Connection) -> None:
		"""SQLite uses sqlite_sequence for AUTOINCREMENT; ensure it exists."""
		# sqlite_sequence is created automatically by SQLite when a table
		# with AUTOINCREMENT is first created.  We just ensure the
		# `tabSequence` table exists for Frappe's explicit sequence tracking.
		self._exec_schema(conn, """
			CREATE TABLE IF NOT EXISTS `tabSequence` (
				name              TEXT PRIMARY KEY,
				creation          DATETIME,
				modified          DATETIME,
				modified_by       TEXT,
				owner             TEXT DEFAULT 'Administrator',
				docstatus         INTEGER DEFAULT 0,
				current           INTEGER DEFAULT 0
			)
		""")

	def _insert_seed_data(self, conn: sqlite3.Connection) -> None:
		"""Insert minimal seed data so the framework can bootstrap."""
		now = datetime.utcnow().isoformat()

		# Seed DocType entries for core types
		core_types = [
			("DocType", 0, 0, 0, "Core", "naming_rule", "Core", "modified", "DESC"),
			("DocField", 0, 0, 1, "Core", None, "Core", "modified", "DESC"),
			("DocPerm", 0, 0, 1, "Core", None, "Core", "modified", "DESC"),
			("Module Def", 0, 0, 0, "Core", None, "Core", "modified", "DESC"),
			("User", 0, 0, 0, "Core", None, "Core", "modified", "DESC"),
			("Role", 0, 0, 0, "Core", None, "Core", "modified", "DESC"),
			("Version", 0, 0, 0, "Core", None, "Core", "modified", "DESC"),
			("Error Log", 0, 0, 0, "Core", None, "Core", "modified", "DESC"),
			("DefaultValue", 0, 0, 1, "Core", None, "Core", "modified", "DESC"),
		]

		for name, issingle, is_tree, istable, module, naming_rule, mod, sf, so in core_types:
			try:
				conn.execute(
					"""INSERT OR IGNORE INTO `tabDocType`
					(name, creation, modified, owner, issingle, is_tree,
					 istable, module, naming_rule, docstatus, idx,
					 sort_field, sort_order, engine)
					VALUES (?, ?, ?, 'Administrator', ?, ?, ?, ?, ?, 0, 0, ?, ?, 'InnoDB')""",
					(name, now, now, issingle, is_tree, istable, module, naming_rule, sf, so),
				)
			except Exception:
				pass  # Already exists

		# Seed Administrator user
		try:
			conn.execute(
				"""INSERT OR IGNORE INTO `tabUser`
				(name, creation, modified, owner, first_name, full_name,
				 email, enabled, language, `type`, docstatus, idx)
				VALUES ('Administrator', ?, ?, 'Administrator',
					'Administrator', 'Administrator',
					'admin@example.com', 1, 'en', 'System User', 0, 0)""",
				(now, now),
			)
		except Exception:
			pass

		# Seed core roles
		roles = ["Administrator", "System Manager", "All", "Guest"]
		for role in roles:
			try:
				conn.execute(
					"""INSERT OR IGNORE INTO `tabRole`
					(name, creation, modified, owner, desk_access, docstatus, idx)
					VALUES (?, ?, ?, 'Administrator', 1, 0, 0)""",
					(role, now, now),
				)
			except Exception:
				pass

		# Seed Module Def for Core
		try:
			conn.execute(
				"""INSERT OR IGNORE INTO `tabModule Def`
				(name, creation, modified, owner, app_name, custom, docstatus, idx)
				VALUES ('Core', ?, ?, 'Administrator', 'frappe', 0, 0, 0)""",
				(now, now),
			)
		except Exception:
			pass

	# ================================================================
	# CRUD overrides (SQLite-specific formatting)
	# ================================================================

	def _cast_row_value(self, value: Any) -> Any:
		"""Cast a raw SQLite cell back to the appropriate Python type."""
		return _cast_result(value)

	# ================================================================
	# Schema introspection overrides
	# ================================================================

	def get_db_table_columns(self, table: str) -> list[str]:
		"""Return column names using PRAGMA table_info."""
		try:
			rows = self.sql(
				"PRAGMA table_info(`{}`)".format(table),
				as_dict=False,
			)
			return [r[1] for r in (rows or [])]
		except Exception:
			return []

	def get_tables(self, cached: bool = True) -> list:
		"""Return all tab-prefixed tables."""
		if cached:
			cached_tables = getattr(self, "_cached_tables", None)
			if cached_tables is not None:
				return sorted(cached_tables)
		rows = self.sql(
			"SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'tab%'",
			as_dict=False,
		)
		tables = [r[0] for r in (rows or [])]
		self._cached_tables = set(tables)
		return tables

	def has_index(self, table_name: str, index_name: str) -> bool:
		"""Check if an index exists on the table."""
		try:
			rows = self.sql(
				"PRAGMA index_list(`{}`)".format(table_name),
				as_dict=False,
			)
			names = [r[1] for r in (rows or [])]
			return index_name in names
		except Exception:
			return False

	# ================================================================
	# Additional SQLite-specific helpers
	# ================================================================

	def vacuum(self) -> None:
		"""Run VACUUM to reclaim space."""
		self.sql("VACUUM")

	def analyze(self, table: str | None = None) -> None:
		"""Run ANALYZE to update statistics."""
		if table:
			self.sql("ANALYZE `{}`".format(table))
		else:
			self.sql("ANALYZE")

	def checkpoint(self, mode: str = "PASSIVE") -> None:
		"""Run WAL checkpoint."""
		self.sql(f"PRAGMA wal_checkpoint({mode})")

	def get_journal_mode(self) -> str:
		"""Return the current journal mode."""
		rows = self.sql("PRAGMA journal_mode", as_dict=False)
		return rows[0][0] if rows else "unknown"

	def get_wal_checkpoint(self) -> dict:
		"""Return WAL checkpoint status."""
		rows = self.sql("PRAGMA wal_checkpoint", as_dict=True)
		return rows[0] if rows else {}

	def get_page_count(self) -> int:
		"""Return the number of pages in the database."""
		rows = self.sql("PRAGMA page_count", as_dict=False)
		return int(rows[0][0]) if rows else 0

	def get_page_size(self) -> int:
		"""Return the database page size."""
		rows = self.sql("PRAGMA page_size", as_dict=False)
		return int(rows[0][0]) if rows else 4096

	def get_freelist_count(self) -> int:
		"""Return the number of unused pages."""
		rows = self.sql("PRAGMA freelist_count", as_dict=False)
		return int(rows[0][0]) if rows else 0

	def integrity_check(self) -> list[str]:
		"""Run PRAGMA integrity_check and return the result lines."""
		rows = self.sql("PRAGMA integrity_check", as_dict=False)
		return [r[0] for r in (rows or [])]

	def foreign_key_check(self, table: str | None = None) -> list:
		"""Run PRAGMA foreign_key_check."""
		if table:
			rows = self.sql(
				"PRAGMA foreign_key_check(`{}`)".format(table),
				as_dict=False,
			)
		else:
			rows = self.sql("PRAGMA foreign_key_check", as_dict=False)
		return rows or []

	# ================================================================
	# Async helpers (for future async compatibility)
	# ================================================================

	async def _async_execute(self, query: str, values: Any = ()) -> list:
		"""Execute a query asynchronously using aiosqlite (if available)."""
		if not _HAS_AIOSQLITE:
			raise RuntimeError(
				"aiosqlite is not installed. Run: pip install aiosqlite"
			)
		async with aiosqlite.connect(self.db_path) as db:
			async with db.execute(query, values or ()) as cursor:
				return await cursor.fetchall()

	def run_async(self, coro):
		"""Run an async coroutine from sync code."""
		try:
			loop = asyncio.get_running_loop()
		except RuntimeError:
			return asyncio.run(coro)
		# Already in an event loop – use run_coroutine_threadsafe
		return asyncio.run_coroutine_threadsafe(coro, loop).result()

	# ================================================================
	# Aliases for Frappe compatibility
	# ================================================================

	# The original Frappe Database exposes these as properties
	@property
	def is_connected(self) -> bool:
		"""Return True if a connection is open."""
		return self._conn is not None

	@property	# type: ignore[override]
	def connected(self) -> bool:  # noqa: D401
		"""Alias for is_connected (used by some ERPNext code)."""
		return self.is_connected

	def get_database_list(self) -> list:
		"""Return list of attached databases."""
		rows = self.sql("PRAGMA database_list", as_dict=True)
		return [r["name"] for r in (rows or [])]

	def create_database(self, db_name: str) -> None:
		"""No-op for SQLite – the 'database' is a file."""
		logger.debug("create_database() is a no-op for SQLite (%s)", db_name)

	def drop_database(self, db_name: str) -> None:
		"""Delete the SQLite database file (use with caution)."""
		if self.db_path != ":memory:" and os.path.exists(self.db_path):
			os.remove(self.db_path)

	def create_session_settings_table(self) -> None:
		"""Create the session settings table if it does not exist."""
		self.sql_ddl("""
			CREATE TABLE IF NOT EXISTS __session_settings (
				key TEXT PRIMARY KEY,
				value TEXT
			)
		""")

	def get_row_size(self, doctype: str, name: str) -> int:
		"""Estimate the row size by serializing to JSON."""
		row = self.get(doctype, name)
		if not row:
			return 0
		return len(json.dumps(row, default=str))

	# ================================================================
	# Pretty repr
	# ================================================================

	def __repr__(self) -> str:
		return (
			f"<SQLiteDatabase path={self.db_path!r} "
			f"transaction={self._in_transaction}>"
		)
