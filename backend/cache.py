"""
backend/cache.py — Bounded in-memory cache with LRU eviction and background reaper.

Extracted from backend/app.py (V300 architecture improvement) to reduce the
monolithic app.py from 1056 lines and improve testability.

Features:
  - Maximum entry count (default 10,000) with LRU eviction
  - Per-value size cap (default 1 MB) to prevent memory abuse
  - Background reaper thread that periodically cleans expired entries
  - Thread-safe with locking for all operations

Usage:
    from backend.cache import cache_get, cache_set, cache_delete, cache_stats
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
from collections import OrderedDict
from typing import Any

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────
_CACHE_MAX_ENTRIES = int(os.getenv("FIREAI_CACHE_MAX_ENTRIES", "10000"))
_CACHE_MAX_VALUE_SIZE = int(os.getenv("FIREAI_CACHE_MAX_VALUE_SIZE", str(1024 * 1024)))
_CACHE_REAPER_INTERVAL = int(os.getenv("FIREAI_CACHE_REAPER_INTERVAL", "60"))

# ── Internal state ─────────────────────────────────────────────────────────
_cache: OrderedDict[str, dict] = OrderedDict()
_cache_lock = threading.Lock()
_cache_reaper_started = False
_cache_reaper_lock = threading.Lock()


# ── Internal helpers (MUST be called with _cache_lock held) ────────────────

def _evict_expired_locked() -> int:
    """Remove all expired entries. MUST be called with _cache_lock held."""
    now = time.time()
    expired = [k for k, v in _cache.items() if v.get("expire", 0) <= now]
    for k in expired:
        _cache.pop(k, None)
    return len(expired)


def _evict_oldest_locked(n: int = 1) -> None:
    """
    Evict the n oldest entries. MUST be called with _cache_lock held.

    Uses OrderedDict.popitem(last=False) which IS supported (unlike
    regular dict.popitem() in CPython).
    """
    for _ in range(n):
        if not _cache:
            return
        try:
            _cache.popitem(last=False)
        except KeyError:
            return


def _ensure_cache_reaper_started() -> None:
    """Start the background cache reaper thread (once, idempotent)."""
    global _cache_reaper_started
    if _cache_reaper_started:
        return
    with _cache_reaper_lock:
        if _cache_reaper_started:
            return
        _cache_reaper_started = True

        def _reaper_loop() -> None:
            while True:
                try:
                    time.sleep(_CACHE_REAPER_INTERVAL)
                    with _cache_lock:
                        removed = _evict_expired_locked()
                    if removed > 0:
                        logger.debug("Cache reaper removed %d expired entries", removed)
                except Exception as exc:
                    # F5 FIX: Log reaper errors instead of silently swallowing them.
                    # In a safety-critical system, silent failures are more
                    # dangerous than noisy ones.
                    logger.exception("Cache reaper error: %s", exc)

        t = threading.Thread(target=_reaper_loop, daemon=True, name="cache-reaper")
        t.start()
        logger.info("Cache reaper thread started (interval=%ds)", _CACHE_REAPER_INTERVAL)


# ── Public API ─────────────────────────────────────────────────────────────

def get_cache() -> OrderedDict[str, dict]:
    """Get cache instance. Returns in-memory dict if Redis unavailable."""
    return _cache


async def cache_get(key: str) -> Any:  # NOSONAR - python:S7503
    """Get value from cache. Returns None if expired or missing."""
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        if time.time() > entry.get("expire", 0):
            _cache.pop(key, None)  # Remove expired entry
            return None
        # Move to end so recently-accessed entries survive eviction longer.
        _cache.move_to_end(key)
        return entry["value"]


async def cache_set(key: str, value: object, expire: int = 300) -> None:  # NOSONAR - python:S7503
    """
    Set value in cache with expiration in seconds.

    If cache is at capacity, expired entries are evicted first;
    if still at capacity, the oldest entry is evicted (LRU policy).

    Values larger than _CACHE_MAX_VALUE_SIZE are rejected to prevent
    a single entry from consuming excessive memory.
    """
    # Check value size BEFORE acquiring the lock
    # Check raw object size before string coercion to avoid
    # allocating a potentially huge string just to reject it.
    if not isinstance(value, str):
        raw_size = sys.getsizeof(value)
        if raw_size > _CACHE_MAX_VALUE_SIZE:
            logger.warning(
                "Cache value too large before coercion (%d bytes raw, max %d) -- rejecting",
                raw_size, _CACHE_MAX_VALUE_SIZE,
            )
            return
        # Coerce to str for cache storage (cache stores str per signature)
        value = str(value)
    if len(value) > _CACHE_MAX_VALUE_SIZE:
        logger.warning(
            "Cache value too large (%d bytes, max %d) — rejecting",
            len(value), _CACHE_MAX_VALUE_SIZE,
        )
        return

    with _cache_lock:
        # If this is a new key and we're at capacity, make room.
        if key not in _cache:
            if len(_cache) >= _CACHE_MAX_ENTRIES:
                # First pass: evict expired entries (cheap)
                _evict_expired_locked()
                # Second pass: if still at capacity, evict oldest (LRU)
                while len(_cache) >= _CACHE_MAX_ENTRIES:
                    _evict_oldest_locked(1)
        else:
            # Existing key — move to end (most recently used)
            _cache.move_to_end(key)
        _cache[key] = {"value": value, "expire": time.time() + expire}

    # Start the reaper on first cache_set
    _ensure_cache_reaper_started()


async def cache_delete(key: str) -> None:  # NOSONAR - python:S7503
    """Delete key from cache."""
    with _cache_lock:
        _cache.pop(key, None)


async def cache_stats() -> dict[str, Any]:
    """
    Return cache statistics (entry count, memory estimate, top keys).

    Also triggers a sweep of expired entries as a side effect.
    """
    with _cache_lock:
        _evict_expired_locked()
        total = len(_cache)
        # Estimate memory: sum of sys.getsizeof for each entry
        mem_estimate = sum(
            sys.getsizeof(k) + sys.getsizeof(v)
            for k, v in _cache.items()
        )
        # Top 10 keys by remaining TTL
        now = time.time()
        top_keys = sorted(
            ((k, v.get("expire", 0) - now) for k, v in _cache.items()),
            key=lambda x: x[1],
            reverse=True,
        )[:10]

    return {
        "entries": total,
        "max_entries": _CACHE_MAX_ENTRIES,
        "memory_estimate_bytes": mem_estimate,
        "top_keys": [{"key": k, "ttl_remaining": round(t, 1)} for k, t in top_keys],
    }


async def cache_invalidate(pattern: str = "") -> int:
    """
    Invalidate cache entries matching a pattern prefix.

    Args:
        pattern: If provided, only delete keys starting with this prefix.
                 If empty, delete ALL entries.

    Returns:
        Number of entries invalidated.
    """
    with _cache_lock:
        if not pattern:
            count = len(_cache)
            _cache.clear()
            return count
        keys_to_delete = [k for k in _cache if k.startswith(pattern)]
        for k in keys_to_delete:
            _cache.pop(k, None)
        return len(keys_to_delete)
