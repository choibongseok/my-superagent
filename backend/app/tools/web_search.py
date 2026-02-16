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
        prefix: str | None = None,
        pattern: str | None = None,
        regex: str | None = None,
    ) -> int:
        """Invalidate selected cache entries or clear the full cache.

        Args:
            query: Optional query string to invalidate after normalization.
            queries: Optional iterable of query strings to invalidate in one
                call. Normalization and de-duplication are applied before
                deletion.
            prefix: Optional normalized-query prefix used to invalidate all
                matching cache entries.
            pattern: Optional glob-style matcher applied against normalized
                query keys (for example, ``"news *"``).
            regex: Optional regular-expression matcher applied against
                normalized query keys.

        Returns:
            Number of entries removed from cache.

        Raises:
            ValueError: If more than one selector argument is provided, if
                ``queries`` is not an iterable of non-empty strings, or if
                ``regex`` is not a valid regular expression.
        """
        selector_count = sum(
            candidate is not None
            for candidate in (query, queries, prefix, pattern, regex)
        )
        if selector_count > 1:
            raise ValueError(
                "query, queries, prefix, pattern, and regex are mutually exclusive"
            )

        if selector_count == 0:
            removed_entries = len(self._cache)
            self._cache.clear()
            return removed_entries

        if query is not None:
            normalized_query = self._normalize_query(query)
            if normalized_query in self._cache:
                self._cache.pop(normalized_query, None)
                return 1
            return 0

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

            removed_entries = 0
            for normalized_query in dict.fromkeys(normalized_queries):
                if normalized_query in self._cache:
                    self._cache.pop(normalized_query, None)
                    removed_entries += 1

            return removed_entries

        if prefix is not None:
            normalized_prefix = self._normalize_query(prefix)
            matching_queries = [
                cached_query
                for cached_query in self._cache
                if cached_query.startswith(normalized_prefix)
            ]
        elif pattern is not None:
            normalized_pattern = self._normalize_query(pattern)
            matching_queries = [
                cached_query
                for cached_query in self._cache
                if fnmatchcase(cached_query, normalized_pattern)
            ]
        else:
            assert regex is not None
            try:
                compiled_pattern = re.compile(regex)
            except re.error as exc:
                raise ValueError("regex must be a valid regular expression") from exc

            matching_queries = [
                cached_query
                for cached_query in self._cache
                if compiled_pattern.search(cached_query)
            ]

        for cached_query in matching_queries:
            self._cache.pop(cached_query, None)

        return len(matching_queries)

    def clear_cache(self) -> None:
        """Clear in-memory cached search results."""
        self.invalidate_cache()

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

    def _run(self, query: str) -> str:
        """
        Run web search synchronously.

        Args:
            query: Search query string

        Returns:
            Formatted search results
        """
        normalized_query: str | None = None

        try:
            normalized_query = self._normalize_query(query)

            cached_results = self._get_cached_results(normalized_query)
            if cached_results is not None:
                logger.debug(
                    "Returning cached DuckDuckGo results: %s", normalized_query
                )
                return cached_results

            logger.debug("Running DuckDuckGo search: %s", normalized_query)
            results = self._run_search_with_retries(normalized_query)
            normalized_results = self._truncate_results(results)
            self._set_cached_results(normalized_query, normalized_results)
            logger.debug("Search completed: %d characters", len(normalized_results))
            return normalized_results

        except Exception as error:
            if normalized_query is not None:
                stale_results = self._get_stale_cached_results(normalized_query)
                if stale_results is not None:
                    logger.warning(
                        "Search failed for '%s'; returning stale cached response: %s",
                        normalized_query,
                        error,
                    )
                    return (
                        f"{stale_results}\n\n"
                        f"[stale cache fallback due to search error: {error}]"
                    )

            logger.error("Search failed: %s", error, exc_info=True)
            return f"Search failed: {error}"

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
