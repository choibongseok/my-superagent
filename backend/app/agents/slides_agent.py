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
        # Call parent init first so base fields (including credentials) are consistent.
        super().__init__(
            user_id=str(user_id),
            session_id=str(session_id) if session_id is not None else None,
            credentials=credentials,
        )

        self.slides_service = None
        if self.credentials:
            # Build Google Slides API service
            self.slides_service = build("slides", "v1", credentials=self.credentials)

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
                position: Text position (CENTERED, TOP_LEFT, BOTTOM_RIGHT, etc.)
                
            Returns:
                Success message with text box ID
            """
            if not self.slides_service:
                return "Error: Google Slides API not initialized. Missing credentials."
            
            try:
                logger.info(f"Inserting text to slide {slide_id}: {text[:50]}...")
                
                # Get presentation to determine dimensions
                presentation = self.slides_service.presentations().get(
                    presentationId=presentation_id
                ).execute()
                
                page_width = presentation.get('pageSize', {}).get('width', {}).get('magnitude', 720)
                page_height = presentation.get('pageSize', {}).get('height', {}).get('magnitude', 540)
                
                # Define text box dimensions and position based on position parameter
                box_width = page_width * 0.8
                box_height = page_height * 0.3
                
                if position == "CENTERED":
                    x = (page_width - box_width) / 2
                    y = (page_height - box_height) / 2
                elif position == "TOP_LEFT":
                    x = page_width * 0.05
                    y = page_height * 0.05
                elif position == "TOP_CENTER":
                    x = (page_width - box_width) / 2
                    y = page_height * 0.05
                elif position == "BOTTOM_RIGHT":
                    x = page_width - box_width - (page_width * 0.05)
                    y = page_height - box_height - (page_height * 0.05)
                else:
                    # Default to centered
                    x = (page_width - box_width) / 2
                    y = (page_height - box_height) / 2
                
                # Create text box with text
                text_box_id = f"textbox_{slide_id}_{hash(text) % 10000}"
                
                requests = [
                    {
                        "createShape": {
                            "objectId": text_box_id,
                            "shapeType": "TEXT_BOX",
                            "elementProperties": {
                                "pageObjectId": slide_id,
                                "size": {
                                    "width": {"magnitude": box_width, "unit": "PT"},
                                    "height": {"magnitude": box_height, "unit": "PT"}
                                },
                                "transform": {
                                    "scaleX": 1,
                                    "scaleY": 1,
                                    "translateX": x,
                                    "translateY": y,
                                    "unit": "PT"
                                }
                            }
                        }
                    },
                    {
                        "insertText": {
                            "objectId": text_box_id,
                            "text": text
                        }
                    }
                ]
                
                # Execute requests
                response = self.slides_service.presentations().batchUpdate(
                    presentationId=presentation_id,
                    body={"requests": requests}
                ).execute()
                
                logger.info(f"Inserted text to slide {slide_id} - Text box ID: {text_box_id}")
                return f"Successfully inserted text to slide {slide_id}\nText box ID: {text_box_id}"
                
            except Exception as e:
                logger.error(f"Failed to insert text: {e}")
                return f"Error inserting text: {str(e)}"
        
        def insert_image(presentation_id: str, slide_id: str, image_url: str, position: Dict[str, float] = None) -> str:
            """
            Insert an image into a slide.
            
            Args:
                presentation_id: Presentation ID
                slide_id: Slide ID
                image_url: URL of the image (must be publicly accessible)
                position: Position dict with x, y, width, height (optional, defaults to centered)
                
            Returns:
                Success message with image ID
            """
            if not self.slides_service:
                return "Error: Google Slides API not initialized. Missing credentials."
            
            try:
                logger.info(f"Inserting image to slide {slide_id} from {image_url}")
                
                # Get presentation dimensions
                presentation = self.slides_service.presentations().get(
                    presentationId=presentation_id
                ).execute()
                
                page_width = presentation.get('pageSize', {}).get('width', {}).get('magnitude', 720)
                page_height = presentation.get('pageSize', {}).get('height', {}).get('magnitude', 540)
                
                # Set default position if not provided
                if position is None:
                    # Center image with 60% of page width
                    img_width = page_width * 0.6
                    img_height = page_height * 0.6
                    x = (page_width - img_width) / 2
                    y = (page_height - img_height) / 2
                else:
                    x = position.get('x', 0)
                    y = position.get('y', 0)
                    img_width = position.get('width', page_width * 0.5)
                    img_height = position.get('height', page_height * 0.5)
                
                # Create image ID
                image_id = f"image_{slide_id}_{hash(image_url) % 10000}"
                
                # Create image insertion request
                requests = [{
                    "createImage": {
                        "objectId": image_id,
                        "url": image_url,
                        "elementProperties": {
                            "pageObjectId": slide_id,
                            "size": {
                                "width": {"magnitude": img_width, "unit": "PT"},
                                "height": {"magnitude": img_height, "unit": "PT"}
                            },
                            "transform": {
                                "scaleX": 1,
                                "scaleY": 1,
                                "translateX": x,
                                "translateY": y,
                                "unit": "PT"
                            }
                        }
                    }
                }]
                
                # Execute request
                response = self.slides_service.presentations().batchUpdate(
                    presentationId=presentation_id,
                    body={"requests": requests}
                ).execute()
                
                logger.info(f"Inserted image to slide {slide_id} - Image ID: {image_id}")
                return f"Successfully inserted image to slide {slide_id}\nImage ID: {image_id}\nSource: {image_url}"
                
            except Exception as e:
                logger.error(f"Failed to insert image: {e}")
                return f"Error inserting image: {str(e)}"
        
        def apply_theme(presentation_id: str, theme_id: str) -> str:
            """
            Apply a theme to the presentation.
            
            Args:
                presentation_id: Presentation ID
                theme_id: Theme color (e.g., 'blue', 'red', 'green') or hex color
                
            Returns:
                Success message
            """
            if not self.slides_service:
                return "Error: Google Slides API not initialized. Missing credentials."
            
            try:
                logger.info(f"Applying theme {theme_id} to {presentation_id}")
                
                # Map theme names to colors
                theme_colors = {
                    'blue': {'red': 0.0, 'green': 0.5, 'blue': 1.0},
                    'red': {'red': 1.0, 'green': 0.0, 'blue': 0.0},
                    'green': {'red': 0.0, 'green': 0.8, 'blue': 0.0},
                    'purple': {'red': 0.6, 'green': 0.0, 'blue': 0.8},
                    'orange': {'red': 1.0, 'green': 0.5, 'blue': 0.0},
                    'teal': {'red': 0.0, 'green': 0.7, 'blue': 0.7},
                }
                
                # Get color
                color = theme_colors.get(theme_id.lower(), theme_colors['blue'])
                
                # Get all slides
                presentation = self.slides_service.presentations().get(
                    presentationId=presentation_id
                ).execute()
                
                requests = []
                
                # Apply background color to all slides
                for slide in presentation.get('slides', []):
                    slide_id = slide.get('objectId')
                    requests.append({
                        "updatePageProperties": {
                            "objectId": slide_id,
                            "pageProperties": {
                                "pageBackgroundFill": {
                                    "solidFill": {
                                        "color": {
                                            "rgbColor": color
                                        },
                                        "alpha": 0.2  # Light theme
                                    }
                                }
                            },
                            "fields": "pageBackgroundFill.solidFill"
                        }
                    })
                
                # Execute theme application
                if requests:
                    self.slides_service.presentations().batchUpdate(
                        presentationId=presentation_id,
                        body={"requests": requests}
                    ).execute()
                
                logger.info(f"Applied {theme_id} theme to presentation {presentation_id}")
                return f"Successfully applied {theme_id} theme to presentation"
                
            except Exception as e:
                logger.error(f"Failed to apply theme: {e}")
                return f"Error applying theme: {str(e)}"
        
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
            if not self.slides_service:
                return "Error: Google Slides API not initialized. Missing credentials."
            
            try:
                logger.info(f"Adding speaker notes to slide {slide_id}")
                
                # Get the slide to find notes page
                presentation = self.slides_service.presentations().get(
                    presentationId=presentation_id
                ).execute()
                
                # Find the slide
                slide = None
                for s in presentation.get('slides', []):
                    if s.get('objectId') == slide_id:
                        slide = s
                        break
                
                if not slide:
                    return f"Error: Slide {slide_id} not found"
                
                # Get notes page object ID
                notes_page = slide.get('slideProperties', {}).get('notesPage', {})
                notes_page_id = notes_page.get('objectId')
                
                if not notes_page_id:
                    return f"Error: Notes page not found for slide {slide_id}"
                
                # Find the notes shape (usually the second shape after the slide thumbnail)
                notes_shape_id = None
                for element in notes_page.get('pageElements', []):
                    shape = element.get('shape', {})
                    if shape.get('shapeType') == 'TEXT_BOX':
                        # This is likely the notes text box
                        notes_shape_id = element.get('objectId')
                        break
                
                if not notes_shape_id:
                    # Create a new text box for notes
                    notes_shape_id = f"notes_{slide_id}"
                    requests = [{
                        "createShape": {
                            "objectId": notes_shape_id,
                            "shapeType": "TEXT_BOX",
                            "elementProperties": {
                                "pageObjectId": notes_page_id,
                                "size": {
                                    "width": {"magnitude": 600, "unit": "PT"},
                                    "height": {"magnitude": 200, "unit": "PT"}
                                },
                                "transform": {
                                    "scaleX": 1,
                                    "scaleY": 1,
                                    "translateX": 60,
                                    "translateY": 350,
                                    "unit": "PT"
                                }
                            }
                        }
                    }]
                    
                    self.slides_service.presentations().batchUpdate(
                        presentationId=presentation_id,
                        body={"requests": requests}
                    ).execute()
                
                # Insert text into notes
                requests = [{
                    "insertText": {
                        "objectId": notes_shape_id,
                        "text": notes,
                        "insertionIndex": 0
                    }
                }]
                
                self.slides_service.presentations().batchUpdate(
                    presentationId=presentation_id,
                    body={"requests": requests}
                ).execute()
                
                logger.info(f"Added speaker notes to slide {slide_id}")
                return f"Successfully added speaker notes to slide {slide_id}"
                
            except Exception as e:
                logger.error(f"Failed to add speaker notes: {e}")
                return f"Error adding speaker notes: {str(e)}"
        
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
