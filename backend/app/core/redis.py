"""
Redis client management.

Provides a singleton Redis client for synchronous operations.
"""

from typing import Optional

from redis import Redis

from app.core.config import settings

# Singleton Redis client instance
_redis_client: Optional[Redis] = None


def get_redis_client() -> Redis:
    """
    Get or create the Redis client.
    
    Returns:
        Redis client instance
    """
    global _redis_client
    
    if _redis_client is None:
        _redis_client = Redis.from_url(
            settings.REDIS_URL,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            decode_responses=False
        )
    
    return _redis_client


def close_redis_client():
    """Close the Redis client connection."""
    global _redis_client
    
    if _redis_client is not None:
        _redis_client.close()
        _redis_client = None


# Export for convenience
redis_client = get_redis_client()
