"""PostgreSQL-specific Database implementation.

This module provides a native PostgreSQL backend for the Frappe framework.
Unlike the SQLite backend, it does NOT translate SQL queries extensively.
Frappe's SQL is mostly standard and runs natively on PostgreSQL with only
minimal rewrites (backticks → double quotes, ? → $N placeholders).

Design decisions
----------------
*   Async-first using ``asyncpg``. All actual DB operations are async.
*   A background event loop runs asyncpg so that Frappe's synchronous API
    (``frappe.db.sql``, ``get_value``, etc.) works without changes.
*   Native JSONB columns for JSON/Geolocation/Code fields.
*   ``tsvector`` / ``tsquery`` for full-text search.
*   Sequences for autoincrement support (matching Frappe's naming).
*   ``tabDoctype`` naming is preserved exactly (quoted with double quotes).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
from datetime import date, datetime, time as dt_time, timedelta
from typing import Any

try:
    import asyncpg
    from asyncpg import Pool, Connection
    _HAS_ASYNCPG = True
except ImportError:
    asyncpg = None  # type: ignore
    Pool = None  # type: ignore
    Connection = None  # type: ignore
    _HAS_ASYNCPG = False

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
    _UNSET,
    RE_SQL_CALC_FOUND_ROWS,
    RE_FOUND_ROWS,
    RE_LIMIT_FOR_UPDATE,
)
from frappe.exceptions import DatabaseError, IntegrityError, OperationalError

logger = logging.getLogger("frappe.database.postgres")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_RE_BACKTICK = re.compile(r"`")
_RE_QUESTION_MARK = re.compile(r"\?")
_RE_IFNULL = re.compile(r"\bIFNULL\b", re.IGNORECASE)
_RE_INSERT_IGNORE = re.compile(r"\bINSERT\s+IGNORE\b", re.IGNORECASE)
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
_RE_DATE_FORMAT = re.compile(
    r"DATE_FORMAT\s*\(\s*([^,]+)\s*,\s*'([^']+)'\s*\)",
    re.IGNORECASE,
)
_RE_CAST_SIGNED = re.compile(
    r"CAST\s*\(\s*([^)]+)\s+AS\s+SIGNED\s*\)",
    re.IGNORECASE,
)
_RE_ON_DUPLICATE = re.compile(
    r"\bON\s+DUPLICATE\s+KEY\s+UPDATE\b",
    re.IGNORECASE,
)
_RE_AUTO_INCREMENT = re.compile(r"\bAUTO_INCREMENT\b", re.IGNORECASE)
_RE_ENGINE_INNODB = re.compile(
    r"\bENGINE\s*=\s*InnoDB\b", re.IGNORECASE
)
_RE_CHARACTER_SET = re.compile(
    r"\bCHARACTER\s+SET\s+\w+\b", re.IGNORECASE
)
_RE_COLLATE = re.compile(
    r"\bCOLLATE\s+\w+\b", re.IGNORECASE
)
_RE_LIMIT_OFFSET_MARIADB = re.compile(
    r"\bLIMIT\s+(\d+)\s*,\s*(\d+)\b", re.IGNORECASE
)

# Fieldtype → PostgreSQL type mapping
PG_TYPE_MAP: dict[str, str] = {
    "Data": "VARCHAR(255)",
    "Link": "VARCHAR(255)",
    "Dynamic Link": "VARCHAR(255)",
    "Password": "VARCHAR(255)",
    "Select": "VARCHAR(255)",
    "Read Only": "VARCHAR(255)",
    "Text": "TEXT",
    "Long Text": "TEXT",
    "Text Editor": "TEXT",
    "Code": "TEXT",
    "Markdown Editor": "TEXT",
    "HTML Editor": "TEXT",
    "Int": "INTEGER",
    "Integer": "INTEGER",
    "Check": "BOOLEAN DEFAULT FALSE",
    "Float": "NUMERIC(18,6)",
    "Currency": "NUMERIC(18,6)",
    "Percent": "NUMERIC(9,2)",
    "Date": "DATE",
    "Datetime": "TIMESTAMP",
    "Time": "TIME",
    "Color": "VARCHAR(7)",
    "Barcode": "VARCHAR(255)",
    "Attach": "VARCHAR(255)",
    "Attach Image": "VARCHAR(255)",
    "Signature": "TEXT",
    "JSON": "JSONB",
    "Geolocation": "JSONB",
    "Autocomplete": "VARCHAR(255)",
    "Rating": "NUMERIC(3,2)",
    "Duration": "NUMERIC(18,6)",
    "Phone": "VARCHAR(255)",
}

# MariaDB format → PostgreSQL TO_CHAR format (for DATE_FORMAT)
_MYSQL_TO_PG_FMT: dict[str, str] = {
    "%Y": "YYYY", "%y": "YY",
    "%m": "MM", "%c": "MM",
    "%d": "DD", "%e": "DD",
    "%H": "HH24", "%h": "HH12", "%I": "HH12",
    "%i": "MI",
    "%s": "SS", "%S": "SS",
    "%p": "AM",
    "%w": "D", "%W": "Day",
    "%M": "Month", "%b": "Mon",
    "%f": "US",
    "%j": "DDD",
    "%U": "WW",
    "%T": "HH24:MI:SS",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rewrite_placeholders(query: str) -> str:
    """Replace ? placeholders with PostgreSQL $1, $2, ... style."""
    counter = [0]

    def repl(match: re.Match) -> str:
        counter[0] += 1
        return f"${counter[0]}"

    return _RE_QUESTION_MARK.sub(repl, query)


def _rewrite_identifiers(query: str) -> str:
    """Replace MySQL backtick-quoted identifiers with PostgreSQL double quotes."""
    return _RE_BACKTICK.sub('"', query)


# ---------------------------------------------------------------------------
# Background event loop helper
# ---------------------------------------------------------------------------

class _AsyncLoopThread:
    """Manages a background thread with a dedicated asyncio event loop.

    This lets us call asyncpg from Frappe's synchronous codebase.
    """

    def __init__(self):
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._loop is not None and not self._loop.is_closed():
                return
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(
                target=self._loop.run_forever,
                daemon=True,
                name="asyncpg-bg-loop",
            )
            self._thread.start()

    def run(self, coro) -> Any:
        """Run a coroutine in the background loop and block for the result."""
        self.start()
        assert self._loop is not None
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=120)

    def stop(self) -> None:
        with self._lock:
            if self._loop is not None and not self._loop.is_closed():
                self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread is not None:
                self._thread.join(timeout=5)
                self._thread = None
            self._loop = None


# ---------------------------------------------------------------------------
# Cursor-like wrapper for asyncpg results
# ---------------------------------------------------------------------------

class _AsyncpgCursorProxy:
    """Wraps an asyncpg result so it looks like a DB-API cursor.

    The base Database class expects ``cursor.fetchall()`` and
    ``cursor.description``.  This proxy satisfies that interface.
    """

    def __init__(self, rows: list[tuple], columns: list[str]):
        self._rows = rows
        self._columns = columns
        # description is a list of 7-item sequences; we only need the name (index 0)
        self.description: list[tuple] = [(c,) for c in columns]
        self._idx = 0

    def fetchall(self) -> list[tuple]:
        return self._rows

    def fetchone(self) -> tuple | None:
        if self._idx < len(self._rows):
            row = self._rows[self._idx]
            self._idx += 1
            return row
        return None

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# PostgreSQLDatabase
# ---------------------------------------------------------------------------

class PostgreSQLDatabase(Database):
    """Native PostgreSQL backend for Frappe.

    Uses ``asyncpg`` for all actual I/O.  A background event loop translates
    Frappe's synchronous API calls into async operations so that existing
    ERPNext code requires zero changes.
    """

    # ================================================================
    # Construction & connection
    # ================================================================

    def __init__(
        self,
        host: str | None = "localhost",
        port: int | None = 5432,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
        charset: str = "utf8mb4",
        min_pool_size: int = 1,
        max_pool_size: int = 10,
        **kwargs,
    ):
        super().__init__(host, port, user, password, database, **kwargs)
        self.dialect = "postgresql"
        self.param_style = "numeric"  # $1, $2, ...

        self.host = host or "localhost"
        self.port = port or 5432
        self.user = user or os.getenv("PGUSER", "postgres")
        self.password = password or os.getenv("PGPASSWORD", "")
        self.database = database or os.getenv("PGDATABASE", "frappe")
        self.charset = charset
        self.min_pool_size = min_pool_size
        self.max_pool_size = max_pool_size
        self.command_timeout = kwargs.get("command_timeout", 60)

        self._pool: Pool | None = None
        self._conn: Connection | None = None
        self._in_transaction: bool = False
        self._savepoints: list[str] = []

        # Background loop for sync wrappers
        self._bg_loop = _AsyncLoopThread()

        # Schema readiness flag
        self._schema_ready = False

    # -- connection lifecycle (sync wrappers) ----------------------

    def connect(self) -> None:
        """Open the PostgreSQL connection pool."""
        self._bg_loop.run(self._connect_async())
        if not self._schema_ready:
            self._bg_loop.run(self._ensure_schema_async())
            self._schema_ready = True

    async def _connect_async(self) -> None:
        """Create the asyncpg connection pool."""
        if self._pool is not None:
            return
        self._pool = await asyncpg.create_pool(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
            min_size=self.min_pool_size,
            max_size=self.max_pool_size,
            command_timeout=self.command_timeout,
            init=self._init_connection,
        )
        logger.info(
            "PostgreSQL pool created: %s@%s:%s/%s",
            self.user, self.host, self.port, self.database,
        )

    @staticmethod
    async def _init_connection(conn: Connection) -> None:
        """Run on every new connection in the pool."""
        await conn.set_type_codec(
            "jsonb",
            encoder=json.dumps,
            decoder=json.loads,
            schema="pg_catalog",
        )

    def close(self) -> None:
        """Close the pool and stop the background loop."""
        if self._pool is not None:
            try:
                self._bg_loop.run(self._pool.close())
            except Exception:
                logger.debug("Error closing pool", exc_info=True)
            self._pool = None
        self._bg_loop.stop()
        self._in_transaction = False
        self._savepoints.clear()

    def _ensure_pool(self) -> Pool:
        if self._pool is None:
            self.connect()
        assert self._pool is not None
        return self._pool

    # ================================================================
    # SQL dialect translation
    # ================================================================

    def _translate_query(self, query: str) -> str:
        """Minimal MariaDB → PostgreSQL rewrites.

        Frappe's core SQL is standard enough to run natively.
        We only fix identifiers, placeholders, and a handful of functions.
        """
        # 1. Strip MariaDB-only hints
        query = RE_SQL_CALC_FOUND_ROWS.sub("", query)
        query = RE_FOUND_ROWS.sub("SELECT 0", query)
        query = RE_LIMIT_FOR_UPDATE.sub("", query)

        # 2. Convert backticks → double quotes
        query = _rewrite_identifiers(query)

        # 3. Convert ? placeholders → $1, $2, ...
        query = _rewrite_placeholders(query)

        # 4. IFNULL → COALESCE
        query = _RE_IFNULL.sub("COALESCE", query)

        # 5. INSERT IGNORE → INSERT ... ON CONFLICT DO NOTHING
        query = self._rewrite_insert_ignore(query)

        # 6. ON DUPLICATE KEY UPDATE → ON CONFLICT DO UPDATE
        query = self._rewrite_on_duplicate(query)

        # 7. Function rewrites
        query = self._rewrite_group_concat(query)
        query = self._rewrite_match_against(query)
        query = _RE_CAST_SIGNED.sub(r"CAST(\1 AS INTEGER)", query)
        query = self._rewrite_date_format(query)
        query = _RE_RAND.sub("RANDOM()", query)
        query = _RE_NOW.sub("NOW()", query)  # NOW() is native in PG
        query = _RE_CURDATE.sub("CURRENT_DATE", query)
        query = _RE_CURTIME.sub("CURRENT_TIME", query)
        query = _RE_UNIX_TIMESTAMP.sub("EXTRACT(EPOCH FROM NOW())", query)

        # 8. AUTO_INCREMENT → strip (PG uses SERIAL / IDENTITY)
        query = _RE_AUTO_INCREMENT.sub("", query)

        # 9. ENGINE=InnoDB, CHARACTER SET, COLLATE — strip
        query = _RE_ENGINE_INNODB.sub("", query)
        query = _RE_CHARACTER_SET.sub("", query)
        query = _RE_COLLATE.sub("", query)

        # 10. LIMIT offset, count → LIMIT count OFFSET offset
        query = self._rewrite_limit(query)

        return query

    # -- specific rewriters -----------------------------------------

    @staticmethod
    def _rewrite_insert_ignore(query: str) -> str:
        """INSERT IGNORE → INSERT ... ON CONFLICT DO NOTHING."""
        def repl(m: re.Match) -> str:
            return "INSERT"
        query = _RE_INSERT_IGNORE.sub(repl, query)
        if re.match(r"^\s*INSERT\b", query, re.IGNORECASE) and "ON CONFLICT" not in query.upper():
            query = query.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
        return query

    @staticmethod
    def _rewrite_on_duplicate(query: str) -> str:
        """ON DUPLICATE KEY UPDATE → ON CONFLICT(...) DO UPDATE SET."""
        if not _RE_ON_DUPLICATE.search(query):
            return query
        parts = _RE_ON_DUPLICATE.split(query, maxsplit=1)
        if len(parts) != 2:
            return query
        prefix = parts[0]
        assignments = parts[1].strip()
        # Default conflict target: 'name' (Frappe PK convention)
        conflict_target = "name"
        upsert = f'ON CONFLICT ("{conflict_target}") DO UPDATE SET {assignments}'
        return f"{prefix} {upsert}"

    @staticmethod
    def _rewrite_group_concat(query: str) -> str:
        """GROUP_CONCAT(... SEPARATOR 'x') → STRING_AGG(..., 'x')."""
        def repl(m: re.Match) -> str:
            expr = m.group(1).strip()
            sep = m.group(2)
            return f"STRING_AGG({expr}, '{sep}')"
        return _RE_GROUP_CONCAT.sub(repl, query)

    @staticmethod
    def _rewrite_match_against(query: str) -> str:
        """MATCH(col) AGAINST('term') → to_tsvector(col) @@ plainto_tsquery('term')."""
        def repl(m: re.Match) -> str:
            match_str = m.group(0)
            term_match = re.search(r"'([^']+)'", match_str)
            col_match = re.search(r"MATCH\s*\(\s*([^)]+)\s*\)", match_str)
            if term_match and col_match:
                term = term_match.group(1)
                col = col_match.group(1).strip()
                return f"to_tsvector('simple', {col}) @@ plainto_tsquery('simple', '{_sql_escape(term, percent=False)}')"
            return "TRUE"
        return _RE_MATCH_AGAINST.sub(repl, query)

    @staticmethod
    def _rewrite_date_format(query: str) -> str:
        """DATE_FORMAT(date, 'fmt') → TO_CHAR(date, 'pg_fmt')."""
        def repl(m: re.Match) -> str:
            expr = m.group(1).strip()
            fmt = m.group(2)
            pg_fmt = fmt
            for mysql, pg in _MYSQL_TO_PG_FMT.items():
                pg_fmt = pg_fmt.replace(mysql, pg)
            return f"TO_CHAR({expr}, '{pg_fmt}')"
        return _RE_DATE_FORMAT.sub(repl, query)

    @staticmethod
    def _rewrite_limit(query: str) -> str:
        """LIMIT offset, count → LIMIT count OFFSET offset."""
        def repl(m: re.Match) -> str:
            offset = m.group(1)
            count = m.group(2)
            return f"LIMIT {count} OFFSET {offset}"
        return _RE_LIMIT_OFFSET_MARIADB.sub(repl, query)

    # ================================================================
    # Query execution
    # ================================================================

    def _execute(self, query: str, values: Any) -> _AsyncpgCursorProxy:
        """Execute *query* with *values* and return a cursor-like proxy."""
        return self._bg_loop.run(self._execute_async(query, values))

    async def _execute_async(
        self,
        query: str,
        values: Any,
    ) -> _AsyncpgCursorProxy:
        """Core async execution using asyncpg."""
        pool = self._ensure_pool()
        if values is None:
            values = ()

        async with pool.acquire() as conn:
            if isinstance(values, dict):
                rows = await conn.fetch(query, **values)
            elif isinstance(values, (list, tuple)):
                rows = await conn.fetch(query, *values)
            else:
                rows = await conn.fetch(query, values)

            if not rows:
                return _AsyncpgCursorProxy([], [])

            columns = list(rows[0].keys())
            tuple_rows = [tuple(r) for r in rows]
            return _AsyncpgCursorProxy(tuple_rows, columns)

    def _execute_raw(self, sql: str) -> None:
        """Execute a raw SQL statement (BEGIN, COMMIT, etc.)."""
        self._bg_loop.run(self._execute_raw_async(sql))

    async def _execute_raw_async(self, sql: str) -> None:
        pool = self._ensure_pool()
        async with pool.acquire() as conn:
            await conn.execute(sql)

    # -- mogrify override -------------------------------------------

    def mogrify(self, query: str, values: Any) -> str:
        """Return the query with values bound (for debugging)."""
        if not values:
            return query
        if isinstance(values, dict):
            for k, v in values.items():
                placeholder = f"${k}"
                query = query.replace(placeholder, repr(_to_serializable(v)))
            return query
        if isinstance(values, (list, tuple)):
            parts = query.split("$")
            if len(parts) - 1 == len(values):
                result = parts[0]
                for i, val in enumerate(values):
                    result += repr(_to_serializable(val)) + parts[i + 1]
                return result
        # Fallback – manual replacement
        counter = 1
        for val in values if isinstance(values, (list, tuple)) else [values]:
            query = query.replace(f"${counter}", repr(_to_serializable(val)), 1)
            counter += 1
        return query

    # ================================================================
    # Async SQL API (native asyncpg interface)
    # ================================================================

    async def sql_async(
        self,
        query: str,
        values: Any = (),
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
        """Async version of sql()."""
        translated = self._translate_query(query)
        if explain:
            translated = f"EXPLAIN {translated}"
        if debug or self._debug:
            self._log_query(translated, values)
        if not run:
            return self.mogrify(translated, values)

        try:
            cursor = await self._execute_async(translated, values)
        except Exception as exc:
            self._handle_execution_error(exc, translated, ignore_ddl)
            return [] if ignore_ddl else None

        self.log_touched_tables(translated, None)

        if auto_commit and not self._in_transaction:
            await self.commit_async()

        if cursor is None:
            return None

        rows = cursor.fetchall()
        if not rows:
            return [] if (as_dict or as_list or pluck) else None

        columns = [desc[0] for desc in (cursor.description or [])]
        return self._format_results(
            rows, columns,
            as_dict=as_dict, as_list=as_list,
            pluck=pluck, update=update,
        )

    async def commit_async(self) -> None:
        """Async commit."""
        if self._in_transaction:
            await self._execute_raw_async("COMMIT")
            self._in_transaction = False
            self._savepoints.clear()
            self.query_cache.clear()

    async def rollback_async(
        self,
        save_point: str | None = None,
        chain: bool = False,
    ) -> None:
        """Async rollback."""
        if save_point:
            await self._execute_raw_async(f'ROLLBACK TO SAVEPOINT "{save_point}"')
            if save_point in self._savepoints:
                idx = self._savepoints.index(save_point)
                self._savepoints = self._savepoints[: idx + 1]
        elif self._in_transaction:
            await self._execute_raw_async("ROLLBACK")
            self._in_transaction = False
            self._savepoints.clear()
            self.query_cache.clear()
        if chain:
            await self.begin_async()

    async def begin_async(self, *, read_only: bool = False) -> None:
        """Async begin transaction."""
        if not self._in_transaction:
            mode = "READ ONLY" if read_only else "READ WRITE"
            await self._execute_raw_async(f"BEGIN {mode}")
            self._in_transaction = True
            self._read_only_mode = read_only
        self.touched_tables.clear()

    # ================================================================
    # Transaction overrides (sync, using background loop)
    # ================================================================

    def begin(self, *, read_only: bool = False) -> None:
        self._bg_loop.run(self.begin_async(read_only=read_only))

    def commit(self, *, chain: bool = False) -> None:
        with self._lock:
            if self._in_transaction:
                self._bg_loop.run(self.commit_async())
            if chain:
                self.begin()

    def rollback(
        self,
        *,
        save_point: str | None = None,
        chain: bool = False,
    ) -> None:
        with self._lock:
            self._bg_loop.run(self.rollback_async(save_point=save_point, chain=False))
        if chain:
            self.begin()

    def savepoint(self, save_point: str) -> None:
        with self._lock:
            self._execute_raw(f'SAVEPOINT "{save_point}"')
            self._savepoints.append(save_point)

    def release_savepoint(self, save_point: str) -> None:
        with self._lock:
            self._execute_raw(f'RELEASE SAVEPOINT "{save_point}"')
            if save_point in self._savepoints:
                self._savepoints.remove(save_point)

    # ================================================================
    # Schema management
    # ================================================================

    def create_table(
        self,
        doctype: str,
        fields: list[dict] | None = None,
    ) -> None:
        """Create a table for a DocType using PostgreSQL types."""
        self._bg_loop.run(self._create_table_async(doctype, fields))

    async def _create_table_async(
        self,
        doctype: str,
        fields: list[dict] | None = None,
    ) -> None:
        table = _scrub_table_name(doctype)
        if await self._table_exists_async(table):
            return

        columns = [
            '"name" VARCHAR(255) PRIMARY KEY',
            '"creation" TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
            '"modified" TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
            '"modified_by" VARCHAR(255)',
            '"owner" VARCHAR(255)',
            '"docstatus" SMALLINT DEFAULT 0',
            '"idx" INTEGER DEFAULT 0',
        ]

        if fields:
            for field in fields:
                fieldname = field.get("fieldname") if isinstance(field, dict) else getattr(field, "fieldname", None)
                fieldtype = field.get("fieldtype") if isinstance(field, dict) else getattr(field, "fieldtype", "Data")
                if not fieldname:
                    continue
                if fieldtype in ("Table", "Table MultiSelect", "Section Break",
                                 "Column Break", "Tab Break", "HTML", "Button", "Fold"):
                    continue
                pg_type = PG_TYPE_MAP.get(fieldtype, "VARCHAR(255)")
                columns.append(f'"{fieldname}" {pg_type}')

        col_sql = ",\n    ".join(columns)
        ddl = f'CREATE TABLE IF NOT EXISTS "{table}" (\n    {col_sql}\n)'
        await self._execute_raw_async(ddl)
        logger.info("Created table %s", table)

    def sync_doctype_table(self, doctype: str, fields: list[dict]) -> None:
        """Sync table schema — add missing columns."""
        self._bg_loop.run(self._sync_doctype_table_async(doctype, fields))

    async def _sync_doctype_table_async(
        self,
        doctype: str,
        fields: list[dict],
    ) -> None:
        table = _scrub_table_name(doctype)
        if not await self._table_exists_async(table):
            await self._create_table_async(doctype, fields)
            return

        existing = await self._get_db_table_columns_async(table)
        for field in fields:
            fieldname = field.get("fieldname") if isinstance(field, dict) else getattr(field, "fieldname", None)
            fieldtype = field.get("fieldtype") if isinstance(field, dict) else getattr(field, "fieldtype", "Data")
            if not fieldname or fieldname in existing:
                continue
            if fieldtype in ("Table", "Table MultiSelect", "Section Break",
                             "Column Break", "Tab Break", "HTML", "Button", "Fold"):
                continue
            pg_type = PG_TYPE_MAP.get(fieldtype, "VARCHAR(255)")
            ddl = f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS "{fieldname}" {pg_type}'
            try:
                await self._execute_raw_async(ddl)
                existing.append(fieldname)
            except Exception as exc:
                logger.debug("Column add skipped: %s", exc)

    def table_exists(self, doctype: str, cached: bool = True) -> bool:
        return self._bg_loop.run(self._table_exists_async(_scrub_table_name(doctype)))

    async def _table_exists_async(self, table: str) -> bool:
        rows = await self._fetchall(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = $1",
            (table,),
        )
        return bool(rows)

    def get_tables(self, cached: bool = True) -> list:
        if cached:
            cached_tables = getattr(self, "_cached_tables", None)
            if cached_tables is not None:
                return sorted(cached_tables)
        return self._bg_loop.run(self._get_tables_async())

    async def _get_tables_async(self) -> list:
        rows = await self._fetchall(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name LIKE 'tab%'",
            (),
        )
        tables = [r[0] for r in rows]
        self._cached_tables = set(tables)
        return tables

    def get_db_table_columns(self, table: str) -> list[str]:
        return self._bg_loop.run(self._get_db_table_columns_async(table))

    async def _get_db_table_columns_async(self, table: str) -> list[str]:
        rows = await self._fetchall(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = $1 "
            "ORDER BY ordinal_position",
            (table,),
        )
        return [r[0] for r in rows]

    def get_table_columns(self, doctype: str) -> list[str]:
        table = _scrub_table_name(doctype)
        return self.get_db_table_columns(table)

    def has_index(self, table_name: str, index_name: str) -> bool:
        return self._bg_loop.run(self._has_index_async(table_name, index_name))

    async def _has_index_async(self, table_name: str, index_name: str) -> bool:
        rows = await self._fetchall(
            "SELECT 1 FROM pg_indexes WHERE tablename = $1 AND indexname = $2",
            (table_name, index_name),
        )
        return bool(rows)

    def add_index(
        self,
        doctype: str,
        fields: list[str],
        index_name: str | None = None,
    ) -> None:
        table = _scrub_table_name(doctype)
        if not index_name:
            index_name = f"{table}_{'_'.join(fields)}_index"
        field_sql = ", ".join(f'"{f}"' for f in fields)
        ddl = f'CREATE INDEX IF NOT EXISTS "{index_name}" ON "{table}" ({field_sql})'
        self.sql_ddl(ddl)

    def add_unique(
        self,
        doctype: str,
        fields: list[str],
        constraint_name: str | None = None,
    ) -> None:
        table = _scrub_table_name(doctype)
        if not constraint_name:
            constraint_name = f"{table}_{'_'.join(fields)}_unique"
        field_sql = ", ".join(f'"{f}"' for f in fields)
        ddl = (
            f'ALTER TABLE "{table}" '
            f'ADD CONSTRAINT "{constraint_name}" UNIQUE ({field_sql})'
        )
        self.sql_ddl(ddl)

    # -- internal fetch helper --------------------------------------

    async def _fetchall(self, query: str, values: tuple = ()) -> list[tuple]:
        """Simple fetchall for internal queries."""
        pool = self._ensure_pool()
        async with pool.acquire() as conn:
            if values:
                rows = await conn.fetch(query, *values)
            else:
                rows = await conn.fetch(query)
            return [tuple(r) for r in rows]

    # ================================================================
    # CRUD operations (async-native + sync wrappers)
    # ================================================================

    # -- get_value / get_values -------------------------------------

    async def get_value_async(
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
        """Async get_value."""
        if cache:
            cached = self.query_cache.get(
                "get_value", doctype, filters, fieldname, as_dict, order_by,
            )
            if cached is not _UNSET:
                return cached

        if self._is_single(doctype):
            fields = _parse_field_expression(fieldname)
            result = await self._get_values_from_single_async(
                fields, filters, doctype, as_dict=as_dict, debug=debug,
            )
            if not result:
                return _dict() if as_dict else None
            if as_dict:
                return result[0]
            return result[0].get(fields[0]) if isinstance(result[0], dict) else result[0][0]

        result = await self.get_values_async(
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
            value = result[0][0] if result else None

        if cache:
            self.query_cache.set(
                value, "get_value", doctype, filters, fieldname, as_dict, order_by,
            )
        return value

    def get_value(self, *args, **kwargs) -> Any:
        """Sync wrapper for get_value_async."""
        return self._bg_loop.run(self.get_value_async(*args, **kwargs))

    async def get_values_async(
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
        """Async get_values."""
        if cache and limit == 1:
            cached = self.query_cache.get(
                "get_values", doctype, filters, fieldname, as_dict, order_by,
            )
            if cached is not _UNSET:
                return cached

        if self._is_single(doctype):
            fields = _parse_field_expression(fieldname)
            return await self._get_values_from_single_async(
                fields, filters, doctype, as_dict=as_dict, debug=debug,
                update=update, pluck=pluck, distinct=distinct,
            )

        # Use base class query builder (backticks + ?) then translate
        table = _scrub_table_name(doctype)
        fields = _parse_field_expression(fieldname)
        field_sql = self._build_field_clause(fields, distinct)
        where_sql, where_vals = self._build_where_clause(filters, table)

        query = f"SELECT {field_sql} FROM `{table}` {where_sql}"
        if order_by:
            query += f" ORDER BY {order_by}"
        if limit is not None:
            query += f" LIMIT {int(limit)}"

        # Translate to PostgreSQL syntax
        query = self._translate_query(query)

        result = await self.sql_async(
            query, tuple(where_vals),
            as_dict=as_dict, debug=debug, update=update,
            pluck=pluck,
        )
        if cache and limit == 1 and result is not None:
            self.query_cache.set(
                result, "get_values", doctype, filters, fieldname, as_dict, order_by,
            )
        return result if result is not None else []

    def get_values(self, *args, **kwargs) -> list | None:
        """Sync wrapper for get_values_async."""
        return self._bg_loop.run(self.get_values_async(*args, **kwargs))

    async def _get_values_from_single_async(
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
        """Async read values from tabSingles."""
        if not fields:
            fields = ["*"]
        if len(fields) == 1 and fields[0] == "*":
            rows = await self.sql_async(
                'SELECT field, value FROM "tabSingles" WHERE doctype=$1',
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

        placeholders = ",".join(f"${i + 2}" for i in range(len(fields)))
        rows = await self.sql_async(
            f'SELECT field, value FROM "tabSingles" '
            f'WHERE doctype=$1 AND field IN ({placeholders})',
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

    # -- set_value --------------------------------------------------

    async def set_value_async(
        self,
        doctype: str,
        name: str | None,
        fieldname: str | dict,
        value: Any = None,
        **kwargs,
    ) -> None:
        """Async set_value."""
        debug = kwargs.get("debug", False)
        table = _scrub_table_name(doctype)

        if isinstance(fieldname, dict):
            updates = {k: _to_serializable(v) for k, v in fieldname.items()}
        else:
            updates = {fieldname: _to_serializable(value)}

        # Build query using base class patterns, then translate
        set_clauses = [f"`{f}` = ?" for f in updates.keys()]
        set_values = list(updates.values())

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
        query = self._translate_query(query)
        await self.sql_async(query, tuple(set_values + where_vals), debug=debug)
        self.query_cache.invalidate_doctype(doctype)

    def set_value(self, *args, **kwargs) -> None:
        """Sync wrapper for set_value_async."""
        return self._bg_loop.run(self.set_value_async(*args, **kwargs))

    # -- delete -----------------------------------------------------

    async def delete_async(
        self,
        doctype: str,
        filters: Any = None,
        debug: bool = False,
        **kwargs,
    ) -> None:
        """Async delete."""
        table = _scrub_table_name(doctype)
        if filters is None:
            await self.sql_async(f'DELETE FROM "{table}"', debug=debug)
        else:
            where_sql, where_vals = self._build_where_clause(filters, table)
            query = f"DELETE FROM `{table}`{where_sql}"
            query = self._translate_query(query)
            await self.sql_async(query, tuple(where_vals), debug=debug)
        self.query_cache.invalidate_doctype(doctype)

    def delete(self, *args, **kwargs) -> None:
        """Sync wrapper for delete_async."""
        return self._bg_loop.run(self.delete_async(*args, **kwargs))

    # -- count ------------------------------------------------------

    async def count_async(
        self,
        dt: str,
        filters: Any = None,
        debug: bool = False,
        cache: bool = False,
        distinct: bool = True,
    ) -> int:
        """Async count."""
        if cache:
            cached = self.query_cache.get("count", dt, filters)
            if cached is not _UNSET:
                return cached

        table = _scrub_table_name(dt)
        where_sql, where_vals = self._build_where_clause(filters, table)
        query = f"SELECT COUNT(*) FROM `{table}`{where_sql}"
        query = self._translate_query(query)
        rows = await self.sql_async(query, tuple(where_vals), as_dict=False, debug=debug)
        result = rows[0][0] if rows else 0
        if cache:
            self.query_cache.set(result, "count", dt, filters)
        return int(result) if result else 0

    def count(self, *args, **kwargs) -> int:
        """Sync wrapper for count_async."""
        return self._bg_loop.run(self.count_async(*args, **kwargs))

    # -- exists -----------------------------------------------------

    async def exists_async(
        self,
        dt: str,
        dn: str | None = None,
        cache: bool = False,
        *,
        debug: bool = False,
    ) -> str | None:
        """Async exists."""
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
            query = f"SELECT `name` FROM `{table}` WHERE `name` = ? LIMIT 1"
            values = (dn,)
        else:
            query = f"SELECT `name` FROM `{table}` LIMIT 1"
            values = ()

        query = self._translate_query(query)
        rows = await self.sql_async(query, values, as_dict=False, debug=debug)
        value = rows[0][0] if rows else None
        if cache:
            self.query_cache.set(value, "exists", doctype, dn)
        return value

    def exists(self, *args, **kwargs) -> str | None:
        """Sync wrapper for exists_async."""
        return self._bg_loop.run(self.exists_async(*args, **kwargs))

    # -- sequence operations ----------------------------------------

    async def get_next_sequence_val_async(
        self,
        doctype: str,
        fieldname: str = "name",
    ) -> int:
        """Get next value from a sequence."""
        seq_name = f"seq_{_scrub_table_name(doctype)}_{fieldname}"
        rows = await self.sql_async(
            f"SELECT nextval(\"{seq_name}\")",
            as_dict=False,
        )
        return int(rows[0][0]) if rows else 0

    def get_next_sequence_val(self, *args, **kwargs) -> int:
        return self._bg_loop.run(self.get_next_sequence_val_async(*args, **kwargs))

    async def create_sequence_async(
        self,
        doctype: str,
        fieldname: str = "name",
    ) -> None:
        """Create a PostgreSQL sequence for autoincrement."""
        seq_name = f"seq_{_scrub_table_name(doctype)}_{fieldname}"
        await self.sql_async(
            f'CREATE SEQUENCE IF NOT EXISTS "{seq_name}"',
        )

    def create_sequence(self, *args, **kwargs) -> None:
        return self._bg_loop.run(self.create_sequence_async(*args, **kwargs))

    # ================================================================
    # Full-text search
    # ================================================================

    async def setup_search_index_async(
        self,
        doctype: str,
        fields: list[str],
    ) -> None:
        """Create tsvector index for full-text search."""
        table = _scrub_table_name(doctype)
        index_name = f"{table}_search_idx"

        # Build concatenated text expression
        concat_parts = " || ' ' || ".join(
            f'COALESCE("{f}"::text, \'\')' for f in fields
        )

        # Create GIN index on generated tsvector
        ddl = (
            f'CREATE INDEX IF NOT EXISTS "{index_name}" '
            f'ON "{table}" USING GIN '
            f'(to_tsvector(\'simple\', {concat_parts}))'
        )
        await self.sql_async(ddl, auto_commit=True)

    def setup_search_index(self, *args, **kwargs) -> None:
        return self._bg_loop.run(self.setup_search_index_async(*args, **kwargs))

    # ================================================================
    # Schema setup (internal tables)
    # ================================================================

    async def _ensure_schema_async(self) -> None:
        """Create all internal tables on first connect."""
        await self._create_table_doc_type_async()
        await self._create_table_doc_field_async()
        await self._create_table_doc_perm_async()
        await self._create_table_module_def_async()
        await self._create_table_user_async()
        await self._create_table_role_async()
        await self._create_table_version_async()
        await self._create_table_error_log_async()
        await self._create_table_scheduled_job_type_async()
        await self._create_table_default_value_async()
        await self._create_table_singles_async()
        await self._create_table_sequences_async()
        await self._insert_seed_data_async()

    async def _exec_schema_async(self, ddl: str) -> None:
        try:
            await self._execute_raw_async(ddl)
        except asyncpg.exceptions.DuplicateTableError:
            pass
        except asyncpg.exceptions.DuplicateObjectError:
            pass
        except Exception as exc:
            if "already exists" in str(exc).lower():
                return
            raise

    async def _create_table_doc_type_async(self) -> None:
        await self._exec_schema_async("""
            CREATE TABLE IF NOT EXISTS "tabDocType" (
                name              VARCHAR(255) PRIMARY KEY,
                creation          TIMESTAMP,
                modified          TIMESTAMP,
                modified_by       VARCHAR(255),
                owner             VARCHAR(255) DEFAULT 'Administrator',
                docstatus         SMALLINT DEFAULT 0,
                idx               INTEGER DEFAULT 0,
                search_fields     TEXT,
                issingle          BOOLEAN DEFAULT FALSE,
                is_tree           BOOLEAN DEFAULT FALSE,
                istable           BOOLEAN DEFAULT FALSE,
                editable_grid     BOOLEAN DEFAULT TRUE,
                track_changes     BOOLEAN DEFAULT TRUE,
                module            VARCHAR(255),
                autoname          VARCHAR(255),
                naming_rule       VARCHAR(255),
                title_field       VARCHAR(255),
                sort_field        VARCHAR(255) DEFAULT 'modified',
                sort_order        VARCHAR(255) DEFAULT 'DESC',
                description       TEXT,
                colour            VARCHAR(255),
                read_only         BOOLEAN DEFAULT FALSE,
                in_create         BOOLEAN DEFAULT FALSE,
                settings          JSONB,
                has_web_view      BOOLEAN DEFAULT FALSE,
                allow_guest_to_view BOOLEAN DEFAULT FALSE,
                index_web_pages_for_search BOOLEAN DEFAULT FALSE,
                engine            VARCHAR(255) DEFAULT 'InnoDB',
                custom            BOOLEAN DEFAULT FALSE,
                beta              BOOLEAN DEFAULT FALSE,
                is_virtual        BOOLEAN DEFAULT FALSE,
                _fields           JSONB,
                _permissions      JSONB,
                _links            JSONB,
                _actions          JSONB,
                _states           JSONB,
                _dashboard        JSONB
            )
        """)

    async def _create_table_doc_field_async(self) -> None:
        await self._exec_schema_async("""
            CREATE TABLE IF NOT EXISTS "tabDocField" (
                name              VARCHAR(255) PRIMARY KEY,
                creation          TIMESTAMP,
                modified          TIMESTAMP,
                modified_by       VARCHAR(255),
                owner             VARCHAR(255) DEFAULT 'Administrator',
                docstatus         SMALLINT DEFAULT 0,
                idx               INTEGER DEFAULT 0,
                fieldname         VARCHAR(255),
                label             VARCHAR(255),
                fieldtype         VARCHAR(255),
                options           TEXT,
                search_index      BOOLEAN DEFAULT FALSE,
                hidden            BOOLEAN DEFAULT FALSE,
                set_only_once     BOOLEAN DEFAULT FALSE,
                allow_in_quick_entry BOOLEAN DEFAULT FALSE,
                print_hide        BOOLEAN DEFAULT FALSE,
                report_hide       BOOLEAN DEFAULT FALSE,
                reqd              BOOLEAN DEFAULT FALSE,
                bold              BOOLEAN DEFAULT FALSE,
                in_global_search  BOOLEAN DEFAULT FALSE,
                collapsible       BOOLEAN DEFAULT FALSE,
                "unique"          BOOLEAN DEFAULT FALSE,
                no_copy           BOOLEAN DEFAULT FALSE,
                allow_on_submit   BOOLEAN DEFAULT FALSE,
                show_preview_popup BOOLEAN DEFAULT FALSE,
                trigger           VARCHAR(255),
                collapsible_depends_on TEXT,
                mandatory_depends_on TEXT,
                read_only_depends_on TEXT,
                depends_on        TEXT,
                description       TEXT,
                ignore_user_permissions BOOLEAN DEFAULT FALSE,
                allow_bulk_edit   BOOLEAN DEFAULT FALSE,
                "default"         TEXT,
                fetch_from        VARCHAR(255),
                fetch_if_empty    BOOLEAN DEFAULT FALSE,
                permlevel         INTEGER DEFAULT 0,
                ignore_xss_filter BOOLEAN DEFAULT FALSE,
                translatable      BOOLEAN DEFAULT FALSE,
                length            INTEGER DEFAULT 0,
                doc_parent        VARCHAR(255),
                _doc_parent       VARCHAR(255)
            )
        """)

    async def _create_table_doc_perm_async(self) -> None:
        await self._exec_schema_async("""
            CREATE TABLE IF NOT EXISTS "tabDocPerm" (
                name              VARCHAR(255) PRIMARY KEY,
                creation          TIMESTAMP,
                modified          TIMESTAMP,
                modified_by       VARCHAR(255),
                owner             VARCHAR(255) DEFAULT 'Administrator',
                docstatus         SMALLINT DEFAULT 0,
                idx               INTEGER DEFAULT 0,
                role              VARCHAR(255),
                "match"           VARCHAR(255),
                "read"            BOOLEAN DEFAULT TRUE,
                "write"           BOOLEAN DEFAULT TRUE,
                "create"          BOOLEAN DEFAULT TRUE,
                submit            BOOLEAN DEFAULT FALSE,
                cancel            BOOLEAN DEFAULT FALSE,
                "delete"          BOOLEAN DEFAULT TRUE,
                amend             BOOLEAN DEFAULT FALSE,
                report            BOOLEAN DEFAULT TRUE,
                export            BOOLEAN DEFAULT TRUE,
                import_data       BOOLEAN DEFAULT FALSE,
                share             BOOLEAN DEFAULT TRUE,
                print             BOOLEAN DEFAULT TRUE,
                email             BOOLEAN DEFAULT TRUE,
                if_owner          BOOLEAN DEFAULT FALSE,
                permlevel         INTEGER DEFAULT 0,
                doc_parent        VARCHAR(255),
                _doc_parent       VARCHAR(255)
            )
        """)

    async def _create_table_module_def_async(self) -> None:
        await self._exec_schema_async("""
            CREATE TABLE IF NOT EXISTS "tabModule Def" (
                name              VARCHAR(255) PRIMARY KEY,
                creation          TIMESTAMP,
                modified          TIMESTAMP,
                modified_by       VARCHAR(255),
                owner             VARCHAR(255) DEFAULT 'Administrator',
                docstatus         SMALLINT DEFAULT 0,
                idx               INTEGER DEFAULT 0,
                app_name          VARCHAR(255),
                custom            BOOLEAN DEFAULT FALSE,
                package           VARCHAR(255),
                restrict_to_domain VARCHAR(255)
            )
        """)

    async def _create_table_user_async(self) -> None:
        await self._exec_schema_async("""
            CREATE TABLE IF NOT EXISTS "tabUser" (
                name              VARCHAR(255) PRIMARY KEY,
                creation          TIMESTAMP,
                modified          TIMESTAMP,
                modified_by       VARCHAR(255),
                owner             VARCHAR(255) DEFAULT 'Administrator',
                docstatus         SMALLINT DEFAULT 0,
                idx               INTEGER DEFAULT 0,
                enabled           BOOLEAN DEFAULT TRUE,
                email             VARCHAR(255) UNIQUE,
                send_welcome_email BOOLEAN DEFAULT FALSE,
                first_name        VARCHAR(255),
                middle_name       VARCHAR(255),
                last_name         VARCHAR(255),
                full_name         VARCHAR(255),
                username          VARCHAR(255),
                language          VARCHAR(255),
                time_zone         VARCHAR(255),
                user_image        VARCHAR(255),
                role_profile_name VARCHAR(255),
                phone             VARCHAR(255),
                mobile_no         VARCHAR(255),
                location          VARCHAR(255),
                gender            VARCHAR(255),
                birth_date        DATE,
                interest          VARCHAR(255),
                desk_theme        VARCHAR(255),
                banner_image      VARCHAR(255),
                document_follow_notify BOOLEAN DEFAULT FALSE,
                follow_liked_documents BOOLEAN DEFAULT FALSE,
                follow_commented_documents BOOLEAN DEFAULT FALSE,
                follow_assigned_documents BOOLEAN DEFAULT FALSE,
                follow_shared_documents BOOLEAN DEFAULT FALSE,
                home_settings     JSONB,
                thread_notify     BOOLEAN DEFAULT FALSE,
                allowed_in_mentions BOOLEAN DEFAULT TRUE,
                simultaneous_sessions INTEGER DEFAULT 0,
                login_after       INTEGER DEFAULT 0,
                login_before      INTEGER DEFAULT 0,
                restrict_ip       VARCHAR(255),
                bypass_restrict_ip_check_if_2fa_enabled BOOLEAN DEFAULT FALSE,
                last_ip           VARCHAR(255),
                last_active       TIMESTAMP,
                last_login        VARCHAR(255),
                last_known_versions JSONB,
                new_password      VARCHAR(255),
                logout_all_sessions BOOLEAN DEFAULT FALSE,
                reset_password_key VARCHAR(255),
                last_password_reset_date DATE,
                redirect_url      VARCHAR(255),
                send_me_a_copy    BOOLEAN DEFAULT FALSE,
                unsuccessful_logins INTEGER DEFAULT 0,
                notify_email      VARCHAR(255),
                api_key           VARCHAR(255),
                api_secret        VARCHAR(255),
                "type"            VARCHAR(255) DEFAULT 'System User'
            )
        """)

    async def _create_table_role_async(self) -> None:
        await self._exec_schema_async("""
            CREATE TABLE IF NOT EXISTS "tabRole" (
                name              VARCHAR(255) PRIMARY KEY,
                creation          TIMESTAMP,
                modified          TIMESTAMP,
                modified_by       VARCHAR(255),
                owner             VARCHAR(255) DEFAULT 'Administrator',
                docstatus         SMALLINT DEFAULT 0,
                idx               INTEGER DEFAULT 0,
                desk_access       BOOLEAN DEFAULT TRUE,
                restrict_to_domain VARCHAR(255),
                _two_factor_auth  VARCHAR(255),
                home_page         VARCHAR(255)
            )
        """)

    async def _create_table_version_async(self) -> None:
        await self._exec_schema_async("""
            CREATE TABLE IF NOT EXISTS "tabVersion" (
                name              VARCHAR(255) PRIMARY KEY,
                creation          TIMESTAMP,
                modified          TIMESTAMP,
                modified_by       VARCHAR(255),
                owner             VARCHAR(255) DEFAULT 'Administrator',
                docstatus         SMALLINT DEFAULT 0,
                idx               INTEGER DEFAULT 0,
                ref_doctype       VARCHAR(255),
                docname           VARCHAR(255),
                data              JSONB
            )
        """)

    async def _create_table_error_log_async(self) -> None:
        await self._exec_schema_async("""
            CREATE TABLE IF NOT EXISTS "tabError Log" (
                name              VARCHAR(255) PRIMARY KEY,
                creation          TIMESTAMP,
                modified          TIMESTAMP,
                modified_by       VARCHAR(255),
                owner             VARCHAR(255) DEFAULT 'Administrator',
                docstatus         SMALLINT DEFAULT 0,
                idx               INTEGER DEFAULT 0,
                method            VARCHAR(255),
                error             TEXT,
                reference_doctype VARCHAR(255),
                reference_name    VARCHAR(255),
                seen              BOOLEAN DEFAULT FALSE,
                roll_up           BOOLEAN DEFAULT FALSE,
                trace_id          VARCHAR(255)
            )
        """)

    async def _create_table_scheduled_job_type_async(self) -> None:
        await self._exec_schema_async("""
            CREATE TABLE IF NOT EXISTS "tabScheduled Job Type" (
                name              VARCHAR(255) PRIMARY KEY,
                creation          TIMESTAMP,
                modified          TIMESTAMP,
                modified_by       VARCHAR(255),
                owner             VARCHAR(255) DEFAULT 'Administrator',
                docstatus         SMALLINT DEFAULT 0,
                idx               INTEGER DEFAULT 0,
                stopped           BOOLEAN DEFAULT FALSE,
                method            VARCHAR(255),
                frequency         VARCHAR(255),
                cron_format       VARCHAR(255),
                create_log        BOOLEAN DEFAULT TRUE,
                last_execution    TIMESTAMP
            )
        """)

    async def _create_table_default_value_async(self) -> None:
        await self._exec_schema_async("""
            CREATE TABLE IF NOT EXISTS "tabDefaultValue" (
                name              VARCHAR(255) PRIMARY KEY,
                creation          TIMESTAMP,
                modified          TIMESTAMP,
                modified_by       VARCHAR(255),
                owner             VARCHAR(255) DEFAULT 'Administrator',
                docstatus         SMALLINT DEFAULT 0,
                idx               INTEGER DEFAULT 0,
                defkey            VARCHAR(255),
                defvalue          TEXT,
                parent            VARCHAR(255),
                parenttype        VARCHAR(255),
                parentfield       VARCHAR(255)
            )
        """)

    async def _create_table_singles_async(self) -> None:
        await self._exec_schema_async("""
            CREATE TABLE IF NOT EXISTS "tabSingles" (
                doctype           VARCHAR(255) NOT NULL,
                field             VARCHAR(255) NOT NULL,
                value             TEXT,
                PRIMARY KEY (doctype, field)
            )
        """)

    async def _create_table_sequences_async(self) -> None:
        await self._exec_schema_async("""
            CREATE TABLE IF NOT EXISTS "tabSequence" (
                name              VARCHAR(255) PRIMARY KEY,
                creation          TIMESTAMP,
                modified          TIMESTAMP,
                modified_by       VARCHAR(255),
                owner             VARCHAR(255) DEFAULT 'Administrator',
                docstatus         SMALLINT DEFAULT 0,
                idx               INTEGER DEFAULT 0,
                current           INTEGER DEFAULT 0
            )
        """)

    async def _insert_seed_data_async(self) -> None:
        now = datetime.utcnow().isoformat()
        core_types = [
            ("DocType", False, False, False, "Core", None, "Core", "modified", "DESC"),
            ("DocField", False, False, True, "Core", None, "Core", "modified", "DESC"),
            ("DocPerm", False, False, True, "Core", None, "Core", "modified", "DESC"),
            ("Module Def", False, False, False, "Core", None, "Core", "modified", "DESC"),
            ("User", False, False, False, "Core", None, "Core", "modified", "DESC"),
            ("Role", False, False, False, "Core", None, "Core", "modified", "DESC"),
            ("Version", False, False, False, "Core", None, "Core", "modified", "DESC"),
            ("Error Log", False, False, False, "Core", None, "Core", "modified", "DESC"),
            ("DefaultValue", False, False, True, "Core", None, "Core", "modified", "DESC"),
        ]

        for name, issingle, is_tree, istable, module, naming_rule, mod, sf, so in core_types:
            try:
                await self.sql_async(
                    """
                    INSERT INTO "tabDocType"
                    (name, creation, modified, owner, issingle, is_tree,
                     istable, module, naming_rule, docstatus, idx,
                     sort_field, sort_order, engine)
                    VALUES ($1, $2, $3, 'Administrator', $4, $5, $6, $7, $8, 0, 0, $9, $10, 'InnoDB')
                    ON CONFLICT (name) DO NOTHING
                    """,
                    (name, now, now, issingle, is_tree, istable, module, naming_rule, sf, so),
                )
            except Exception:
                pass

        # Seed Administrator user
        try:
            await self.sql_async(
                """
                INSERT INTO "tabUser"
                (name, creation, modified, owner, first_name, full_name,
                 email, enabled, language, "type", docstatus, idx)
                VALUES ('Administrator', $1, $2, 'Administrator',
                    'Administrator', 'Administrator',
                    'admin@example.com', TRUE, 'en', 'System User', 0, 0)
                ON CONFLICT (name) DO NOTHING
                """,
                (now, now),
            )
        except Exception:
            pass

        # Seed core roles
        roles = ["Administrator", "System Manager", "All", "Guest"]
        for role in roles:
            try:
                await self.sql_async(
                    """
                    INSERT INTO "tabRole"
                    (name, creation, modified, owner, desk_access, docstatus, idx)
                    VALUES ($1, $2, $3, 'Administrator', TRUE, 0, 0)
                    ON CONFLICT (name) DO NOTHING
                    """,
                    (role, now, now),
                )
            except Exception:
                pass

        # Seed Module Def for Core
        try:
            await self.sql_async(
                """
                INSERT INTO "tabModule Def"
                (name, creation, modified, owner, app_name, custom, docstatus, idx)
                VALUES ('Core', $1, $2, 'Administrator', 'frappe', FALSE, 0, 0)
                ON CONFLICT (name) DO NOTHING
                """,
                (now, now),
            )
        except Exception:
            pass

    # ================================================================
    # CRUD overrides (PostgreSQL-specific formatting)
    # ================================================================

    def _cast_row_value(self, value: Any) -> Any:
        """Cast a raw PostgreSQL cell back to the appropriate Python type."""
        if value is None:
            return None
        if isinstance(value, (bool, int, float, str, bytes)):
            return value
        if isinstance(value, (datetime, date, dt_time)):
            return value
        if isinstance(value, (list, dict)):
            return value
        return _cast_result(value)

    # ================================================================
    # Additional PostgreSQL-specific helpers
    # ================================================================

    def vacuum(self, table: str | None = None) -> None:
        """Run VACUUM to reclaim space and update statistics."""
        if table:
            self.sql_ddl(f'VACUUM "{table}"')
        else:
            self.sql_ddl("VACUUM")

    def analyze(self, table: str | None = None) -> None:
        """Run ANALYZE to update statistics."""
        if table:
            self.sql_ddl(f'ANALYZE "{table}"')
        else:
            self.sql_ddl("ANALYZE")

    def get_database_size(self) -> int:
        """Return the database size in bytes."""
        rows = self.sql(
            "SELECT pg_database_size($1)",
            (self.database,),
            as_dict=False,
        )
        return int(rows[0][0]) if rows else 0

    def get_table_size(self, table: str) -> int:
        """Return the table size in bytes."""
        rows = self.sql(
            "SELECT pg_total_relation_size($1)",
            (table,),
            as_dict=False,
        )
        return int(rows[0][0]) if rows else 0

    def get_index_size(self, index_name: str) -> int:
        """Return the index size in bytes."""
        rows = self.sql(
            "SELECT pg_relation_size($1)",
            (index_name,),
            as_dict=False,
        )
        return int(rows[0][0]) if rows else 0

    def explain(self, query: str, values: Any = ()) -> list:
        """Return the EXPLAIN plan for a query."""
        translated = self._translate_query(query)
        return self.sql(f"EXPLAIN {translated}", values, as_dict=False)

    def get_pg_version(self) -> str:
        """Return the PostgreSQL server version."""
        rows = self.sql("SELECT version()", as_dict=False)
        return rows[0][0] if rows else "unknown"

    # ================================================================
    # Truncate
    # ================================================================

    def truncate(self, doctype: str) -> None:
        """Remove all rows from a table (DDL)."""
        table = _scrub_table_name(doctype)
        self.sql_ddl(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE')
        self.query_cache.invalidate_doctype(doctype)

    # ================================================================
    # Context manager support
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
