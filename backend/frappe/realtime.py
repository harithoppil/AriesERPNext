"""
Frappe Realtime — Event Publishing

Replaces frappe/realtime.py — handles publishing real-time events.
Uses in-memory pub/sub for now (Redis/Socket.IO planned).
"""

from __future__ import annotations

from typing import Any, Callable

import frappe
from frappe.types import _dict


# In-memory realtime log — stores events to be flushed
_realtime_log: list[dict] = []
_subscribers: dict[str, list[Callable]] = {}


def publish_progress(
    percent: int,
    title: str | None = None,
    doctype: str | None = None,
    docname: str | None = None,
    description: str | None = None,
    task_id: str | None = None,
):
    """Publish a progress update for background tasks."""
    publish_realtime(
        "progress",
        {
            "percent": percent,
            "title": title,
            "description": description,
        },
        doctype=doctype,
        docname=docname,
        task_id=task_id,
    )


def publish_realtime(
    event: str,
    message: Any = None,
    room: str | None = None,
    user: str | None = None,
    doctype: str | None = None,
    docname: str | None = None,
    task_id: str | None = None,
    after_commit: bool = False,
):
    """Publish a real-time event.

    Events can be targeted by:
    - room: specific room name
    - user: specific user
    - doctype + docname: document-specific events
    - task_id: background task progress
    """
    event_data = {
        "event": event,
        "message": message,
        "room": room,
        "user": user,
        "doctype": doctype,
        "docname": docname,
        "task_id": task_id,
    }

    if after_commit:
        # Queue for delivery after transaction commit
        _realtime_log.append(event_data)
    else:
        _deliver_event(event_data)


def _deliver_event(event_data: dict):
    """Deliver an event to subscribers."""
    event = event_data["event"]
    room = event_data.get("room")

    # Notify local subscribers
    if room and room in _subscribers:
        for callback in _subscribers[room]:
            try:
                callback(event_data)
            except Exception:
                pass

    # Store in shared cache for polling clients
    cache_key = f"realtime:{event_data.get('user') or event_data.get('room') or 'global'}"
    events = frappe.cache.get_value(cache_key, []) or []
    events.append(event_data)
    # Keep only last 100 events
    events = events[-100:]
    frappe.cache.set_value(cache_key, events)


def flush_realtime_log():
    """Flush queued realtime events (called after transaction commit)."""
    global _realtime_log
    for event_data in _realtime_log:
        _deliver_event(event_data)
    _realtime_log.clear()


def clear_realtime_log():
    """Clear queued realtime events (called on rollback)."""
    global _realtime_log
    _realtime_log.clear()


def subscribe(room: str, callback: Callable):
    """Subscribe to events in a room."""
    if room not in _subscribers:
        _subscribers[room] = []
    _subscribers[room].append(callback)


def unsubscribe(room: str, callback: Callable | None = None):
    """Unsubscribe from events in a room."""
    if room in _subscribers:
        if callback:
            _subscribers[room] = [c for c in _subscribers[room] if c != callback]
        else:
            del _subscribers[room]


def get_doctype_room(doctype: str) -> str:
    """Get the room name for a DocType."""
    return f"doctype:{doctype}"


def get_doc_room(doctype: str, docname: str) -> str:
    """Get the room name for a specific document."""
    return f"doc:{doctype}/{docname}"


def get_user_room(user: str | None = None) -> str:
    """Get the room name for a user."""
    if not user:
        user = frappe.session.user
    return f"user:{user}"


def get_site_room() -> str:
    """Get the room name for the current site."""
    site = getattr(frappe.local, "site", "")
    return f"site:{site}"


def get_task_progress_room(task_id: str) -> str:
    """Get the room name for a task's progress updates."""
    return f"task:{task_id}"


def get_website_room() -> str:
    """Get the room for website events."""
    return "website"


def has_permission(doctype: str, name: str) -> bool:
    """Check if current user has permission to subscribe to a document."""
    try:
        return frappe.has_permission(doctype, doc=name, ptype="read")
    except Exception:
        return False


def get_user_info():
    """Get user info for realtime connections."""
    return {
        "user": frappe.session.user,
        "full_name": getattr(frappe.session, "full_name", None),
        "user_type": getattr(frappe.session, "user_type", None),
    }


def get_socketio_secret() -> str:
    """Get secret for Socket.IO authentication."""
    import secrets

    return secrets.token_hex(32)
