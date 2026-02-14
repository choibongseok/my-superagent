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
        # key -> tags attached to the cache entry
        self._tags_by_key: dict[str, set[str]] = {}
        # tag -> keys attached to that tag
        self._keys_by_tag: dict[str, set[str]] = {}
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

    def _delete_key(self, key: str, *, cancel_inflight: bool = True) -> None:
        """Delete key bookkeeping across all internal structures."""
        self._store.pop(key, None)
        self._access_order.pop(key, None)
        self._detach_key_from_tags(key)

        if not cancel_inflight:
            return

        in_flight = self._inflight.pop(key, None)
        if in_flight is not None and not in_flight.done():
            in_flight.cancel()

    @staticmethod
    def _normalize_tags(tags: Iterable[str]) -> set[str]:
        """Normalize and validate tag inputs."""
        normalized: set[str] = set()

        for raw_tag in tags:
            if not isinstance(raw_tag, str):
                raise TypeError("tags must contain only strings")

            tag = raw_tag.strip()
            if tag:
                normalized.add(tag)

        return normalized

    def _detach_key_from_tags(self, key: str) -> None:
        """Remove all tag-index references for ``key``."""
        existing_tags = self._tags_by_key.pop(key, None)
        if not existing_tags:
            return

        for tag in existing_tags:
            tagged_keys = self._keys_by_tag.get(tag)
            if tagged_keys is None:
                continue

            tagged_keys.discard(key)
            if not tagged_keys:
                self._keys_by_tag.pop(tag, None)

    def _replace_key_tags(self, key: str, tags: Iterable[str]) -> set[str]:
        """Replace all tags associated with ``key`` and return normalized tags."""
        normalized_tags = self._normalize_tags(tags)
        self._detach_key_from_tags(key)

        if not normalized_tags:
            return normalized_tags

        self._tags_by_key[key] = set(normalized_tags)
        for tag in normalized_tags:
            self._keys_by_tag.setdefault(tag, set()).add(key)

        return normalized_tags

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
            self._delete_key(oldest_key, cancel_inflight=False)
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

    def set_tagged(
        self,
        key: str,
        value: Any,
        *,
        tags: Iterable[str],
        ttl_seconds: int | None = None,
    ) -> None:
        """Store a value and replace all tags associated with ``key``."""
        self.set(key, value, ttl_seconds=ttl_seconds)
        self._replace_key_tags(key, tags)

    def tag(self, key: str, tags: Iterable[str]) -> bool:
        """Attach ``tags`` to an existing key.

        Returns ``False`` when the key is missing or expired.
        """
        item = self._get_entry(key)
        self._record_lookup(hit=item is not None)
        if item is None:
            return False

        normalized_tags = self._normalize_tags(tags)
        if not normalized_tags:
            return True

        existing_tags = self._tags_by_key.get(key, set())
        combined_tags = existing_tags | normalized_tags
        self._replace_key_tags(key, combined_tags)
        return True

    def untag(self, key: str, tags: Iterable[str] | None = None) -> bool:
        """Remove selected tags (or all tags) from an existing key.

        Returns ``False`` when the key is missing/expired.
        """
        item = self._get_entry(key)
        self._record_lookup(hit=item is not None)
        if item is None:
            return False

        existing_tags = self._tags_by_key.get(key)
        if not existing_tags:
            return True

        if tags is None:
            self._detach_key_from_tags(key)
            return True

        tags_to_remove = self._normalize_tags(tags)
        if not tags_to_remove:
            return True

        remaining_tags = existing_tags - tags_to_remove
        self._replace_key_tags(key, remaining_tags)
        return True

    def list_tags(self, key: str) -> list[str]:
        """List tags associated with ``key`` in sorted order."""
        item = self._get_entry(key, mark_access=False)
        if item is None:
            return []

        return sorted(self._tags_by_key.get(key, set()))

    def clear_tag(self, tag: str) -> int:
        """Delete all keys attached to ``tag`` and return removed count."""
        return self.clear_tags([tag])

    def clear_tags(
        self,
        tags: Iterable[str],
        *,
        match_all_tags: bool = False,
    ) -> int:
        """Delete keys attached to ``tags`` using any/all matching semantics.

        Args:
            tags: Tag values used to select cached entries.
            match_all_tags: Matching mode for tag selection.
                ``False`` (default) removes keys associated with any provided
                tag, while ``True`` removes only keys that contain every
                provided tag.

        Empty tags are ignored and matching keys are de-duplicated.
        """
        if not isinstance(match_all_tags, bool):
            raise ValueError("match_all_tags must be a boolean")

        matching_keys = self._resolve_keys_for_tags(
            tags,
            match_all_tags=match_all_tags,
        )
        if not matching_keys:
            return 0

        return self.delete_many(matching_keys)

    def _resolve_keys_for_tags(
        self,
        tags: Iterable[str],
        *,
        match_all_tags: bool,
    ) -> set[str]:
        """Resolve active keys matching ``tags`` with any/all semantics."""
        normalized_tags = self._normalize_tags(tags)
        if not normalized_tags:
            return set()

        if match_all_tags:
            tag_sets = [
                set(self._keys_by_tag.get(tag, set())) for tag in normalized_tags
            ]
            matching_keys = set.intersection(*tag_sets) if tag_sets else set()
        else:
            matching_keys: set[str] = set()
            for tag in normalized_tags:
                matching_keys.update(self._keys_by_tag.get(tag, set()))

        if not matching_keys:
            return set()

        return {
            key
            for key in matching_keys
            if self._get_entry(key, mark_access=False) is not None
        }

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

    def compare_and_set(
        self,
        key: str,
        expected_value: Any,
        new_value: Any,
        ttl_seconds: int | None = None,
        *,
        keep_ttl: bool = True,
    ) -> bool:
        """Update ``key`` only when its current value matches ``expected_value``.

        This lightweight compare-and-set (CAS) helper enables optimistic
        concurrency workflows without introducing external locking.

        Args:
            key: Cache key to update.
            expected_value: Value required for the update to proceed.
            new_value: Value written when comparison succeeds.
            ttl_seconds: TTL to apply when ``keep_ttl`` is ``False``.
            keep_ttl: Preserve the existing absolute expiration by default.

        Returns:
            ``True`` when the key existed and matched ``expected_value``,
            ``False`` otherwise.
        """
        item = self._get_entry(key)
        self._record_lookup(hit=item is not None)
        if item is None:
            return False

        current_value, expires_at = item
        if current_value != expected_value:
            return False

        if keep_ttl:
            self._store[key] = (new_value, expires_at)
            self._mark_accessed(key)
            self._increment_stat("sets")
            return True

        self.set(key, new_value, ttl_seconds=ttl_seconds)
        return True

    def compare_and_delete(self, key: str, expected_value: Any) -> bool:
        """Delete ``key`` only when it currently matches ``expected_value``.

        Returns:
            ``True`` when the key existed and was removed,
            ``False`` when missing/expired or value mismatch.
        """
        item = self._get_entry(key)
        self._record_lookup(hit=item is not None)
        if item is None:
            return False

        current_value, _ = item
        if current_value != expected_value:
            return False

        self._delete_key(key)
        self._increment_stat("deletes")
        return True

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

    def get_with_metadata(self, key: str) -> dict[str, Any] | None:
        """Return value with TTL/tag metadata for a single key.

        This helper provides lightweight key-level introspection without
        requiring a full ``list_entries`` scan.

        Returns:
            Dictionary containing ``key``, ``value``, ``ttl_seconds``,
            ``expires_at`` (unix timestamp), and sorted ``tags`` when key is
            present. Returns ``None`` when key is missing or expired.
        """
        item = self._get_entry(key)
        self._record_lookup(hit=item is not None)
        if item is None:
            return None

        value, expires_at = item
        ttl_seconds = None if expires_at is None else max(0.0, expires_at - time.time())

        return {
            "key": key,
            "value": value,
            "ttl_seconds": ttl_seconds,
            "expires_at": expires_at,
            "tags": sorted(self._tags_by_key.get(key, set())),
        }

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

    def touch_many(self, keys: Iterable[str], ttl_seconds: int | None) -> int:
        """Refresh TTL for multiple keys and return the update count.

        Duplicate keys are only processed once. Missing or expired keys are
        skipped.
        """
        touched = 0
        for key in dict.fromkeys(keys):
            if self.touch(key, ttl_seconds=ttl_seconds):
                touched += 1

        return touched

    def expire(self, key: str, ttl_seconds: float) -> bool:
        """Set or refresh expiration for an existing key.

        Args:
            key: Cache key to expire.
            ttl_seconds: Positive TTL in seconds.

        Returns:
            ``True`` when ``key`` exists and expiration was updated,
            ``False`` otherwise.
        """
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be greater than 0")

        item = self._get_entry(key)
        if item is None:
            return False

        value, _ = item
        self.set(key, value, ttl_seconds=ttl_seconds)
        return True

    def expire_many(self, keys: Iterable[str], ttl_seconds: float) -> int:
        """Apply :meth:`expire` to multiple keys and return the update count."""
        expired = 0
        for key in dict.fromkeys(keys):
            if self.expire(key, ttl_seconds=ttl_seconds):
                expired += 1

        return expired

    def persist(self, key: str) -> bool:
        """Remove expiration from an existing key.

        Returns ``True`` only when a key existed and had an expiration removed.
        """
        item = self._get_entry(key)
        if item is None:
            return False

        value, expires_at = item
        if expires_at is None:
            return False

        self._store[key] = (value, None)
        self._mark_accessed(key)
        self._increment_stat("sets")
        return True

    def persist_many(self, keys: Iterable[str]) -> int:
        """Remove expiration from multiple keys and return the update count."""
        persisted = 0
        for key in dict.fromkeys(keys):
            if self.persist(key):
                persisted += 1

        return persisted

    def get_and_touch(
        self,
        key: str,
        ttl_seconds: int | None,
        default: Any | None = None,
    ) -> Any | None:
        """Return value for ``key`` and refresh its TTL in one call.

        This helper supports sliding-expiration access patterns. Missing or
        expired keys return ``default`` and are not inserted.
        """
        item = self._get_entry(key)
        self._record_lookup(hit=item is not None)
        if item is None:
            return default

        value, _ = item
        self.set(key, value, ttl_seconds=ttl_seconds)
        return value

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

    def pop_many(self, keys: Iterable[str]) -> dict[str, Any]:
        """Remove and return values for multiple keys.

        Missing or expired keys are skipped. Duplicate keys are resolved once,
        preserving the order of first appearance.
        """
        values: dict[str, Any] = {}
        seen: set[str] = set()

        for key in keys:
            if key in seen:
                continue
            seen.add(key)

            item = self._get_entry(key)
            self._record_lookup(hit=item is not None)
            if item is None:
                continue

            value, _ = item
            values[key] = value
            self._delete_key(key)

        if values:
            self._increment_stat("deletes", len(values))

        return values

    def copy(self, key: str, new_key: str, *, overwrite: bool = False) -> bool:
        """Copy an active key while preserving remaining TTL and tags.

        Args:
            key: Existing cache key to copy from.
            new_key: Destination cache key.
            overwrite: When ``True``, replace ``new_key`` if it already exists.

        Returns:
            ``True`` when ``key`` exists and copy succeeds, ``False`` otherwise.
        """
        if key == new_key:
            exists = self._get_entry(key) is not None
            self._record_lookup(hit=exists)
            return exists

        item = self._get_entry(key)
        self._record_lookup(hit=item is not None)
        if item is None:
            return False

        source_tags = set(self._tags_by_key.get(key, set()))

        target_exists = self._get_entry(new_key) is not None
        self._record_lookup(hit=target_exists)
        if target_exists and not overwrite:
            return False

        if target_exists or new_key in self._inflight:
            self._delete_key(new_key)
            self._increment_stat("deletes")
        else:
            self._evict_if_needed()

        value, expires_at = item
        self._store[new_key] = (value, expires_at)
        self._mark_accessed(new_key)
        self._replace_key_tags(new_key, source_tags)
        self._increment_stat("sets")
        return True

    def copy_many(
        self,
        key_mapping: Mapping[str, str],
        *,
        overwrite: bool = False,
    ) -> int:
        """Copy multiple keys and return the number of successful copies."""
        copied = 0
        for source_key, target_key in key_mapping.items():
            if self.copy(source_key, target_key, overwrite=overwrite):
                copied += 1

        return copied

    def rename(self, key: str, new_key: str, *, overwrite: bool = False) -> bool:
        """Rename an active key while preserving value, remaining TTL, and tags.

        Args:
            key: Existing cache key to move.
            new_key: Destination cache key.
            overwrite: When ``True``, replace ``new_key`` if it already exists.

        Returns:
            ``True`` when ``key`` exists and rename succeeds, ``False`` otherwise.
        """
        if key == new_key:
            exists = self._get_entry(key) is not None
            self._record_lookup(hit=exists)
            return exists

        item = self._get_entry(key)
        self._record_lookup(hit=item is not None)
        if item is None:
            return False

        source_tags = set(self._tags_by_key.get(key, set()))

        target_exists = self._get_entry(new_key) is not None
        self._record_lookup(hit=target_exists)
        if target_exists and not overwrite:
            return False

        removed_entries = 0
        if key in self._store or key in self._inflight:
            self._delete_key(key)
            removed_entries += 1

        if target_exists or new_key in self._inflight:
            self._delete_key(new_key)
            removed_entries += 1

        value, expires_at = item
        self._store[new_key] = (value, expires_at)
        self._mark_accessed(new_key)
        self._replace_key_tags(new_key, source_tags)

        if removed_entries:
            self._increment_stat("deletes", removed_entries)
        self._increment_stat("sets")
        return True

    def rename_many(
        self,
        key_mapping: Mapping[str, str],
        *,
        overwrite: bool = False,
    ) -> int:
        """Rename multiple keys and return the number of successful moves."""
        renamed = 0
        for source_key, target_key in key_mapping.items():
            if self.rename(source_key, target_key, overwrite=overwrite):
                renamed += 1

        return renamed

    def swap(self, key: str, other_key: str) -> bool:
        """Swap values, TTLs, and tags between two active keys.

        Returns ``False`` when either key is missing/expired.
        """
        if key == other_key:
            exists = self._get_entry(key) is not None
            self._record_lookup(hit=exists)
            return exists

        left_entry = self._get_entry(key)
        self._record_lookup(hit=left_entry is not None)

        right_entry = self._get_entry(other_key)
        self._record_lookup(hit=right_entry is not None)

        if left_entry is None or right_entry is None:
            return False

        left_tags = set(self._tags_by_key.get(key, set()))
        right_tags = set(self._tags_by_key.get(other_key, set()))

        self._store[key], self._store[other_key] = right_entry, left_entry
        self._mark_accessed(key)
        self._mark_accessed(other_key)

        self._replace_key_tags(key, right_tags)
        self._replace_key_tags(other_key, left_tags)
        self._increment_stat("sets", 2)
        return True

    def delete(self, key: str) -> None:
        """Delete a cached key if present."""
        if key in self._store or key in self._inflight:
            self._delete_key(key)
            self._increment_stat("deletes")

    def delete_many(self, keys: Iterable[str]) -> int:
        """Delete multiple keys and return how many entries were removed."""
        removed = 0
        for key in keys:
            if key in self._store or key in self._inflight:
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

    def clear_prefixes(self, prefixes: Iterable[str]) -> int:
        """Delete keys that match any prefix in ``prefixes``.

        Empty prefix values are ignored. Matching keys are deduplicated so
        overlapping prefixes do not inflate the removal count.
        """
        prefix_list = [prefix for prefix in prefixes if prefix]
        if not prefix_list:
            return 0

        matching_keys = {
            key
            for key in self._store
            if any(key.startswith(prefix) for prefix in prefix_list)
        }
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
        tags: Iterable[str] | None = None,
        match_all_tags: bool = False,
        offset: int | None = None,
        limit: int | None = None,
    ) -> list[str]:
        """List active keys with optional prefix/glob/tag filtering.

        Args:
            prefix: Optional key prefix to match.
            pattern: Optional glob pattern matched with :func:`fnmatchcase`.
            tags: Optional tag filter. When provided, only keys associated with
                matching tags are returned.
            match_all_tags: Tag matching mode when ``tags`` are provided.
                ``False`` (default) returns keys matching any tag, while
                ``True`` requires keys to contain every provided tag.
            offset: Optional number of sorted matching keys to skip.
            limit: Optional maximum number of keys to return.

        Keys are returned in deterministic lexicographic order and do not affect
        hit/miss counters or LRU order.
        """
        if offset is not None and offset < 0:
            raise ValueError("offset must be greater than or equal to 0")

        if limit is not None and limit <= 0:
            raise ValueError("limit must be greater than 0")

        if not isinstance(match_all_tags, bool):
            raise ValueError("match_all_tags must be a boolean")

        self._purge_expired_entries()

        if tags is None:
            candidate_keys = set(self._store.keys())
        else:
            candidate_keys = self._resolve_keys_for_tags(
                tags,
                match_all_tags=match_all_tags,
            )

        matching_keys: list[str] = []
        for key in candidate_keys:
            if prefix is not None and not key.startswith(prefix):
                continue
            if pattern is not None and not fnmatchcase(key, pattern):
                continue
            matching_keys.append(key)

        matching_keys.sort()

        if offset:
            matching_keys = matching_keys[offset:]

        if limit is not None:
            return matching_keys[:limit]
        return matching_keys

    def list_entries(
        self,
        *,
        prefix: str | None = None,
        pattern: str | None = None,
        tags: Iterable[str] | None = None,
        match_all_tags: bool = False,
        offset: int | None = None,
        limit: int | None = None,
        include_values: bool = False,
        include_entry_tags: bool = False,
        include_expires_at: bool = False,
    ) -> list[dict[str, Any]]:
        """List active cache entries with optional filters and metadata.

        Args:
            offset: Optional number of sorted matching entries to skip.
            include_values: Include cached values in each entry payload.
            include_entry_tags: Include sorted tags associated with each key.
            include_expires_at: Include absolute unix expiration timestamps.
        """
        entries: list[dict[str, Any]] = []
        for key in self.list_keys(
            prefix=prefix,
            pattern=pattern,
            tags=tags,
            match_all_tags=match_all_tags,
            offset=offset,
            limit=limit,
        ):
            value, expires_at = self._store[key]
            entry: dict[str, Any] = {
                "key": key,
                "ttl_seconds": (
                    None if expires_at is None else max(0.0, expires_at - time.time())
                ),
            }
            if include_values:
                entry["value"] = value
            if include_entry_tags:
                entry["tags"] = sorted(self._tags_by_key.get(key, set()))
            if include_expires_at:
                entry["expires_at"] = expires_at
            entries.append(entry)

        return entries

    def stats(self, reset: bool = False) -> dict[str, Any]:
        """Return cache operational counters and runtime metadata.

        In addition to raw counters, this includes derived lookup metrics to
        simplify dashboards and alerting:

        - ``lookups``: Total cache lookups (hits + misses)
        - ``hit_rate``: Hit ratio in the ``0.0`` to ``1.0`` range
        - ``miss_rate``: Miss ratio in the ``0.0`` to ``1.0`` range

        Args:
            reset: When ``True``, reset accumulated counters after generating
                the returned snapshot.
        """
        hits = self._stats.get("hits", 0)
        misses = self._stats.get("misses", 0)
        lookups = hits + misses

        hit_rate = hits / lookups if lookups else 0.0
        miss_rate = misses / lookups if lookups else 0.0

        snapshot: dict[str, Any] = {
            **self._stats,
            "lookups": lookups,
            "hit_rate": round(hit_rate, 4),
            "miss_rate": round(miss_rate, 4),
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

        for in_flight in list(self._inflight.values()):
            if not in_flight.done():
                in_flight.cancel()

        self._store.clear()
        self._access_order.clear()
        self._inflight.clear()
        self._tags_by_key.clear()
        self._keys_by_tag.clear()
        if removed:
            self._increment_stat("deletes", removed)


__all__ = ["LocalCacheService"]
