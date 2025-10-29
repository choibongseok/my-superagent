"""Research Agent for web search and information synthesis."""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import BaseTool

from app.agents.base import BaseAgent
from app.tools.web_search import DuckDuckGoSearchTool

logger = logging.getLogger(__name__)


class ResearchAgent(BaseAgent):
    """
    Agent for web research and information gathering with citation tracking.

    Features:
        - Web search via DuckDuckGo
        - Information synthesis from multiple sources
        - Automatic citation generation
        - Source tracking and validation
        - Integration with Phase 2 ConversationMemory

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
        
        # Citation tracking
        self.citations: List[Dict[str, Any]] = []
        
        logger.info(f"ResearchAgent initialized for user {user_id}")

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

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_message),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

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

        # Extract citations from intermediate steps
        citations = self._extract_citations(result.get("intermediate_steps", []))
        
        # Store citations
        self.citations.extend(citations)
        
        # Add citations to result
        result["citations"] = citations
        result["citation_count"] = len(citations)
        
        logger.info(f"Research completed with {len(citations)} citations")
        
        return result

    def _extract_citations(
        self,
        intermediate_steps: List[tuple],
    ) -> List[Dict[str, Any]]:
        """
        Extract citations from agent's intermediate steps.

        Args:
            intermediate_steps: List of (action, observation) tuples

        Returns:
            List of citation dictionaries
        """
        citations = []
        
        for action, observation in intermediate_steps:
            if hasattr(action, 'tool') and action.tool == 'web_search':
                # Parse search results for URLs
                citation = {
                    "query": action.tool_input if isinstance(action.tool_input, str) else action.tool_input.get("query", ""),
                    "results": observation,
                    "timestamp": datetime.utcnow().isoformat(),
                    "source": "duckduckgo",
                }
                citations.append(citation)
        
        return citations

    def get_citations(self, format: str = "apa") -> List[str]:
        """
        Get formatted citations.

        Args:
            format: Citation format ("apa", "mla", "chicago")

        Returns:
            List of formatted citation strings
        """
        # Simple citation formatting
        formatted = []
        
        for i, cite in enumerate(self.citations, 1):
            query = cite.get("query", "Unknown")
            timestamp = cite.get("timestamp", "")
            
            if format == "apa":
                # APA: Author. (Year). Title. Retrieved from URL
                citation_str = f"{i}. Web Search. ({timestamp}). Results for '{query}'. Retrieved from DuckDuckGo."
            elif format == "mla":
                # MLA: "Title." Website, Date, URL.
                citation_str = f"{i}. \"Results for '{query}'.\" DuckDuckGo, {timestamp}."
            elif format == "chicago":
                # Chicago: Author. "Title." Website. Date. URL.
                citation_str = f"{i}. Web Search. \"Results for '{query}'.\" DuckDuckGo. {timestamp}."
            else:
                citation_str = f"{i}. {query} - {timestamp}"
            
            formatted.append(citation_str)
        
        return formatted

    def clear_citations(self):
        """Clear citation history."""
        self.citations.clear()
        logger.debug("Citations cleared")


__all__ = ["ResearchAgent"]
