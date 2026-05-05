"""
Redis-backed JWT session management.

Replaces in-memory session store with Redis (Dragonfly-compatible).
Sessions are stored as Redis hashes with TTL.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import secrets
import time
from typing import Any, Optional

import frappe
from frappe.types import _dict

logger = logging.getLogger("frappe.sessions")

SESSION_KEY_PREFIX = "frappe_session:"


def _session_key(sid: str) -> str:
    return f"{SESSION_KEY_PREFIX}{sid}"


def generate_session_id() -> str:
    """Generate a cryptographically secure session ID."""
    return secrets.token_urlsafe(24)


def get_expiry_period() -> str:
    """Get session expiry from config (default 24 hours)."""
    return frappe.conf.get("session_expiry", "24:00:00")


def get_expiry_in_seconds() -> int:
    """Convert expiry period to seconds."""
    period = get_expiry_period()
    parts = period.split(":")
    hours = int(parts[0]) if parts else 24
    minutes = int(parts[1]) if len(parts) > 1 else 0
    return hours * 3600 + minutes * 60


# ─── Serialization helpers for session values ────────────────────────────────

def _serialize_session_value(value: Any) -> str:
    """Serialize a session value to a string for Redis hash storage."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _deserialize_session_value(value: str | bytes | None) -> Any:
    """Deserialize a session value from Redis hash storage."""
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if value == "true":
        return True
    if value == "false":
        return False
    try:
        return json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return value


# ─── Redis-backed session store ─────────────────────────────────────────────

async def get_session_async(sid: str) -> Optional[_dict]:
    """Get session from Redis by session ID."""
    from frappe.redis_client import get_redis_client

    redis = await get_redis_client()
    data = await redis.hgetall(_session_key(sid))
    if not data:
        return None
    return _dict({k: _deserialize_session_value(v) for k, v in data.items()})


async def set_session_async(
    sid: str, session_data: dict, expiry_seconds: int | None = None
) -> None:
    """Store session in Redis as a hash with TTL."""
    from frappe.redis_client import get_redis_client

    redis = await get_redis_client()
    key = _session_key(sid)
    # Store as hash
    for k, v in session_data.items():
        await redis.hset(key, k, _serialize_session_value(v))
    # Set TTL
    expiry = expiry_seconds or get_expiry_in_seconds()
    await redis.expire(key, expiry)


async def delete_session_async(sid: str) -> None:
    """Delete session from Redis."""
    from frappe.redis_client import get_redis_client

    redis = await get_redis_client()
    await redis.delete(_session_key(sid))


async def get_csrf_token_async(sid: str) -> str:
    """Get or create CSRF token for session."""
    from frappe.redis_client import get_redis_client

    redis = await get_redis_client()
    key = f"frappe_csrf:{sid}"
    token = await redis.get(key)
    if not token:
        token = secrets.token_hex(16)
        await redis.setex(key, get_expiry_in_seconds(), token)
    return token.decode() if isinstance(token, bytes) else token


# ─── Sync helper ────────────────────────────────────────────────────────────

def _run_sync(coro, timeout: float = 5.0):
    """Run an async coroutine from sync code, handling both sync and async contexts."""
    try:
        loop = asyncio.get_running_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)
    except RuntimeError:
        return asyncio.run(coro)


# ─── Public API ────────────────────────────────────────────────────────────

class Session:
    """Session object backed by Redis."""

    def __init__(
        self,
        user: str,
        resume: bool = False,
        full_name: str | None = None,
        user_type: str | None = None,
        **kwargs: Any,
    ):
        self.user = user
        self.resume = resume
        self.full_name = full_name or user
        self.user_type = user_type or "System User"
        self.session_country = kwargs.get("session_country")
        self.device = kwargs.get("device")
        self.ip = kwargs.get("ip")
        self.token = kwargs.get("token")
        self.sid = generate_session_id()
        self.data = _dict()

    def start(self) -> dict:
        """Start session and store in Redis."""
        session_data = {
            "user": self.user,
            "full_name": self.full_name,
            "user_type": self.user_type,
            "session_country": self.session_country or "",
            "device": self.device or "",
            "ip": self.ip or "",
            "token": self.token or "",
        }
        _run_sync(set_session_async(self.sid, session_data))
        return session_data


# ─── Sync wrappers for Frappe compatibility ──────────────────────────────────

def get(sid: str) -> Optional[_dict]:
    """Get session by ID (sync wrapper)."""
    return _run_sync(get_session_async(sid))


def start(user_data: dict | str) -> _dict:
    """Start a new session."""
    if isinstance(user_data, dict):
        user = user_data.get("user", "Guest")
    else:
        user = user_data

    full_name = user
    user_type = "System User"
    if user not in ("Guest", "Administrator"):
        try:
            full_name = frappe.db.get_value("User", user, "full_name") or user
        except Exception:
            pass
        try:
            user_type = frappe.db.get_value("User", user, "user_type") or "System User"
        except Exception:
            pass

    sid = generate_session_id()
    expiry_seconds = get_expiry_in_seconds()

    session_data = {
        "sid": sid,
        "user": user,
        "session_country": None,
        "session_expiry": get_expiry_period(),
        "full_name": full_name,
        "user_type": user_type,
        "data": {},
    }

    _run_sync(set_session_async(sid, session_data, expiry_seconds))

    frappe.local.session = _dict(session_data)
    frappe.local.user = user
    return frappe.local.session


def clear(sid: str | None = None) -> None:
    """Clear a session."""
    sid = sid or getattr(frappe.local.session, "sid", None)
    if sid:
        _run_sync(delete_session_async(sid))


def delete_session(sid: str | None = None, user: str | None = None) -> None:
    """Delete a session."""
    clear(sid)


def get_csrf_token() -> str | None:
    """Get CSRF token."""
    sid = getattr(frappe.local.session, "sid", None)
    if sid:
        return _run_sync(get_csrf_token_async(sid))
    return None
