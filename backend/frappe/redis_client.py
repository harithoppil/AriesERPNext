from __future__ import annotations

import asyncio
import time
import functools
import json
import logging
from typing import Any, Optional

try:
    import redis.asyncio as redis
    from redis.asyncio import Redis
    _HAS_REDIS = True
except ImportError:
    redis = None  # type: ignore
    Redis = None  # type: ignore
    _HAS_REDIS = False

logger = logging.getLogger("frappe.redis")

# Global Redis client instance
_redis_client: Optional[Redis] = None




# ─── FakeRedis fallback (when redis is not installed) ──────────────────────

class FakeRedis:
    """In-memory Redis replacement for development/testing without Redis."""

    def __init__(self):
        self._store: dict = {}
        self._hash_store: dict = {}
        self._list_store: dict = {}
        self._set_store: dict = {}
        self._zset_store: dict = {}
        self._expiry: dict = {}

    async def ping(self):
        return True

    async def get(self, key):
        self._cleanup_expired()
        val = self._store.get(key)
        return val

    async def set(self, key, value, ex=None, px=None, nx=False, xx=False):
        self._store[key] = value
        if ex:
            self._expiry[key] = time.time() + ex
        return True

    async def setex(self, key, seconds, value):
        self._store[key] = value
        self._expiry[key] = time.time() + seconds
        return True

    async def delete(self, *keys):
        count = 0
        for key in keys:
            for store in (self._store, self._hash_store, self._list_store, self._set_store, self._zset_store):
                if key in store:
                    del store[key]
                    count += 1
        return count

    async def exists(self, *keys):
        self._cleanup_expired()
        return sum(1 for k in keys if k in self._store or k in self._hash_store or k in self._list_store)

    async def keys(self, pattern):
        self._cleanup_expired()
        import fnmatch
        all_keys = set(self._store.keys()) | set(self._hash_store.keys()) | set(self._list_store.keys())
        return [k for k in all_keys if fnmatch.fnmatch(k, pattern)]

    async def hget(self, key, field):
        return self._hash_store.get(key, {}).get(field)

    async def hgetall(self, key):
        return dict(self._hash_store.get(key, {}))

    async def hset(self, key, field=None, value=None, mapping=None):
        if key not in self._hash_store:
            self._hash_store[key] = {}
        if mapping:
            self._hash_store[key].update(mapping)
        elif field is not None:
            self._hash_store[key][field] = value
        return 1

    async def lpush(self, key, *values):
        if key not in self._list_store:
            self._list_store[key] = []
        self._list_store[key] = list(values) + self._list_store[key]
        return len(self._list_store[key])

    async def rpush(self, key, *values):
        if key not in self._list_store:
            self._list_store[key] = []
        self._list_store[key].extend(values)
        return len(self._list_store[key])

    async def llen(self, key):
        return len(self._list_store.get(key, []))

    async def zadd(self, key, mapping):
        if key not in self._zset_store:
            self._zset_store[key] = {}
        for member, score in mapping.items():
            self._zset_store[key][member] = score
        return len(mapping)

    async def zcard(self, key):
        return len(self._zset_store.get(key, {}))

    async def zrange(self, key, start, stop, withscores=False):
        items = sorted(self._zset_store.get(key, {}).items(), key=lambda x: x[1])
        if withscores:
            return items[start:stop+1] if stop >= 0 else items[start:]
        return [m for m, s in items[start:stop+1]] if stop >= 0 else [m for m, s in items[start:]]

    async def zremrangebyscore(self, key, min_score, max_score):
        if key not in self._zset_store:
            return 0
        removed = 0
        new_zset = {}
        for member, score in self._zset_store[key].items():
            if not (min_score <= score <= max_score):
                new_zset[member] = score
            else:
                removed += 1
        self._zset_store[key] = new_zset
        return removed

    async def ttl(self, key):
        if key not in self._expiry:
            return -1
        remaining = self._expiry[key] - time.time()
        return max(0, int(remaining))

    async def expire(self, key, seconds):
        if key in self._store or key in self._hash_store:
            self._expiry[key] = time.time() + seconds
            return True
        return False

    async def publish(self, channel, message):
        return 1

    async def pubsub(self):
        return FakePubSub()

    def _cleanup_expired(self):
        now = time.time()
        expired = [k for k, v in self._expiry.items() if v < now]
        for k in expired:
            for store in (self._store, self._hash_store, self._list_store, self._set_store, self._zset_store):
                store.pop(k, None)
            self._expiry.pop(k, None)


class FakePubSub:
    """Fake pub/sub for when Redis is not available."""

    async def subscribe(self, *channels):
        pass

    async def unsubscribe(self, *channels):
        pass

    async def listen(self):
        while True:
            await asyncio.sleep(3600)  # Never yield messages
            yield {"type": "message", "channel": "", "data": ""}

async def get_redis_client():
    """Get or create Redis client singleton.
    
    Returns real Redis if available, otherwise FakeRedis in-memory fallback.
    """
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    if not _HAS_REDIS:
        logger.debug("Redis not installed — using FakeRedis in-memory fallback")
        _redis_client = FakeRedis()
        return _redis_client
    # Lazy import to avoid circular dependency
    import frappe
    config = frappe.conf.get("redis_cache") or frappe.conf.get("redis") or {}
    host = config.get("host", "localhost")
    port = config.get("port", 6379)
    db = config.get("db", 0)
    password = config.get("password")
    username = config.get("username")
    ssl = config.get("ssl", False)
    max_connections = config.get("max_connections", 50)
    pool = redis.ConnectionPool(
        host=host, port=port, db=db, password=password,
        username=username, ssl=ssl, decode_responses=True,
        socket_connect_timeout=5, socket_keepalive=True,
        health_check_interval=30, max_connections=max_connections,
    )
    _redis_client = redis.Redis(connection_pool=pool)
    await _redis_client.ping()
    logger.info("Redis connection established to %s:%s/%s", host, port, db)
    return _redis_client
async def close_redis() -> None:
    """Close Redis connection pool."""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
        logger.info("Redis connection closed")


def get_sync_redis() -> Redis:
    """Synchronous wrapper for getting Redis client."""
    return asyncio.run(get_redis_client())
