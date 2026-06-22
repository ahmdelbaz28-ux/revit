"""
Redis client module for backend services.
Provides Redis connection and utility functions.
"""
import redis.asyncio as redis
from typing import Optional, Any
from ..config import settings


async def get_redis_client() -> redis.Redis:
    """
    Get a Redis client instance.
    
    Returns:
        redis.Redis: Redis client instance
    """
    redis_client = redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        password=settings.redis_password,
        decode_responses=False,  # Keep as bytes for consistency
        health_check_interval=30
    )
    return redis_client


async def get_value(key: str) -> Optional[Any]:
    """
    Get a value from Redis by key.
    
    Args:
        key: The key to retrieve
        
    Returns:
        The value if found, None otherwise
    """
    redis_client = await get_redis_client()
    try:
        value = await redis_client.get(key)
        return value
    except Exception:
        return None


async def set_value(key: str, value: Any, expire: Optional[int] = 3600) -> bool:
    """
    Set a value in Redis with optional expiration.
    
    Args:
        key: The key to set
        value: The value to store
        expire: Expiration time in seconds (default: 3600)
        
    Returns:
        True if successful, False otherwise
    """
    redis_client = await get_redis_client()
    try:
        await redis_client.set(key, value, ex=expire)
        return True
    except Exception:
        return False


async def delete_key(key: str) -> bool:
    """
    Delete a key from Redis.
    
    Args:
        key: The key to delete
        
    Returns:
        True if successful, False otherwise
    """
    redis_client = await get_redis_client()
    try:
        result = await redis_client.delete(key)
        return result > 0
    except Exception:
        return False