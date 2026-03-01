"""Docs Agent for Google Docs creation with integrated research."""

import logging
from typing import Any, Dict, List, Optional

from google.oauth2.credentials import Credentials
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.agents.research_agent import ResearchAgent
from app.tools.google_apis import GoogleDocsAPI

logger = logging.getLogger(__name__)


# Tool input schemas
class FormattingInput(BaseModel):
    """Input for text formatting."""
    document_id: str = Field(description="Document ID")
    start_index: int = Field(description="Start position")
    end_index: int = Field(description="End position")
    bold: Optional[bool] = Field(None, description="Make text bold")
    italic: Optional[bool] = Field(None, description="Make text italic")
    underline: Optional[bool] = Field(None, description="Underline text")
    font_size: Optional[int] = Field(None, description="Font size in points")


class StyleInput(BaseModel):
    """Input for applying named styles."""
    document_id: str = Field(description="Document ID")
    start_index: int = Field(description="Start position")
    end_index: int = Field(description="End position")
    style_name: str = Field(
        description="Style name (HEADING_1, HEADING_2, HEADING_3, TITLE, SUBTITLE, NORMAL_TEXT)"
    )


class TableInput(BaseModel):
    """Input for table insertion."""
    document_id: str = Field(description="Document ID")
    rows: int = Field(description="Number of rows")
    columns: int = Field(description="Number of columns")
    index: int = Field(description="Insert position")
    data: Optional[List[List[str]]] = Field(None, description="2D list of cell data")


class ImageInput(BaseModel):
    """Input for image insertion."""
    document_id: str = Field(description="Document ID")
    image_url: str = Field(description="Publicly accessible image URL")
    index: int = Field(description="Insert position")
    width: Optional[int] = Field(None, description="Width in points")
    height: Optional[int] = Field(None, description="Height in points")


class PageBreakInput(BaseModel):
    """Input for page break insertion."""
    document_id: str = Field(description="Document ID")
    index: int = Field(description="Insert position")


class BulletListInput(BaseModel):
    """Input for bullet list creation."""
    document_id: str = Field(description="Document ID")
    start_index: int = Field(description="Start position")
    end_index: int = Field(description="End position")
    bullet_preset: Optional[str] = Field(
        "BULLET_DISC_CIRCLE_SQUARE",
        description="Bullet style preset"
    )


class DocsAgent(BaseAgent):
    """
    Agent for Google Docs creation with integrated research capabilities.

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
            **kwargs,
        )
        
        # Google Docs API
        self.credentials = credentials
        self.docs_api = GoogleDocsAPI(credentials) if credentials else None
        
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
            "version": "2.0",
            "capabilities": [
                "document_creation",
                "research_integration",
                "citation_management",
                "advanced_formatting",
                "text_styling",
                "table_insertion",
                "image_insertion",
                "bullet_lists",
                "page_breaks",
                "named_styles",
            ],
        }

    def _create_tools(self) -> List[BaseTool]:
        """Create docs agent tools."""
        if not self.docs_api:
            logger.warning("Google Docs API not configured, no tools available")
            return []
        
        tools = [
            StructuredTool.from_function(
                func=self._apply_formatting_tool,
                name="apply_text_formatting",
                description="Apply text formatting (bold, italic, underline, font size, color) to a text range",
                args_schema=FormattingInput,
            ),
            StructuredTool.from_function(
                func=self._apply_style_tool,
                name="apply_paragraph_style",
                description="Apply named paragraph style (HEADING_1, HEADING_2, HEADING_3, TITLE, SUBTITLE, NORMAL_TEXT)",
                args_schema=StyleInput,
            ),
            StructuredTool.from_function(
                func=self._insert_table_tool,
                name="insert_table",
                description="Insert a table with optional data",
                args_schema=TableInput,
            ),
            StructuredTool.from_function(
                func=self._insert_image_tool,
                name="insert_image",
                description="Insert an image from a URL",
                args_schema=ImageInput,
            ),
            StructuredTool.from_function(
                func=self._insert_page_break_tool,
                name="insert_page_break",
                description="Insert a page break",
                args_schema=PageBreakInput,
            ),
            StructuredTool.from_function(
                func=self._create_bullet_list_tool,
                name="create_bullet_list",
                description="Convert paragraphs to a bulleted list",
                args_schema=BulletListInput,
            ),
        ]
        
        logger.debug(f"Created {len(tools)} tools for DocsAgent")
        return tools
    
    # Tool wrapper methods
    def _apply_formatting_tool(
        self,
        document_id: str,
        start_index: int,
        end_index: int,
        bold: Optional[bool] = None,
        italic: Optional[bool] = None,
        underline: Optional[bool] = None,
        font_size: Optional[int] = None,
    ) -> str:
        """Apply text formatting."""
        try:
            self.docs_api.apply_formatting(
                document_id=document_id,
                start_index=start_index,
                end_index=end_index,
                bold=bold,
                italic=italic,
                underline=underline,
                font_size=font_size,
            )
            return f"Applied formatting to range {start_index}-{end_index}"
        except Exception as e:
            return f"Error applying formatting: {str(e)}"
    
    def _apply_style_tool(
        self,
        document_id: str,
        start_index: int,
        end_index: int,
        style_name: str,
    ) -> str:
        """Apply named paragraph style."""
        try:
            self.docs_api.apply_named_style(
                document_id=document_id,
                start_index=start_index,
                end_index=end_index,
                style_name=style_name,
            )
            return f"Applied {style_name} to range {start_index}-{end_index}"
        except Exception as e:
            return f"Error applying style: {str(e)}"
    
    def _insert_table_tool(
        self,
        document_id: str,
        rows: int,
        columns: int,
        index: int,
        data: Optional[List[List[str]]] = None,
    ) -> str:
        """Insert a table."""
        try:
            self.docs_api.insert_table(
                document_id=document_id,
                rows=rows,
                columns=columns,
                index=index,
                data=data,
            )
            return f"Inserted {rows}x{columns} table at index {index}"
        except Exception as e:
            return f"Error inserting table: {str(e)}"
    
    def _insert_image_tool(
        self,
        document_id: str,
        image_url: str,
        index: int,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> str:
        """Insert an image."""
        try:
            self.docs_api.insert_image(
                document_id=document_id,
                image_url=image_url,
                index=index,
                width=width,
                height=height,
            )
            return f"Inserted image at index {index}"
        except Exception as e:
            return f"Error inserting image: {str(e)}"
    
    def _insert_page_break_tool(
        self,
        document_id: str,
        index: int,
    ) -> str:
        """Insert a page break."""
        try:
            self.docs_api.insert_page_break(
                document_id=document_id,
                index=index,
            )
            return f"Inserted page break at index {index}"
        except Exception as e:
            return f"Error inserting page break: {str(e)}"
    
    def _create_bullet_list_tool(
        self,
        document_id: str,
        start_index: int,
        end_index: int,
        bullet_preset: str = "BULLET_DISC_CIRCLE_SQUARE",
    ) -> str:
        """Create a bullet list."""
        try:
            self.docs_api.create_bullet_list(
                document_id=document_id,
                start_index=start_index,
                end_index=end_index,
                bullet_preset=bullet_preset,
            )
            return f"Created bullet list for range {start_index}-{end_index}"
        except Exception as e:
            return f"Error creating bullet list: {str(e)}"

    def _create_prompt(self) -> ChatPromptTemplate:
        """Create docs agent prompt template."""
        system_message = """You are a professional document creation agent specialized in structured report writing with advanced formatting capabilities.

