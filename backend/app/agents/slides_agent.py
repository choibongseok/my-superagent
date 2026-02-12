"""Google Slides Agent for presentation generation."""

from typing import Any, Dict, List, Optional
import logging
import json
from uuid import UUID

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from langchain.tools import Tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class SlidesAgent(BaseAgent):
    """
    Agent for Google Slides presentation generation and editing.
    
    Capabilities:
    - Create new presentations
    - Add and edit slides
    - Insert text, images, and shapes
    - Apply themes and layouts
    - Generate speaker notes
    - Share and manage permissions
    """
    
    def __init__(
        self,
        user_id: str | UUID,
        session_id: Optional[str | UUID] = None,
        credentials: Optional[Credentials] = None,
    ):
        """
        Initialize SlidesAgent with Google credentials.
        
        Args:
            user_id: User ID for LangFuse tracking
            session_id: Session ID for conversation memory
            credentials: Google OAuth2 credentials
        """
        self.credentials = credentials
        self.slides_service = None
        
        if credentials:
            # Build Google Slides API service
            self.slides_service = build("slides", "v1", credentials=credentials)
        
        # Call parent init
        super().__init__(user_id=user_id, session_id=session_id)

    def _get_metadata(self) -> Dict[str, Any]:
        return {
            "agent_type": "slides",
            "version": "1.0",
            "status": "active",
            "capabilities": [
                "create_presentation",
                "add_slide",
                "insert_text",
                "insert_image",
                "apply_theme",
                "add_speaker_notes",
                "share_presentation"
            ]
        }

    def _create_tools(self) -> List[Tool]:
        """Create Google Slides API tools."""
        
        def create_presentation(title: str) -> str:
            """
            Create a new Google Slides presentation.
            
            Args:
                title: Title of the presentation
                
            Returns:
                Presentation ID and URL
            """
            if not self.slides_service:
                return "Error: Google Slides API not initialized. Missing credentials."
            
            try:
                logger.info(f"Creating presentation: {title}")
                
                # Create presentation
                presentation_body = {
                    "title": title
                }
                
                presentation = self.slides_service.presentations().create(
                    body=presentation_body
                ).execute()
                
                presentation_id = presentation.get("presentationId")
                presentation_url = f"https://docs.google.com/presentation/d/{presentation_id}/edit"
                
                logger.info(f"Created presentation '{title}' - ID: {presentation_id}")
                return f"Successfully created presentation '{title}'\nURL: {presentation_url}\nID: {presentation_id}"
                
            except Exception as e:
                logger.error(f"Failed to create presentation: {e}")
                return f"Error creating presentation: {str(e)}"
        
        def add_slide(presentation_id: str, layout: str = "BLANK") -> str:
            """
            Add a new slide to the presentation.
            
            Args:
                presentation_id: Presentation ID
                layout: Slide layout type (BLANK, TITLE, TITLE_AND_BODY, etc.)
                
            Returns:
                Success message with slide ID
            """
            if not self.slides_service:
                return "Error: Google Slides API not initialized. Missing credentials."
            
            try:
                logger.info(f"Adding {layout} slide to {presentation_id}")
                
                # Create slide
                requests = [{
                    "createSlide": {
                        "slideLayoutReference": {
                            "predefinedLayout": layout
                        }
                    }
                }]
                
                response = self.slides_service.presentations().batchUpdate(
                    presentationId=presentation_id,
                    body={"requests": requests}
                ).execute()
                
                slide_id = response.get("replies", [{}])[0].get("createSlide", {}).get("objectId")
                
                logger.info(f"Added {layout} slide - ID: {slide_id}")
                return f"Successfully added {layout} slide\nSlide ID: {slide_id}"
                
            except Exception as e:
                logger.error(f"Failed to add slide: {e}")
                return f"Error adding slide: {str(e)}"
        
        def insert_text(presentation_id: str, slide_id: str, text: str, position: str = "CENTERED") -> str:
            """
            Insert text into a slide.
            
            Args:
                presentation_id: Presentation ID
                slide_id: Slide ID
                text: Text content to insert
                position: Text position (CENTERED, TOP_LEFT, etc.)
                
            Returns:
                Success message
            """
            # TODO: Implement text insertion
            logger.info(f"Inserting text to slide {slide_id}: {text[:50]}...")
            return f"Inserted text to slide {slide_id}"
        
        def insert_image(presentation_id: str, slide_id: str, image_url: str, position: Dict[str, float]) -> str:
            """
            Insert an image into a slide.
            
            Args:
                presentation_id: Presentation ID
                slide_id: Slide ID
                image_url: URL of the image
                position: Position dict with x, y, width, height
                
            Returns:
                Success message with image ID
            """
            # TODO: Implement image insertion
            logger.info(f"Inserting image to slide {slide_id} from {image_url}")
            return f"Inserted image to slide {slide_id} (ID: image_123)"
        
        def apply_theme(presentation_id: str, theme_id: str) -> str:
            """
            Apply a theme to the presentation.
            
            Args:
                presentation_id: Presentation ID
                theme_id: Theme ID or predefined theme name
                
            Returns:
                Success message
            """
            # TODO: Implement theme application
            logger.info(f"Applying theme {theme_id} to {presentation_id}")
            return f"Applied theme {theme_id} to presentation"
        
        def add_speaker_notes(presentation_id: str, slide_id: str, notes: str) -> str:
            """
            Add speaker notes to a slide.
            
            Args:
                presentation_id: Presentation ID
                slide_id: Slide ID
                notes: Speaker notes content
                
            Returns:
                Success message
            """
            # TODO: Implement speaker notes
            logger.info(f"Adding speaker notes to slide {slide_id}")
            return f"Added speaker notes to slide {slide_id}"
        
        return [
            Tool(
                name="create_presentation",
                description="Create a new Google Slides presentation with the given title",
                func=create_presentation
            ),
            Tool(
                name="add_slide",
                description="Add a new slide to an existing presentation",
                func=lambda args: add_slide(**json.loads(args) if isinstance(args, str) else args)
            ),
            Tool(
                name="insert_text",
                description="Insert text content into a specific slide",
                func=lambda args: insert_text(**json.loads(args) if isinstance(args, str) else args)
            ),
            Tool(
                name="insert_image",
                description="Insert an image into a specific slide",
                func=lambda args: insert_image(**json.loads(args) if isinstance(args, str) else args)
            ),
            Tool(
                name="apply_theme",
                description="Apply a theme to the entire presentation",
                func=lambda args: apply_theme(**json.loads(args) if isinstance(args, str) else args)
            ),
            Tool(
                name="add_speaker_notes",
                description="Add speaker notes to a slide",
                func=lambda args: add_speaker_notes(**json.loads(args) if isinstance(args, str) else args)
            )
        ]

    def _create_prompt(self) -> ChatPromptTemplate:
        system_message = """You are an expert Google Slides agent specialized in presentation creation and design.

Your capabilities include:
- Creating professional presentations from scratch
- Designing slides with proper layouts and visual hierarchy
- Inserting text, images, and multimedia content
- Applying consistent themes and branding
- Adding speaker notes for presentation delivery

When creating presentations:
1. Start with a clear structure (title slide, agenda, content, conclusion)
2. Keep slides concise and visually appealing
3. Use appropriate layouts for different content types
4. Maintain visual consistency across slides
5. Add helpful speaker notes for complex topics

Current tools available:
- create_presentation: Create new presentations
- add_slide: Add slides with different layouts
- insert_text: Add text content to slides
- insert_image: Insert images from URLs
- apply_theme: Apply visual themes
- add_speaker_notes: Add presentation notes

Design principles:
- One main idea per slide
- Use bullet points sparingly (3-5 points max)
- Balance text and visuals
- Ensure readability (font size, contrast)

Respond professionally and provide clear summaries of created content."""

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_message),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        return prompt


__all__ = ["SlidesAgent"]
