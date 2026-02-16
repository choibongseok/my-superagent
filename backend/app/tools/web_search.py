"""Web search tool using DuckDuckGo."""

import logging
import time
from collections import OrderedDict
from typing import Any, Optional

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
    def _normalize_query(query: str) -> str:
        """Normalize and validate incoming search queries."""
        if not isinstance(query, str):
            raise ValueError("query must be a non-empty string")

        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query must be a non-empty string")

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

    def clear_cache(self) -> None:
        """Clear in-memory cached search results."""
        self._cache.clear()

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
