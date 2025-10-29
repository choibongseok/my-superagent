"""Web search tool using DuckDuckGo."""

import logging
from typing import Optional

from langchain_core.tools import Tool
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper

logger = logging.getLogger(__name__)


def create_web_search_tool(max_results: int = 5) -> Tool:
    """
    Create web search tool using DuckDuckGo.
    
    Args:
        max_results: Maximum number of search results
        
    Returns:
        LangChain Tool instance
    """
    search = DuckDuckGoSearchAPIWrapper()
    
    def search_wrapper(query: str) -> str:
        """Search the web and return results."""
        try:
            results = search.results(query, max_results=max_results)
            
            if not results:
                return "No results found."
            
            # Format results
            formatted = []
            for i, result in enumerate(results, 1):
                formatted.append(
                    f"{i}. {result['title']}\n"
                    f"   URL: {result['link']}\n"
                    f"   {result['snippet']}\n"
                )
            
            return "\n".join(formatted)
            
        except Exception as e:
            logger.error(f"Web search failed: {e}")
            return f"Search failed: {str(e)}"
    
    return Tool(
        name="web_search",
        description=(
            "Useful for searching the web for current information. "
            "Input should be a search query string. "
            "Returns formatted search results with titles, URLs, and snippets."
        ),
        func=search_wrapper,
    )


__all__ = ["create_web_search_tool"]
