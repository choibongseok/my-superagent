"""Lightweight local cache service used by orchestrator workflows.

The sprint docs and E2E tests expect ``LocalCacheService`` to exist in
``app.services.cache``. This in-memory TTL cache keeps that contract and adds
small ergonomics for bulk and lazy caching workflows.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable, Iterable, Mapping
from typing import Any


class LocalCacheService:
    """Simple in-process key/value cache with optional TTL."""

    def __init__(self) -> None:
        # key -> (value, expires_at)
        # expires_at is None for non-expiring entries
        self._store: dict[str, tuple[Any, float | None]] = {}
        # key -> in-flight async population task
        self._inflight: dict[str, asyncio.Task[Any]] = {}

    def _get_entry(self, key: str) -> tuple[Any, float | None] | None:
        """Return a non-expired cache entry or ``None`` when missing/expired."""
        item = self._store.get(key)
        if item is None:
            return None

        _, expires_at = item
        if expires_at is not None and time.time() >= expires_at:
            self._store.pop(key, None)
            return None

        return item

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        """Store a value, optionally expiring after ``ttl_seconds``."""
        expires_at = None
        if ttl_seconds is not None and ttl_seconds > 0:
            expires_at = time.time() + ttl_seconds
        self._store[key] = (value, expires_at)

    def set_many(self, items: Mapping[str, Any], ttl_seconds: int | None = None) -> None:
        """Store multiple key/value pairs with an optional shared TTL."""
        for key, value in items.items():
            self.set(key, value, ttl_seconds=ttl_seconds)

    def get(self, key: str) -> Any | None:
        """Return cached value or ``None`` when missing/expired."""
        item = self._get_entry(key)
        if item is None:
            return None

        value, _ = item
        return value

    def get_many(self, keys: Iterable[str]) -> dict[str, Any]:
        """Return available values for the requested keys."""
        results: dict[str, Any] = {}
        for key in keys:
            item = self._get_entry(key)
            if item is not None:
                value, _ = item
                results[key] = value
        return results

    def has(self, key: str) -> bool:
        """Return ``True`` when a non-expired key exists."""
        return self._get_entry(key) is not None

    def get_or_set(
        self,
        key: str,
        factory: Callable[[], Any],
        ttl_seconds: int | None = None,
    ) -> Any:
        """Return cached value or populate it via ``factory`` when absent."""
        item = self._get_entry(key)
        if item is not None:
            value, _ = item
            return value

        value = factory()
        self.set(key, value, ttl_seconds=ttl_seconds)
        return value

    async def _resolve_async_factory(
        self,
        factory: Callable[[], Awaitable[Any] | Any],
    ) -> Any:
        """Resolve a lazy factory that may be sync or async."""
        produced = factory()
        return await produced if inspect.isawaitable(produced) else produced

    async def _populate_async(
        self,
        key: str,
        factory: Callable[[], Awaitable[Any] | Any],
        ttl_seconds: int | None,
    ) -> Any:
        """Populate a key from ``factory`` and persist it in cache."""
        value = await self._resolve_async_factory(factory)
        self.set(key, value, ttl_seconds=ttl_seconds)
        return value

    def _track_inflight(self, key: str, task: asyncio.Task[Any]) -> None:
        """Track an in-flight task and clean it up when it finishes."""
        self._inflight[key] = task

        def _cleanup(finished: asyncio.Task[Any]) -> None:
            if self._inflight.get(key) is finished:
                self._inflight.pop(key, None)

        task.add_done_callback(_cleanup)

    async def get_or_set_async(
        self,
        key: str,
        factory: Callable[[], Awaitable[Any] | Any],
        ttl_seconds: int | None = None,
    ) -> Any:
        """Async-friendly variant of :meth:`get_or_set`.

        The ``factory`` may return either a direct value or an awaitable.
        Concurrent callers for the same key are de-duplicated so that only
        one factory execution runs while others await the same result.

        This method is cancellation-safe for shared in-flight work: if one
        caller is cancelled, the underlying population task continues and
        other callers still receive/cache the resolved value.
        """
        item = self._get_entry(key)
        if item is not None:
            value, _ = item
            return value

        in_flight = self._inflight.get(key)
        if in_flight is None:
            in_flight = asyncio.create_task(self._populate_async(key, factory, ttl_seconds))
            self._track_inflight(key, in_flight)

        return await asyncio.shield(in_flight)

    def delete(self, key: str) -> None:
        """Delete a cached key if present."""
        self._store.pop(key, None)

    def delete_many(self, keys: Iterable[str]) -> int:
        """Delete multiple keys and return how many entries were removed."""
        removed = 0
        for key in keys:
            if key in self._store:
                self._store.pop(key, None)
                removed += 1
        return removed

    def clear_prefix(self, prefix: str) -> int:
        """Delete all keys that start with ``prefix`` and return removal count."""
        matching_keys = [key for key in self._store if key.startswith(prefix)]
        return self.delete_many(matching_keys)

    def size(self) -> int:
        """Return the number of active (non-expired) cache entries."""
        # Purge expired entries as a side effect to keep the store tidy.
        for key in list(self._store.keys()):
            self._get_entry(key)
        return len(self._store)

    def clear(self) -> None:
        """Clear all cached entries."""
        self._store.clear()


__all__ = ["LocalCacheService"]
