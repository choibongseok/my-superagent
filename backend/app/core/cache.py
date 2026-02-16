"""Redis cache configuration and utilities."""

import asyncio
from dataclasses import asdict, is_dataclass
from functools import wraps
import hashlib
import inspect
import json
from collections.abc import Awaitable, Iterable, Mapping
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

    async def expire(self, key: str, ttl: int) -> bool:
        """Refresh a cache key expiry window.

        Args:
            key: Cache key
            ttl: New time-to-live in seconds

        Returns:
            True if expiration was updated, False otherwise
        """
        try:
            return await self.client.expire(key, ttl)
        except Exception:
            return False


# Global cache instance
cache = RedisCache()


def _extract_mapping_payload(value: Any) -> Mapping[str, Any] | None:
    """Extract mapping-style payloads from structured objects for key stability."""
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)

    mapping_extractors = (
        ("model_dump", {"mode": "json"}),
        ("dict", {}),
        ("_asdict", {}),
    )

    for extractor_name, extractor_kwargs in mapping_extractors:
        extractor = getattr(value, extractor_name, None)
        if not callable(extractor):
            continue

        try:
            payload = extractor(**extractor_kwargs)
        except TypeError:
            payload = extractor()
        except Exception:
            continue

        if isinstance(payload, Mapping):
            return payload

    return None


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

    extracted_mapping = _extract_mapping_payload(value)
    if extracted_mapping is not None:
        return _normalize_cache_key_value(extracted_mapping)

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


def _normalize_key_version(key_version: Optional[str | int]) -> Optional[str]:
    """Normalize optional cache-key namespace versions."""
    if key_version is None:
        return None

    if isinstance(key_version, bool):
        raise ValueError("key_version must be a non-empty string or integer")

    if isinstance(key_version, int):
        return str(key_version)

    if isinstance(key_version, str):
        normalized_key_version = key_version.strip()
        if not normalized_key_version:
            raise ValueError("key_version must be a non-empty string or integer")

        return normalized_key_version

    raise ValueError("key_version must be a non-empty string or integer")


def _build_cache_namespace(prefix: str, key_version: Optional[str | int]) -> str:
    """Build cache namespace, optionally appending version marker."""
    normalized_key_version = _normalize_key_version(key_version)
    if normalized_key_version is None:
        return prefix

    return f"{prefix}:v{normalized_key_version}"


def _validate_max_key_length(
    max_key_length: Optional[int],
    *,
    key_namespace: str,
) -> None:
    """Validate optional cache-key hashing length constraints."""
    if max_key_length is None:
        return

    if isinstance(max_key_length, bool) or not isinstance(max_key_length, int):
        raise ValueError("max_key_length must be an integer when provided")

    minimum_hashed_key_length = len(key_namespace) + 3 + 16
    if max_key_length < minimum_hashed_key_length:
        raise ValueError(
            "max_key_length is too small for hashed keys; "
            "must be at least "
            f"{minimum_hashed_key_length} for namespace '{key_namespace}'"
        )


def _normalize_ignored_kwargs(
    ignored_kwargs: Optional[Iterable[str]],
) -> frozenset[str]:
    """Normalize optional kwarg names excluded from cache-key generation."""
    if ignored_kwargs is None:
        return frozenset()

    if isinstance(ignored_kwargs, str):
        raise ValueError("ignored_kwargs must be an iterable of non-empty strings")

    normalized_values: set[str] = set()
    for name in ignored_kwargs:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("ignored_kwargs must be an iterable of non-empty strings")
        normalized_values.add(name)

    return frozenset(normalized_values)


def _shorten_cache_storage_key(
    key: str,
    *,
    key_namespace: str,
    max_key_length: Optional[int],
) -> str:
    """Deterministically hash cache keys that exceed ``max_key_length``."""
    if max_key_length is None or len(key) <= max_key_length:
        return key

    hashed_prefix = f"{key_namespace}:h:"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    available_digest_chars = max_key_length - len(hashed_prefix)
    return f"{hashed_prefix}{digest[:available_digest_chars]}"


