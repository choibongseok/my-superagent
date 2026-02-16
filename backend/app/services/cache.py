"""Lightweight local cache service used by orchestrator workflows.

The sprint docs and E2E tests expect ``LocalCacheService`` to exist in
``app.services.cache``. This in-memory TTL cache keeps that contract and adds
small ergonomics for bulk and lazy caching workflows.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from collections import Counter, OrderedDict
from collections.abc import Awaitable, Callable, Iterable, Mapping
from fnmatch import fnmatchcase
from numbers import Real
from typing import Any, Literal, cast

_MISSING = object()


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

    def list_tag_stats(
        self,
        *,
        prefix: str | None = None,
        pattern: str | None = None,
        tag_prefix: str | None = None,
        tag_pattern: str | None = None,
        min_count: int | None = None,
        max_count: int | None = None,
        offset: int | None = None,
        limit: int | None = None,
        include_keys: bool = False,
        sort_by: str = "tag",
        descending: bool = False,
    ) -> list[dict[str, Any]]:
        """List active tags with per-tag entry counts.

        Args:
            prefix: Optional key prefix filter applied to keys counted per tag.
            pattern: Optional key glob filter applied with :func:`fnmatchcase`.
            tag_prefix: Optional tag-name prefix filter.
            tag_pattern: Optional tag-name glob filter.
            min_count: Optional minimum number of matching keys required
                for a tag to be included.
            max_count: Optional maximum number of matching keys allowed
                for a tag to be included.
            offset: Optional number of sorted tag rows to skip.
            limit: Optional maximum number of tag rows to return.
            include_keys: Include sorted matching keys for each tag row.
            sort_by: Sort criterion, either ``"tag"`` or ``"count"``.
            descending: Return rows in descending order when ``True``.

        Returns:
            A sorted list of dictionaries in ``{"tag": str, "count": int}``
            shape. When ``include_keys`` is ``True``, each row includes
            ``"keys"`` with the matching key names.

        Notes:
            Expired keys are ignored and cleaned up during enumeration. This
            helper does not affect lookup stats or LRU order.
        """
        if tag_prefix is not None and not isinstance(tag_prefix, str):
            raise ValueError("tag_prefix must be a string")

        if tag_pattern is not None and not isinstance(tag_pattern, str):
            raise ValueError("tag_pattern must be a string")

        if min_count is not None:
            if isinstance(min_count, bool) or not isinstance(min_count, int):
                raise ValueError("min_count must be a non-negative integer")
            if min_count < 0:
                raise ValueError("min_count must be a non-negative integer")

        if max_count is not None:
            if isinstance(max_count, bool) or not isinstance(max_count, int):
                raise ValueError("max_count must be a non-negative integer")
            if max_count < 0:
                raise ValueError("max_count must be a non-negative integer")

        if min_count is not None and max_count is not None and min_count > max_count:
            raise ValueError("min_count cannot be greater than max_count")

        if offset is not None and offset < 0:
            raise ValueError("offset must be greater than or equal to 0")

        if limit is not None and limit <= 0:
            raise ValueError("limit must be greater than 0")

        if not isinstance(include_keys, bool):
            raise ValueError("include_keys must be a boolean")

        if sort_by not in {"tag", "count"}:
            raise ValueError('sort_by must be either "tag" or "count"')

        if not isinstance(descending, bool):
            raise ValueError("descending must be a boolean")

        self._purge_expired_entries()

        rows: list[dict[str, Any]] = []
        for tag in sorted(list(self._keys_by_tag.keys())):
            if tag_prefix is not None and not tag.startswith(tag_prefix):
                continue
            if tag_pattern is not None and not fnmatchcase(tag, tag_pattern):
                continue

            matching_keys: list[str] = []
            for key in sorted(self._keys_by_tag.get(tag, set())):
                if self._get_entry(key, mark_access=False) is None:
                    continue
                if prefix is not None and not key.startswith(prefix):
                    continue
                if pattern is not None and not fnmatchcase(key, pattern):
                    continue
                matching_keys.append(key)

            if not matching_keys:
                continue

            tag_count = len(matching_keys)
            if min_count is not None and tag_count < min_count:
                continue
            if max_count is not None and tag_count > max_count:
                continue

            row: dict[str, Any] = {
                "tag": tag,
                "count": tag_count,
            }
            if include_keys:
                row["keys"] = matching_keys
            rows.append(row)

        if sort_by == "count":
            if descending:
                rows.sort(key=lambda row: (-row["count"], row["tag"]))
            else:
                rows.sort(key=lambda row: (row["count"], row["tag"]))
        else:
            rows.sort(key=lambda row: row["tag"], reverse=descending)

        if offset:
            rows = rows[offset:]

        if limit is not None:
            return rows[:limit]
        return rows

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

    def update(
        self,
        key: str,
        updater: Callable[[Any], Any],
        *,
        default: Any = _MISSING,
        ttl_seconds: int | None = None,
        keep_ttl: bool = True,
    ) -> Any:
        """Transform and store a key using ``updater``.

        Args:
            key: Cache key to update.
            updater: Callable receiving the current value and returning the
                next value to store.
            default: Optional value used when ``key`` is missing or expired.
                When omitted, missing keys raise :class:`LookupError`.
            ttl_seconds: TTL to apply for new keys, or when ``keep_ttl`` is
                ``False`` for existing keys.
            keep_ttl: Preserve the current absolute expiration for existing
                keys by default.

        Returns:
            The new value returned by ``updater``.

        Raises:
            LookupError: If ``key`` is missing/expired and ``default`` is not
                provided.
            TypeError: If ``updater`` is not callable or returns an awaitable.
            ValueError: If ``keep_ttl`` is not a boolean.
        """
        if not callable(updater):
            raise TypeError("updater must be callable")

        if not isinstance(keep_ttl, bool):
            raise ValueError("keep_ttl must be a boolean")

        item = self._get_entry(key)
        self._record_lookup(hit=item is not None)

        if item is None:
            if default is _MISSING:
                raise LookupError(
                    "update cannot mutate a missing key without a default"
                )

            new_value = updater(default)
            if inspect.isawaitable(new_value):
                raise TypeError("updater must return a non-awaitable value")

            self.set(key, new_value, ttl_seconds=ttl_seconds)
            return new_value

        current_value, expires_at = item
        new_value = updater(current_value)
        if inspect.isawaitable(new_value):
            raise TypeError("updater must return a non-awaitable value")

        if keep_ttl:
            self._store[key] = (new_value, expires_at)
            self._mark_accessed(key)
            self._increment_stat("sets")
            return new_value

        self.set(key, new_value, ttl_seconds=ttl_seconds)
        return new_value

    def update_many(
        self,
        keys: Iterable[str],
        updater: Callable[[Any], Any],
        *,
        default: Any = _MISSING,
        ttl_seconds: int | None = None,
        keep_ttl: bool = True,
    ) -> dict[str, Any]:
        """Apply :meth:`update` across multiple keys.

        Duplicate keys are processed once, preserving the order of first
        appearance in ``keys``.
        """
        updated_values: dict[str, Any] = {}
        for key in dict.fromkeys(keys):
            updated_values[key] = self.update(
                key,
                updater,
                default=default,
                ttl_seconds=ttl_seconds,
                keep_ttl=keep_ttl,
            )

        return updated_values

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

    def get_many_with_metadata(
        self,
        keys: Iterable[str],
        *,
        include_missing: bool = False,
    ) -> dict[str, dict[str, Any] | None]:
        """Return metadata payloads for multiple keys.

        Duplicate keys are resolved once, preserving order of first appearance.

        Args:
            keys: Cache keys to inspect.
            include_missing: Include missing/expired keys with ``None`` values
                in the returned mapping.

        Returns:
            Mapping of key -> metadata dictionaries (same shape as
            :meth:`get_with_metadata`) and optionally ``None`` placeholders for
            missing keys when ``include_missing`` is ``True``.
        """
        results: dict[str, dict[str, Any] | None] = {}

        for key in dict.fromkeys(keys):
            item = self._get_entry(key)
            self._record_lookup(hit=item is not None)

            if item is None:
                if include_missing:
                    results[key] = None
                continue

            value, expires_at = item
            ttl_seconds = (
                None if expires_at is None else max(0.0, expires_at - time.time())
            )
            results[key] = {
                "key": key,
                "value": value,
                "ttl_seconds": ttl_seconds,
                "expires_at": expires_at,
                "tags": sorted(self._tags_by_key.get(key, set())),
            }

        return results

    def peek(self, key: str, default: Any | None = None) -> Any | None:
        """Read a cached value without affecting stats or LRU order."""
        item = self._get_entry(key, mark_access=False)
        if item is None:
            return default

        value, _ = item
        return value

    def get_many(
        self,
        keys: Iterable[str],
        *,
        include_missing: bool = False,
        default: Any | None = None,
    ) -> dict[str, Any]:
        """Return cached values for ``keys`` with optional missing-key placeholders.

        Duplicate keys are resolved only once and results preserve first-seen
        request order.
        """
        if not isinstance(include_missing, bool):
            raise ValueError("include_missing must be a boolean")

        results: dict[str, Any] = {}
        lookup_cache: dict[str, tuple[Any, float | None] | None] = {}
        for key in keys:
            if key in lookup_cache:
                item = lookup_cache[key]
            else:
                item = self._get_entry(key)
                lookup_cache[key] = item
                self._record_lookup(hit=item is not None)

            if item is not None:
                value, _ = item
                results[key] = value
            elif include_missing:
                results[key] = default

        return results

    def peek_many(
        self,
        keys: Iterable[str],
        *,
        include_missing: bool = False,
        default: Any | None = None,
    ) -> dict[str, Any]:
        """Read multiple values without touching stats or LRU order.

        Duplicate keys are resolved once and results preserve first-seen
        request order.
        """
        if not isinstance(include_missing, bool):
            raise ValueError("include_missing must be a boolean")

        results: dict[str, Any] = {}
        lookup_cache: dict[str, tuple[Any, float | None] | None] = {}
        for key in keys:
            if key in lookup_cache:
                item = lookup_cache[key]
            else:
                item = self._get_entry(key, mark_access=False)
                lookup_cache[key] = item

            if item is not None:
                value, _ = item
                results[key] = value
            elif include_missing:
                results[key] = default

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

    def has_many(self, keys: Iterable[str]) -> dict[str, bool]:
        """Return existence flags for requested keys.

        Duplicate keys are resolved once, preserving first-seen order.
        Missing or expired keys are included with ``False`` values.
        """
        results: dict[str, bool] = {}

        for key in dict.fromkeys(keys):
            exists = self._get_entry(key) is not None
            self._record_lookup(hit=exists)
            results[key] = exists

        return results

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

    def ttl_remaining_many(
        self,
        keys: Iterable[str],
        *,
        include_missing: bool = False,
    ) -> dict[str, float | None]:
        """Return TTL metadata for multiple keys.

        Duplicate keys are processed once, preserving order of first
        appearance.

        Args:
            keys: Cache keys to inspect.
            include_missing: Include missing/expired keys in the output with
                ``None`` values.

        Returns:
            Mapping of key -> remaining TTL seconds. Non-expiring keys are
            included with ``None`` values.
        """
        results: dict[str, float | None] = {}

        for key in dict.fromkeys(keys):
            item = self._get_entry(key)
            if item is None:
                if include_missing:
                    results[key] = None
                continue

            _, expires_at = item
            if expires_at is None:
                results[key] = None
                continue

            results[key] = max(0.0, expires_at - time.time())

        return results

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

    def get_and_touch_many(
        self,
        keys: Iterable[str],
        ttl_seconds: int | None,
    ) -> dict[str, Any]:
        """Return values for existing keys and refresh TTL in one pass.

        Duplicate keys are processed once, preserving the order of first
        appearance. Missing or expired keys are skipped.
        """
        values: dict[str, Any] = {}

        for key in dict.fromkeys(keys):
            item = self._get_entry(key)
            self._record_lookup(hit=item is not None)
            if item is None:
                continue

            value, _ = item
            self.set(key, value, ttl_seconds=ttl_seconds)
            values[key] = value

        return values

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

    def increment_many(
        self,
        updates: Mapping[str, Real],
        *,
        initial: Real = 0,
        ttl_seconds: int | None = None,
    ) -> dict[str, Real]:
        """Increase multiple keys and return updated values by key.

        Args:
            updates: Mapping of ``key -> amount`` increments.
            initial: Baseline value used when a key is missing/expired.
            ttl_seconds: Optional TTL override applied to each updated key.

        Returns:
            Ordered mapping of updated numeric values for each processed key.
            Duplicate keys are naturally coalesced by mapping semantics.
        """
        updated_values: dict[str, Real] = {}
        for key, amount in updates.items():
            updated_values[key] = self.increment(
                key,
                amount=amount,
                initial=initial,
                ttl_seconds=ttl_seconds,
            )

        return updated_values

    def decrement_many(
        self,
        updates: Mapping[str, Real],
        *,
        initial: Real = 0,
        ttl_seconds: int | None = None,
    ) -> dict[str, Real]:
        """Decrease multiple keys and return updated values by key.

        Args:
            updates: Mapping of ``key -> amount`` decrements.
            initial: Baseline value used when a key is missing/expired.
            ttl_seconds: Optional TTL override applied to each updated key.

        Returns:
            Ordered mapping of updated numeric values for each processed key.

        Raises:
            ValueError: If any decrement amount is negative.
        """
        updated_values: dict[str, Real] = {}
        for key, amount in updates.items():
            updated_values[key] = self.decrement(
                key,
                amount=amount,
                initial=initial,
                ttl_seconds=ttl_seconds,
            )

        return updated_values

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

    def _all_known_keys(self) -> set[str]:
        """Return keys known to cache storage or in-flight population tasks."""
        return set(self._store) | set(self._inflight)

    def clear_prefix(self, prefix: str) -> int:
        """Delete all keys that start with ``prefix`` and return removal count."""
        matching_keys = [
            key for key in self._all_known_keys() if key.startswith(prefix)
        ]
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
            for key in self._all_known_keys()
            if any(key.startswith(prefix) for prefix in prefix_list)
        }
        return self.delete_many(matching_keys)

    def clear_pattern(self, pattern: str) -> int:
        """Delete keys that match a glob ``pattern``.

        Pattern syntax follows :mod:`fnmatch` conventions (for example,
        ``"user:*:profile"`` or ``"workspace:?"``).
        """
        matching_keys = [
            key for key in self._all_known_keys() if fnmatchcase(key, pattern)
        ]
        return self.delete_many(matching_keys)

    def clear_patterns(self, patterns: Iterable[str]) -> int:
        """Delete keys that match any glob pattern in ``patterns``."""
        pattern_list = [pattern for pattern in patterns if pattern]
        if not pattern_list:
            return 0

        matching_keys = {
            key
            for key in self._all_known_keys()
            if any(fnmatchcase(key, pattern) for pattern in pattern_list)
        }
        return self.delete_many(matching_keys)

    @staticmethod
    def _normalize_namespace_separator(separator: str) -> str:
        """Validate namespace separators used by namespace helpers."""
        if not isinstance(separator, str):
            raise ValueError("separator must be a string")

        normalized_separator = separator.strip()
        if not normalized_separator:
            raise ValueError("separator cannot be empty")

        return normalized_separator

    @staticmethod
    def _extract_namespace(key: str, *, separator: str) -> str:
        """Extract namespace from key using the first separator occurrence."""
        namespace, _, _ = key.partition(separator)
        return namespace

    @classmethod
    def _normalize_namespace(cls, namespace: str, *, separator: str) -> str:
        """Validate namespace values used by namespace-aware operations."""
        if not isinstance(namespace, str):
            raise ValueError("namespace must be a string")

        normalized_namespace = namespace.strip()
        if not normalized_namespace:
            raise ValueError("namespace cannot be empty")
        if separator in normalized_namespace:
            raise ValueError("namespace cannot contain separator")

        return normalized_namespace

    def list_namespaces(
        self,
        *,
        prefix: str | None = None,
        pattern: str | None = None,
        tags: Iterable[str] | None = None,
        match_all_tags: bool = False,
        separator: str = ":",
        min_count: int | None = None,
        max_count: int | None = None,
        offset: int | None = None,
        limit: int | None = None,
        include_counts: bool = False,
        sort_by: str = "namespace",
        descending: bool = False,
    ) -> list[str] | list[dict[str, Any]]:
        """List active key namespaces with optional filtering and counts.

        Namespace is defined as the key segment before the first separator.
        Keys without the separator use the full key as their namespace.

        Args:
            prefix: Optional namespace prefix filter.
            pattern: Optional key glob filter matched with :func:`fnmatchcase`.
            tags: Optional key-tag filters.
            match_all_tags: Tag matching mode when ``tags`` are provided.
            separator: Namespace delimiter used to split keys.
            min_count: Optional minimum number of matching keys required
                for a namespace to be included.
            max_count: Optional maximum number of matching keys allowed
                for a namespace to be included.
            offset: Optional number of sorted namespaces to skip.
            limit: Optional maximum number of namespaces to return.
            include_counts: Include entry counts per namespace.
            sort_by: Sort strategy. ``"namespace"`` (default) sorts by name,
                while ``"count"`` sorts by per-namespace entry counts.
            descending: Return namespaces in descending order for ``sort_by``.
        """
        if prefix is not None and not isinstance(prefix, str):
            raise ValueError("prefix must be a string")

        if pattern is not None and not isinstance(pattern, str):
            raise ValueError("pattern must be a string")

        if not isinstance(match_all_tags, bool):
            raise ValueError("match_all_tags must be a boolean")

        if min_count is not None:
            if isinstance(min_count, bool) or not isinstance(min_count, int):
                raise ValueError("min_count must be a non-negative integer")
            if min_count < 0:
                raise ValueError("min_count must be a non-negative integer")

        if max_count is not None:
            if isinstance(max_count, bool) or not isinstance(max_count, int):
                raise ValueError("max_count must be a non-negative integer")
            if max_count < 0:
                raise ValueError("max_count must be a non-negative integer")

        if min_count is not None and max_count is not None and min_count > max_count:
            raise ValueError("min_count cannot be greater than max_count")

        if offset is not None and offset < 0:
            raise ValueError("offset must be greater than or equal to 0")

        if limit is not None and limit <= 0:
            raise ValueError("limit must be greater than 0")

        if not isinstance(include_counts, bool):
            raise ValueError("include_counts must be a boolean")

        if sort_by not in {"namespace", "count"}:
            raise ValueError('sort_by must be either "namespace" or "count"')

        if not isinstance(descending, bool):
            raise ValueError("descending must be a boolean")

        normalized_separator = self._normalize_namespace_separator(separator)

        self._purge_expired_entries()

        matching_keys = self._find_matching_keys(
            pattern=pattern,
            tags=tags,
            match_all_tags=match_all_tags,
        )

        namespace_counts: Counter[str] = Counter()
        for key in matching_keys:
            namespace = self._extract_namespace(key, separator=normalized_separator)
            if prefix is not None and not namespace.startswith(prefix):
                continue

            namespace_counts[namespace] += 1

        namespace_rows = [
            (namespace, count)
            for namespace, count in namespace_counts.items()
            if (min_count is None or count >= min_count)
            and (max_count is None or count <= max_count)
        ]
        if sort_by == "count":
            if descending:
                namespace_rows.sort(key=lambda row: (-row[1], row[0]))
            else:
                namespace_rows.sort(key=lambda row: (row[1], row[0]))
        else:
            namespace_rows.sort(key=lambda row: row[0], reverse=descending)

        if offset:
            namespace_rows = namespace_rows[offset:]

        if limit is not None:
            namespace_rows = namespace_rows[:limit]

        if include_counts:
            return [
                {"namespace": namespace, "count": count}
                for namespace, count in namespace_rows
            ]

        return [namespace for namespace, _ in namespace_rows]

    def clear_namespace(
        self,
        namespace: str,
        *,
        separator: str = ":",
    ) -> int:
        """Delete all keys belonging to ``namespace``.

        A key belongs to a namespace when the segment before the first
        separator matches ``namespace``.
        """
        normalized_separator = self._normalize_namespace_separator(separator)
        normalized_namespace = self._normalize_namespace(
            namespace,
            separator=normalized_separator,
        )

        matching_keys = {
            key
            for key in self._all_known_keys()
            if self._extract_namespace(key, separator=normalized_separator)
            == normalized_namespace
        }
        return self.delete_many(matching_keys)

    def clear_namespaces(
        self,
        namespaces: Iterable[str],
        *,
        separator: str = ":",
    ) -> int:
        """Delete keys that belong to any namespace in ``namespaces``.

        Namespace extraction follows :meth:`clear_namespace`: the key segment
        before the first ``separator`` is treated as the namespace.

        Duplicate namespaces are deduplicated before matching keys.
        """
        normalized_separator = self._normalize_namespace_separator(separator)

        normalized_namespaces: set[str] = set()
        for namespace in namespaces:
            normalized_namespaces.add(
                self._normalize_namespace(namespace, separator=normalized_separator)
            )

        if not normalized_namespaces:
            return 0

        matching_keys = {
            key
            for key in self._all_known_keys()
            if self._extract_namespace(key, separator=normalized_separator)
            in normalized_namespaces
        }
        return self.delete_many(matching_keys)

    def _build_namespace_key_mapping(
        self,
        source_namespace: str,
        target_namespace: str,
        *,
        separator: str,
    ) -> dict[str, str]:
        """Build deterministic ``source_key -> target_key`` namespace mappings."""
        source_prefix = f"{source_namespace}{separator}"
        target_prefix = f"{target_namespace}{separator}"

        source_keys = sorted(
            key
            for key in self._store
            if self._extract_namespace(key, separator=separator) == source_namespace
        )

        key_mapping: dict[str, str] = {}
        for source_key in source_keys:
            if source_key == source_namespace:
                target_key = target_namespace
            else:
                suffix = source_key.removeprefix(source_prefix)
                target_key = f"{target_prefix}{suffix}"

            key_mapping[source_key] = target_key

        return key_mapping

    def copy_namespace(
        self,
        source_namespace: str,
        target_namespace: str,
        *,
        separator: str = ":",
        overwrite: bool = False,
    ) -> int:
        """Copy all keys from one namespace into another namespace.

        Root keys and nested keys preserve relative suffixes. For example,
        ``session`` and ``session:alpha`` copy into ``archive`` as
        ``archive`` and ``archive:alpha``.
        """
        normalized_separator = self._normalize_namespace_separator(separator)
        normalized_source = self._normalize_namespace(
            source_namespace,
            separator=normalized_separator,
        )
        normalized_target = self._normalize_namespace(
            target_namespace,
            separator=normalized_separator,
        )

        if normalized_source == normalized_target:
            return 0

        self._purge_expired_entries()
        key_mapping = self._build_namespace_key_mapping(
            normalized_source,
            normalized_target,
            separator=normalized_separator,
        )
        if not key_mapping:
            return 0

        return self.copy_many(key_mapping, overwrite=overwrite)

    def rename_namespace(
        self,
        source_namespace: str,
        target_namespace: str,
        *,
        separator: str = ":",
        overwrite: bool = False,
    ) -> int:
        """Rename all keys from ``source_namespace`` into ``target_namespace``.

        Key suffixes are preserved using the same mapping semantics as
        :meth:`copy_namespace`.
        """
        normalized_separator = self._normalize_namespace_separator(separator)
        normalized_source = self._normalize_namespace(
            source_namespace,
            separator=normalized_separator,
        )
        normalized_target = self._normalize_namespace(
            target_namespace,
            separator=normalized_separator,
        )

        if normalized_source == normalized_target:
            return 0

        self._purge_expired_entries()
        key_mapping = self._build_namespace_key_mapping(
            normalized_source,
            normalized_target,
            separator=normalized_separator,
        )
        if not key_mapping:
            return 0

        return self.rename_many(key_mapping, overwrite=overwrite)

    def _find_matching_keys(
        self,
        *,
        prefix: str | None = None,
        pattern: str | None = None,
        tags: Iterable[str] | None = None,
        match_all_tags: bool = False,
        include_inflight: bool = False,
        namespace: str | None = None,
        namespace_separator: str = ":",
    ) -> set[str]:
        """Resolve keys matching combined prefix/glob/tag filters.

        Args:
            prefix: Optional key prefix filter.
            pattern: Optional glob pattern matched with :func:`fnmatchcase`.
            tags: Optional tag filter with any/all matching semantics.
            match_all_tags: Require all tags when ``True``.
            include_inflight: Include in-flight population keys when ``True``.
            namespace: Optional exact namespace filter.
            namespace_separator: Namespace delimiter used when
                ``namespace`` filtering is enabled.

        Returns:
            Set of matching key names.

        Notes:
            Expired keys are expected to be purged by caller before invoking
            this helper.
        """
        if tags is None:
            candidate_keys = (
                self._all_known_keys() if include_inflight else set(self._store.keys())
            )
        else:
            candidate_keys = self._resolve_keys_for_tags(
                tags,
                match_all_tags=match_all_tags,
            )

        normalized_namespace: str | None = None
        normalized_namespace_separator: str | None = None
        if namespace is not None:
            normalized_namespace_separator = self._normalize_namespace_separator(
                namespace_separator
            )
            normalized_namespace = self._normalize_namespace(
                namespace,
                separator=normalized_namespace_separator,
            )

        return {
            key
            for key in candidate_keys
            if (prefix is None or key.startswith(prefix))
            and (pattern is None or fnmatchcase(key, pattern))
            and (
                normalized_namespace is None
                or (
                    normalized_namespace_separator is not None
                    and self._extract_namespace(
                        key,
                        separator=normalized_namespace_separator,
                    )
                    == normalized_namespace
                )
            )
        }

    def tag_where(
        self,
        add_tags: Iterable[str],
        *,
        prefix: str | None = None,
        pattern: str | None = None,
        tags: Iterable[str] | None = None,
        match_all_tags: bool = False,
        namespace: str | None = None,
        namespace_separator: str = ":",
    ) -> int:
        """Attach ``add_tags`` to keys matching combined filters.

        At least one filter must be provided to avoid accidental broad writes.

        Args:
            add_tags: Tags to add to each matching key.
            prefix: Optional key prefix to match.
            pattern: Optional glob pattern matched with :func:`fnmatchcase`.
            tags: Optional tag filter used to select candidate keys.
            match_all_tags: Tag matching mode when ``tags`` are provided.
                ``False`` (default) matches keys with any provided tag, while
                ``True`` requires keys to contain every provided tag.
            namespace: Optional exact namespace filter.
            namespace_separator: Namespace delimiter used when
                ``namespace`` filtering is enabled.

        Returns:
            Number of keys whose tag sets changed.
        """
        if not isinstance(match_all_tags, bool):
            raise ValueError("match_all_tags must be a boolean")

        if prefix is None and pattern is None and tags is None and namespace is None:
            raise ValueError("at least one filter must be provided")

        normalized_add_tags = self._normalize_tags(add_tags)
        if not normalized_add_tags:
            raise ValueError("add_tags must include at least one non-empty tag")

        self._purge_expired_entries()
        matching_keys = sorted(
            self._find_matching_keys(
                prefix=prefix,
                pattern=pattern,
                tags=tags,
                match_all_tags=match_all_tags,
                namespace=namespace,
                namespace_separator=namespace_separator,
            )
        )

        tagged = 0
        for key in matching_keys:
            existing_tags = self._tags_by_key.get(key, set())
            combined_tags = existing_tags | normalized_add_tags
            if combined_tags == existing_tags:
                continue

            self._replace_key_tags(key, combined_tags)
            tagged += 1

        return tagged

    def untag_where(
        self,
        remove_tags: Iterable[str] | None = None,
        *,
        prefix: str | None = None,
        pattern: str | None = None,
        tags: Iterable[str] | None = None,
        match_all_tags: bool = False,
        namespace: str | None = None,
        namespace_separator: str = ":",
    ) -> int:
        """Remove tags from keys matching combined filters.

        At least one filter must be provided to avoid accidental broad writes.

        Args:
            remove_tags: Optional subset of tags to remove. When ``None``, all
                tags are removed from matching keys.
            prefix: Optional key prefix to match.
            pattern: Optional glob pattern matched with :func:`fnmatchcase`.
            tags: Optional tag filter used to select candidate keys.
            match_all_tags: Tag matching mode when ``tags`` are provided.
                ``False`` (default) matches keys with any provided tag, while
                ``True`` requires keys to contain every provided tag.
            namespace: Optional exact namespace filter.
            namespace_separator: Namespace delimiter used when
                ``namespace`` filtering is enabled.

        Returns:
            Number of keys whose tag sets changed.
        """
        if not isinstance(match_all_tags, bool):
            raise ValueError("match_all_tags must be a boolean")

        if prefix is None and pattern is None and tags is None and namespace is None:
            raise ValueError("at least one filter must be provided")

        normalized_remove_tags: set[str] | None = None
        if remove_tags is not None:
            normalized_remove_tags = self._normalize_tags(remove_tags)
            if not normalized_remove_tags:
                return 0

        self._purge_expired_entries()
        matching_keys = sorted(
            self._find_matching_keys(
                prefix=prefix,
                pattern=pattern,
                tags=tags,
                match_all_tags=match_all_tags,
                namespace=namespace,
                namespace_separator=namespace_separator,
            )
        )

        untagged = 0
        for key in matching_keys:
            existing_tags = self._tags_by_key.get(key, set())
            if not existing_tags:
                continue

            if normalized_remove_tags is None:
                self._detach_key_from_tags(key)
                untagged += 1
                continue

            remaining_tags = existing_tags - normalized_remove_tags
            if remaining_tags == existing_tags:
                continue

            self._replace_key_tags(key, remaining_tags)
            untagged += 1

        return untagged

    def clear_where(
        self,
        *,
        prefix: str | None = None,
        pattern: str | None = None,
        tags: Iterable[str] | None = None,
        match_all_tags: bool = False,
        namespace: str | None = None,
        namespace_separator: str = ":",
    ) -> int:
        """Delete keys matching combined prefix/glob/tag filters.

        At least one filter must be provided; use :meth:`clear` to remove
        everything.

        Args:
            prefix: Optional key prefix to match.
            pattern: Optional glob pattern matched with :func:`fnmatchcase`.
            tags: Optional tag filter. When provided, only keys associated with
                matching tags are considered.
            match_all_tags: Tag matching mode when ``tags`` are provided.
                ``False`` (default) matches keys with any provided tag, while
                ``True`` requires keys to contain every provided tag.
            namespace: Optional exact namespace filter.
            namespace_separator: Namespace delimiter used when
                ``namespace`` filtering is enabled.

        Returns:
            Number of removed keys.
        """
        if not isinstance(match_all_tags, bool):
            raise ValueError("match_all_tags must be a boolean")

        if prefix is None and pattern is None and tags is None and namespace is None:
            raise ValueError("at least one filter must be provided")

        self._purge_expired_entries()

        matching_keys = self._find_matching_keys(
            prefix=prefix,
            pattern=pattern,
            tags=tags,
            match_all_tags=match_all_tags,
            include_inflight=True,
            namespace=namespace,
            namespace_separator=namespace_separator,
        )

        return self.delete_many(matching_keys)

    def pop_where(
        self,
        *,
        prefix: str | None = None,
        pattern: str | None = None,
        tags: Iterable[str] | None = None,
        match_all_tags: bool = False,
        namespace: str | None = None,
        namespace_separator: str = ":",
    ) -> dict[str, Any]:
        """Pop values for keys matching combined prefix/glob/tag filters.

        This behaves like :meth:`clear_where` but returns removed cache values
        for matching stored keys. Matching in-flight population tasks are
        cancelled and removed, but naturally have no value payload to return.

        Args:
            prefix: Optional key prefix to match.
            pattern: Optional glob pattern matched with :func:`fnmatchcase`.
            tags: Optional tag filter. When provided, only keys associated with
                matching tags are considered.
            match_all_tags: Tag matching mode when ``tags`` are provided.
                ``False`` (default) matches keys with any provided tag, while
                ``True`` requires keys to contain every provided tag.
            namespace: Optional exact namespace filter.
            namespace_separator: Namespace delimiter used when
                ``namespace`` filtering is enabled.

        Returns:
            Mapping of removed key/value pairs for matching stored entries.

        Raises:
            ValueError: If no filters are provided or ``match_all_tags`` is not
                a boolean.
        """
        if not isinstance(match_all_tags, bool):
            raise ValueError("match_all_tags must be a boolean")

        if prefix is None and pattern is None and tags is None and namespace is None:
            raise ValueError("at least one filter must be provided")

        self._purge_expired_entries()

        matching_keys = self._find_matching_keys(
            prefix=prefix,
            pattern=pattern,
            tags=tags,
            match_all_tags=match_all_tags,
            include_inflight=True,
            namespace=namespace,
            namespace_separator=namespace_separator,
        )

        popped_values = self.pop_many(sorted(matching_keys))

        remaining_keys = matching_keys - set(popped_values)
        if remaining_keys:
            self.delete_many(remaining_keys)

        return popped_values

    def touch_where(
        self,
        *,
        ttl_seconds: int | None,
        prefix: str | None = None,
        pattern: str | None = None,
        tags: Iterable[str] | None = None,
        match_all_tags: bool = False,
        namespace: str | None = None,
        namespace_separator: str = ":",
    ) -> int:
        """Refresh TTL for keys matching combined prefix/glob/tag filters.

        At least one filter must be provided to avoid accidental bulk updates.

        Args:
            ttl_seconds: New TTL applied to matching keys. ``None`` or
                non-positive values make keys non-expiring.
            prefix: Optional key prefix to match.
            pattern: Optional glob pattern matched with :func:`fnmatchcase`.
            tags: Optional tag filter. When provided, only keys associated with
                matching tags are considered.
            match_all_tags: Tag matching mode when ``tags`` are provided.
                ``False`` (default) matches keys with any provided tag, while
                ``True`` requires keys to contain every provided tag.
            namespace: Optional exact namespace filter.
            namespace_separator: Namespace delimiter used when
                ``namespace`` filtering is enabled.

        Returns:
            Number of matching active keys whose TTL was refreshed.

        Raises:
            ValueError: If no filters are provided or ``match_all_tags`` is not
                a boolean.
        """
        if not isinstance(match_all_tags, bool):
            raise ValueError("match_all_tags must be a boolean")

        if prefix is None and pattern is None and tags is None and namespace is None:
            raise ValueError("at least one filter must be provided")

        self._purge_expired_entries()

        matching_keys = self._find_matching_keys(
            prefix=prefix,
            pattern=pattern,
            tags=tags,
            match_all_tags=match_all_tags,
            namespace=namespace,
            namespace_separator=namespace_separator,
        )

        return self.touch_many(sorted(matching_keys), ttl_seconds=ttl_seconds)

    def update_where(
        self,
        updater: Callable[[Any], Any],
        *,
        prefix: str | None = None,
        pattern: str | None = None,
        tags: Iterable[str] | None = None,
        match_all_tags: bool = False,
        namespace: str | None = None,
        namespace_separator: str = ":",
        ttl_seconds: int | None = None,
        keep_ttl: bool = True,
    ) -> dict[str, Any]:
        """Update values for keys matching combined prefix/glob/tag filters.

        At least one filter must be provided to avoid accidental bulk updates.

        Args:
            updater: Callable receiving each current value and returning a new
                value to store.
            prefix: Optional key prefix to match.
            pattern: Optional glob pattern matched with :func:`fnmatchcase`.
            tags: Optional tag filter. When provided, only keys associated with
                matching tags are considered.
            match_all_tags: Tag matching mode when ``tags`` are provided.
                ``False`` (default) matches keys with any provided tag, while
                ``True`` requires keys to contain every provided tag.
            namespace: Optional exact namespace filter.
            namespace_separator: Namespace delimiter used when
                ``namespace`` filtering is enabled.
            ttl_seconds: TTL override used when ``keep_ttl`` is ``False``.
            keep_ttl: Preserve each key's existing absolute expiration by
                default.

        Returns:
            Mapping of ``key -> updated value`` for keys that matched filters.

        Raises:
            TypeError: If ``updater`` is not callable.
            ValueError: If no filters are provided, or when
                ``match_all_tags`` / ``keep_ttl`` are not booleans.
        """
        if not callable(updater):
            raise TypeError("updater must be callable")

        if not isinstance(match_all_tags, bool):
            raise ValueError("match_all_tags must be a boolean")

        if not isinstance(keep_ttl, bool):
            raise ValueError("keep_ttl must be a boolean")

        if prefix is None and pattern is None and tags is None and namespace is None:
            raise ValueError("at least one filter must be provided")

        self._purge_expired_entries()

        matching_keys = sorted(
            self._find_matching_keys(
                prefix=prefix,
                pattern=pattern,
                tags=tags,
                match_all_tags=match_all_tags,
                namespace=namespace,
                namespace_separator=namespace_separator,
            )
        )

        updated_values: dict[str, Any] = {}
        for key in matching_keys:
            updated_values[key] = self.update(
                key,
                updater,
                ttl_seconds=ttl_seconds,
                keep_ttl=keep_ttl,
            )

        return updated_values

    def count_where(
        self,
        *,
        prefix: str | None = None,
        pattern: str | None = None,
        tags: Iterable[str] | None = None,
        match_all_tags: bool = False,
        namespace: str | None = None,
        namespace_separator: str = ":",
    ) -> int:
        """Count active keys matching combined prefix/glob/tag filters.

        Args:
            prefix: Optional key prefix to match.
            pattern: Optional glob pattern matched with :func:`fnmatchcase`.
            tags: Optional tag filter. When provided, only keys associated with
                matching tags are counted.
            match_all_tags: Tag matching mode when ``tags`` are provided.
                ``False`` (default) counts keys matching any provided tag,
                while ``True`` requires keys to contain every provided tag.
            namespace: Optional exact namespace filter.
            namespace_separator: Namespace delimiter used when
                ``namespace`` filtering is enabled.

        Returns:
            Number of matching active cache entries.
        """
        if not isinstance(match_all_tags, bool):
            raise ValueError("match_all_tags must be a boolean")

        self._purge_expired_entries()
        return len(
            self._find_matching_keys(
                prefix=prefix,
                pattern=pattern,
                tags=tags,
                match_all_tags=match_all_tags,
                namespace=namespace,
                namespace_separator=namespace_separator,
            )
        )

    def get_where(
        self,
        *,
        prefix: str | None = None,
        pattern: str | None = None,
        tags: Iterable[str] | None = None,
        match_all_tags: bool = False,
        namespace: str | None = None,
        namespace_separator: str = ":",
        offset: int | None = None,
        limit: int | None = None,
        descending: bool = False,
    ) -> dict[str, Any]:
        """Return key/value pairs for active entries matching filters.

        This is a value-centric companion to :meth:`list_keys`, preserving the
        deterministic key ordering semantics from that helper while returning
        cached values.

        Args:
            prefix: Optional key prefix to match.
            pattern: Optional glob pattern matched with :func:`fnmatchcase`.
            tags: Optional tag filter. When provided, only keys associated with
                matching tags are returned.
            match_all_tags: Tag matching mode when ``tags`` are provided.
                ``False`` (default) returns keys matching any tag, while
                ``True`` requires keys to contain every provided tag.
            namespace: Optional exact namespace filter.
            namespace_separator: Namespace delimiter used when
                ``namespace`` filtering is enabled.
            offset: Optional number of sorted matching keys to skip.
            limit: Optional maximum number of keys to return.
            descending: Return keys in descending lexicographic order when
                ``True``.

        Returns:
            Ordered mapping of ``key -> value`` for matching active entries.

        Notes:
            Unlike :meth:`list_keys`, this helper performs value lookups and
            therefore updates hit/miss counters and LRU access order.
        """
        matching_keys = self.list_keys(
            prefix=prefix,
            pattern=pattern,
            tags=tags,
            match_all_tags=match_all_tags,
            namespace=namespace,
            namespace_separator=namespace_separator,
            offset=offset,
            limit=limit,
            descending=descending,
        )

        return self.get_many(matching_keys)

    def peek_where(
        self,
        *,
        prefix: str | None = None,
        pattern: str | None = None,
        tags: Iterable[str] | None = None,
        match_all_tags: bool = False,
        namespace: str | None = None,
        namespace_separator: str = ":",
        offset: int | None = None,
        limit: int | None = None,
        descending: bool = False,
    ) -> dict[str, Any]:
        """Return matching key/value pairs without mutating stats or LRU order.

        This helper mirrors :meth:`get_where` filtering and deterministic
        ordering semantics while using :meth:`peek_many` for non-observing
        reads.

        Args:
            prefix: Optional key prefix to match.
            pattern: Optional glob pattern matched with :func:`fnmatchcase`.
            tags: Optional tag filter. When provided, only keys associated with
                matching tags are returned.
            match_all_tags: Tag matching mode when ``tags`` are provided.
                ``False`` (default) returns keys matching any tag, while
                ``True`` requires keys to contain every provided tag.
            namespace: Optional exact namespace filter.
            namespace_separator: Namespace delimiter used when
                ``namespace`` filtering is enabled.
            offset: Optional number of sorted matching keys to skip.
            limit: Optional maximum number of keys to return.
            descending: Return keys in descending lexicographic order when
                ``True``.

        Returns:
            Ordered mapping of ``key -> value`` for matching active entries.
        """
        matching_keys = self.list_keys(
            prefix=prefix,
            pattern=pattern,
            tags=tags,
            match_all_tags=match_all_tags,
            namespace=namespace,
            namespace_separator=namespace_separator,
            offset=offset,
            limit=limit,
            descending=descending,
        )

        return self.peek_many(matching_keys)

    def list_keys(
        self,
        *,
        prefix: str | None = None,
        pattern: str | None = None,
        tags: Iterable[str] | None = None,
        match_all_tags: bool = False,
        namespace: str | None = None,
        namespace_separator: str = ":",
        offset: int | None = None,
        limit: int | None = None,
        descending: bool = False,
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
            namespace: Optional exact namespace filter applied after
                prefix/pattern/tag matching.
            namespace_separator: Namespace delimiter used with ``namespace``.
            offset: Optional number of sorted matching keys to skip.
            limit: Optional maximum number of keys to return.
            descending: Return keys in descending lexicographic order when
                ``True``.

        Keys are returned in deterministic lexicographic order and do not affect
        hit/miss counters or LRU order.
        """
        if offset is not None and offset < 0:
            raise ValueError("offset must be greater than or equal to 0")

        if limit is not None and limit <= 0:
            raise ValueError("limit must be greater than 0")

        if not isinstance(match_all_tags, bool):
            raise ValueError("match_all_tags must be a boolean")

        if not isinstance(descending, bool):
            raise ValueError("descending must be a boolean")

        normalized_namespace: str | None = None
        normalized_namespace_separator: str | None = None
        if namespace is not None:
            normalized_namespace_separator = self._normalize_namespace_separator(
                namespace_separator
            )
            normalized_namespace = self._normalize_namespace(
                namespace,
                separator=normalized_namespace_separator,
            )

        self._purge_expired_entries()

        matching_keys = list(
            self._find_matching_keys(
                prefix=prefix,
                pattern=pattern,
                tags=tags,
                match_all_tags=match_all_tags,
            )
        )

        if (
            normalized_namespace is not None
            and normalized_namespace_separator is not None
        ):
            matching_keys = [
                key
                for key in matching_keys
                if self._extract_namespace(
                    key,
                    separator=normalized_namespace_separator,
                )
                == normalized_namespace
            ]

        matching_keys.sort(reverse=descending)

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
        namespace: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
        descending: bool = False,
        include_values: bool = False,
        include_entry_tags: bool = False,
        include_expires_at: bool = False,
        include_namespace: bool = False,
        namespace_separator: str = ":",
        expiration: str = "all",
        sort_by: str = "key",
        min_ttl_seconds: Real | None = None,
        max_ttl_seconds: Real | None = None,
    ) -> list[dict[str, Any]]:
        """List active cache entries with optional filters and metadata.

        Args:
            namespace: Optional exact namespace filter applied before entry
                metadata generation.
            offset: Optional number of sorted matching entries to skip.
            descending: Return entries in descending sort order when ``True``.
            include_values: Include cached values in each entry payload.
            include_entry_tags: Include sorted tags associated with each key.
            include_expires_at: Include absolute unix expiration timestamps.
            include_namespace: Include key namespace extracted via
                ``namespace_separator``.
            namespace_separator: Namespace delimiter used for namespace
                filtering and optional metadata extraction.
            expiration: Expiration filter. ``"all"`` (default) returns every
                active key, ``"expiring"`` returns only TTL-bound keys, and
                ``"persistent"`` returns only non-expiring keys.
            sort_by: Entry sort strategy. ``"key"`` (default) sorts by key,
                ``"namespace"`` groups by extracted namespace, ``"ttl_seconds"``
                sorts by remaining TTL, and ``"expires_at"`` sorts by
                absolute expiration time.
            min_ttl_seconds: Optional lower bound (inclusive) for entry TTL.
                When provided, only expiring entries with remaining TTL at or
                above this value are returned.
            max_ttl_seconds: Optional upper bound (inclusive) for entry TTL.
                When provided, only expiring entries with remaining TTL at or
                below this value are returned.
        """
        if offset is not None and offset < 0:
            raise ValueError("offset must be greater than or equal to 0")

        if limit is not None and limit <= 0:
            raise ValueError("limit must be greater than 0")

        if not isinstance(match_all_tags, bool):
            raise ValueError("match_all_tags must be a boolean")

        if not isinstance(descending, bool):
            raise ValueError("descending must be a boolean")

        if not isinstance(include_namespace, bool):
            raise ValueError("include_namespace must be a boolean")

        if expiration not in {"all", "expiring", "persistent"}:
            raise ValueError(
                'expiration must be one of: "all", "expiring", "persistent"'
            )

        if sort_by not in {"key", "namespace", "ttl_seconds", "expires_at"}:
            raise ValueError(
                'sort_by must be one of: "key", "namespace", "ttl_seconds", "expires_at"'
            )

        normalized_min_ttl: float | None = None
        if min_ttl_seconds is not None:
            if isinstance(min_ttl_seconds, bool) or not isinstance(
                min_ttl_seconds,
                Real,
            ):
                raise ValueError("min_ttl_seconds must be a non-negative number")
            if min_ttl_seconds < 0:
                raise ValueError("min_ttl_seconds must be a non-negative number")
            normalized_min_ttl = float(min_ttl_seconds)

        normalized_max_ttl: float | None = None
        if max_ttl_seconds is not None:
            if isinstance(max_ttl_seconds, bool) or not isinstance(
                max_ttl_seconds,
                Real,
            ):
                raise ValueError("max_ttl_seconds must be a non-negative number")
            if max_ttl_seconds < 0:
                raise ValueError("max_ttl_seconds must be a non-negative number")
            normalized_max_ttl = float(max_ttl_seconds)

        if (
            normalized_min_ttl is not None
            and normalized_max_ttl is not None
            and normalized_min_ttl > normalized_max_ttl
        ):
            raise ValueError("min_ttl_seconds cannot be greater than max_ttl_seconds")

        normalized_namespace_separator: str | None = None
        if include_namespace or sort_by == "namespace":
            normalized_namespace_separator = self._normalize_namespace_separator(
                namespace_separator
            )

        entries: list[dict[str, Any]] = []
        for key in self.list_keys(
            prefix=prefix,
            pattern=pattern,
            tags=tags,
            match_all_tags=match_all_tags,
            namespace=namespace,
            namespace_separator=namespace_separator,
        ):
            value, expires_at = self._store[key]
            ttl_seconds = (
                None if expires_at is None else max(0.0, expires_at - time.time())
            )

            if expiration == "expiring" and expires_at is None:
                continue
            if expiration == "persistent" and expires_at is not None:
                continue

            if normalized_min_ttl is not None or normalized_max_ttl is not None:
                if ttl_seconds is None:
                    continue
                if normalized_min_ttl is not None and ttl_seconds < normalized_min_ttl:
                    continue
                if normalized_max_ttl is not None and ttl_seconds > normalized_max_ttl:
                    continue

            namespace_value: str | None = None
            if normalized_namespace_separator is not None:
                namespace_value = self._extract_namespace(
                    key,
                    separator=normalized_namespace_separator,
                )

            entry: dict[str, Any] = {
                "key": key,
                "ttl_seconds": ttl_seconds,
                "_expires_at": expires_at,
                "_namespace": namespace_value,
            }
            if include_values:
                entry["value"] = value
            if include_entry_tags:
                entry["tags"] = sorted(self._tags_by_key.get(key, set()))
            if include_expires_at:
                entry["expires_at"] = expires_at
            if include_namespace:
                entry["namespace"] = namespace_value
            entries.append(entry)

        if sort_by == "key":
            entries.sort(key=lambda entry: entry["key"], reverse=descending)
        elif sort_by == "namespace":
            entries.sort(
                key=lambda entry: (entry["_namespace"] or "", entry["key"]),
                reverse=descending,
            )
        elif sort_by == "ttl_seconds":
            entries.sort(
                key=lambda entry: (
                    entry["ttl_seconds"] is None,
                    -(entry["ttl_seconds"] or 0.0)
                    if descending
                    else (entry["ttl_seconds"] or 0.0),
                    entry["key"],
                )
            )
        else:
            entries.sort(
                key=lambda entry: (
                    entry["_expires_at"] is None,
                    -(entry["_expires_at"] or 0.0)
                    if descending
                    else (entry["_expires_at"] or 0.0),
                    entry["key"],
                )
            )

        if offset:
            entries = entries[offset:]

        if limit is not None:
            entries = entries[:limit]

        for entry in entries:
            entry.pop("_expires_at", None)
            entry.pop("_namespace", None)

        return entries

    def export_state(
        self,
        *,
        include_stats: bool = False,
        prefix: str | None = None,
        pattern: str | None = None,
        tags: Iterable[str] | None = None,
        match_all_tags: bool = False,
        offset: int | None = None,
        limit: int | None = None,
        descending: bool = False,
    ) -> dict[str, Any]:
        """Export active cache entries into a serializable snapshot.

        The snapshot stores TTL as remaining seconds so that import can rebuild
        equivalent expiry windows relative to restore time.

        Args:
            include_stats: Include cache counters in the returned snapshot.
            prefix: Optional key prefix filter.
            pattern: Optional glob filter matched with :func:`fnmatchcase`.
            tags: Optional tag filter used to restrict exported keys.
            match_all_tags: Require all tags to match when ``tags`` is provided.
            offset: Optional number of sorted matching keys to skip.
            limit: Optional max number of matching keys to export.
            descending: Export keys in descending lexicographic order when
                ``True``.
        """
        self._purge_expired_entries()

        keys = self.list_keys(
            prefix=prefix,
            pattern=pattern,
            tags=tags,
            match_all_tags=match_all_tags,
            offset=offset,
            limit=limit,
            descending=descending,
        )

        entries: list[dict[str, Any]] = []
        now = time.time()
        for key in keys:
            value, expires_at = self._store[key]
            ttl_seconds = None
            if expires_at is not None:
                ttl_seconds = max(0.0, expires_at - now)

            entries.append(
                {
                    "key": key,
                    "value": value,
                    "ttl_seconds": ttl_seconds,
                    "tags": sorted(self._tags_by_key.get(key, set())),
                }
            )

        snapshot: dict[str, Any] = {
            "entries": entries,
            "max_entries": self._max_entries,
        }

        if include_stats:
            snapshot["stats"] = self.stats()

        return snapshot

    def _normalize_snapshot_stats(self, raw_stats: Any) -> dict[str, int]:
        """Validate and normalize snapshot stats payloads."""
        if not isinstance(raw_stats, Mapping):
            raise TypeError("snapshot stats must be a mapping")

        normalized_stats: dict[str, int] = {}
        for stat_name in self._stats:
            raw_value = raw_stats.get(stat_name, 0)
            if isinstance(raw_value, bool) or not isinstance(raw_value, Real):
                raise TypeError(
                    f"snapshot stats field '{stat_name}' must be a non-negative integer"
                )

            if int(raw_value) != raw_value:
                raise TypeError(
                    f"snapshot stats field '{stat_name}' must be a non-negative integer"
                )

            value = int(raw_value)
            if value < 0:
                raise ValueError(
                    f"snapshot stats field '{stat_name}' must be non-negative"
                )

            normalized_stats[stat_name] = value

        return normalized_stats

    @staticmethod
    def _normalize_import_conflict_policy(
        conflict_policy: str,
    ) -> Literal["overwrite", "skip", "error"]:
        """Validate import conflict behavior options."""
        if not isinstance(conflict_policy, str):
            raise ValueError("conflict_policy must be one of: overwrite, skip, error")

        normalized_policy = conflict_policy.strip().lower()
        if normalized_policy not in {"overwrite", "skip", "error"}:
            raise ValueError("conflict_policy must be one of: overwrite, skip, error")

        return cast(Literal["overwrite", "skip", "error"], normalized_policy)

    @staticmethod
    def _normalize_import_key_prefix(key_prefix: str | None) -> str:
        """Validate and normalize optional key prefix used during import."""
        if key_prefix is None:
            return ""

        if not isinstance(key_prefix, str):
            raise ValueError("key_prefix must be a string")

        return key_prefix.strip()

    def import_state(
        self,
        snapshot: Mapping[str, Any],
        *,
        clear_existing: bool = False,
        restore_stats: bool = False,
        conflict_policy: str = "overwrite",
        key_prefix: str | None = None,
    ) -> int:
        """Import entries from :meth:`export_state` snapshots.

        Args:
            snapshot: Mapping payload with an ``entries`` collection.
            clear_existing: Remove existing cache data before import.
            restore_stats: Restore exported operational counters when ``True``.
            conflict_policy: Behavior when imported keys already exist in the
                target cache (and ``clear_existing`` is ``False``):
                ``"overwrite"`` (default) replaces existing values,
                ``"skip"`` keeps existing values and skips conflicting entries,
                and ``"error"`` raises ``ValueError``.
            key_prefix: Optional prefix prepended to every imported entry key.
                Useful when restoring a snapshot into a namespaced keyspace.

        Returns:
            Number of successfully imported entries.
        """
        if not isinstance(snapshot, Mapping):
            raise TypeError("snapshot must be a mapping")

        if not isinstance(restore_stats, bool):
            raise ValueError("restore_stats must be a boolean")

        normalized_conflict_policy = self._normalize_import_conflict_policy(
            conflict_policy
        )
        normalized_key_prefix = self._normalize_import_key_prefix(key_prefix)

        if "entries" not in snapshot:
            raise ValueError("snapshot must include an 'entries' field")

        raw_entries = snapshot["entries"]
        if isinstance(raw_entries, (str, bytes, bytearray, Mapping)) or not isinstance(
            raw_entries, Iterable
        ):
            raise TypeError("snapshot entries must be an iterable of mappings")

        if clear_existing:
            self.clear()

        imported = 0
        for raw_entry in raw_entries:
            if not isinstance(raw_entry, Mapping):
                raise TypeError("each snapshot entry must be a mapping")

            key = raw_entry.get("key")
            if not isinstance(key, str) or not key:
                raise ValueError("snapshot entry key must be a non-empty string")

            imported_key = f"{normalized_key_prefix}{key}"

            if "value" not in raw_entry:
                raise ValueError("snapshot entry must include a value")

            ttl_seconds = raw_entry.get("ttl_seconds")
            if ttl_seconds is not None:
                if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, Real):
                    raise TypeError("snapshot entry ttl_seconds must be numeric")
                if ttl_seconds <= 0:
                    continue

            existing_entry = self._get_entry(imported_key, mark_access=False)
            if existing_entry is not None:
                if normalized_conflict_policy == "skip":
                    continue
                if normalized_conflict_policy == "error":
                    raise ValueError(
                        f"snapshot entry key '{imported_key}' already exists"
                    )

            raw_tags = raw_entry.get("tags", [])
            if raw_tags is None:
                raw_tags = []
            if isinstance(raw_tags, (str, bytes, bytearray)):
                raise TypeError("snapshot entry tags must be an iterable of strings")

            normalized_tags = self._normalize_tags(raw_tags)

            if normalized_tags:
                self.set_tagged(
                    imported_key,
                    raw_entry["value"],
                    tags=normalized_tags,
                    ttl_seconds=ttl_seconds,
                )
            else:
                self.set(imported_key, raw_entry["value"], ttl_seconds=ttl_seconds)

            imported += 1

        if restore_stats:
            if "stats" not in snapshot:
                raise ValueError(
                    "snapshot must include a 'stats' field when restore_stats=True"
                )
            self._stats = self._normalize_snapshot_stats(snapshot["stats"])

        return imported

    def stats(
        self,
        reset: bool = False,
        *,
        include_ttl_summary: bool = False,
        include_tag_summary: bool = False,
        include_capacity_summary: bool = False,
        include_namespace_summary: bool = False,
        namespace_separator: str = ":",
        namespace_limit: int = 5,
    ) -> dict[str, Any]:
        """Return cache operational counters and runtime metadata.

        In addition to raw counters, this includes derived lookup metrics to
        simplify dashboards and alerting:

        - ``lookups``: Total cache lookups (hits + misses)
        - ``hit_rate``: Hit ratio in the ``0.0`` to ``1.0`` range
        - ``miss_rate``: Miss ratio in the ``0.0`` to ``1.0`` range

        Args:
            reset: When ``True``, reset accumulated counters after generating
                the returned snapshot.
            include_ttl_summary: When ``True``, include TTL-oriented entry
                breakdown metadata:

                - ``expiring_entries``: Active entries with expiration.
                - ``persistent_entries``: Active entries without expiration.
                - ``next_expiration_in_seconds``: Remaining lifetime (seconds)
                  for the soonest-expiring key, or ``None`` if no expiring
                  entries exist.
            include_tag_summary: When ``True``, include tag-oriented metadata
                for active entries:

                - ``tagged_entries``: Active entries with at least one tag.
                - ``untagged_entries``: Active entries without tags.
                - ``unique_tags``: Number of active unique tags.
            include_capacity_summary: When ``True``, include cache capacity
                metadata:

                - ``has_capacity_limit``: Whether ``max_entries`` is enforced.
                - ``capacity_remaining``: Available slots before eviction, or
                  ``None`` when unbounded.
                - ``capacity_utilization``: ``entries / max_entries`` ratio,
                  or ``None`` when unbounded.
                - ``is_near_capacity``: ``True`` when utilization is at least
                  ``0.9`` for bounded caches.
            include_namespace_summary: When ``True``, include namespace
                distribution metadata for active keys:

                - ``unique_namespaces``: Number of active namespaces.
                - ``largest_namespace``: Namespace with most entries.
                - ``largest_namespace_entries``: Entry count for
                  ``largest_namespace``.
                - ``top_namespaces``: Top namespace/count rows sorted by count
                  descending then namespace name.
            namespace_separator: Delimiter used to split key namespaces when
                ``include_namespace_summary`` is enabled.
            namespace_limit: Maximum number of entries included in
                ``top_namespaces``.
        """
        if not isinstance(include_ttl_summary, bool):
            raise ValueError("include_ttl_summary must be a boolean")

        if not isinstance(include_tag_summary, bool):
            raise ValueError("include_tag_summary must be a boolean")

        if not isinstance(include_capacity_summary, bool):
            raise ValueError("include_capacity_summary must be a boolean")

        if not isinstance(include_namespace_summary, bool):
            raise ValueError("include_namespace_summary must be a boolean")

        if isinstance(namespace_limit, bool) or not isinstance(namespace_limit, int):
            raise ValueError("namespace_limit must be an integer greater than 0")

        if namespace_limit <= 0:
            raise ValueError("namespace_limit must be an integer greater than 0")

        normalized_namespace_separator = self._normalize_namespace_separator(
            namespace_separator
        )

        self._purge_expired_entries()
        active_entries = len(self._store)

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
            "entries": active_entries,
            "max_entries": self._max_entries,
            "inflight": len(self._inflight),
        }

        if include_ttl_summary:
            now = time.time()
            expiring_entries = 0
            persistent_entries = 0
            next_expiration_in_seconds: float | None = None

            for _, expires_at in self._store.values():
                if expires_at is None:
                    persistent_entries += 1
                    continue

                expiring_entries += 1
                remaining_seconds = max(0.0, expires_at - now)
                if (
                    next_expiration_in_seconds is None
                    or remaining_seconds < next_expiration_in_seconds
                ):
                    next_expiration_in_seconds = remaining_seconds

            snapshot.update(
                {
                    "expiring_entries": expiring_entries,
                    "persistent_entries": persistent_entries,
                    "next_expiration_in_seconds": next_expiration_in_seconds,
                }
            )

        if include_tag_summary:
            active_tags = {tag for tag, keys in self._keys_by_tag.items() if keys}
            tagged_entries = sum(1 for key in self._store if self._tags_by_key.get(key))

            snapshot.update(
                {
                    "tagged_entries": tagged_entries,
                    "untagged_entries": active_entries - tagged_entries,
                    "unique_tags": len(active_tags),
                }
            )

        if include_capacity_summary:
            if self._max_entries is None:
                snapshot.update(
                    {
                        "has_capacity_limit": False,
                        "capacity_remaining": None,
                        "capacity_utilization": None,
                        "is_near_capacity": False,
                    }
                )
            else:
                capacity_remaining = max(self._max_entries - active_entries, 0)
                capacity_utilization = active_entries / self._max_entries

                snapshot.update(
                    {
                        "has_capacity_limit": True,
                        "capacity_remaining": capacity_remaining,
                        "capacity_utilization": round(capacity_utilization, 4),
                        "is_near_capacity": capacity_utilization >= 0.9,
                    }
                )

        if include_namespace_summary:
            namespace_counts = Counter(
                self._extract_namespace(
                    key,
                    separator=normalized_namespace_separator,
                )
                for key in self._store
            )
            sorted_namespace_rows = sorted(
                namespace_counts.items(),
                key=lambda row: (-row[1], row[0]),
            )
            top_namespace_rows = sorted_namespace_rows[:namespace_limit]

            largest_namespace: str | None = None
            largest_namespace_entries = 0
            if sorted_namespace_rows:
                largest_namespace, largest_namespace_entries = sorted_namespace_rows[0]

            snapshot.update(
                {
                    "unique_namespaces": len(namespace_counts),
                    "largest_namespace": largest_namespace,
                    "largest_namespace_entries": largest_namespace_entries,
                    "top_namespaces": [
                        {"namespace": namespace, "count": count}
                        for namespace, count in top_namespace_rows
                    ],
                }
            )

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
