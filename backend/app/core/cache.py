"""Redis cache configuration and utilities."""

from functools import wraps
import json
from collections.abc import Mapping
from datetime import date, datetime
from enum import Enum
from typing import Any, Callable, Optional
from uuid import UUID

import redis.asyncio as redis
from redis.asyncio import Redis

from app.core.config import settings


class RedisCache:
    """Redis cache manager."""

    def __init__(self):
        self._client: Optional[Redis] = None

    async def connect(self) -> None:
        """Connect to Redis."""
        if not self._client:
            self._client = await redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
            )

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self._client:
            await self._client.close()
            self._client = None

    @property
    def client(self) -> Redis:
        """Get Redis client."""
        if not self._client:
            raise RuntimeError("Redis client not connected. Call connect() first.")
        return self._client

    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        try:
            value = await self.client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception:
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (default from settings)

        Returns:
            True if successful, False otherwise
        """
        try:
            serialized = json.dumps(value)
            if ttl is None:
                ttl = settings.REDIS_DEFAULT_TTL
            await self.client.setex(key, ttl, serialized)
            return True
        except Exception:
            return False

    async def delete(self, key: str) -> bool:
        """
        Delete value from cache.

        Args:
            key: Cache key

        Returns:
            True if deleted, False otherwise
        """
        try:
            await self.client.delete(key)
            return True
        except Exception:
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching pattern.

        Args:
            pattern: Key pattern (e.g., "user:*")

        Returns:
            Number of keys deleted
        """
        try:
            keys = []
            async for key in self.client.scan_iter(match=pattern):
                keys.append(key)
            if keys:
                return await self.client.delete(*keys)
            return 0
        except Exception:
            return 0

    async def exists(self, key: str) -> bool:
        """
        Check if key exists.

        Args:
            key: Cache key

        Returns:
            True if exists, False otherwise
        """
        try:
            return await self.client.exists(key) > 0
        except Exception:
            return False


# Global cache instance
cache = RedisCache()


def _normalize_cache_key_value(value: Any) -> Any:
    """Normalize cache-key values into deterministic JSON-serializable payloads."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    if isinstance(value, Enum):
        return _normalize_cache_key_value(value.value)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, Mapping):
        return {
            str(key): _normalize_cache_key_value(nested_value)
            for key, nested_value in sorted(
                value.items(),
                key=lambda item: str(item[0]),
            )
        }

    if isinstance(value, (list, tuple)):
        return [_normalize_cache_key_value(item) for item in value]

    if isinstance(value, (set, frozenset)):
        normalized_items = [_normalize_cache_key_value(item) for item in value]
        return sorted(
            normalized_items,
            key=lambda item: json.dumps(
                item,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ),
        )

    return repr(value)


def _serialize_cache_key_value(value: Any) -> str:
    """Serialize cache-key values with deterministic JSON encoding."""
    return json.dumps(
        _normalize_cache_key_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def cache_key(*args, **kwargs) -> str:
    """
    Generate a deterministic cache key from arguments.

    Args:
        *args: Positional arguments
        **kwargs: Keyword arguments

    Returns:
        Cache key string
    """
    parts = [_serialize_cache_key_value(arg) for arg in args]
    parts.extend(
        f"{key}={_serialize_cache_key_value(value)}"
        for key, value in sorted(kwargs.items(), key=lambda item: item[0])
    )
    return ":".join(parts)


def cached(
    prefix: str,
    ttl: Optional[int] = None,
    key_builder: Optional[Callable] = None,
    skip_first_arg: Optional[bool] = None,
    refresh_flag: Optional[str] = "refresh_cache",
    disable_flag: Optional[str] = "disable_cache",
):
    """
    Decorator for caching function results.

    Args:
        prefix: Cache key prefix
        ttl: Time to live in seconds
        key_builder: Custom key builder function
        skip_first_arg: Whether to omit the first positional argument when
            building cache keys. ``None`` auto-detects bound methods when
            ``key_builder`` is not provided.
        refresh_flag: Optional kwarg name that forces a fresh function call
            while still writing the new result to cache.
        disable_flag: Optional kwarg name that bypasses cache reads and writes
            for a single call.

    Example:
        @cached(prefix="user", ttl=300)
        async def get_user(user_id: str):
            return await db.get_user(user_id)
    """

    if skip_first_arg is not None and not isinstance(skip_first_arg, bool):
        raise ValueError("skip_first_arg must be a boolean when provided")

    for flag_name, option_name in (
        (refresh_flag, "refresh_flag"),
        (disable_flag, "disable_flag"),
    ):
        if flag_name is None:
            continue

        if not isinstance(flag_name, str):
            raise ValueError(f"{option_name} must be a string when provided")

        if not flag_name.strip():
            raise ValueError(f"{option_name} cannot be empty")

    if (
        refresh_flag is not None
        and disable_flag is not None
        and refresh_flag == disable_flag
    ):
        raise ValueError("refresh_flag and disable_flag must be different values")

    def decorator(func: Callable):
        def _resolve_key_args(call_args: tuple[Any, ...]) -> tuple[Any, ...]:
            if not call_args:
                return call_args

            if skip_first_arg is True:
                return call_args[1:]

            if skip_first_arg is False:
                return call_args

            if key_builder is not None:
                return call_args

            method_candidate = getattr(call_args[0], func.__name__, None)
            if callable(method_candidate):
                return call_args[1:]

            return call_args

        def _consume_control_flag(
            payload_kwargs: dict[str, Any],
            flag_name: Optional[str],
        ) -> bool:
            if flag_name is None or flag_name not in payload_kwargs:
                return False

            flag_value = payload_kwargs.pop(flag_name)
            if not isinstance(flag_value, bool):
                raise ValueError(f"{flag_name} must be a boolean when provided")

            return flag_value

        @wraps(func)
        async def wrapper(*args, **kwargs):
            runtime_kwargs = dict(kwargs)
            refresh_cache = _consume_control_flag(runtime_kwargs, refresh_flag)
            disable_cache = _consume_control_flag(runtime_kwargs, disable_flag)

            if disable_cache:
                return await func(*args, **runtime_kwargs)

            key_args = _resolve_key_args(args)

            # Build cache key
            if key_builder:
                key = f"{prefix}:{key_builder(*key_args, **runtime_kwargs)}"
            else:
                key = f"{prefix}:{cache_key(*key_args, **runtime_kwargs)}"

            # Try to get from cache
            if not refresh_cache:
                cached_value = await cache.get(key)
                if cached_value is not None:
                    return cached_value

            # Execute function
            result = await func(*args, **runtime_kwargs)

            # Cache result
            await cache.set(key, result, ttl)

            return result

        return wrapper

    return decorator


async def invalidate_cache(prefix: str, *args, **kwargs) -> None:
    """
    Invalidate cache for specific key or pattern.

    Args:
        prefix: Cache key prefix
        *args: Positional arguments for key building
        **kwargs: Keyword arguments for key building
    """
    if args or kwargs:
        key = f"{prefix}:{cache_key(*args, **kwargs)}"
        await cache.delete(key)
    else:
        # Delete all keys with prefix
        await cache.delete_pattern(f"{prefix}:*")
