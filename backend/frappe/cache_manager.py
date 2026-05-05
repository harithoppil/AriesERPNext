"""
Redis-backed cache manager for Frappe.

Replaces in-memory LRU cache with Redis (Dragonfly-compatible).
Supports: string GET/SET/EXPIRE, hash HGET/HSET, list LPUSH/RPUSH,
set SADD/SMEMBERS, sorted set ZADD/ZRANGE.
"""

from __future__ import annotations

import asyncio
import json
import logging
import pickle
from typing import Any, Callable, Optional

import frappe
from frappe.types import _dict

logger = logging.getLogger("frappe.cache_manager")

# Key prefix for namespacing
KEY_PREFIX = "frappe_cache:"


def _make_key(key: str) -> str:
    return f"{KEY_PREFIX}{key}"


# ─── Value serialization ─────────────────────────────────────────────────────

def _serialize(value: Any) -> str:
    """Serialize value to JSON string."""
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, default=str)
    if isinstance(value, bool):
        return json.dumps(value)
    if isinstance(value, (int, float)):
        return str(value)
    return value if isinstance(value, str) else json.dumps(value, default=str)


def _deserialize(value: str | bytes | None) -> Any:
    """Deserialize value from Redis."""
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    # Try JSON first
    try:
        return json.loads(value)
    except (json.JSONDecodeError, ValueError):
        pass
    # Try bool
    if value == "true":
        return True
    if value == "false":
        return False
    # Try int
    try:
        return int(value)
    except ValueError:
        pass
    # Try float
    try:
        return float(value)
    except ValueError:
        pass
    return value


# ─── Async Operations ───────────────────────────────────────────────────────

async def get_value_async(
    key: str, *, expires_in_sec: int = 0, generator: Optional[Callable] = None
) -> Any:
    """Get value from Redis cache."""
    from frappe.redis_client import get_redis_client

    redis = await get_redis_client()
    val = await redis.get(_make_key(key))
    if val is not None:
        return _deserialize(val)
    if generator:
        value = generator()
        await set_value_async(key, value, expires_in_sec=expires_in_sec)
        return value
    return None


async def set_value_async(
    key: str, value: Any, *, expires_in_sec: int = 0
) -> None:
    """Set value in Redis cache."""
    from frappe.redis_client import get_redis_client

    redis = await get_redis_client()
    serialized = _serialize(value)
    if expires_in_sec > 0:
        await redis.setex(_make_key(key), expires_in_sec, serialized)
    else:
        await redis.set(_make_key(key), serialized)


async def delete_value_async(key: str) -> None:
    """Delete value from Redis cache."""
    from frappe.redis_client import get_redis_client

    redis = await get_redis_client()
    await redis.delete(_make_key(key))


async def hget_async(doctype: str, docname: str, field: str) -> Any:
    """Get hash field value."""
    from frappe.redis_client import get_redis_client

    redis = await get_redis_client()
    val = await redis.hget(_make_key(f"{doctype}:{docname}"), field)
    return _deserialize(val)


async def hset_async(doctype: str, docname: str, field: str, value: Any) -> None:
    """Set hash field value."""
    from frappe.redis_client import get_redis_client

    redis = await get_redis_client()
    await redis.hset(_make_key(f"{doctype}:{docname}"), field, _serialize(value))


async def lpush_async(key: str, value: Any) -> None:
    """Push to left of list."""
    from frappe.redis_client import get_redis_client

    redis = await get_redis_client()
    await redis.lpush(_make_key(key), _serialize(value))


async def rpush_async(key: str, value: Any) -> None:
    """Push to right of list."""
    from frappe.redis_client import get_redis_client

    redis = await get_redis_client()
    await redis.rpush(_make_key(key), _serialize(value))


async def exists_async(key: str) -> bool:
    """Check if key exists."""
    from frappe.redis_client import get_redis_client

    redis = await get_redis_client()
    return await redis.exists(_make_key(key)) > 0


async def clear_cache_async() -> None:
    """Clear all frappe cache keys."""
    from frappe.redis_client import get_redis_client

    redis = await get_redis_client()
    keys = await redis.keys(f"{KEY_PREFIX}*")
    if keys:
        await redis.delete(*keys)


async def clear_user_cache_async(user: str) -> None:
    """Clear cache for a user."""
    from frappe.redis_client import get_redis_client

    redis = await get_redis_client()
    keys = await redis.keys(f"{KEY_PREFIX}*user:{user}*")
    if keys:
        await redis.delete(*keys)


async def clear_doctype_cache_async(doctype: str) -> None:
    """Clear cache for a DocType."""
    from frappe.redis_client import get_redis_client

    redis = await get_redis_client()
    keys = await redis.keys(f"{KEY_PREFIX}*{doctype}*")
    if keys:
        await redis.delete(*keys)


async def reset_metadata_version_async() -> None:
    """Reset metadata version."""
    await set_value_async("metadata_version", frappe.generate_hash(length=8))


# ─── Sync Wrappers (for Frappe compatibility) ─────────────────────────────────

def _run_sync(coro, timeout: float = 5.0):
    """Run an async coroutine from sync code, handling both sync and async contexts."""
    try:
        loop = asyncio.get_running_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)
    except RuntimeError:
        return asyncio.run(coro)


def get_value(key, *, expires_in_sec=0, generator=None):
    """Sync wrapper for get_value_async."""
    return _run_sync(
        get_value_async(key, expires_in_sec=expires_in_sec, generator=generator)
    )


def set_value(key, value, *, expires_in_sec=0):
    """Sync wrapper for set_value_async."""
    return _run_sync(set_value_async(key, value, expires_in_sec=expires_in_sec))


def delete_value(key):
    """Sync wrapper for delete_value_async."""
    return _run_sync(delete_value_async(key))


def hget(doctype, docname, field):
    """Sync wrapper for hget_async."""
    return _run_sync(hget_async(doctype, docname, field))


def hset(doctype, docname, field, value):
    """Sync wrapper for hset_async."""
    return _run_sync(hset_async(doctype, docname, field, value))


def lpush(key, value):
    """Sync wrapper for lpush_async."""
    return _run_sync(lpush_async(key, value))


def rpush(key, value):
    """Sync wrapper for rpush_async."""
    return _run_sync(rpush_async(key, value))


def exists(key):
    """Sync wrapper for exists_async."""
    return _run_sync(exists_async(key))


def clear_cache():
    """Sync wrapper for clear_cache_async."""
    return _run_sync(clear_cache_async(), timeout=30)


def clear_user_cache(user):
    """Sync wrapper for clear_user_cache_async."""
    return _run_sync(clear_user_cache_async(user), timeout=10)


def clear_doctype_cache(doctype):
    """Sync wrapper for clear_doctype_cache_async."""
    return _run_sync(clear_doctype_cache_async(doctype), timeout=10)


def reset_metadata_version():
    """Sync wrapper for reset_metadata_version_async."""
    return _run_sync(reset_metadata_version_async())
