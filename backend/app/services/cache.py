"""Lightweight local cache service used by orchestrator workflows.

The sprint docs and E2E tests expect ``LocalCacheService`` to exist in
``app.services.cache``. This in-memory TTL cache keeps that contract and adds
small ergonomics for bulk and lazy caching workflows.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Iterable, Mapping
from fnmatch import fnmatchcase
from numbers import Real
from typing import Any


class LocalCacheService:
    """Simple in-process key/value cache with optional TTL.

    The cache can optionally be size-bounded using ``max_entries``. When the
    limit is reached, least-recently-used (LRU) entries are evicted.
    """

    def __init__(self, max_entries: int | None = None) -> None:
        if max_entries is not None and max_entries <= 0:
            raise ValueError("max_entries must be greater than 0")

        # key -> (value, expires_at)
        # expires_at is None for non-expiring entries
        self._store: dict[str, tuple[Any, float | None]] = {}
        # key -> in-flight async population task
        self._inflight: dict[str, asyncio.Task[Any]] = {}
        # insertion/access order for LRU eviction
        self._access_order: OrderedDict[str, None] = OrderedDict()
        self._max_entries = max_entries
        # Operational counters for lightweight cache observability.
        self._stats: dict[str, int] = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "evictions": 0,
            "expirations": 0,
        }

    def _increment_stat(self, name: str, amount: int = 1) -> None:
        """Increment a named statistic by ``amount``."""
        self._stats[name] = self._stats.get(name, 0) + amount

    def _record_lookup(self, *, hit: bool) -> None:
        """Record cache lookup hit/miss counters."""
        self._increment_stat("hits" if hit else "misses")

    def _delete_key(self, key: str) -> None:
        """Delete key bookkeeping across all internal structures."""
        self._store.pop(key, None)
        self._access_order.pop(key, None)

    def _mark_accessed(self, key: str) -> None:
        """Mark key as recently used for LRU eviction tracking."""
        self._access_order[key] = None
        self._access_order.move_to_end(key)

    def _purge_expired_entries(self) -> int:
        """Remove all expired keys from the cache and return removal count."""
        return self.prune_expired()

    def _evict_if_needed(self) -> None:
        """Evict least-recently-used entries when size limit is reached."""
        if self._max_entries is None:
            return

        self._purge_expired_entries()
        while len(self._store) >= self._max_entries and self._access_order:
            oldest_key, _ = self._access_order.popitem(last=False)
            self._store.pop(oldest_key, None)
            self._increment_stat("evictions")

    def _get_entry(
        self,
        key: str,
        *,
        mark_access: bool = True,
    ) -> tuple[Any, float | None] | None:
        """Return a non-expired cache entry or ``None`` when missing/expired."""
        item = self._store.get(key)
        if item is None:
            return None

        _, expires_at = item
        if expires_at is not None and time.time() >= expires_at:
            self._delete_key(key)
            self._increment_stat("expirations")
            return None

        if mark_access:
            self._mark_accessed(key)
        return item

    @staticmethod
    def _validate_numeric(value: Any, *, field_name: str) -> Real:
        """Validate and return numeric values used by arithmetic cache operations."""
        if isinstance(value, bool) or not isinstance(value, Real):
            raise TypeError(f"{field_name} must be a numeric value")
        return value

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        """Store a value, optionally expiring after ``ttl_seconds``."""
        expires_at = None
        if ttl_seconds is not None and ttl_seconds > 0:
            expires_at = time.time() + ttl_seconds

        if key not in self._store:
            self._evict_if_needed()

        self._store[key] = (value, expires_at)
        self._mark_accessed(key)
        self._increment_stat("sets")

    def set_many(
        self, items: Mapping[str, Any], ttl_seconds: int | None = None
    ) -> None:
        """Store multiple key/value pairs with an optional shared TTL."""
        for key, value in items.items():
            self.set(key, value, ttl_seconds=ttl_seconds)

    def replace(
        self,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
        *,
        keep_ttl: bool = True,
    ) -> bool:
        """Replace an existing key value and return whether replacement happened.

        Args:
            key: Cache key to update.
            value: New value to store.
            ttl_seconds: TTL to apply when ``keep_ttl`` is ``False``.
            keep_ttl: Preserve the current absolute expiration by default.

        Returns:
            ``True`` when an active key existed and was replaced,
            ``False`` otherwise.
        """
        item = self._get_entry(key)
        self._record_lookup(hit=item is not None)
        if item is None:
            return False

        _, expires_at = item
        if keep_ttl:
            self._store[key] = (value, expires_at)
            self._mark_accessed(key)
            self._increment_stat("sets")
            return True

        self.set(key, value, ttl_seconds=ttl_seconds)
        return True

    def replace_many(
        self,
        items: Mapping[str, Any],
        ttl_seconds: int | None = None,
        *,
        keep_ttl: bool = True,
    ) -> int:
        """Replace multiple existing keys and return the replacement count."""
        replaced = 0
        for key, value in items.items():
            if self.replace(
                key,
                value,
                ttl_seconds=ttl_seconds,
                keep_ttl=keep_ttl,
            ):
                replaced += 1

        return replaced

    def set_if_absent(
        self,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> bool:
        """Store ``value`` only when ``key`` is currently missing.

        Returns:
            ``True`` when the value was inserted, ``False`` when an active
            (non-expired) value already exists for ``key``.
        """
        item = self._get_entry(key)
        self._record_lookup(hit=item is not None)
        if item is not None:
            return False

        self.set(key, value, ttl_seconds=ttl_seconds)
        return True

    def get(self, key: str) -> Any | None:
        """Return cached value or ``None`` when missing/expired."""
        item = self._get_entry(key)
        self._record_lookup(hit=item is not None)
        if item is None:
            return None

        value, _ = item
        return value

    def peek(self, key: str, default: Any | None = None) -> Any | None:
        """Read a cached value without affecting stats or LRU order."""
        item = self._get_entry(key, mark_access=False)
        if item is None:
            return default

        value, _ = item
        return value

    def get_many(self, keys: Iterable[str]) -> dict[str, Any]:
        """Return available values for the requested keys."""
        results: dict[str, Any] = {}
        for key in keys:
            item = self._get_entry(key)
            self._record_lookup(hit=item is not None)
            if item is not None:
                value, _ = item
                results[key] = value
        return results

    def peek_many(self, keys: Iterable[str]) -> dict[str, Any]:
        """Read multiple cached values without affecting stats or LRU order."""
        results: dict[str, Any] = {}
        for key in keys:
            item = self._get_entry(key, mark_access=False)
            if item is not None:
                value, _ = item
                results[key] = value
        return results

    def _resolve_missing_values(
        self,
        missing_keys: list[str],
        produced_values: Mapping[str, Any],
        *,
        ttl_seconds: int | None,
        resolved_values: dict[str, Any],
    ) -> None:
        """Validate and persist factory-produced values for missing keys."""
        unresolved_keys = [key for key in missing_keys if key not in produced_values]
        if unresolved_keys:
            missing_display = ", ".join(unresolved_keys)
            raise ValueError(
                f"factory result is missing values for keys: {missing_display}"
            )

        for key in missing_keys:
            value = produced_values[key]
            self.set(key, value, ttl_seconds=ttl_seconds)
            resolved_values[key] = value

    @staticmethod
    def _order_resolved_values(
        requested_keys: list[str],
        resolved_values: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Return resolved values in deterministic request order without duplicates."""
        ordered_results: dict[str, Any] = {}
        for key in requested_keys:
            if key in resolved_values and key not in ordered_results:
                ordered_results[key] = resolved_values[key]

        return ordered_results

    def get_or_set_many(
        self,
        keys: Iterable[str],
        factory: Callable[[list[str]], Mapping[str, Any]],
        ttl_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Return values for ``keys``, populating misses in one factory call.

        Args:
            keys: Cache keys to resolve.
            factory: Callable that receives missing keys and returns a mapping
                containing values for each missing key.
            ttl_seconds: Optional TTL applied only to values populated by
                ``factory``.

        Returns:
            Mapping of resolved key/value pairs for the requested keys.

        Raises:
            TypeError: If ``factory`` is not callable or does not return a
                mapping.
            ValueError: If the factory result omits any requested missing key.
        """
        if not callable(factory):
            raise TypeError("factory must be callable")

        requested_keys = list(keys)
        lookup_cache: dict[str, tuple[Any, float | None] | None] = {}
        resolved_values: dict[str, Any] = {}
        missing_keys: list[str] = []

        for key in requested_keys:
            item = lookup_cache.get(key)
            if key not in lookup_cache:
                item = self._get_entry(key)
                lookup_cache[key] = item
                if item is None:
                    missing_keys.append(key)
                else:
                    value, _ = item
                    resolved_values[key] = value

            self._record_lookup(hit=item is not None)

        if missing_keys:
            unique_missing_keys = list(dict.fromkeys(missing_keys))
            produced_values = factory(unique_missing_keys)
            if not isinstance(produced_values, Mapping):
                raise TypeError("factory must return a mapping of key/value pairs")

            self._resolve_missing_values(
                unique_missing_keys,
                produced_values,
                ttl_seconds=ttl_seconds,
                resolved_values=resolved_values,
            )

        return self._order_resolved_values(requested_keys, resolved_values)

    async def get_or_set_many_async(
        self,
        keys: Iterable[str],
        factory: Callable[
            [list[str]], Mapping[str, Any] | Awaitable[Mapping[str, Any]]
        ],
        ttl_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Async-friendly bulk variant of :meth:`get_or_set_many`.

        The ``factory`` receives a list of missing keys and may return either a
        mapping directly or an awaitable that resolves to a mapping.
        """
        if not callable(factory):
            raise TypeError("factory must be callable")

        requested_keys = list(keys)
        lookup_cache: dict[str, tuple[Any, float | None] | None] = {}
        resolved_values: dict[str, Any] = {}
        missing_keys: list[str] = []

        for key in requested_keys:
            item = lookup_cache.get(key)
            if key not in lookup_cache:
                item = self._get_entry(key)
                lookup_cache[key] = item
                if item is None:
                    missing_keys.append(key)
                else:
                    value, _ = item
                    resolved_values[key] = value

            self._record_lookup(hit=item is not None)

        if missing_keys:
            unique_missing_keys = list(dict.fromkeys(missing_keys))
            produced_values = factory(unique_missing_keys)
            if inspect.isawaitable(produced_values):
                produced_values = await produced_values
            if not isinstance(produced_values, Mapping):
                raise TypeError("factory must return a mapping of key/value pairs")

            self._resolve_missing_values(
                unique_missing_keys,
                produced_values,
                ttl_seconds=ttl_seconds,
                resolved_values=resolved_values,
            )

        return self._order_resolved_values(requested_keys, resolved_values)

    def has(self, key: str) -> bool:
        """Return ``True`` when a non-expired key exists."""
        exists = self._get_entry(key) is not None
        self._record_lookup(hit=exists)
        return exists

    def ttl_remaining(self, key: str) -> float | None:
        """Return remaining TTL seconds for ``key``.

        Returns ``None`` when the key is missing/expired or when it has no
        expiration configured.
        """
        item = self._get_entry(key)
        if item is None:
            return None

        _, expires_at = item
        if expires_at is None:
            return None

        return max(0.0, expires_at - time.time())

    def touch(self, key: str, ttl_seconds: int | None) -> bool:
        """Refresh TTL for an existing key while preserving its value.

        Args:
            key: Cache key to refresh.
            ttl_seconds: New TTL to apply. ``None`` or non-positive values make
                the key non-expiring.

        Returns:
            ``True`` when the key exists and was updated, ``False`` otherwise.
        """
        item = self._get_entry(key)
        if item is None:
            return False

        value, _ = item
        self.set(key, value, ttl_seconds=ttl_seconds)
        return True

    def increment(
        self,
        key: str,
        amount: Real = 1,
        *,
        initial: Real = 0,
        ttl_seconds: int | None = None,
    ) -> Real:
        """Increase a numeric cache value and return the updated number.

        Missing/expired keys are initialized from ``initial`` before applying
        ``amount``. Existing key TTL is preserved unless ``ttl_seconds`` is
        explicitly provided.
        """
        numeric_amount = self._validate_numeric(amount, field_name="amount")
        item = self._get_entry(key)

        if item is None:
            numeric_current = self._validate_numeric(initial, field_name="initial")
            self._evict_if_needed()
            expires_at = None
        else:
            current, expires_at = item
            numeric_current = self._validate_numeric(
                current, field_name="existing cache value"
            )

        if ttl_seconds is not None:
            expires_at = time.time() + ttl_seconds if ttl_seconds > 0 else None

        new_value = numeric_current + numeric_amount
        self._store[key] = (new_value, expires_at)
        self._mark_accessed(key)
        return new_value

    def decrement(
        self,
        key: str,
        amount: Real = 1,
        *,
        initial: Real = 0,
        ttl_seconds: int | None = None,
    ) -> Real:
        """Decrease a numeric cache value and return the updated number."""
        numeric_amount = self._validate_numeric(amount, field_name="amount")
        if numeric_amount < 0:
            raise ValueError("amount must be greater than or equal to 0")

        return self.increment(
            key,
            amount=-numeric_amount,
            initial=initial,
            ttl_seconds=ttl_seconds,
        )

    def get_or_set(
        self,
        key: str,
        factory: Callable[[], Any],
        ttl_seconds: int | None = None,
    ) -> Any:
        """Return cached value or populate it via ``factory`` when absent."""
        item = self._get_entry(key)
        self._record_lookup(hit=item is not None)
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
        self._record_lookup(hit=item is not None)
        if item is not None:
            value, _ = item
            return value

        in_flight = self._inflight.get(key)
        if in_flight is None:
            in_flight = asyncio.create_task(
                self._populate_async(key, factory, ttl_seconds)
            )
            self._track_inflight(key, in_flight)

        return await asyncio.shield(in_flight)

    def pop(self, key: str, default: Any | None = None) -> Any | None:
        """Remove and return ``key`` value, or ``default`` when absent."""
        item = self._get_entry(key)
        self._record_lookup(hit=item is not None)
        if item is None:
            return default

        value, _ = item
        self._delete_key(key)
        self._increment_stat("deletes")
        return value

    def delete(self, key: str) -> None:
        """Delete a cached key if present."""
        if key in self._store:
            self._delete_key(key)
            self._increment_stat("deletes")

    def delete_many(self, keys: Iterable[str]) -> int:
        """Delete multiple keys and return how many entries were removed."""
        removed = 0
        for key in keys:
            if key in self._store:
                self._delete_key(key)
                removed += 1

        if removed:
            self._increment_stat("deletes", removed)
        return removed

    def prune_expired(self) -> int:
        """Remove expired keys immediately and return the number deleted."""
        now = time.time()
        expired_keys = [
            key
            for key, (_, expires_at) in self._store.items()
            if expires_at is not None and now >= expires_at
        ]
        for key in expired_keys:
            self._delete_key(key)

        if expired_keys:
            self._increment_stat("expirations", len(expired_keys))

        return len(expired_keys)

    def clear_prefix(self, prefix: str) -> int:
        """Delete all keys that start with ``prefix`` and return removal count."""
        matching_keys = [key for key in self._store if key.startswith(prefix)]
        return self.delete_many(matching_keys)

    def clear_pattern(self, pattern: str) -> int:
        """Delete keys that match a glob ``pattern``.

        Pattern syntax follows :mod:`fnmatch` conventions (for example,
        ``"user:*:profile"`` or ``"workspace:?"``).
        """
        matching_keys = [key for key in self._store if fnmatchcase(key, pattern)]
        return self.delete_many(matching_keys)

    def clear_patterns(self, patterns: Iterable[str]) -> int:
        """Delete keys that match any glob pattern in ``patterns``."""
        pattern_list = [pattern for pattern in patterns if pattern]
        if not pattern_list:
            return 0

        matching_keys = {
            key
            for key in self._store
            if any(fnmatchcase(key, pattern) for pattern in pattern_list)
        }
        return self.delete_many(matching_keys)

    def list_keys(
        self,
        *,
        prefix: str | None = None,
        pattern: str | None = None,
        limit: int | None = None,
    ) -> list[str]:
        """List active keys with optional prefix/glob filtering.

        Keys are returned in deterministic lexicographic order and do not affect
        hit/miss counters or LRU order.
        """
        if limit is not None and limit <= 0:
            raise ValueError("limit must be greater than 0")

        self._purge_expired_entries()

        matching_keys: list[str] = []
        for key in self._store:
            if prefix is not None and not key.startswith(prefix):
                continue
            if pattern is not None and not fnmatchcase(key, pattern):
                continue
            matching_keys.append(key)

        matching_keys.sort()
        if limit is not None:
            return matching_keys[:limit]
        return matching_keys

    def list_entries(
        self,
        *,
        prefix: str | None = None,
        pattern: str | None = None,
        limit: int | None = None,
        include_values: bool = False,
    ) -> list[dict[str, Any]]:
        """List active cache entries with optional value and TTL metadata."""
        entries: list[dict[str, Any]] = []
        for key in self.list_keys(prefix=prefix, pattern=pattern, limit=limit):
            value, expires_at = self._store[key]
            entry: dict[str, Any] = {
                "key": key,
                "ttl_seconds": (
                    None if expires_at is None else max(0.0, expires_at - time.time())
                ),
            }
            if include_values:
                entry["value"] = value
            entries.append(entry)

        return entries

    def stats(self, reset: bool = False) -> dict[str, Any]:
        """Return cache operational counters and runtime metadata.

        Args:
            reset: When ``True``, reset accumulated counters after generating
                the returned snapshot.
        """
        snapshot: dict[str, Any] = {
            **self._stats,
            "entries": self.size(),
            "max_entries": self._max_entries,
            "inflight": len(self._inflight),
        }

        if reset:
            for key in self._stats:
                self._stats[key] = 0

        return snapshot

    def size(self) -> int:
        """Return the number of active (non-expired) cache entries."""
        self._purge_expired_entries()
        return len(self._store)

    def clear(self) -> None:
        """Clear all cached entries."""
        removed = len(self._store)
        self._store.clear()
        self._access_order.clear()
        self._inflight.clear()
        if removed:
            self._increment_stat("deletes", removed)


__all__ = ["LocalCacheService"]
