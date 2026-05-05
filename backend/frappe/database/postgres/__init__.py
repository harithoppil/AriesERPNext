"""PostgreSQL database backend for Frappe.

Exports the main ``PostgreSQLDatabase`` class and the ``PostgresPoolManager``
for standalone pool management. Imported lazily to avoid hard dependency on asyncpg.
"""
from __future__ import annotations

def __getattr__(name: str):
    """Lazy import to avoid loading asyncpg at module import time."""
    if name == "PostgreSQLDatabase":
        from frappe.database.postgres.database import PostgreSQLDatabase
        return PostgreSQLDatabase
    if name == "PostgresPoolManager":
        from frappe.database.postgres.pool import PostgresPoolManager
        return PostgresPoolManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["PostgreSQLDatabase", "PostgresPoolManager"]