def cached(
    prefix: str,
    ttl: Optional[int] = None,
    key_builder: Optional[Callable] = None,
    skip_first_arg: Optional[bool] = None,
    refresh_flag: Optional[str] = "refresh_cache",
    disable_flag: Optional[str] = "disable_cache",
    cache_condition: Optional[Callable[[Any], bool | Awaitable[bool]]] = None,
    coalesce_inflight: bool = True,
    ignored_kwargs: Optional[Iterable[str]] = None,
    cache_none: bool = False,
    max_key_length: Optional[int] = None,
    key_version: Optional[str | int] = None,
    refresh_ttl_on_hit: bool = False,
    hit_ttl: Optional[int] = None,
):
    """
    Decorator for caching function results.

    Supports both async and sync callables; sync callables are executed
    directly and their return values are cached the same way.

    Args:
        prefix: Cache key prefix
        ttl: Time to live in seconds
        key_builder: Custom key builder function. May be sync or async.
        skip_first_arg: Whether to omit the first positional argument when
            building cache keys. ``None`` auto-detects bound methods when
            ``key_builder`` is not provided.
        refresh_flag: Optional kwarg name that forces a fresh function call
            while still writing the new result to cache.
        disable_flag: Optional kwarg name that bypasses cache reads and writes
            for a single call.
        cache_condition: Optional predicate that receives the computed result
            and returns ``True`` when the value should be written to cache.
            The predicate may be synchronous or asynchronous.
        coalesce_inflight: When ``True`` (default), concurrent calls that
            resolve to the same cache key will await a single in-flight
            execution instead of triggering duplicate work.
        ignored_kwargs: Optional iterable of kwarg names excluded from cache
            key generation while still being passed to the wrapped function.
        cache_none: When ``True``, cache and replay ``None`` results by
            storing an internal envelope payload.
        max_key_length: Optional maximum cache-key length. Keys longer than
            this threshold are deterministically hashed while preserving the
            configured prefix.
        key_version: Optional cache namespace version marker used to isolate
            keys during rollouts (e.g., ``v2``).
        refresh_ttl_on_hit: When ``True``, successful cache hits will refresh
            the key expiry window by calling Redis ``EXPIRE``.
        hit_ttl: Optional TTL override (seconds) used only when
            ``refresh_ttl_on_hit`` is enabled. Defaults to ``ttl`` or
            ``settings.REDIS_DEFAULT_TTL``.

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

    if cache_condition is not None and not callable(cache_condition):
        raise ValueError("cache_condition must be callable when provided")

    if not isinstance(coalesce_inflight, bool):
        raise ValueError("coalesce_inflight must be a boolean")

    if not isinstance(cache_none, bool):
        raise ValueError("cache_none must be a boolean")

    if not isinstance(refresh_ttl_on_hit, bool):
        raise ValueError("refresh_ttl_on_hit must be a boolean")

    if hit_ttl is not None:
        if isinstance(hit_ttl, bool) or not isinstance(hit_ttl, int):
            raise ValueError("hit_ttl must be a positive integer when provided")
        if hit_ttl <= 0:
            raise ValueError("hit_ttl must be a positive integer when provided")

    key_namespace = _build_cache_namespace(prefix, key_version)
    _validate_max_key_length(max_key_length, key_namespace=key_namespace)

    normalized_ignored_kwargs = _normalize_ignored_kwargs(ignored_kwargs)

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

        async def _build_cache_key(
            key_args: tuple[Any, ...],
            runtime_kwargs: dict[str, Any],
        ) -> str:
            if key_builder:
                built_key = key_builder(*key_args, **runtime_kwargs)
                if inspect.isawaitable(built_key):
                    built_key = await built_key
                return _shorten_cache_storage_key(
                    f"{key_namespace}:{built_key}",
                    key_namespace=key_namespace,
                    max_key_length=max_key_length,
                )

            return _shorten_cache_storage_key(
                f"{key_namespace}:{cache_key(*key_args, **runtime_kwargs)}",
                key_namespace=key_namespace,
                max_key_length=max_key_length,
            )

        async def _should_cache_result(result: Any) -> bool:
            if cache_condition is None:
                return True

            decision = cache_condition(result)
            if inspect.isawaitable(decision):
                decision = await decision

            if not isinstance(decision, bool):
                raise ValueError("cache_condition must return a boolean")

            return decision

        def _encode_cached_payload(result: Any) -> Any:
            if not cache_none:
                return result

            return {
                "__openclaw_cached_payload_v1__": True,
                "value": result,
            }

        def _decode_cached_payload(payload: Any) -> tuple[bool, Any]:
            if not cache_none:
                if payload is None:
                    return False, None
                return True, payload

            if (
                isinstance(payload, Mapping)
                and payload.get("__openclaw_cached_payload_v1__") is True
                and "value" in payload
            ):
                return True, payload["value"]

            if payload is None:
                return False, None

            # Backward compatibility for values cached before envelope support.
            return True, payload

        async def _refresh_ttl_for_cache_hit(key: str) -> None:
            if not refresh_ttl_on_hit:
                return

            effective_hit_ttl = hit_ttl if hit_ttl is not None else ttl
            if effective_hit_ttl is None:
                effective_hit_ttl = settings.REDIS_DEFAULT_TTL

            await cache.expire(key, effective_hit_ttl)

        inflight_tasks: dict[str, asyncio.Task[Any]] = {}

        async def _call_wrapped_function(
            *call_args: Any,
            **call_kwargs: Any,
        ) -> Any:
            result = func(*call_args, **call_kwargs)
            if inspect.isawaitable(result):
                return await result

            return result

        async def _execute_and_maybe_cache(
            key: str,
            call_args: tuple[Any, ...],
            runtime_kwargs: dict[str, Any],
        ) -> Any:
            result = await _call_wrapped_function(*call_args, **runtime_kwargs)

            if await _should_cache_result(result):
                await cache.set(key, _encode_cached_payload(result), ttl)

            return result

        @wraps(func)
        async def wrapper(*args, **kwargs):
            runtime_kwargs = dict(kwargs)
            refresh_cache = _consume_control_flag(runtime_kwargs, refresh_flag)
            disable_cache = _consume_control_flag(runtime_kwargs, disable_flag)

            if disable_cache:
                return await _call_wrapped_function(*args, **runtime_kwargs)

            key_kwargs = dict(runtime_kwargs)
            for ignored_name in normalized_ignored_kwargs:
                key_kwargs.pop(ignored_name, None)

            key_args = _resolve_key_args(args)
            key = await _build_cache_key(key_args, key_kwargs)

            # Try to get from cache
            if not refresh_cache:
                cached_payload = await cache.get(key)
                has_cached_value, cached_value = _decode_cached_payload(cached_payload)
                if has_cached_value:
                    await _refresh_ttl_for_cache_hit(key)
                    return cached_value

            if not coalesce_inflight:
                return await _execute_and_maybe_cache(key, args, runtime_kwargs)

            existing_task = inflight_tasks.get(key)
            if existing_task is not None:
                return await asyncio.shield(existing_task)

            task = asyncio.create_task(
                _execute_and_maybe_cache(key, args, runtime_kwargs)
            )
            inflight_tasks[key] = task

            try:
                return await asyncio.shield(task)
            finally:
                if inflight_tasks.get(key) is task:
                    inflight_tasks.pop(key, None)

        return wrapper

    return decorator


async def invalidate_cache(
    prefix: str,
    *args: Any,
    key_version: Optional[str | int] = None,
    max_key_length: Optional[int] = None,
    key_builder: Optional[Callable[..., str | Awaitable[str]]] = None,
    ignored_kwargs: Optional[Iterable[str]] = None,
    **kwargs: Any,
) -> None:
    """
    Invalidate cache for specific key or pattern.

    Args:
        prefix: Cache key prefix
        *args: Positional arguments for key building
        key_version: Optional cache namespace version marker used in ``cached``.
        max_key_length: Optional key hashing length used with ``cached``.
        key_builder: Optional key builder used by ``cached``.
        ignored_kwargs: Optional kwarg names excluded from key generation.
        **kwargs: Keyword arguments for key building
    """
    namespace = _build_cache_namespace(prefix, key_version)
    _validate_max_key_length(max_key_length, key_namespace=namespace)

    if key_builder is not None and not callable(key_builder):
        raise ValueError("key_builder must be callable when provided")

    normalized_ignored_kwargs = _normalize_ignored_kwargs(ignored_kwargs)

    if args or kwargs:
        key_kwargs = dict(kwargs)
        for ignored_name in normalized_ignored_kwargs:
            key_kwargs.pop(ignored_name, None)

        if key_builder is not None:
            built_key = key_builder(*args, **key_kwargs)
            if inspect.isawaitable(built_key):
                built_key = await built_key

            full_key = f"{namespace}:{built_key}"
        else:
            full_key = f"{namespace}:{cache_key(*args, **key_kwargs)}"

        key = _shorten_cache_storage_key(
            full_key,
            key_namespace=namespace,
            max_key_length=max_key_length,
        )
        await cache.delete(key)
    else:
        # Delete all keys with namespace prefix
        await cache.delete_pattern(f"{namespace}:*")
