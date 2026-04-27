"""
Redis caching layer for analytics queries.

Provides get/set helpers with a configurable TTL.  Falls back gracefully
if Redis is unavailable — the app continues to work, just without caching.
"""

import json
from typing import Any, Optional

import redis

from app.config import get_settings

_client: Optional[redis.Redis] = None


def init_cache() -> Optional[redis.Redis]:
    global _client
    settings = get_settings()
    try:
        _client = redis.from_url(settings.redis_url, decode_responses=True)
        _client.ping()
        return _client
    except Exception:
        _client = None
        return None


def close_cache() -> None:
    global _client
    if _client:
        _client.close()
        _client = None


def get_cached(key: str) -> Optional[Any]:
    if not _client:
        return None
    try:
        raw = _client.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def set_cached(key: str, value: Any, ttl: Optional[int] = None) -> None:
    if not _client:
        return
    if ttl is None:
        ttl = get_settings().redis_cache_ttl
    try:
        _client.setex(key, ttl, json.dumps(value, default=str))
    except Exception:
        pass


def invalidate(pattern: str = "analytics:*") -> None:
    """Delete keys matching *pattern* so next request gets fresh data."""
    if not _client:
        return
    try:
        for key in _client.scan_iter(match=pattern):
            _client.delete(key)
    except Exception:
        pass
