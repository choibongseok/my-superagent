"""Research Agent for web search and information synthesis."""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import BaseTool

from app.agents.base import BaseAgent
from app.tools.web_search import DuckDuckGoSearchTool
from app.services.citation.tracker import CitationTracker
from app.services.citation.models import SourceType

logger = logging.getLogger(__name__)


class ResearchAgent(BaseAgent):
    """
    Agent for web research and information gathering with citation tracking.

    Features:
        - Web search via DuckDuckGo
        - Information synthesis from multiple sources
        - Automatic citation generation
        - Source tracking and validation
        - Integration with Phase 2 MemoryManager

    Usage:
        agent = ResearchAgent(
            user_id="user123",
            session_id="research_session",
        )
        result = await agent.run("Research latest AI developments in 2024")

        # Result includes:
        # - synthesized_info: Key findings and analysis
        # - citations: List of sources with URLs
        # - search_results: Raw search data
    """

    def __init__(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        **kwargs,
    ):
        """
        Initialize Research Agent.

        Args:
            user_id: User identifier
            session_id: Session identifier
            **kwargs: Additional BaseAgent parameters
        """
        super().__init__(
            user_id=user_id,
            session_id=session_id or f"research_{user_id}",
            **kwargs,
        )

        # Initialize Citation Tracker (rich metadata/validation API)
        self.citation_tracker = CitationTracker()

        # Simple citations list — lightweight dict records for quick access.
        # Tests and external callers can append dicts here directly;
        # _extract_citations() also populates this list.
        self._citations: List[Dict[str, Any]] = []

        logger.info(f"ResearchAgent initialized for user {user_id}")

    @property
    def citations(self) -> List[Dict[str, Any]]:
        """Mutable list of citation dicts for this research session.

        Each entry is a plain dict, e.g.::

            {"query": "AI trends", "source": "duckduckgo",
             "timestamp": "2024-01-01T00:00:00", "url": "https://…"}

        You can append to this list directly or use ``_extract_citations()``
        to populate it from agent intermediate steps.
        """
        return self._citations

    def _get_metadata(self) -> Dict[str, Any]:
        """Get agent metadata for tracking."""
        return {
            "agent_type": "research",
            "version": "1.0",
            "capabilities": [
                "web_search",
                "citation_tracking",
                "information_synthesis",
                "source_validation",
            ],
        }

    def _create_tools(self) -> List[BaseTool]:
        """Create research tools."""
        tools = [
            DuckDuckGoSearchTool(),
        ]

        logger.debug(f"Created {len(tools)} tools for ResearchAgent")
        return tools

    def _create_prompt(self) -> ChatPromptTemplate:
        """Create research agent prompt template."""
        system_message = """You are a professional research agent specialized in web research and information synthesis.

Your responsibilities:
1. Search the web for accurate, up-to-date information using the web_search tool
2. Analyze and synthesize information from multiple sources
3. Provide citations for all claims with URLs
4. Present information in a clear, structured format
5. Cross-reference information when possible

Guidelines:
- Always cite your sources with URLs
- Prioritize recent and authoritative sources
- Clearly distinguish facts from opinions
- Be transparent about information gaps or conflicting information
- Use multiple searches if needed to gather comprehensive information

Output format:
## Key Findings
- [Bullet point 1]
- [Bullet point 2]
- [Bullet point 3]

## Detailed Analysis
[Comprehensive analysis with inline citations]

## Sources
1. [Source title] - [URL]
2. [Source title] - [URL]
3. [Source title] - [URL]

Note: Use the web_search tool for each distinct query needed to answer the user's question thoroughly.
"""

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_message),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ]
        )

        return prompt

    async def research(
        self,
        query: str,
        max_sources: int = 5,
    ) -> Dict[str, Any]:
        """
        Perform research on a query with citation tracking.

        Args:
            query: Research query
            max_sources: Maximum number of sources to gather

        Returns:
            Research results with citations
        """
        logger.info(f"Starting research: {query}")

        # Run the agent
        result = await self.run(query)

        if not result["success"]:
            logger.error(f"Research failed: {result.get('error')}")
            return result

        # Extract and track citations from intermediate steps
        self._process_citations(
            result.get("intermediate_steps", []),
            max_sources=max_sources,
        )

        # Get formatted citations and validation report
        citations = self.citation_tracker.get_bibliography(style="apa")
        validation_report = self.citation_tracker.get_validation_report(
            min_sources=max(1, min(max_sources, 3))
        )

        # Add citation outputs to result
        result["citations"] = citations
        result["citation_count"] = len(citations)
        result["tracker_stats"] = self.citation_tracker.get_statistics()
        result["validation_report"] = validation_report

        logger.info(f"Research completed with {len(citations)} sources")

        return result

    def _process_citations(
        self,
        intermediate_steps: List[tuple],
        max_sources: int = 5,
    ) -> None:
        """Process intermediate steps and add sources to citation tracker.

        Args:
            intermediate_steps: List of ``(action, observation)`` tuples.
            max_sources: Maximum total source entries tracked for the run.
        """
        if max_sources <= 0:
            raise ValueError("max_sources must be greater than 0")

        for action, observation in intermediate_steps:
            if len(self.citation_tracker.sources) >= max_sources:
                break

            if not (hasattr(action, "tool") and action.tool == "web_search"):
                continue

            # Extract query text from either raw string input or structured payload.
            if isinstance(action.tool_input, str):
                query = action.tool_input
            else:
                query = action.tool_input.get("query", "")

            if not isinstance(observation, str):
                continue

            try:
                # Simple parsing: look for URLs in the text.
                import re

                urls = re.findall(r'https?://[^\s<>"]+', observation)

                remaining_budget = max_sources - len(self.citation_tracker.sources)
                for url in urls[:remaining_budget]:
                    source_id = self.citation_tracker.add_source(
                        title=f"Web Search Result: {query}",
                        url=url,
                        type=SourceType.WEB,
                        author="DuckDuckGo Search",
                        published_date=datetime.utcnow(),
                        description=f"Search result for query: {query}",
                        metadata={
                            "query": query,
                            "search_engine": "duckduckgo",
                        },
                    )

                    self.citation_tracker.cite(
                        source_id=source_id,
                        context=f"Found via web search for: {query}",
                        metadata={
                            "query": query,
                            "timestamp": datetime.utcnow().isoformat(),
                        },
                    )

                # No URLs found in observation — add the search itself as source
                if not urls and len(self.citation_tracker.sources) < max_sources:
                    source_id = self.citation_tracker.add_source(
                        title=f"Web Search: {query}",
                        type=SourceType.WEB,
                        author="DuckDuckGo",
                        description=(
                            observation[:200] + "..."
                            if len(observation) > 200
                            else observation
                        ),
                        metadata={"query": query},
                    )
                    self.citation_tracker.cite(
                        source_id=source_id,
                        quoted_text=observation[:500],
                        context=f"Search query: {query}",
                    )

            except Exception as exc:
                logger.warning(f"Failed to parse search results: {exc}")

                if len(self.citation_tracker.sources) >= max_sources:
                    continue

                # Fallback: add the search itself as a source.
                source_id = self.citation_tracker.add_source(
                    title=f"Web Search: {query}",
                    type=SourceType.WEB,
                    author="DuckDuckGo",
                    description=(
                        observation[:200] + "..."
                        if len(observation) > 200
                        else observation
                    ),
                    metadata={"query": query},
                )

                self.citation_tracker.cite(
                    source_id=source_id,
                    quoted_text=observation[:500],
                    context=f"Search query: {query}",
                )

        logger.debug(f"Processed {len(intermediate_steps)} intermediate steps")

    def _extract_citations(
        self,
        intermediate_steps: List[tuple],
        max_sources: int = 5,
    ) -> List[Dict[str, Any]]:
        """Extract simple citation dicts from agent intermediate steps.

        Parses ``(action, observation)`` pairs and returns a list of dicts
        for every web_search action found.  Results are also appended to
        ``self.citations`` for later retrieval.

        Args:
            intermediate_steps: List of ``(AgentAction, observation)`` tuples.
            max_sources: Maximum number of citations to extract.

        Returns:
            List of citation dicts with ``query``, ``source``, ``timestamp``,
            and (when available) ``url`` keys.
        """
        extracted: List[Dict[str, Any]] = []

        for action, observation in intermediate_steps:
            if len(extracted) >= max_sources:
                break

            if not (hasattr(action, "tool") and action.tool == "web_search"):
                continue

            query = (
                action.tool_input
                if isinstance(action.tool_input, str)
                else action.tool_input.get("query", "")
            )

            entry: Dict[str, Any] = {
                "query": query,
                "source": "duckduckgo",
                "timestamp": datetime.utcnow().isoformat(),
            }

            # Try to pick up a URL from the observation text
            if isinstance(observation, str):
                import re
                urls = re.findall(r"https?://[^\s<>\"]+", observation)
                if urls:
                    entry["url"] = urls[0]

            extracted.append(entry)
            self._citations.append(entry)

        return extracted

    def get_citations(self, format: str = "apa") -> List[str]:
        """Get formatted citations.

        Combines citations from the simple ``self.citations`` list **and**
        the richer ``CitationTracker``, deduplicating by query/URL.

        Args:
            format: Citation format ("apa", "mla", "chicago")

        Returns:
            List of formatted citation strings
        """
        results: List[str] = []

        # Format simple citation dicts first
        for cit in self._citations:
            query = cit.get("query", "")
            ts = cit.get("timestamp", "")
            url = cit.get("url", "")
            source = cit.get("source", "web")

            if format.lower() == "mla":
                entry = f'"{query}." {source.capitalize()}. {ts[:10]}.'
                if url:
                    entry += f" Web. <{url}>."
            else:
                # APA / default
                entry = f"{source.capitalize()}. ({ts[:10]}). {query}."
                if url:
                    entry += f" Retrieved from {url}"

            results.append(entry)

        # Also append tracker-based bibliography if tracker has sources
        try:
            tracker_bib = self.citation_tracker.get_bibliography(
                style=format, sort_by="author"
            )
            # Only add tracker entries not already in results (simple de-dup)
            for bib_entry in tracker_bib:
                if bib_entry not in results:
                    results.append(bib_entry)
        except Exception:
            pass

        return results

    def get_citation_statistics(self) -> Dict[str, Any]:
        """Get citation statistics from tracker."""
        return self.citation_tracker.get_statistics()

    def get_validation_report(
        self,
        min_sources: int = 3,
        recency_window_days: int = 730,
        recency_profile: str = "balanced",
    ) -> Dict[str, Any]:
        """Get source validation confidence metrics for current research context."""
        return self.citation_tracker.get_validation_report(
            min_sources=min_sources,
            recency_window_days=recency_window_days,
            recency_profile=recency_profile,
        )

    def clear_citations(self):
        """Clear citation history (both simple list and tracker)."""
        self._citations.clear()
        self.citation_tracker.clear()
        logger.debug("Citations cleared")

    def get_all_sources(self) -> List[Any]:
        """
        Get all sources from the citation tracker.

        Returns:
            List of Source objects
        """
        return self.citation_tracker.get_all_sources()

    def add_manual_source(
        self,
        title: str,
        url: Optional[str] = None,
        author: Optional[str] = None,
        **kwargs,
    ) -> str:
        """
        Manually add a source to the citation tracker.

        Args:
            title: Source title
            url: Source URL
            author: Author name
            **kwargs: Additional source parameters

        Returns:
            Source ID
        """
        source_id = self.citation_tracker.add_source(
            title=title,
            url=url,
            author=author,
            **kwargs,
        )
        logger.info(f"Manually added source: {source_id}")
        return source_id


__all__ = ["ResearchAgent"]
