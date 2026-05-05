"""
Redis-backed rate limiting.

Uses Redis sorted sets for sliding window rate limiting.
Compatible with Dragonfly (drop-in Redis replacement).
"""

from __future__ import annotations

import asyncio
import functools
import time
from typing import Any, Callable, Optional

import frappe


class RateLimiter:
    """Sliding window rate limiter backed by Redis sorted sets."""

    def __init__(self, key: str, limit: int, window_seconds: int):
        self.key = f"frappe_rate_limit:{key}"
        self.limit = limit
        self.window = window_seconds

    async def is_allowed_async(self) -> bool:
        """Check if request is allowed under rate limit."""
        from frappe.redis_client import get_redis_client

        redis = await get_redis_client()
        now = time.time()
        window_start = now - self.window

        # Remove old entries outside the sliding window
        await redis.zremrangebyscore(self.key, 0, window_start)

        # Count entries in current window
        count = await redis.zcard(self.key)
        if count >= self.limit:
            return False

        # Add current request timestamp
        await redis.zadd(self.key, {str(now): now})
        # Set expiry on the key to auto-cleanup
        await redis.expire(self.key, self.window + 1)
        return True

    def is_allowed(self) -> bool:
        """Sync wrapper for is_allowed_async."""
        try:
            loop = asyncio.get_running_loop()
            future = asyncio.run_coroutine_threadsafe(self.is_allowed_async(), loop)
            return future.result(timeout=5)
        except RuntimeError:
            return asyncio.run(self.is_allowed_async())

    async def get_retry_after_async(self) -> int:
        """Get seconds until next request is allowed."""
        from frappe.redis_client import get_redis_client

        redis = await get_redis_client()
        now = time.time()
        window_start = now - self.window

        # Remove old entries
        await redis.zremrangebyscore(self.key, 0, window_start)

        # Get oldest entry in window
        entries = await redis.zrange(self.key, 0, 0, withscores=True)
        if not entries:
            return 0
        oldest = entries[0][1]
        return max(0, int(oldest + self.window - now))

    def get_retry_after(self) -> int:
        """Sync wrapper for get_retry_after_async."""
        try:
            loop = asyncio.get_running_loop()
            future = asyncio.run_coroutine_threadsafe(self.get_retry_after_async(), loop)
            return future.result(timeout=5)
        except RuntimeError:
            return asyncio.run(self.get_retry_after_async())


# ─── Decorator ─────────────────────────────────────────────────────────────

def rate_limit(
    key_prefix: str,
    limit: int,
    window: int,
    key_func: Optional[Callable[[], str]] = None,
    exempt_user: Optional[str] = None,
) -> Callable:
    """Rate limit decorator using Redis."""

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            user = frappe.session.user if frappe.session else "Guest"
            if exempt_user and user == exempt_user:
                return fn(*args, **kwargs)

            key = key_func() if key_func else f"{key_prefix}:{user}"
            rl = RateLimiter(key, limit, window)
            if not rl.is_allowed():
                retry = rl.get_retry_after()
                from frappe.exceptions import RateLimitExceededError

                raise RateLimitExceededError(
                    f"Rate limit exceeded. Retry after {retry} seconds."
                )

            return fn(*args, **kwargs)

        return wrapper

    return decorator


# Pre-configured rate limiters
login_rate_limit = functools.partial(rate_limit, "login", 5, 60)
api_rate_limit = functools.partial(rate_limit, "api", 1000, 60)
guest_rate_limit = functools.partial(rate_limit, "guest", 100, 60)


# ─── Utility functions ─────────────────────────────────────────────────────

def _run_sync(coro, timeout: float = 5.0):
    """Run an async coroutine from sync code, handling both sync and async contexts."""
    try:
        loop = asyncio.get_running_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)
    except RuntimeError:
        return asyncio.run(coro)


def clear_all_limits() -> None:
    """Clear all rate limit keys."""

    async def _clear() -> None:
        from frappe.redis_client import get_redis_client

        redis = await get_redis_client()
        keys = await redis.keys("frappe_rate_limit:*")
        if keys:
            await redis.delete(*keys)

    _run_sync(_clear(), timeout=10)


def get_limit_info(key_prefix: str, user: Optional[str] = None) -> dict:
    """Get current rate limit status."""

    async def _info() -> dict:
        from frappe.redis_client import get_redis_client

        redis = await get_redis_client()
        key = f"frappe_rate_limit:{key_prefix}:{user or frappe.session.user}"
        count = await redis.zcard(key)
        ttl = await redis.ttl(key)
        return {"count": count, "ttl": ttl, "key": key}

    return _run_sync(_info())
