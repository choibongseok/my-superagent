"""Research Agent for web search and analysis."""

from typing import Any, Dict, List

from langchain.tools import Tool
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.agents.base import BaseAgent


class ResearchAgent(BaseAgent):
    """
    Agent for web research and information gathering.

    Features:
        - Web search (DuckDuckGo)
        - Content extraction
        - Source citation
        - Information synthesis
    """

    def _get_metadata(self) -> Dict[str, Any]:
        """Get agent metadata."""
        return {
            "agent_type": "research",
            "version": "1.0",
            "capabilities": ["web_search", "citation", "synthesis"],
        }

    def _create_tools(self) -> List[Tool]:
        """Create research tools."""
        # DuckDuckGo search tool
        search = DuckDuckGoSearchRun()

        tools = [
            Tool(
                name="web_search",
                func=search.run,
                description=(
                    "Useful for searching the web for current information. "
                    "Input should be a search query string. "
                    "Returns search results with titles and snippets."
                ),
            ),
        ]

        return tools

    def _create_prompt(self) -> ChatPromptTemplate:
        """Create research agent prompt."""
        system_message = """You are a professional research agent.

Your responsibilities:
1. Search the web for accurate, up-to-date information
2. Analyze and synthesize information from multiple sources
3. Provide citations for all claims
4. Present information in a clear, structured format

Guidelines:
- Always cite your sources with URLs
- Prioritize recent and authoritative sources
- Cross-reference information when possible
- Clearly distinguish facts from opinions
- Be transparent about information gaps

Output format:
- Key findings (bullet points)
- Detailed analysis
- Source citations (numbered list with URLs)
"""

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_message),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        return prompt


__all__ = ["ResearchAgent"]
