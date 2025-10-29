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


__all__ = ["GoogleDocsAPI"]
