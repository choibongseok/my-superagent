"""Google Workspace API tools for document creation and manipulation."""

import logging
from typing import Dict, Any, Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


class GoogleDocsAPI:
    """
    Google Docs API wrapper for document creation and editing.

    Features:
        - Create new documents
        - Insert text content
        - Apply formatting
        - Get document content

    Usage:
        api = GoogleDocsAPI(credentials)
        doc_id = api.create_document("My Report")
        api.insert_text(doc_id, "Content here")
    """

    def __init__(self, credentials: Credentials):
        """
        Initialize Google Docs API client.

        Args:
            credentials: OAuth2 credentials
        """
        self.credentials = credentials
        self.service = build('docs', 'v1', credentials=credentials)
        logger.debug("Google Docs API client initialized")

    def create_document(self, title: str) -> str:
        """
        Create a new Google Doc.

        Args:
            title: Document title

        Returns:
            Document ID

        Raises:
            HttpError: If document creation fails
        """
        try:
            document = {
                'title': title
            }
            
            doc = self.service.documents().create(body=document).execute()
            doc_id = doc.get('documentId')
            
            logger.info(f"Created document '{title}' with ID: {doc_id}")
            return doc_id
        
        except HttpError as e:
            logger.error(f"Failed to create document: {e}")
            raise

    def insert_text(
        self,
        document_id: str,
        text: str,
        index: int = 1,
    ) -> Dict[str, Any]:
        """
        Insert text into document.

        Args:
            document_id: Target document ID
            text: Text content to insert
            index: Insert position (default: 1, start of document)

        Returns:
            API response dictionary

        Raises:
            HttpError: If insertion fails
        """
        try:
            requests = [
                {
                    'insertText': {
                        'location': {
                            'index': index,
                        },
                        'text': text,
                    }
                }
            ]

            result = self.service.documents().batchUpdate(
                documentId=document_id,
                body={'requests': requests}
            ).execute()

            logger.debug(f"Inserted {len(text)} characters into document {document_id}")
            return result
        
        except HttpError as e:
            logger.error(f"Failed to insert text: {e}")
            raise

    def get_document(self, document_id: str) -> Dict[str, Any]:
        """
        Get document content and metadata.

        Args:
            document_id: Document ID

        Returns:
            Document data dictionary

        Raises:
            HttpError: If retrieval fails
        """
        try:
            document = self.service.documents().get(
                documentId=document_id
            ).execute()
            
            logger.debug(f"Retrieved document {document_id}")
            return document
        
        except HttpError as e:
            logger.error(f"Failed to get document: {e}")
            raise

    def get_document_url(self, document_id: str) -> str:
        """
        Get shareable URL for document.

        Args:
            document_id: Document ID

        Returns:
            Document URL
        """
        return f"https://docs.google.com/document/d/{document_id}/edit"

    def apply_formatting(
        self,
        document_id: str,
        start_index: int,
        end_index: int,
        bold: Optional[bool] = None,
        italic: Optional[bool] = None,
        underline: Optional[bool] = None,
        font_size: Optional[int] = None,
        foreground_color: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """
        Apply text formatting to a range.

        Args:
            document_id: Target document ID
            start_index: Start position
            end_index: End position
            bold: Make text bold
            italic: Make text italic
            underline: Underline text
            font_size: Font size in points
            foreground_color: Text color as RGB dict (e.g., {"red": 1.0, "green": 0.0, "blue": 0.0})

        Returns:
            API response dictionary

        Raises:
            HttpError: If formatting fails
        """
        try:
            text_style = {}
            
            if bold is not None:
                text_style['bold'] = bold
            if italic is not None:
                text_style['italic'] = italic
            if underline is not None:
                text_style['underline'] = underline
            if font_size is not None:
                text_style['fontSize'] = {'magnitude': font_size, 'unit': 'PT'}
            if foreground_color is not None:
                text_style['foregroundColor'] = {'color': {'rgbColor': foreground_color}}

            requests = [
                {
                    'updateTextStyle': {
                        'range': {
                            'startIndex': start_index,
                            'endIndex': end_index,
                        },
                        'textStyle': text_style,
                        'fields': ','.join(text_style.keys()),
                    }
                }
            ]

            result = self.service.documents().batchUpdate(
                documentId=document_id,
                body={'requests': requests}
            ).execute()

            logger.debug(f"Applied formatting to range {start_index}-{end_index}")
            return result

        except HttpError as e:
            logger.error(f"Failed to apply formatting: {e}")
            raise

    def apply_named_style(
        self,
        document_id: str,
        start_index: int,
        end_index: int,
        style_name: str,
    ) -> Dict[str, Any]:
        """
        Apply a named paragraph style.

        Args:
            document_id: Target document ID
            start_index: Start position
            end_index: End position
            style_name: Style name (e.g., 'HEADING_1', 'HEADING_2', 'TITLE', 'NORMAL_TEXT')

        Returns:
            API response dictionary

        Raises:
            HttpError: If style application fails
        """
        try:
            requests = [
                {
                    'updateParagraphStyle': {
                        'range': {
                            'startIndex': start_index,
                            'endIndex': end_index,
                        },
                        'paragraphStyle': {
                            'namedStyleType': style_name,
                        },
                        'fields': 'namedStyleType',
                    }
                }
            ]

            result = self.service.documents().batchUpdate(
                documentId=document_id,
                body={'requests': requests}
            ).execute()

            logger.debug(f"Applied {style_name} to range {start_index}-{end_index}")
            return result

        except HttpError as e:
            logger.error(f"Failed to apply named style: {e}")
            raise

    def insert_table(
        self,
        document_id: str,
        rows: int,
        columns: int,
        index: int,
        data: Optional[list] = None,
    ) -> Dict[str, Any]:
        """
        Insert a table into the document.

        Args:
            document_id: Target document ID
            rows: Number of rows
            columns: Number of columns
            index: Insert position
            data: Optional 2D list of cell data [[row1_col1, row1_col2], [row2_col1, row2_col2], ...]

        Returns:
            API response dictionary with table location

        Raises:
            HttpError: If table insertion fails
        """
        try:
            requests = [
                {
                    'insertTable': {
                        'rows': rows,
                        'columns': columns,
                        'location': {
                            'index': index,
                        }
                    }
                }
            ]

            result = self.service.documents().batchUpdate(
                documentId=document_id,
                body={'requests': requests}
            ).execute()

            logger.debug(f"Inserted {rows}x{columns} table at index {index}")

            # If data provided, populate the table
            if data:
                # Get the document to find table locations
                doc = self.get_document(document_id)
                
                # Find the newly inserted table
                for element in doc.get('body', {}).get('content', []):
                    if 'table' in element:
                        table = element['table']
                        table_rows = table.get('tableRows', [])
                        
                        # Populate cells
                        populate_requests = []
                        for row_idx, row_data in enumerate(data[:len(table_rows)]):
                            for col_idx, cell_value in enumerate(row_data[:columns]):
                                cell = table_rows[row_idx]['tableCells'][col_idx]
                                cell_start = cell['content'][0]['startIndex']
                                
                                populate_requests.append({
                                    'insertText': {
                                        'location': {'index': cell_start},
                                        'text': str(cell_value),
                                    }
                                })
                        
                        if populate_requests:
                            self.service.documents().batchUpdate(
                                documentId=document_id,
                                body={'requests': populate_requests}
                            ).execute()
                            logger.debug(f"Populated table with {len(populate_requests)} cells")
                        
                        break

            return result

        except HttpError as e:
            logger.error(f"Failed to insert table: {e}")
            raise

    def insert_image(
        self,
        document_id: str,
        image_url: str,
        index: int,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Insert an image from a URL.

        Args:
            document_id: Target document ID
            image_url: Publicly accessible image URL
            index: Insert position
            width: Optional width in points
            height: Optional height in points

        Returns:
            API response dictionary

        Raises:
            HttpError: If image insertion fails
        """
        try:
            image_properties = {
                'sourceUri': image_url,
            }

            if width or height:
                image_properties['imageProperties'] = {}
                if width:
                    image_properties['imageProperties']['width'] = {'magnitude': width, 'unit': 'PT'}
                if height:
                    image_properties['imageProperties']['height'] = {'magnitude': height, 'unit': 'PT'}

            requests = [
                {
                    'insertInlineImage': {
                        'location': {
                            'index': index,
                        },
                        'uri': image_url,
                    }
                }
            ]

            result = self.service.documents().batchUpdate(
                documentId=document_id,
                body={'requests': requests}
            ).execute()

            logger.debug(f"Inserted image from {image_url} at index {index}")
            return result

        except HttpError as e:
            logger.error(f"Failed to insert image: {e}")
            raise

    def insert_page_break(
        self,
        document_id: str,
        index: int,
    ) -> Dict[str, Any]:
        """
        Insert a page break.

        Args:
            document_id: Target document ID
            index: Insert position

        Returns:
            API response dictionary

        Raises:
            HttpError: If page break insertion fails
        """
        try:
            requests = [
                {
                    'insertPageBreak': {
                        'location': {
                            'index': index,
                        }
                    }
                }
            ]

            result = self.service.documents().batchUpdate(
                documentId=document_id,
                body={'requests': requests}
            ).execute()

            logger.debug(f"Inserted page break at index {index}")
            return result

        except HttpError as e:
            logger.error(f"Failed to insert page break: {e}")
            raise

    def create_bullet_list(
        self,
        document_id: str,
        start_index: int,
        end_index: int,
        bullet_preset: str = 'BULLET_DISC_CIRCLE_SQUARE',
    ) -> Dict[str, Any]:
        """
        Convert paragraphs to a bulleted list.

        Args:
            document_id: Target document ID
            start_index: Start position
            end_index: End position
            bullet_preset: Bullet style preset

        Returns:
            API response dictionary

        Raises:
            HttpError: If bullet list creation fails
        """
        try:
            requests = [
                {
                    'createParagraphBullets': {
                        'range': {
                            'startIndex': start_index,
                            'endIndex': end_index,
                        },
                        'bulletPreset': bullet_preset,
                    }
                }
            ]

            result = self.service.documents().batchUpdate(
                documentId=document_id,
                body={'requests': requests}
            ).execute()

            logger.debug(f"Created bullet list for range {start_index}-{end_index}")
            return result

        except HttpError as e:
            logger.error(f"Failed to create bullet list: {e}")
            raise


__all__ = ["GoogleDocsAPI"]
