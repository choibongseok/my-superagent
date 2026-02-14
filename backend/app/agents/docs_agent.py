"""Docs Agent for Google Docs creation with integrated research."""

import logging
import math
import re
from typing import Any, Dict, List, Optional

from google.oauth2.credentials import Credentials
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import BaseTool

from app.agents.base import BaseAgent
from app.agents.research_agent import ResearchAgent
from app.tools.google_apis import GoogleDocsAPI

logger = logging.getLogger(__name__)


class DocsAgent(BaseAgent):
    """
    Agent for Google Docs creation with integrated research capabilities.

    Automatically enriches generated content with a lightweight outline and
    readability metrics so downstream consumers can render structured previews.

    Features:
        - Create structured documents
        - Integrate research findings
        - Apply formatting and styling
        - Include citations and sources
        - Use ResearchAgent for content gathering

    Usage:
        agent = DocsAgent(
            user_id="user123",
            credentials=google_credentials,
        )
        result = await agent.create_document(
            title="AI Report 2024",
            prompt="Create a comprehensive report on AI developments in 2024",
        )
    """

    MARKDOWN_HEADING_PATTERN = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$")
    NUMBERED_HEADING_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)*)[.)]?\s+(.+?)\s*$")

    def __init__(
        self,
        user_id: str,
        credentials: Optional[Credentials] = None,
        session_id: Optional[str] = None,
        **kwargs,
    ):
        """
        Initialize Docs Agent.

        Args:
            user_id: User identifier
            credentials: Google OAuth2 credentials
            session_id: Session identifier
            **kwargs: Additional BaseAgent parameters
        """
        super().__init__(
            user_id=user_id,
            session_id=session_id or f"docs_{user_id}",
            credentials=credentials,
            **kwargs,
        )

        # Google Docs API
        self.docs_api = GoogleDocsAPI(self.credentials) if self.credentials else None

        # Research agent for content gathering
        self.research_agent = ResearchAgent(
            user_id=user_id,
            session_id=f"{self.session_id}_research",
        )

        logger.info(f"DocsAgent initialized for user {user_id}")

    def _get_metadata(self) -> Dict[str, Any]:
        """Get agent metadata for tracking."""
        return {
            "agent_type": "docs",
            "version": "1.0",
            "capabilities": [
                "document_creation",
                "research_integration",
                "citation_management",
                "formatting",
            ],
        }

    def _create_tools(self) -> List[BaseTool]:
        """Create docs agent tools."""
        # DocsAgent uses ResearchAgent's tools indirectly
        # Could add document-specific tools here
        tools = []

        logger.debug(f"Created {len(tools)} tools for DocsAgent")
        return tools

    def _create_prompt(self) -> ChatPromptTemplate:
        """Create docs agent prompt template."""
        system_message = """You are a professional document creation agent specialized in structured report writing.

Your responsibilities:
1. Create well-structured, professional documents
2. Integrate research findings effectively
3. Use proper formatting and organization
4. Include citations and sources
5. Maintain clarity and readability

Document Structure:
- Title and introduction
- Main sections with headers
- Supporting evidence and citations
- Conclusion
- References/Sources section

Guidelines:
- Use clear, professional language
- Structure content logically
- Support claims with evidence
- Include proper citations
- Format for readability

When given a document creation task:
1. Break down the requirements
2. Identify research needs
3. Organize content structure
4. Draft sections systematically
5. Include proper citations
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

    def _extract_outline(self, content: str) -> List[Dict[str, Any]]:
        """Extract a structured outline from markdown/numbered headings."""
        outline: List[Dict[str, Any]] = []

        for line in content.splitlines():
            markdown_match = self.MARKDOWN_HEADING_PATTERN.match(line)
            if markdown_match:
                heading_level = len(markdown_match.group(1))
                heading_title = markdown_match.group(2).strip().rstrip("#").strip()
                if heading_title:
                    outline.append({"level": heading_level, "title": heading_title})
                continue

            numbered_match = self.NUMBERED_HEADING_PATTERN.match(line)
            if numbered_match:
                section_number = numbered_match.group(1)
                heading_title = numbered_match.group(2).strip()
                if heading_title:
                    outline.append(
                        {
                            "level": section_number.count(".") + 1,
                            "title": heading_title,
                            "section": section_number,
                        }
                    )

        return outline

    def _build_content_metrics(self, content: str) -> Dict[str, Any]:
        """Build lightweight readability metrics for generated content."""
        words = re.findall(r"\b\w+\b", content)
        non_empty_lines = [line for line in content.splitlines() if line.strip()]
        outline = self._extract_outline(content)

        word_count = len(words)

        return {
            "character_count": len(content),
            "word_count": word_count,
            "line_count": len(non_empty_lines),
            "heading_count": len(outline),
            "estimated_read_time_minutes": (
                math.ceil(word_count / 200) if word_count > 0 else 0
            ),
        }

    async def create_document(
        self,
        title: str,
        prompt: str,
        include_research: bool = True,
    ) -> Dict[str, Any]:
        """
        Create a Google Doc with optional research integration.

        Args:
            title: Document title
            prompt: Content creation prompt/requirements
            include_research: Whether to gather research before writing

        Returns:
            Result dictionary with content, optional document metadata,
            extracted outline, and readability metrics.
        """
        logger.info(f"Creating document: {title}")

        try:
            # Step 1: Gather research if requested
            research_results = None
            if include_research:
                logger.debug("Gathering research for document")
                research_results = await self.research_agent.research(prompt)

                if not research_results["success"]:
                    logger.warning("Research failed, proceeding without research data")
                    research_results = None

            # Step 2: Generate document content
            content_prompt = self._build_content_prompt(
                title=title,
                prompt=prompt,
                research=research_results,
            )

            generation_result = await self.run(content_prompt)

            if not generation_result["success"]:
                logger.error(
                    f"Content generation failed: {generation_result.get('error')}"
                )
                return generation_result

            content = generation_result["output"]
            outline = self._extract_outline(content)
            content_metrics = self._build_content_metrics(content)

            # Step 3: Create Google Doc
            if not self.docs_api:
                logger.warning("Google Docs API not configured, returning content only")
                return {
                    "content": content,
                    "outline": outline,
                    "content_metrics": content_metrics,
                    "citations": research_results.get("citations", [])
                    if research_results
                    else [],
                    "success": True,
                }

            # Create document
            doc_id = self.docs_api.create_document(title)

            # Insert content
            self.docs_api.insert_text(doc_id, content)

            # Get document URL
            doc_url = self.docs_api.get_document_url(doc_id)

            logger.info(f"Document created successfully: {doc_url}")

            return {
                "document_id": doc_id,
                "document_url": doc_url,
                "content": content,
                "outline": outline,
                "content_metrics": content_metrics,
                "citations": research_results.get("citations", [])
                if research_results
                else [],
                "success": True,
            }

        except Exception as e:
            logger.error(f"Document creation failed: {e}", exc_info=True)
            return {
                "error": str(e),
                "success": False,
            }

    def _build_content_prompt(
        self,
        title: str,
        prompt: str,
        research: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Build content generation prompt with research context.

        Args:
            title: Document title
            prompt: Original user prompt
            research: Research results (if available)

        Returns:
            Enhanced prompt with research context
        """
        content_prompt = f"""Create a professional document with the following details:

Title: {title}

Requirements:
{prompt}
"""

        if research and research.get("success"):
            content_prompt += f"""

Research Findings:
{research.get('output', '')}

Please integrate the above research findings into the document and include proper citations.
"""

        return content_prompt


__all__ = ["DocsAgent"]
