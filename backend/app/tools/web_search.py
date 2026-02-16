"""Web search tool using DuckDuckGo."""

import logging
import re
import time
from collections import OrderedDict
from fnmatch import fnmatchcase
from typing import Any, Iterable, Optional

from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


class DuckDuckGoSearchTool(BaseTool):
    """
    DuckDuckGo web search tool for agents.

    Provides web search capability without requiring API keys.
    Results include titles, URLs, and snippets.

    Usage:
        tool = DuckDuckGoSearchTool(max_result_chars=4000)
        results = tool.run("latest AI news")
    """

    name: str = "web_search"
    description: str = (
        "Search the web for current information using DuckDuckGo. "
        "Input should be a search query string. "
        "Returns search results with titles, URLs, and content snippets."
    )

    def __init__(
        self,
        max_result_chars: Optional[int] = 4000,
        max_query_length: Optional[int] = 512,
        cache_ttl_seconds: Optional[float] = 300.0,
        cache_max_entries: int = 128,
        stale_cache_ttl_seconds: Optional[float] = None,
        retry_attempts: int = 0,
        retry_backoff_seconds: float = 0.0,
    ):
        """Initialize DuckDuckGo search tool.

        Args:
            max_result_chars: Optional max length for returned search text.
                When configured, oversized results are truncated with a
                deterministic suffix indicating omitted characters.
            max_query_length: Optional max query length after whitespace
                normalization. Set to ``None`` to disable query-length guards.
            cache_ttl_seconds: Optional in-memory cache TTL in seconds.
                Set to ``None`` to disable caching.
            cache_max_entries: Maximum number of cached query results.
                Oldest entries are evicted first once this limit is exceeded.
            stale_cache_ttl_seconds: Optional stale-cache fallback window in
                seconds. When configured, expired cache entries can still be
                returned if a fresh backend lookup fails and the stale entry
                age is within this window. Set to ``None`` to disable fallback.
            retry_attempts: Number of retry attempts after the initial
                backend failure. Set to ``0`` (default) to disable retries.
            retry_backoff_seconds: Base delay between retry attempts in
                seconds. Delay grows exponentially per retry attempt.
        """
        super().__init__()
        self._max_result_chars = self._normalize_max_result_chars(max_result_chars)
        self._max_query_length = self._normalize_max_query_length(max_query_length)
        self._cache_ttl_seconds = self._normalize_cache_ttl(cache_ttl_seconds)
        self._cache_max_entries = self._normalize_cache_max_entries(cache_max_entries)
        self._stale_cache_ttl_seconds = self._normalize_stale_cache_ttl(
            stale_cache_ttl_seconds
        )
        self._retry_attempts = self._normalize_retry_attempts(retry_attempts)
        self._retry_backoff_seconds = self._normalize_retry_backoff_seconds(
            retry_backoff_seconds
        )
        self._cache: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._cache_metrics = {
            "cache_hits": 0,
            "cache_misses": 0,
            "cache_writes": 0,
            "stale_fallback_hits": 0,
        }
        self._search = DuckDuckGoSearchRun()

    @staticmethod
    def _normalize_max_result_chars(value: Optional[int]) -> Optional[int]:
        """Validate optional result-length limits."""
        if value is None:
            return None

        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("max_result_chars must be a positive integer or None")

        if value <= 0:
            raise ValueError("max_result_chars must be a positive integer or None")

        return value

    @staticmethod
    def _normalize_cache_ttl(value: Optional[float]) -> Optional[float]:
        """Validate optional in-memory cache TTL values."""
        if value is None:
            return None

        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("cache_ttl_seconds must be a positive number or None")

        normalized_value = float(value)
        if normalized_value <= 0:
            raise ValueError("cache_ttl_seconds must be a positive number or None")

        return normalized_value

    @staticmethod
    def _normalize_cache_max_entries(value: int) -> int:
        """Validate cache capacity values."""
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("cache_max_entries must be a positive integer")

        if value <= 0:
            raise ValueError("cache_max_entries must be a positive integer")

        return value

    @staticmethod
    def _normalize_stale_cache_ttl(value: Optional[float]) -> Optional[float]:
        """Validate optional stale-cache fallback windows."""
        if value is None:
            return None

        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(
                "stale_cache_ttl_seconds must be a positive number or None"
            )

        normalized_value = float(value)
        if normalized_value <= 0:
            raise ValueError(
                "stale_cache_ttl_seconds must be a positive number or None"
            )

        return normalized_value

    @staticmethod
    def _normalize_retry_attempts(value: int) -> int:
        """Validate retry-attempt configuration."""
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("retry_attempts must be a non-negative integer")

        if value < 0:
            raise ValueError("retry_attempts must be a non-negative integer")

        return value

    @staticmethod
    def _normalize_retry_backoff_seconds(value: float) -> float:
        """Validate retry backoff configuration in seconds."""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("retry_backoff_seconds must be a non-negative number")

        normalized_value = float(value)
        if normalized_value < 0:
            raise ValueError("retry_backoff_seconds must be a non-negative number")

        return normalized_value

    @staticmethod
    def _normalize_max_query_length(value: Optional[int]) -> Optional[int]:
        """Validate optional query-length limits."""
        if value is None:
            return None

        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("max_query_length must be a positive integer or None")

        if value <= 0:
            raise ValueError("max_query_length must be a positive integer or None")

        return value

    @staticmethod
    def _parse_regex_flags(raw_flags: str | None) -> int:
        """Parse optional regex flag strings into ``re`` bitmasks."""
        if raw_flags is None:
            return 0

        if not isinstance(raw_flags, str):
            raise ValueError("regex_flags must be a string containing only i, m, s, x")

        normalized_flags = raw_flags.strip().lower()
        if normalized_flags == "":
            return 0

        supported_flags = {
            "i": re.IGNORECASE,
            "m": re.MULTILINE,
            "s": re.DOTALL,
            "x": re.VERBOSE,
        }

        parsed_flags = 0
        for flag in normalized_flags:
            mapped_flag = supported_flags.get(flag)
            if mapped_flag is None:
                raise ValueError(
                    "regex_flags must contain only supported flags: i, m, s, x"
                )
            parsed_flags |= mapped_flag

        return parsed_flags

    @staticmethod
    def _normalize_cache_status_selector(
        status: str | Iterable[str] | None,
    ) -> set[str] | None:
        """Normalize optional cache-status selectors used by invalidation."""
        if status is None:
            return None

        raw_statuses: list[object]
        if isinstance(status, str):
            raw_statuses = [status]
        else:
            try:
                raw_statuses = list(status)
            except TypeError as exc:
                raise ValueError(
                    "status must be a string or iterable of strings"
                ) from exc

        if not raw_statuses:
            raise ValueError("status must include at least one value")

        supported_statuses = {
            "active",
            "stale_eligible",
            "expired",
            "unbounded",
        }
        normalized_statuses: set[str] = set()

        for raw_status in raw_statuses:
            if not isinstance(raw_status, str):
                raise ValueError("status must contain only string values")

            normalized_status = raw_status.strip().lower()
            if normalized_status not in supported_statuses:
                raise ValueError(
                    "status must contain only: active, stale_eligible, expired, unbounded"
                )

            normalized_statuses.add(normalized_status)

        if not normalized_statuses:
            raise ValueError("status must include at least one value")

        return normalized_statuses

    def _normalize_query(self, query: str) -> str:
        """Normalize and validate incoming search queries."""
        if not isinstance(query, str):
            raise ValueError("query must be a non-empty string")

        normalized_query = re.sub(r"\s+", " ", query).strip()
        if not normalized_query:
            raise ValueError("query must be a non-empty string")

        if (
            self._max_query_length is not None
            and len(normalized_query) > self._max_query_length
        ):
            raise ValueError(
                "query exceeds max_query_length "
                f"({len(normalized_query)} > {self._max_query_length})"
            )

        return normalized_query

    def _truncate_results(self, results: Any) -> str:
        """Apply optional deterministic truncation to search output."""
        result_text = str(results)

        if self._max_result_chars is None or len(result_text) <= self._max_result_chars:
            return result_text

        omitted_characters = len(result_text) - self._max_result_chars
        truncated_text = result_text[: self._max_result_chars].rstrip()
        return f"{truncated_text}\n\n[truncated {omitted_characters} characters]"

    def _get_cached_results(self, query: str) -> str | None:
        """Fetch cached results when available and not expired."""
        if self._cache_ttl_seconds is None:
            return None

        cached_entry = self._cache.get(query)
        if cached_entry is None:
            return None

        cached_at, payload = cached_entry
        if time.monotonic() - cached_at > self._cache_ttl_seconds:
            if self._stale_cache_ttl_seconds is None:
                self._cache.pop(query, None)
            return None

        self._cache.move_to_end(query)
        return payload

    def _get_stale_cached_results(self, query: str) -> str | None:
        """Fetch stale cache payloads that are eligible for error fallback."""
        if self._stale_cache_ttl_seconds is None:
            return None

        cached_entry = self._cache.get(query)
        if cached_entry is None:
            return None

        cached_at, payload = cached_entry
        cache_age = time.monotonic() - cached_at

        if cache_age > self._stale_cache_ttl_seconds:
            self._cache.pop(query, None)
            return None

        self._cache.move_to_end(query)
        return payload

    def _set_cached_results(self, query: str, results: str) -> None:
        """Store results in cache and enforce LRU capacity constraints."""
        if self._cache_ttl_seconds is None:
            return

        self._cache[query] = (time.monotonic(), results)
        self._cache.move_to_end(query)

        while len(self._cache) > self._cache_max_entries:
            self._cache.popitem(last=False)

    def _cache_retention_seconds(self) -> float | None:
        """Return the max age at which cache entries can still be useful."""
        if self._cache_ttl_seconds is None:
            return None

        retention_seconds = self._cache_ttl_seconds
        if self._stale_cache_ttl_seconds is not None:
            retention_seconds = max(retention_seconds, self._stale_cache_ttl_seconds)

        return retention_seconds

    def prune_cache(self) -> int:
        """Remove cache entries older than configured retention windows.

        Returns:
            Number of entries removed from the in-memory cache.
        """
        retention_seconds = self._cache_retention_seconds()
        if retention_seconds is None:
            return 0

        now = time.monotonic()
        removable_queries = [
            query
            for query, (cached_at, _payload) in self._cache.items()
            if now - cached_at > retention_seconds
        ]

        for query in removable_queries:
            self._cache.pop(query, None)

        return len(removable_queries)

    def invalidate_cache(
        self,
        query: str | None = None,
        *,
        queries: Iterable[str] | None = None,
        contains: str | None = None,
        prefix: str | None = None,
        suffix: str | None = None,
        pattern: str | None = None,
        regex: str | None = None,
        regex_flags: str | None = None,
        older_than_seconds: float | None = None,
        younger_than_seconds: float | None = None,
        status: str | Iterable[str] | None = None,
        limit: int | None = None,
        newest_first: bool = False,
        case_sensitive: bool = True,
        dry_run: bool = False,
    ) -> int:
        """Invalidate selected cache entries or clear the full cache.

        Args:
            query: Optional query string to invalidate after normalization.
            queries: Optional iterable of query strings to invalidate in one
                call. Normalization and de-duplication are applied before
                deletion.
            contains: Optional substring matcher applied against normalized
                query keys.
            prefix: Optional normalized-query prefix used to invalidate all
                matching cache entries.
            suffix: Optional normalized-query suffix used to invalidate all
                matching cache entries.
            pattern: Optional glob-style matcher applied against normalized
                query keys (for example, ``"news *"``).
            regex: Optional regular-expression matcher applied against
                normalized query keys.
            regex_flags: Optional regular-expression flags (``i``, ``m``,
                ``s``, ``x``) used only when ``regex`` is provided.
            older_than_seconds: Optional age threshold that removes cache
                entries older than the provided number of seconds.
            younger_than_seconds: Optional age threshold that removes cache
                entries younger than the provided number of seconds.
            status: Optional cache-status selector. Accepts one status or an
                iterable of statuses from ``active``, ``stale_eligible``,
                ``expired``, and ``unbounded``.
            limit: Optional maximum number of matching cache entries to
                invalidate. Matches are processed in deterministic cache
                order.
            newest_first: When ``True``, matching entries are processed from
                newest to oldest before optional ``limit`` capping.
            case_sensitive: When ``True`` (default), text selectors are
                matched with exact case. Set to ``False`` to enable
                case-insensitive matching for ``query``, ``queries``,
                ``contains``, ``prefix``, ``suffix``, ``pattern``, and
                ``regex`` selectors.
            dry_run: When ``True``, returns the number of matching cache
                entries without deleting them.

        Returns:
            Number of cache entries matching the invalidation selector.

        Raises:
            ValueError: If more than one selector argument is provided, if
                ``queries`` is not an iterable of non-empty strings, if
                ``regex`` is not a valid regular expression, if
                ``regex_flags`` is invalid, if ``older_than_seconds`` or
                ``younger_than_seconds`` is not a positive number, if
                ``status`` is invalid, if ``limit`` is
                not a positive integer, if ``newest_first`` is not a boolean,
                if ``case_sensitive`` is not a boolean, or if ``dry_run`` is
                not a boolean.
        """
        normalized_status_selector = self._normalize_cache_status_selector(status)

        selector_count = sum(
            candidate is not None
            for candidate in (
                query,
                queries,
                contains,
                prefix,
                suffix,
                pattern,
                regex,
                older_than_seconds,
                younger_than_seconds,
                normalized_status_selector,
            )
        )
        if selector_count > 1:
            raise ValueError(
                "query, queries, contains, prefix, suffix, pattern, regex, "
                "older_than_seconds, younger_than_seconds, and status are mutually exclusive"
            )

        if not isinstance(dry_run, bool):
            raise ValueError("dry_run must be a boolean value")

        if not isinstance(newest_first, bool):
            raise ValueError("newest_first must be a boolean value")

        if not isinstance(case_sensitive, bool):
            raise ValueError("case_sensitive must be a boolean value")

        if regex_flags is not None and regex is None:
            raise ValueError("regex_flags can only be used with regex selector")

        if older_than_seconds is not None:
            if isinstance(older_than_seconds, bool) or not isinstance(
                older_than_seconds,
                (int, float),
            ):
                raise ValueError("older_than_seconds must be a positive number")

            normalized_age_threshold = float(older_than_seconds)
            if normalized_age_threshold <= 0:
                raise ValueError("older_than_seconds must be a positive number")

        if younger_than_seconds is not None:
            if isinstance(younger_than_seconds, bool) or not isinstance(
                younger_than_seconds,
                (int, float),
            ):
                raise ValueError("younger_than_seconds must be a positive number")

            normalized_age_threshold = float(younger_than_seconds)
            if normalized_age_threshold <= 0:
                raise ValueError("younger_than_seconds must be a positive number")

        if limit is not None:
            if isinstance(limit, bool) or not isinstance(limit, int):
                raise ValueError("limit must be a positive integer")

            if limit <= 0:
                raise ValueError("limit must be a positive integer")

        def _apply_limit(matching_queries: list[str]) -> list[str]:
            if newest_first:
                matching_queries = list(reversed(matching_queries))

            if limit is None:
                return matching_queries

            return matching_queries[:limit]

        if selector_count == 0:
            matching_queries = _apply_limit(list(self._cache.keys()))
            if not dry_run:
                for cached_query in matching_queries:
                    self._cache.pop(cached_query, None)
            return len(matching_queries)

        if query is not None:
            normalized_query = self._normalize_query(query)
            if case_sensitive:
                matching_queries = (
                    [normalized_query] if normalized_query in self._cache else []
                )
            else:
                normalized_query_casefold = normalized_query.casefold()
                matching_queries = [
                    cached_query
                    for cached_query in self._cache
                    if cached_query.casefold() == normalized_query_casefold
                ]

            matching_queries = _apply_limit(matching_queries)
            if not dry_run:
                for cached_query in matching_queries:
                    self._cache.pop(cached_query, None)
            return len(matching_queries)

        if queries is not None:
            if isinstance(queries, str):
                raise ValueError("queries must be an iterable of non-empty strings")

            try:
                normalized_queries = [
                    self._normalize_query(candidate) for candidate in queries
                ]
            except TypeError as exc:
                raise ValueError(
                    "queries must be an iterable of non-empty strings"
                ) from exc

            if case_sensitive:
                matching_queries = [
                    normalized_query
                    for normalized_query in dict.fromkeys(normalized_queries)
                    if normalized_query in self._cache
                ]
            else:
                casefolded_targets = {
                    normalized_query.casefold()
                    for normalized_query in normalized_queries
                }
                matching_queries = [
                    cached_query
                    for cached_query in self._cache
                    if cached_query.casefold() in casefolded_targets
                ]

            matching_queries = _apply_limit(matching_queries)

            if not dry_run:
                for normalized_query in matching_queries:
                    self._cache.pop(normalized_query, None)

            return len(matching_queries)

        if older_than_seconds is not None:
            now = time.monotonic()
            normalized_age_threshold = float(older_than_seconds)
            matching_queries = [
                cached_query
                for cached_query, (cached_at, _payload) in self._cache.items()
                if now - cached_at > normalized_age_threshold
            ]
            matching_queries = _apply_limit(matching_queries)

            if not dry_run:
                for cached_query in matching_queries:
                    self._cache.pop(cached_query, None)

            return len(matching_queries)

        if younger_than_seconds is not None:
            now = time.monotonic()
            normalized_age_threshold = float(younger_than_seconds)
            matching_queries = [
                cached_query
                for cached_query, (cached_at, _payload) in self._cache.items()
                if now - cached_at < normalized_age_threshold
            ]
            matching_queries = _apply_limit(matching_queries)

            if not dry_run:
                for cached_query in matching_queries:
                    self._cache.pop(cached_query, None)

            return len(matching_queries)

        if normalized_status_selector is not None:
            now = time.monotonic()
            matching_queries = [
                cached_query
                for cached_query, (cached_at, _payload) in self._cache.items()
                if self._cache_entry_status(now - cached_at)
                in normalized_status_selector
            ]
            matching_queries = _apply_limit(matching_queries)

            if not dry_run:
                for cached_query in matching_queries:
                    self._cache.pop(cached_query, None)

            return len(matching_queries)

        if contains is not None:
            normalized_contains = self._normalize_query(contains)
            if case_sensitive:
                matching_queries = [
                    cached_query
                    for cached_query in self._cache
                    if normalized_contains in cached_query
                ]
            else:
                normalized_contains_casefold = normalized_contains.casefold()
                matching_queries = [
                    cached_query
                    for cached_query in self._cache
                    if normalized_contains_casefold in cached_query.casefold()
                ]
        elif prefix is not None:
            normalized_prefix = self._normalize_query(prefix)
            if case_sensitive:
                matching_queries = [
                    cached_query
                    for cached_query in self._cache
                    if cached_query.startswith(normalized_prefix)
                ]
            else:
                normalized_prefix_casefold = normalized_prefix.casefold()
                matching_queries = [
                    cached_query
                    for cached_query in self._cache
                    if cached_query.casefold().startswith(normalized_prefix_casefold)
                ]
        elif suffix is not None:
            normalized_suffix = self._normalize_query(suffix)
            if case_sensitive:
                matching_queries = [
                    cached_query
                    for cached_query in self._cache
                    if cached_query.endswith(normalized_suffix)
                ]
            else:
                normalized_suffix_casefold = normalized_suffix.casefold()
                matching_queries = [
                    cached_query
                    for cached_query in self._cache
                    if cached_query.casefold().endswith(normalized_suffix_casefold)
                ]
        elif pattern is not None:
            normalized_pattern = self._normalize_query(pattern)
            if case_sensitive:
                matching_queries = [
                    cached_query
                    for cached_query in self._cache
                    if fnmatchcase(cached_query, normalized_pattern)
                ]
            else:
                normalized_pattern_casefold = normalized_pattern.casefold()
                matching_queries = [
                    cached_query
                    for cached_query in self._cache
                    if fnmatchcase(cached_query.casefold(), normalized_pattern_casefold)
                ]
        else:
            assert regex is not None
            regex_flag_bits = self._parse_regex_flags(regex_flags)
            if not case_sensitive:
                regex_flag_bits |= re.IGNORECASE
            try:
                compiled_pattern = re.compile(regex, flags=regex_flag_bits)
            except re.error as exc:
                raise ValueError("regex must be a valid regular expression") from exc

            matching_queries = [
                cached_query
                for cached_query in self._cache
                if compiled_pattern.search(cached_query)
            ]

        matching_queries = _apply_limit(matching_queries)

        if not dry_run:
            for cached_query in matching_queries:
                self._cache.pop(cached_query, None)

        return len(matching_queries)

    def _increment_cache_metric(self, metric_name: str) -> None:
        """Increment one in-memory cache metric counter."""
        self._cache_metrics[metric_name] += 1

    def clear_cache(self) -> None:
        """Clear in-memory cached search results."""
        self.invalidate_cache()

    def reset_cache_metrics(self) -> None:
        """Reset cache diagnostic counters to zero."""
        for metric_name in self._cache_metrics:
            self._cache_metrics[metric_name] = 0

    def _cache_entry_status(self, age_seconds: float) -> str:
        """Classify cache-entry freshness for diagnostics and observability."""
        if self._cache_ttl_seconds is None:
            return "unbounded"

        if age_seconds <= self._cache_ttl_seconds:
            return "active"

        if (
            self._stale_cache_ttl_seconds is not None
            and age_seconds <= self._stale_cache_ttl_seconds
        ):
            return "stale_eligible"

        return "expired"

    def list_cache_entries(
        self,
        *,
        limit: int | None = None,
        newest_first: bool = False,
        status: str | Iterable[str] | None = None,
        query_contains: str | None = None,
        case_sensitive: bool = True,
    ) -> list[dict[str, Any]]:
        """Return a deterministic snapshot of cached queries and freshness state.

        Args:
            limit: Optional maximum number of cache entries to return.
            newest_first: When ``True``, return entries from newest to oldest.
            status: Optional cache-status selector used to filter entries.
                Accepts one status or an iterable of statuses from ``active``,
                ``stale_eligible``, ``expired``, and ``unbounded``.
            query_contains: Optional substring matcher applied to cache query
                keys after optional whitespace normalization.
            case_sensitive: When ``True`` (default), ``query_contains`` matching
                is case-sensitive. Set to ``False`` for case-insensitive
                matching.

        Returns:
            List of per-entry diagnostics with query key, age, freshness status,
            and payload size metadata.

        Raises:
            ValueError: If ``limit`` is not a positive integer, if
                ``newest_first`` or ``case_sensitive`` is not a boolean value,
                if ``status`` includes unsupported values, or if
                ``query_contains`` is not a non-empty string when provided.
        """
        if not isinstance(newest_first, bool):
            raise ValueError("newest_first must be a boolean value")

        if not isinstance(case_sensitive, bool):
            raise ValueError("case_sensitive must be a boolean value")

        if limit is not None:
            if isinstance(limit, bool) or not isinstance(limit, int):
                raise ValueError("limit must be a positive integer")

            if limit <= 0:
                raise ValueError("limit must be a positive integer")

        normalized_status_selector = self._normalize_cache_status_selector(status)

        normalized_query_contains: str | None = None
        normalized_query_contains_casefold: str | None = None
        if query_contains is not None:
            normalized_query_contains = self._normalize_query(query_contains)
            if not case_sensitive:
                normalized_query_contains_casefold = (
                    normalized_query_contains.casefold()
                )

        now = time.monotonic()
        cache_entries = list(self._cache.items())

        if newest_first:
            cache_entries.reverse()

        inspected_entries: list[dict[str, Any]] = []
        for query, (cached_at, payload) in cache_entries:
            age_seconds = now - cached_at
            cache_status = self._cache_entry_status(age_seconds)

            if (
                normalized_status_selector is not None
                and cache_status not in normalized_status_selector
            ):
                continue

            if normalized_query_contains is not None:
                if case_sensitive:
                    if normalized_query_contains not in query:
                        continue
                else:
                    assert normalized_query_contains_casefold is not None
                    if normalized_query_contains_casefold not in query.casefold():
                        continue

            inspected_entries.append(
                {
                    "query": query,
                    "age_seconds": age_seconds,
                    "status": cache_status,
                    "payload_chars": len(payload),
                }
            )

        if limit is not None:
            inspected_entries = inspected_entries[:limit]

        return inspected_entries

    def get_cache_stats(self) -> dict[str, Any]:
        """Return cache health and retention metrics for diagnostics."""
        retention_seconds = self._cache_retention_seconds()
        now = time.monotonic()

        active_entries = 0
        expired_entries = 0
        stale_eligible_entries = 0

        for cached_at, _payload in self._cache.values():
            age_seconds = now - cached_at

            if (
                self._cache_ttl_seconds is not None
                and age_seconds <= self._cache_ttl_seconds
            ):
                active_entries += 1
                continue

            expired_entries += 1
            if (
                self._stale_cache_ttl_seconds is not None
                and age_seconds <= self._stale_cache_ttl_seconds
            ):
                stale_eligible_entries += 1

        cache_lookups = (
            self._cache_metrics["cache_hits"] + self._cache_metrics["cache_misses"]
        )
        hit_ratio = (
            self._cache_metrics["cache_hits"] / cache_lookups
            if cache_lookups > 0
            else None
        )

        return {
            "enabled": self._cache_ttl_seconds is not None,
            "entries": len(self._cache),
            "max_entries": self._cache_max_entries,
            "ttl_seconds": self._cache_ttl_seconds,
            "stale_ttl_seconds": self._stale_cache_ttl_seconds,
            "retention_seconds": retention_seconds,
            "active_entries": active_entries,
            "expired_entries": expired_entries,
            "stale_eligible_entries": stale_eligible_entries,
            "cache_hits": self._cache_metrics["cache_hits"],
            "cache_misses": self._cache_metrics["cache_misses"],
            "cache_writes": self._cache_metrics["cache_writes"],
            "stale_fallback_hits": self._cache_metrics["stale_fallback_hits"],
            "hit_ratio": hit_ratio,
        }

    def _run_search_with_retries(self, query: str) -> Any:
        """Run backend search with optional retry/backoff semantics."""
        attempts = self._retry_attempts + 1
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                return self._search.run(query)
            except Exception as error:  # pragma: no cover - branches tested via _run
                last_error = error
                is_last_attempt = attempt == attempts - 1
                if is_last_attempt:
                    break

                retry_delay = self._retry_backoff_seconds * (2**attempt)
                logger.warning(
                    "DuckDuckGo search failed for '%s' (attempt %d/%d): %s",
                    query,
                    attempt + 1,
                    attempts,
                    error,
                )
                if retry_delay > 0:
                    time.sleep(retry_delay)

        assert last_error is not None
        raise last_error

    def _execute_search(self, query: str) -> tuple[str, str, str | None]:
        """Execute one search request and return result payload + source metadata.

        Returns:
            Tuple of ``(result, source, normalized_query)`` where source is one
            of ``"cache_hit"``, ``"fresh_search"``, ``"stale_cache_fallback"``,
            or ``"error"``.
        """
        normalized_query: str | None = None

        try:
            normalized_query = self._normalize_query(query)

            cached_results = self._get_cached_results(normalized_query)
            if cached_results is not None:
                self._increment_cache_metric("cache_hits")
                logger.debug(
                    "Returning cached DuckDuckGo results: %s", normalized_query
                )
                return cached_results, "cache_hit", normalized_query

            if self._cache_ttl_seconds is not None:
                self._increment_cache_metric("cache_misses")

            logger.debug("Running DuckDuckGo search: %s", normalized_query)
            results = self._run_search_with_retries(normalized_query)
            normalized_results = self._truncate_results(results)
            self._set_cached_results(normalized_query, normalized_results)
            if self._cache_ttl_seconds is not None:
                self._increment_cache_metric("cache_writes")
            logger.debug("Search completed: %d characters", len(normalized_results))
            return normalized_results, "fresh_search", normalized_query

        except Exception as error:
            if normalized_query is not None:
                stale_results = self._get_stale_cached_results(normalized_query)
                if stale_results is not None:
                    self._increment_cache_metric("stale_fallback_hits")
                    logger.warning(
                        "Search failed for '%s'; returning stale cached response: %s",
                        normalized_query,
                        error,
                    )
                    fallback_payload = (
                        f"{stale_results}\n\n"
                        f"[stale cache fallback due to search error: {error}]"
                    )
                    return (
                        fallback_payload,
                        "stale_cache_fallback",
                        normalized_query,
                    )

            logger.error("Search failed: %s", error, exc_info=True)
            return f"Search failed: {error}", "error", normalized_query

    def search_with_diagnostics(self, query: str) -> dict[str, Any]:
        """Run a search and include source + latency diagnostics.

        This helper keeps the same output payload as ``_run`` while exposing
        metadata that can be used for observability dashboards and debugging.
        """
        start_time = time.monotonic()
        result, source, normalized_query = self._execute_search(query)
        latency_ms = (time.monotonic() - start_time) * 1000

        diagnostics: dict[str, Any] = {
            "query": query,
            "normalized_query": normalized_query,
            "result": result,
            "source": source,
            "latency_ms": latency_ms,
            "success": source != "error",
            "cache_hit": source == "cache_hit",
            "stale_fallback": source == "stale_cache_fallback",
        }

        if source == "error":
            diagnostics["error"] = result.removeprefix("Search failed: ")

        return diagnostics

    @staticmethod
    def _normalize_query_batch(queries: Iterable[str]) -> list[str]:
        """Validate and normalize query batches for bulk diagnostics helpers."""
        if isinstance(queries, str):
            raise ValueError("queries must be an iterable of query strings")

        try:
            normalized_queries = list(queries)
        except TypeError as exc:
            raise ValueError("queries must be an iterable of query strings") from exc

        if not normalized_queries:
            raise ValueError("queries must include at least one query")

        if not all(isinstance(query, str) for query in normalized_queries):
            raise ValueError("queries must contain only string values")

        return normalized_queries

    def search_many_with_diagnostics(self, queries: Iterable[str]) -> dict[str, Any]:
        """Run multiple searches and return per-query + aggregate diagnostics.

        Args:
            queries: Iterable of query strings processed in order.

        Returns:
            Dictionary containing ``results`` (per-query diagnostics payloads)
            and ``summary`` (aggregate success/cache/latency metrics).
        """
        normalized_queries = self._normalize_query_batch(queries)
        diagnostics_rows = [
            self.search_with_diagnostics(query) for query in normalized_queries
        ]

        total_queries = len(diagnostics_rows)
        success_count = sum(1 for row in diagnostics_rows if row["success"])
        cache_hit_count = sum(1 for row in diagnostics_rows if row["cache_hit"])
        stale_fallback_count = sum(
            1 for row in diagnostics_rows if row["stale_fallback"]
        )
        fresh_search_count = sum(
            1 for row in diagnostics_rows if row["source"] == "fresh_search"
        )
        error_count = total_queries - success_count
        average_latency_ms = (
            sum(float(row["latency_ms"]) for row in diagnostics_rows) / total_queries
        )

        return {
            "results": diagnostics_rows,
            "summary": {
                "total_queries": total_queries,
                "successes": success_count,
                "errors": error_count,
                "fresh_searches": fresh_search_count,
                "cache_hits": cache_hit_count,
                "stale_fallbacks": stale_fallback_count,
                "average_latency_ms": average_latency_ms,
            },
        }

    def _run(self, query: str) -> str:
        """
        Run web search synchronously.

        Args:
            query: Search query string

        Returns:
            Formatted search results
        """
        result, _source, _normalized_query = self._execute_search(query)
        return result

    async def _arun(self, query: str) -> str:
        """
        Run web search asynchronously.

        Args:
            query: Search query string

        Returns:
            Formatted search results
        """
        # DuckDuckGo tool doesn't have native async, use sync version.
        return self._run(query)


__all__ = ["DuckDuckGoSearchTool"]
