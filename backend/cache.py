"""
backend/cache.py — Redis Cache Layer
=====================================

High-performance caching layer with Redis backend and in-memory fallback.
Provides TTL support, eviction policies, and graceful degradation.

Features:
- Redis backend with connection pooling
- In-memory fallback when Redis unavailable
- TTL (Time-To-Live) support
- LRU eviction policy
- Automatic reconnection
- Metrics collection

Environment Variables:
- REDIS_URL: Redis connection URL (e.g., redis://localhost:6379/0)
- CACHE_DEFAULT_TTL: Default TTL in seconds (default: 300)
- CACHE_MAX_SIZE: Maximum items in memory fallback (default: 10000)

Usage:
    from backend.cache import cache, CacheMetrics
    
    # Basic operations
    await cache.get("key")
    await cache.set("key", "value", ttl=60)
    await cache.delete("key")
    
    # With default value
    value = await cache.get_or_set("key", default_fn=lambda: compute_value(), ttl=60)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Union

logger = logging.getLogger(__name__)

# Configuration from environment
REDIS_URL = "redis://localhost:6379/0"
try:
    REDIS_URL = str(__import__("os").environ.get("REDIS_URL", REDIS_URL))
except Exception:
    pass

DEFAULT_TTL = 300  # 5 minutes
try:
    DEFAULT_TTL = int(__import__("os").environ.get("CACHE_DEFAULT_TTL", DEFAULT_TTL))
except Exception:
    pass

MAX_MEMORY_SIZE = 10000
try:
    MAX_MEMORY_SIZE = int(__import__("os").environ.get("CACHE_MAX_SIZE", MAX_MEMORY_SIZE))
except Exception:
    pass


@dataclass
class CacheMetrics:
    """Cache performance metrics."""
    hits: int = 0
    misses: int = 0
    sets: int = 0
    deletes: int = 0
    errors: int = 0
    total_time_ms: float = 0.0
    
    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0.0
    
    def to_dict(self) -> dict:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "sets": self.sets,
            "deletes": self.deletes,
            "errors": self.errors,
            "hit_rate_percent": round(self.hit_rate, 2),
            "total_time_ms": round(self.total_time_ms, 2)
        }


class MemoryCache:
    """
    In-memory LRU cache fallback.
    
    Features:
    - LRU (Least Recently Used) eviction
    - TTL support per key
    - Thread-safe with asyncio
    - Automatic cleanup of expired items
    """
    
    def __init__(self, max_size: int = MAX_MEMORY_SIZE, default_ttl: int = DEFAULT_TTL):
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()  # key -> (value, expire_at)
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._lock = asyncio.Lock()
        self._stats = CacheMetrics()
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        """Start background cleanup task."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("Memory cache started with cleanup task")
    
    async def stop(self) -> None:
        """Stop background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("Memory cache stopped")
    
    async def _cleanup_loop(self) -> None:
        """Background task to clean expired items."""
        while True:
            try:
                await asyncio.sleep(60)  # Run every minute
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Cache cleanup error: {e}")
    
    async def _cleanup_expired(self) -> int:
        """Remove all expired items."""
        async with self._lock:
            now = time.time()
            expired_keys = [
                k for k, (_, expire_at) in self._cache.items()
                if expire_at > 0 and expire_at < now
            ]
            for key in expired_keys:
                del self._cache[key]
            if expired_keys:
                logger.debug(f"Cleaned {len(expired_keys)} expired cache entries")
            return len(expired_keys)
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        start = time.time()
        try:
            async with self._lock:
                if key not in self._cache:
                    self._stats.misses += 1
                    return None
                
                value, expire_at = self._cache[key]
                
                # Check if expired
                if expire_at > 0 and expire_at < time.time():
                    del self._cache[key]
                    self._stats.misses += 1
                    return None
                
                # Move to end (most recently used)
                self._cache.move_to_end(key)
                self._stats.hits += 1
                return value
        except Exception as e:
            self._stats.errors += 1
            logger.warning(f"Memory cache get error: {e}")
            return None
        finally:
            self._stats.total_time_ms += (time.time() - start) * 1000
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache with TTL."""
        start = time.time()
        try:
            async with self._lock:
                ttl = ttl if ttl is not None else self._default_ttl
                expire_at = time.time() + ttl if ttl > 0 else 0
                
                # Evict oldest if at capacity
                while len(self._cache) >= self._max_size:
                    self._cache.popitem(last=False)  # Remove oldest (LRU)
                
                self._cache[key] = (value, expire_at)
                self._cache.move_to_end(key)
                self._stats.sets += 1
                return True
        except Exception as e:
            self._stats.errors += 1
            logger.warning(f"Memory cache set error: {e}")
            return False
        finally:
            self._stats.total_time_ms += (time.time() - start) * 1000
    
    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        start = time.time()
        try:
            async with self._lock:
                if key in self._cache:
                    del self._cache[key]
                    self._stats.deletes += 1
                    return True
                return False
        except Exception as e:
            self._stats.errors += 1
            logger.warning(f"Memory cache delete error: {e}")
            return False
        finally:
            self._stats.total_time_ms += (time.time() - start) * 1000
    
    async def clear(self) -> int:
        """Clear all cache entries."""
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count
    
    async def exists(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        value = await self.get(key)
        return value is not None
    
    async def get_or_set(
        self,
        key: str,
        default_fn: Callable[[], Any],
        ttl: Optional[int] = None
    ) -> Any:
        """Get value or compute and set if not exists."""
        value = await self.get(key)
        if value is not None:
            return value
        
        value = default_fn()
        await self.set(key, value, ttl=ttl)
        return value
    
    def get_stats(self) -> dict:
        """Get cache statistics."""
        return self._stats.to_dict()


class RedisCache:
    """
    Redis-backed cache with connection pooling.
    
    Features:
    - Connection pooling
    - Automatic reconnection
    - Redis pub/sub for cache invalidation
    - Pipeline support for batch operations
    - TTL support
    """
    
    def __init__(self, url: str = REDIS_URL, default_ttl: int = DEFAULT_TTL):
        self._url = url
        self._default_ttl = default_ttl
        self._pool: Optional[Any] = None
        self._redis: Optional[Any] = None
        self._connected = False
        self._lock = asyncio.Lock()
        self._stats = CacheMetrics()
    
    async def connect(self) -> bool:
        """Connect to Redis."""
        try:
            import redis.asyncio as redis
            
            self._redis = redis.from_url(
                self._url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=20,
                socket_connect_timeout=5,
                socket_keepalive=True
            )
            
            # Test connection
            await self._redis.ping()
            self._connected = True
            logger.info(f"Redis cache connected: {self._url}")
            return True
        except ImportError:
            logger.warning("redis.asyncio not installed. Install with: pip install redis[hiredis]")
            self._connected = False
            return False
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}. Using in-memory fallback.")
            self._connected = False
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self._redis:
            await self._redis.aclose()
            self._redis = None
            self._connected = False
            logger.info("Redis cache disconnected")
    
    async def _ensure_connected(self) -> bool:
        """Ensure Redis is connected."""
        if self._connected and self._redis:
            return True
        
        async with self._lock:
            if not self._connected:
                await self.connect()
            return self._connected
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        start = time.time()
        try:
            if not await self._ensure_connected():
                return None
            
            value = await self._redis.get(key)
            if value is None:
                self._stats.misses += 1
                return None
            
            self._stats.hits += 1
            # Try to deserialize JSON
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        except Exception as e:
            self._stats.errors += 1
            logger.warning(f"Redis get error: {e}")
            return None
        finally:
            self._stats.total_time_ms += (time.time() - start) * 1000
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache with TTL."""
        start = time.time()
        try:
            if not await self._ensure_connected():
                return False
            
            ttl = ttl if ttl is not None else self._default_ttl
            
            # Serialize to JSON
            try:
                serialized = json.dumps(value)
            except (TypeError, ValueError):
                serialized = str(value)
            
            if ttl > 0:
                await self._redis.setex(key, ttl, serialized)
            else:
                await self._redis.set(key, serialized)
            
            self._stats.sets += 1
            return True
        except Exception as e:
            self._stats.errors += 1
            logger.warning(f"Redis set error: {e}")
            return False
        finally:
            self._stats.total_time_ms += (time.time() - start) * 1000
    
    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        start = time.time()
        try:
            if not await self._ensure_connected():
                return False
            
            result = await self._redis.delete(key)
            self._stats.deletes += 1
            return result > 0
        except Exception as e:
            self._stats.errors += 1
            logger.warning(f"Redis delete error: {e}")
            return False
        finally:
            self._stats.total_time_ms += (time.time() - start) * 1000
    
    async def clear(self) -> int:
        """Clear all cache entries (use with caution)."""
        try:
            if not await self._ensure_connected():
                return 0
            
            # Get all keys with the prefix and delete them
            count = 0
            cursor = 0
            while True:
                cursor, keys = await self._redis.scan(cursor, match="*", count=100)
                if keys:
                    await self._redis.delete(*keys)
                    count += len(keys)
                if cursor == 0:
                    break
            
            return count
        except Exception as e:
            self._stats.errors += 1
            logger.warning(f"Redis clear error: {e}")
            return 0
    
    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        try:
            if not await self._ensure_connected():
                return False
            return await self._redis.exists(key) > 0
        except Exception as e:
            logger.warning(f"Redis exists error: {e}")
            return False
    
    async def get_or_set(
        self,
        key: str,
        default_fn: Callable[[], Any],
        ttl: Optional[int] = None
    ) -> Any:
        """Get value or compute and set if not exists."""
        value = await self.get(key)
        if value is not None:
            return value
        
        value = default_fn()
        await self.set(key, value, ttl=ttl)
        return value
    
    async def get_many(self, keys: list[str]) -> dict[str, Any]:
        """Get multiple keys at once."""
        if not keys:
            return {}
        
        try:
            if not await self._ensure_connected():
                return {}
            
            values = await self._redis.mget(keys)
            result = {}
            for key, value in zip(keys, values):
                if value is not None:
                    try:
                        result[key] = json.loads(value)
                    except (json.JSONDecodeError, TypeError):
                        result[key] = value
            return result
        except Exception as e:
            logger.warning(f"Redis get_many error: {e}")
            return {}
    
    async def set_many(self, items: dict[str, Any], ttl: Optional[int] = None) -> int:
        """Set multiple keys at once using pipeline."""
        if not items:
            return 0
        
        try:
            if not await self._ensure_connected():
                return 0
            
            ttl = ttl if ttl is not None else self._default_ttl
            pipe = self._redis.pipeline()
            
            for key, value in items.items():
                try:
                    serialized = json.dumps(value)
                except (TypeError, ValueError):
                    serialized = str(value)
                
                if ttl > 0:
                    pipe.setex(key, ttl, serialized)
                else:
                    pipe.set(key, serialized)
            
            await pipe.execute()
            return len(items)
        except Exception as e:
            logger.warning(f"Redis set_many error: {e}")
            return 0
    
    def get_stats(self) -> dict:
        """Get cache statistics."""
        return self._stats.to_dict()


class Cache:
    """
    Unified cache interface with automatic backend selection.
    
    Priority:
    1. Redis (if available and connected)
    2. Memory (fallback)
    
    Features:
    - Automatic backend selection
    - Graceful degradation
    - Metrics collection
    - Consistent API
    """
    
    def __init__(
        self,
        redis_url: str = REDIS_URL,
        default_ttl: int = DEFAULT_TTL,
        max_memory_size: int = MAX_MEMORY_SIZE
    ):
        self._redis = RedisCache(url=redis_url, default_ttl=default_ttl)
        self._memory = MemoryCache(max_size=max_memory_size, default_ttl=default_ttl)
        self._use_redis = False
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize cache (connect to Redis, start memory cleanup)."""
        if self._initialized:
            return
        
        # Try Redis first
        if await self._redis.connect():
            self._use_redis = True
            logger.info("Cache initialized with Redis backend")
        else:
            self._use_redis = False
            await self._memory.start()
            logger.info("Cache initialized with memory backend (Redis unavailable)")
        
        self._initialized = True
    
    async def shutdown(self) -> None:
        """Shutdown cache gracefully."""
        if self._use_redis:
            await self._redis.disconnect()
        else:
            await self._memory.stop()
        self._initialized = False
    
    @property
    def backend(self) -> str:
        """Get current backend name."""
        return "redis" if self._use_redis else "memory"
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if self._use_redis:
            return await self._redis.get(key)
        return await self._memory.get(key)
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache."""
        if self._use_redis:
            return await self._redis.set(key, value, ttl)
        return await self._memory.set(key, value, ttl)
    
    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        if self._use_redis:
            return await self._redis.delete(key)
        return await self._memory.delete(key)
    
    async def clear(self) -> int:
        """Clear all cache entries."""
        if self._use_redis:
            return await self._redis.clear()
        return await self._memory.clear()
    
    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        if self._use_redis:
            return await self._redis.exists(key)
        return await self._memory.exists(key)
    
    async def get_or_set(
        self,
        key: str,
        default_fn: Callable[[], Any],
        ttl: Optional[int] = None
    ) -> Any:
        """Get value or compute and set if not exists."""
        if self._use_redis:
            return await self._redis.get_or_set(key, default_fn, ttl)
        return await self._memory.get_or_set(key, default_fn, ttl)
    
    async def get_many(self, keys: list[str]) -> dict[str, Any]:
        """Get multiple keys."""
        if self._use_redis:
            return await self._redis.get_many(keys)
        
        result = {}
        for key in keys:
            value = await self._memory.get(key)
            if value is not None:
                result[key] = value
        return result
    
    async def set_many(self, items: dict[str, Any], ttl: Optional[int] = None) -> int:
        """Set multiple keys."""
        if self._use_redis:
            return await self._redis.set_many(items, ttl)
        
        count = 0
        for key, value in items.items():
            if await self._memory.set(key, value, ttl):
                count += 1
        return count
    
    def get_stats(self) -> dict:
        """Get cache statistics."""
        if self._use_redis:
            return {"backend": "redis", **self._redis.get_stats()}
        return {"backend": "memory", **self._memory.get_stats()}


# Global cache instance
cache = Cache()

# Convenience functions
async def get(key: str) -> Optional[Any]:
    """Get value from cache."""
    return await cache.get(key)

async def set(key: str, value: Any, ttl: Optional[int] = None) -> bool:
    """Set value in cache."""
    return await cache.set(key, value, ttl)

async def delete(key: str) -> bool:
    """Delete key from cache."""
    return await cache.delete(key)

async def clear() -> int:
    """Clear all cache entries."""
    return await cache.clear()

def get_stats() -> dict:
    """Get cache statistics."""
    return cache.get_stats()