Your responsibilities:
1. Create well-structured, professional documents
2. Integrate research findings effectively
3. Use proper formatting and organization
4. Include citations and sources
5. Maintain clarity and readability
6. Apply appropriate visual styling

Document Structure:
- Title and introduction (use TITLE and HEADING_1 styles)
- Main sections with headers (use HEADING_2, HEADING_3)
- Supporting evidence and citations
- Tables for data presentation
- Images where appropriate
- Conclusion
- References/Sources section

Available Tools for Advanced Formatting:
1. apply_text_formatting - Make text bold, italic, underlined, or change font size
2. apply_paragraph_style - Apply heading styles (HEADING_1, HEADING_2, HEADING_3, TITLE, SUBTITLE, NORMAL_TEXT)
3. insert_table - Create tables with data (great for comparisons, data, lists)
4. insert_image - Add images from URLs (diagrams, charts, illustrations)
5. insert_page_break - Start new pages for major sections
6. create_bullet_list - Convert paragraphs to bulleted lists

Formatting Guidelines:
- Use TITLE style for document title
- Use HEADING_1 for major sections
- Use HEADING_2 for subsections
- Use HEADING_3 for minor sections
- Make key terms bold for emphasis
- Use tables for structured data (comparisons, statistics, timelines)
- Add images to illustrate concepts (when URLs available)
- Use bullet lists for key points
- Insert page breaks between major sections in long documents

When given a document creation task:
1. Break down the requirements
2. Plan document structure (outline with headings)
3. Identify research needs
4. Draft content with appropriate formatting
5. Add tables/images where beneficial
6. Include proper citations
7. Review for professional appearance

Example Workflow:
1. Create document with title
2. Insert title text and apply TITLE style
3. Add section headers with HEADING_1/HEADING_2 styles
4. Insert content paragraphs
5. Make important terms bold
6. Add tables for data
7. Insert images for visual appeal
8. Create bullet lists for key takeaways
9. Add page breaks for major sections
"""

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_message),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        return prompt

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
            Result dictionary with document_id, url, and content
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
                logger.error(f"Content generation failed: {generation_result.get('error')}")
                return generation_result

            content = generation_result["output"]

            # Step 3: Create Google Doc
            if not self.docs_api:
                logger.warning("Google Docs API not configured, returning content only")
                return {
                    "content": content,
                    "citations": research_results.get("citations", []) if research_results else [],
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
                "citations": research_results.get("citations", []) if research_results else [],
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
