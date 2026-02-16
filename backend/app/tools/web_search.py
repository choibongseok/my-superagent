"""Web search tool using DuckDuckGo."""

import logging
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

    def __init__(self, max_result_chars: Optional[int] = 4000):
        """Initialize DuckDuckGo search tool.

        Args:
            max_result_chars: Optional max length for returned search text.
                When configured, oversized results are truncated with a
                deterministic suffix indicating omitted characters.
        """
        super().__init__()
        self._max_result_chars = self._normalize_max_result_chars(max_result_chars)
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

    def _run(self, query: str) -> str:
        """
        Run web search synchronously.

        Args:
            query: Search query string

        Returns:
            Formatted search results
        """
        try:
            normalized_query = self._normalize_query(query)
            logger.debug("Running DuckDuckGo search: %s", normalized_query)
            results = self._search.run(normalized_query)
            normalized_results = self._truncate_results(results)
            logger.debug("Search completed: %d characters", len(normalized_results))
            return normalized_results

        except Exception as error:
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
