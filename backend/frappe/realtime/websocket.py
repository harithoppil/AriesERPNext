"""
Native FastAPI WebSocket connection manager.

Replaces Socket.io with FastAPI's built-in WebSocket support.
Uses Redis pub/sub for cross-worker event broadcasting.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Dict, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("frappe.realtime.websocket")

# In-memory connection registry (per-worker)
# For cross-worker, use Redis pub/sub
_connections: Dict[str, WebSocket] = {}  # sid -> WebSocket
_rooms: Dict[str, Set[str]] = {}  # room -> set of sids


class WebSocketManager:
    """Manages WebSocket connections and room subscriptions."""

    async def connect(self, websocket: WebSocket, sid: str) -> None:
        """Accept connection and register."""
        await websocket.accept()
        _connections[sid] = websocket
        logger.debug("WebSocket connected: %s", sid)

    async def disconnect(self, sid: str) -> None:
        """Remove connection and clean up rooms."""
        if sid in _connections:
            del _connections[sid]
        # Remove from all rooms
        for room, sids in list(_rooms.items()):
            sids.discard(sid)
            if not sids:
                del _rooms[room]
        logger.debug("WebSocket disconnected: %s", sid)

    async def subscribe(self, sid: str, room: str) -> None:
        """Subscribe a connection to a room."""
        if sid not in _connections:
            return
        if room not in _rooms:
            _rooms[room] = set()
        _rooms[room].add(sid)
        logger.debug("%s subscribed to %s", sid, room)

    async def unsubscribe(self, sid: str, room: str) -> None:
        """Unsubscribe from a room."""
        if room in _rooms:
            _rooms[room].discard(sid)
            if not _rooms[room]:
                del _rooms[room]

    async def broadcast(self, room: str, event: str, data: dict) -> None:
        """Broadcast to all connections in a room."""
        if room not in _rooms:
            return
        message = json.dumps({"event": event, "data": data})
        dead_sids: list[str] = []
        for sid in _rooms[room]:
            if sid in _connections:
                try:
                    await _connections[sid].send_text(message)
                except Exception:
                    dead_sids.append(sid)
            else:
                dead_sids.append(sid)
        # Clean up dead connections
        for sid in dead_sids:
            await self.disconnect(sid)

    async def send_to(self, sid: str, event: str, data: dict) -> None:
        """Send to a specific connection."""
        if sid in _connections:
            message = json.dumps({"event": event, "data": data})
            try:
                await _connections[sid].send_text(message)
            except Exception:
                await self.disconnect(sid)

    async def publish_progress(self, sid: str, progress: int, title: Optional[str] = None) -> None:
        """Publish progress update."""
        await self.send_to(sid, "progress", {
            "progress": progress,
            "title": title,
        })


# Global manager instance
manager = WebSocketManager()

# ─── Redis Pub/Sub for cross-worker ─────────────────────────────────────────


async def redis_subscriber() -> None:
    """Subscribe to Redis pub/sub channel for cross-worker events."""
    try:
        from frappe.redis_client import get_redis_client
    except ImportError:
        logger.warning("Redis client not available; cross-worker realtime disabled")
        return

    try:
        redis = await get_redis_client()
        pubsub = redis.pubsub()
        await pubsub.subscribe("frappe:realtime")

        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    payload = json.loads(message["data"])
                    room = payload.get("room")
                    event = payload.get("event")
                    data = payload.get("data")
                    if room and event:
                        await manager.broadcast(room, event, data)
                except Exception as e:
                    logger.error("Redis pub/sub error: %s", e)
    except Exception as exc:
        logger.error("Redis subscriber failed: %s", exc)


async def redis_publish(room: str, event: str, data: dict) -> None:
    """Publish event to Redis pub/sub for other workers."""
    try:
        from frappe.redis_client import get_redis_client
    except ImportError:
        return

    try:
        redis = await get_redis_client()
        payload = json.dumps({"room": room, "event": event, "data": data})
        await redis.publish("frappe:realtime", payload)
    except Exception as exc:
        logger.error("Redis publish failed: %s", exc)
