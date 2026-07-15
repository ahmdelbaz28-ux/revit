"""
backend/session_store.py — Session storage abstraction with Redis fallback.

V244: Replaces the bare in-memory dict in auth.py with a hybrid store:
  - If REDIS_URL is set → use Redis (survives restarts, multi-worker safe)
  - If REDIS_URL is NOT set → fall back to in-memory dict (dev mode)

Design goals:
  1. Zero breaking changes — the API is a drop-in replacement for dict operations
  2. Graceful degradation — if Redis is unreachable, fall back to in-memory
  3. Automatic TTL — sessions auto-expire via Redis EXPIRE, no cleanup needed
  4. Thread-safe — uses a threading.Lock for the in-memory fallback

Usage:
    from backend.session_store import session_store

    # Store a session (TTL = _COOKIE_MAX_AGE_SECONDS)
    session_store.set(session_id_hash, {
        "api_key_hash": "...",
        "role": "engineer",
        "expires_at": 1234567890.0,
        "created_at": 1234567000.0,
        "client_ip": "1.2.3.4",
    })

    # Retrieve a session
    session = session_store.get(session_id_hash)  # → dict or None

    # Delete a session (logout)
    session_store.delete(session_id_hash)

    # Rate limiting (failed login attempts)
    session_store.add_failed_attempt(client_ip)
    session_store.get_failed_attempts(client_ip)  # → list of timestamps
    session_store.clear_failed_attempts(client_ip)
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────

# Session TTL in seconds (must match _COOKIE_MAX_AGE_SECONDS in auth.py)
_SESSION_TTL = int(os.getenv("FIREAI_SESSION_TTL", "86400"))  # 24 hours default

# Failed-attempt window in seconds (must match _FAILED_ATTEMPT_WINDOW in auth.py)
_FAILED_ATTEMPT_WINDOW = 300 # 5 minutes

# Maximum failed attempts (must match _MAX_FAILED_ATTEMPTS in auth.py)
_MAX_FAILED_ATTEMPTS = 5

# Redis key prefixes (namespaced to avoid collisions)
_SESSION_PREFIX = "bazspark:session:"
_FAILED_PREFIX = "bazspark:failed:"

# ── Redis connection (lazy, optional) ──────────────────────────────────────

_redis_client: Any = None  # type: ignore[assignment]
_redis_checked = False
_redis_available = False


def _get_redis() -> Any:
    """
    Lazily initialize the Redis client. Returns None if:
      - REDIS_URL is not set
      - Redis is unreachable
    """
    global _redis_client, _redis_checked, _redis_available

    if _redis_checked:
        return _redis_client if _redis_available else None

    _redis_checked = True

    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        logger.info("REDIS_URL not set — using in-memory session store (dev mode)")
        return None

    try:
        import redis  # type: ignore[import-untyped]

        _redis_client = redis.from_url(
            redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
            retry_on_timeout=True,
            decode_responses=True,  # Returns str instead of bytes
        )
        # Test the connection
        _redis_client.ping()
        _redis_available = True
        logger.info("Redis connected at %s — sessions will persist across restarts", _redis_client.redis_url if hasattr(_redis_client, 'redis_url') else redis_url)
        return _redis_client
    except ImportError:
        logger.warning("redis package not installed — falling back to in-memory session store. Install with: pip install redis")
        return None
    except Exception as e:
        logger.warning("Redis connection failed (%s) — falling back to in-memory session store", e)
        return None


# ── In-memory fallback (thread-safe) ───────────────────────────────────────

_mem_sessions: dict[str, dict[str, Any]] = {}
_mem_failed: dict[str, list[float]] = {}
_mem_lock = threading.Lock()


# ── Session Store API ──────────────────────────────────────────────────────


class SessionStore:
    """
    Hybrid session store: Redis (if available) with in-memory fallback.

    All methods are thread-safe. The in-memory fallback uses a threading.Lock;
    Redis is inherently thread-safe via connection pooling.
    """

    def set(self, key: str, value: dict[str, Any], ttl: int = _SESSION_TTL) -> None:
        """Store a session with automatic TTL expiry."""
        redis = _get_redis()
        if redis is not None:
            try:
                redis.setex(
                    f"{_SESSION_PREFIX}{key}",
                    ttl,
                    json.dumps(value, default=str),
                )
                return
            except Exception as e:
                logger.warning("Redis SET failed (%s) — falling back to in-memory", e)

        # In-memory fallback
        with _mem_lock:
            # Deep-copy to prevent external mutation
            _mem_sessions[key] = dict(value)

    def get(self, key: str) -> dict[str, Any] | None:
        """Retrieve a session. Returns None if not found or expired."""
        redis = _get_redis()
        if redis is not None:
            try:
                raw = redis.get(f"{_SESSION_PREFIX}{key}")
                if raw is None:
                    return None
                session = json.loads(raw)
                # Check expiry (Redis TTL handles this, but double-check)
                if time.time() > session.get("expires_at", 0):
                    redis.delete(f"{_SESSION_PREFIX}{key}")
                    return None
                return session
            except Exception as e:
                logger.warning("Redis GET failed (%s) — falling back to in-memory", e)

        # In-memory fallback
        with _mem_lock:
            session = _mem_sessions.get(key)
            if session is None:
                return None
            if time.time() > session.get("expires_at", 0):
                _mem_sessions.pop(key, None)
                return None
            # Return a copy to prevent external mutation
            return dict(session)

    def delete(self, key: str) -> None:
        """Delete a session (logout / revocation)."""
        redis = _get_redis()
        if redis is not None:
            try:
                redis.delete(f"{_SESSION_PREFIX}{key}")
                return
            except Exception as e:
                logger.warning("Redis DELETE failed (%s) — falling back to in-memory", e)

        # In-memory fallback
        with _mem_lock:
            _mem_sessions.pop(key, None)

    # ── Rate limiting (failed login attempts) ───────────────────────────

    def add_failed_attempt(self, client_ip: str) -> None:
        """Record a failed login attempt timestamp for the given IP."""
        now = time.time()
        redis = _get_redis()
        if redis is not None:
            try:
                key = f"{_FAILED_PREFIX}{client_ip}"
                # Use a Redis list with LPUSH + LTRIM to cap at _MAX_FAILED_ATTEMPTS*2
                redis.lpush(key, str(now))
                redis.ltrim(key, 0, 19)  # Keep last 20 attempts
                redis.expire(key, _FAILED_ATTEMPT_WINDOW)
                return
            except Exception as e:
                logger.warning("Redis LPUSH failed (%s) — falling back to in-memory", e)

        # In-memory fallback
        with _mem_lock:
            if client_ip not in _mem_failed:
                _mem_failed[client_ip] = []
            _mem_failed[client_ip].append(now)

    def get_failed_attempts(self, client_ip: str) -> list[float]:
        """
        Get the list of recent failed attempt timestamps (within the window).
        Also cleans up expired entries.
        """
        now = time.time()
        redis = _get_redis()
        if redis is not None:
            try:
                key = f"{_FAILED_PREFIX}{client_ip}"
                raw_list = redis.lrange(key, 0, -1)
                timestamps = [float(t) for t in raw_list if t]
                # Filter to within the window
                valid = [t for t in timestamps if now - t < _FAILED_ATTEMPT_WINDOW]
                if len(valid) != len(timestamps):
                    # Update the list if some entries expired
                    if valid:
                        redis.delete(key)
                        redis.rpush(key, *[str(t) for t in valid])
                        redis.expire(key, _FAILED_ATTEMPT_WINDOW)
                    else:
                        redis.delete(key)
                return valid
            except Exception as e:
                logger.warning("Redis LRANGE failed (%s) — falling back to in-memory", e)

        # In-memory fallback
        with _mem_lock:
            if client_ip not in _mem_failed:
                return []
            _mem_failed[client_ip] = [
                t for t in _mem_failed[client_ip]
                if now - t < _FAILED_ATTEMPT_WINDOW
            ]
            return list(_mem_failed[client_ip])

    def clear_failed_attempts(self, client_ip: str) -> None:
        """Clear failed attempts for an IP (on successful login)."""
        redis = _get_redis()
        if redis is not None:
            try:
                redis.delete(f"{_FAILED_PREFIX}{client_ip}")
                return
            except Exception as e:
                logger.warning("Redis DELETE failed (%s) — falling back to in-memory", e)

        # In-memory fallback
        with _mem_lock:
            _mem_failed.pop(client_ip, None)

    def cleanup_expired(self) -> int:
        """
        Remove expired sessions from the in-memory store.
        (Redis handles this automatically via TTL.)
        Returns the number of sessions removed.
        """
        redis = _get_redis()
        if redis is not None:
            # Redis auto-expires via SETEX — nothing to do
            return 0

        now = time.time()
        removed = 0
        with _mem_lock:
            expired_keys = [
                k for k, v in _mem_sessions.items()
                if now > v.get("expires_at", 0)
            ]
            for k in expired_keys:
                _mem_sessions.pop(k, None)
                removed += 1
        if removed > 0:
            logger.info("Cleaned up %d expired sessions from in-memory store", removed)
        return removed


# ── Singleton ──────────────────────────────────────────────────────────────

session_store = SessionStore()
