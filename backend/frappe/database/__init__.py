"""Frappe database layer - drop-in replacement for frappe.db.*

This module provides the factory function to get a database instance.
All ERPNext code calls frappe.db.* methods; we provide SQLite-backed and
PostgreSQL-backed implementations that match the original MariaDB API signatures exactly.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from .database import Database as DatabaseType

logger = logging.getLogger(__name__)

# Module-level reference for the current database instance
# This is set by frappe.init() and used throughout the framework
db: "DatabaseType | None" = None


# Supported database backends
SUPPORTED_BACKENDS = {"sqlite", "postgres", "postgresql"}


def get_db(
	host=None,
	port=None,
	user=None,
	password=None,
	database=None,
	**kwargs,
) -> "DatabaseType":
	"""Return a Database instance. For SQLite, host/user/password are ignored.

	Parameters
	----------
	host : str, optional
		Hostname (ignored for SQLite).
	port : int, optional
		Port number (ignored for SQLite).
	user : str, optional
		Username (ignored for SQLite).
	password : str, optional
		Password (ignored for SQLite).
	database : str, optional
		Path to SQLite database file. Defaults to ':memory:' or
		the value from kwargs['db_name'].
	**kwargs : dict
		Additional options including:
		  - backend: 'sqlite' (default) or future backends
		  - db_name: alias for database
		  - db_path: path to SQLite file
		  - read_only: open in read-only mode
		  - synchronous: SQLite PRAGMA synchronous value
		  - journal_mode: SQLite PRAGMA journal_mode value

	Returns
	-------
	Database
		An instance of the appropriate Database subclass.
	"""
	backend = (kwargs.get("backend") or "sqlite").lower()

	if backend not in SUPPORTED_BACKENDS:
		raise ValueError(
			f"Unsupported database backend: {backend!r}. "
			f"Supported: {SUPPORTED_BACKENDS}"
		)

	# Resolve database path
	db_path = kwargs.get("db_path") or database or kwargs.get("db_name") or ":memory:"

	# Remove backend from kwargs to avoid passing it through
	driver_kwargs = {k: v for k, v in kwargs.items() if k != "backend"}

	if backend == "sqlite":
		from .sqlite.database import SQLiteDatabase

		return SQLiteDatabase(
			host=host,
			port=port,
			user=user,
			password=password,
			database=db_path,
			**driver_kwargs,
		)

	if backend in ("postgres", "postgresql"):
		from .postgres.database import PostgreSQLDatabase

		return PostgreSQLDatabase(
			host=host or "localhost",
			port=port,
			user=user,
			password=password,
			database=database or driver_kwargs.get("db_name"),
			**driver_kwargs,
		)

	# Fallback – should never reach here due to the check above
	raise RuntimeError(f"Backend {backend!r} registered but no constructor available")
