"""PostgreSQL connection pool manager with health checks.

This module provides a standalone pool manager that can be used outside of the
``PostgreSQLDatabase`` class for advanced connection management, health checks,
and reconnection logic.
"""
from __future__ import annotations

import asyncio
import logging
import time
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

logger = logging.getLogger("frappe.database.postgres.pool")


class PostgresPoolManager:
    """Manages an asyncpg connection pool with health checks and reconnection.

    Typical usage::

        pm = PostgresPoolManager()
        pool = await pm.get_pool(dsn="postgresql://user:pass@host/db")
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT 1")

    Parameters
    ----------
    min_size : int
        Minimum number of connections in the pool (default 1).
    max_size : int
        Maximum number of connections in the pool (default 10).
    command_timeout : int
        Query command timeout in seconds (default 60).
    max_inactive_time : float
        Seconds before a connection is considered stale (default 300).
    health_check_interval : float
        Seconds between background health checks (default 30).
    """

    def __init__(
        self,
        min_size: int = 1,
        max_size: int = 10,
        command_timeout: int = 60,
        max_inactive_time: float = 300.0,
        health_check_interval: float = 30.0,
    ):
        self.min_size = min_size
        self.max_size = max_size
        self.command_timeout = command_timeout
        self.max_inactive_time = max_inactive_time
        self.health_check_interval = health_check_interval

        self._pool: Pool | None = None
        self._dsn: str | None = None
        self._pool_kwargs: dict[str, Any] = {}
        self._last_health_check: float = 0.0
        self._health_check_task: asyncio.Task | None = None
        self._closed: bool = False

    # ------------------------------------------------------------------
    # Pool lifecycle
    # ------------------------------------------------------------------

    async def get_pool(
        self,
        dsn: str | None = None,
        *,
        host: str = "localhost",
        port: int = 5432,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
        min_size: int | None = None,
        max_size: int | None = None,
        **kwargs,
    ) -> Pool:
        """Get or create a connection pool.

        If a pool already exists and is open, it is returned.
        If the DSN or connection parameters change, the old pool is closed
        and a new one is created.
        """
        if self._pool is not None and not self._pool._closed:
            # If same DSN, reuse
            if dsn and dsn == self._dsn:
                return self._pool
            if not dsn and self._pool_kwargs == kwargs:
                return self._pool
            # Close stale pool
            await self.close_all()

        min_size = min_size if min_size is not None else self.min_size
        max_size = max_size if max_size is not None else self.max_size

        if dsn:
            self._pool = await asyncpg.create_pool(
                dsn=dsn,
                min_size=min_size,
                max_size=max_size,
                command_timeout=self.command_timeout,
                init=self._init_connection,
                **kwargs,
            )
            self._dsn = dsn
        else:
            self._pool = await asyncpg.create_pool(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                min_size=min_size,
                max_size=max_size,
                command_timeout=self.command_timeout,
                init=self._init_connection,
                **kwargs,
            )
            self._pool_kwargs = kwargs

        self._closed = False
        self._last_health_check = time.monotonic()
        logger.info(
            "PostgreSQL pool created (min=%d, max=%d) for %s@%s:%s/%s",
            min_size,
            max_size,
            user or "?",
            host,
            port,
            database or "?",
        )

        # Start background health checks
        self._start_health_check()
        return self._pool

    @staticmethod
    async def _init_connection(conn: Connection) -> None:
        """Run on every new connection in the pool."""
        # Set application name for monitoring
        await conn.execute("SET application_name = 'frappe'")

    async def close_all(self) -> None:
        """Close the pool and cancel background tasks."""
        self._closed = True
        if self._health_check_task is not None:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None

        if self._pool is not None and not self._pool._closed:
            await self._pool.close()
            logger.info("PostgreSQL pool closed")
        self._pool = None
        self._dsn = None

    # ------------------------------------------------------------------
    # Health checks
    # ------------------------------------------------------------------

    def _start_health_check(self) -> None:
        """Start a background task that periodically checks pool health."""
        try:
            loop = asyncio.get_running_loop()
            self._health_check_task = loop.create_task(
                self._health_check_loop()
            )
        except RuntimeError:
            # No running loop – caller must manage health checks manually
            pass

    async def _health_check_loop(self) -> None:
        """Background loop that pings the pool."""
        while not self._closed:
            await asyncio.sleep(self.health_check_interval)
            try:
                healthy = await self.health_check()
                if not healthy:
                    logger.warning("Pool health check failed, reconnecting...")
                    await self._reconnect()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Health check error: %s", exc)

    async def health_check(self) -> bool:
        """Check that the pool can execute a simple query.

        Returns ``True`` if the pool is healthy, ``False`` otherwise.
        """
        if self._pool is None or self._pool._closed:
            return False
        try:
            async with self._pool.acquire() as conn:
                result = await conn.fetchval("SELECT 1")
                return result == 1
        except Exception as exc:
            logger.debug("Health check query failed: %s", exc)
            return False

    async def _reconnect(self) -> None:
        """Close the existing pool and recreate it with the same parameters."""
        old_pool = self._pool
        self._pool = None
        if old_pool is not None and not old_pool._closed:
            await old_pool.close()

        if self._dsn:
            await self.get_pool(dsn=self._dsn)
        else:
            # Re-create with stored kwargs
            await self.get_pool(**self._pool_kwargs)

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    async def acquire(self) -> Connection:
        """Acquire a connection from the pool."""
        pool = await self.get_pool()
        return await pool.acquire().__aenter__()

    async def release(self, conn: Connection) -> None:
        """Release a connection back to the pool."""
        if self._pool is not None:
            await self._pool.release(conn)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def is_healthy(self) -> bool:
        """Return ``True`` if the pool exists and is not closed."""
        return self._pool is not None and not self._pool._closed

    def get_pool_size(self) -> int:
        """Return the current number of connections in the pool."""
        if self._pool is None:
            return 0
        return self._pool.get_size()

    def get_idle_size(self) -> int:
        """Return the number of idle connections in the pool."""
        if self._pool is None:
            return 0
        return getattr(self._pool, "_idle_size", 0)

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "PostgresPoolManager":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close_all()

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} "
            f"min={self.min_size} max={self.max_size} "
            f"healthy={self.is_healthy()}>"
        )
