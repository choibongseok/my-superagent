"""Web search tool using DuckDuckGo."""

import logging
from typing import Optional

from langchain_core.tools import BaseTool
from langchain_community.tools import DuckDuckGoSearchRun

logger = logging.getLogger(__name__)


class DuckDuckGoSearchTool(BaseTool):
    """
    DuckDuckGo web search tool for agents.

    Provides web search capability without requiring API keys.
    Results include titles, URLs, and snippets.

    Usage:
        tool = DuckDuckGoSearchTool()
        results = tool.run("latest AI news")
    """

    name: str = "web_search"
    description: str = (
        "Search the web for current information using DuckDuckGo. "
        "Input should be a search query string. "
        "Returns search results with titles, URLs, and content snippets."
    )

    def __init__(self):
        """Initialize DuckDuckGo search tool."""
        super().__init__()
        self._search = DuckDuckGoSearchRun()

    def _run(self, query: str) -> str:
        """
        Run web search synchronously.

        Args:
            query: Search query string

        Returns:
            Formatted search results
        """
        try:
            logger.debug(f"Running DuckDuckGo search: {query}")
            results = self._search.run(query)
            logger.debug(f"Search completed: {len(results)} characters")
            return results
        
        except Exception as e:
            logger.error(f"Search failed: {e}", exc_info=True)
            return f"Search failed: {str(e)}"

    async def _arun(self, query: str) -> str:
        """
        Run web search asynchronously.

        Args:
            query: Search query string

        Returns:
            Formatted search results
        """
        # DuckDuckGo tool doesn't have native async, use sync version
        return self._run(query)


__all__ = ["DuckDuckGoSearchTool"]
