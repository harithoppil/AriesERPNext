"""
Redis-backed pub/sub for Frappe real-time messaging.

Replaces in-memory pub/sub with Redis (Dragonfly-compatible).
Supports: publish, subscribe, room-based messaging, user-targeted events.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Coroutine, Optional

import frappe
from frappe.types import _dict

logger = logging.getLogger("frappe.realtime")

# Key prefixes for namespacing
PUBSUB_CHANNEL_PREFIX = "frappe:pubsub"
ROOM_PREFIX = "frappe:room"
USER_PREFIX = "frappe:user"


# ─── Async API ─────────────────────────────────────────────────────────────

async def publish_async(
    event: str,
    message: dict,
    room: str | None = None,
    user: str | None = None,
    doctype: str | None = None,
    docname: str | None = None,
) -> int:
    """Publish a real-time event to Redis pub/sub.

    Returns the number of clients that received the message.
    """
    from frappe.redis_client import get_redis_client

    redis = await get_redis_client()
    payload = json.dumps({
        "event": event,
        "message": message,
        "room": room,
        "user": user,
        "doctype": doctype,
        "docname": docname,
    }, default=str)

    recipients = []
    if room:
        recipients.append(f"{ROOM_PREFIX}:{room}")
    if user:
        recipients.append(f"{USER_PREFIX}:{user}")
    if doctype and docname:
        recipients.append(f"{ROOM_PREFIX}:{doctype}:{docname}")
    if not recipients:
        recipients.append(f"{PUBSUB_CHANNEL_PREFIX}:global")

    total_receivers = 0
    for channel in recipients:
        total_receivers += await redis.publish(channel, payload)
    return total_receivers


async def get_user_room_async(user: str) -> str:
    """Get the room name for a user."""
    return f"{USER_PREFIX}:{user}"


async def get_doc_room_async(doctype: str, docname: str) -> str:
    """Get the room name for a document."""
    return f"{ROOM_PREFIX}:{doctype}:{docname}"


# ─── Subscription helpers ────────────────────────────────────────────────────

class RealtimeSubscriber:
    """Async Redis pub/sub subscriber for real-time events."""

    def __init__(self):
        self._pubsub: Any = None
        self._channels: set[str] = set()
        self._running = False
        self._callbacks: dict[str, list[Callable[[dict], Coroutine[Any, Any, None]]]] = {}

    async def connect(self) -> None:
        """Connect to Redis pub/sub."""
        from frappe.redis_client import get_redis_client

        redis = await get_redis_client()
        self._pubsub = redis.pubsub()
        self._running = True
        logger.debug("RealtimeSubscriber connected")

    async def subscribe(self, *channels: str) -> None:
        """Subscribe to one or more channels."""
        if not self._pubsub:
            await self.connect()
        await self._pubsub.subscribe(*channels)
        self._channels.update(channels)
        logger.debug("Subscribed to channels: %s", channels)

    async def unsubscribe(self, *channels: str) -> None:
        """Unsubscribe from one or more channels."""
        if self._pubsub:
            await self._pubsub.unsubscribe(*channels)
            self._channels.difference_update(channels)
            logger.debug("Unsubscribed from channels: %s", channels)

    async def listen(self) -> None:
        """Listen for messages and dispatch to callbacks."""
        if not self._pubsub:
            raise RuntimeError("Not connected. Call connect() first.")
        async for message in self._pubsub.listen():
            if not self._running:
                break
            if message["type"] == "message":
                channel = message["channel"]
                try:
                    data = json.loads(message["data"])
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON in pub/sub message: %s", message["data"])
                    continue

                # Dispatch to channel-specific callbacks
                for callback in self._callbacks.get(channel, []):
                    try:
                        await callback(data)
                    except Exception:
                        logger.exception("Error in pub/sub callback for channel %s", channel)

                # Dispatch to global callbacks
                for callback in self._callbacks.get("*", []):
                    try:
                        await callback(data)
                    except Exception:
                        logger.exception("Error in global pub/sub callback")

    def on(self, channel: str, callback: Callable[[dict], Coroutine[Any, Any, None]]) -> None:
        """Register a callback for a channel."""
        if channel not in self._callbacks:
            self._callbacks[channel] = []
        self._callbacks[channel].append(callback)

    def off(self, channel: str, callback: Callable[[dict], Coroutine[Any, Any, None]] | None = None) -> None:
        """Remove a callback from a channel. If callback is None, remove all."""
        if channel in self._callbacks:
            if callback is None:
                self._callbacks[channel].clear()
            else:
                self._callbacks[channel] = [c for c in self._callbacks[channel] if c is not callback]

    async def disconnect(self) -> None:
        """Disconnect from Redis pub/sub."""
        self._running = False
        if self._pubsub:
            await self._pubsub.close()
            self._pubsub = None
            logger.debug("RealtimeSubscriber disconnected")


# ─── Sync API wrappers ─────────────────────────────────────────────────────

def _run_sync(coro, timeout: float = 5.0):
    """Run an async coroutine from sync code, handling both sync and async contexts."""
    try:
        loop = asyncio.get_running_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)
    except RuntimeError:
        return asyncio.run(coro)


def publish(
    event: str,
    message: dict,
    room: str | None = None,
    user: str | None = None,
    doctype: str | None = None,
    docname: str | None = None,
) -> int:
    """Publish a real-time event (sync wrapper)."""
    return _run_sync(
        publish_async(
            event=event,
            message=message,
            room=room,
            user=user,
            doctype=doctype,
            docname=docname,
        )
    )


def get_user_room(user: str) -> str:
    """Get the room name for a user (sync wrapper)."""
    return f"{USER_PREFIX}:{user}"


def get_doc_room(doctype: str, docname: str) -> str:
    """Get the room name for a document (sync wrapper)."""
    return f"{ROOM_PREFIX}:{doctype}:{docname}"


# ─── Frappe-compatible aliases ─────────────────────────────────────────────

# Alias for existing Frappe code that calls publish_realtime()
def publish_realtime(
    event: str,
    message: dict | None = None,
    room: str | None = None,
    user: str | None = None,
    doctype: str | None = None,
    docname: str | None = None,
    after_commit: bool = False,
) -> int:
    """Publish a real-time event. Compatible with original Frappe API."""
    if after_commit:
        # TODO: Add to deferred queue for post-commit publishing
        pass
    return publish(
        event=event,
        message=message or {},
        room=room,
        user=user,
        doctype=doctype,
        docname=docname,
    )


def publish_progress(
    percent: int,
    title: str | None = None,
    description: str | None = None,
    doctype: str | None = None,
    docname: str | None = None,
) -> int:
    """Publish a progress update event."""
    return publish_realtime(
        event="progress",
        message={
            "percent": percent,
            "title": title,
            "description": description,
        },
        doctype=doctype,
        docname=docname,
    )


def get_site_room() -> str:
    """Get the global site room."""
    return f"{PUBSUB_CHANNEL_PREFIX}:global"
