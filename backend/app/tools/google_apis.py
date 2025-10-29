"""Google Workspace API tools."""

import logging
from typing import Dict, Any, Optional

from langchain_core.tools import Tool
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)


class GoogleDocsAPI:
    """Google Docs API wrapper."""
    
    def __init__(self, credentials: Credentials):
        """
        Initialize Google Docs API.
        
        Args:
            credentials: Google OAuth2 credentials
        """
        self.credentials = credentials
        self.service = build("docs", "v1", credentials=credentials)
    
    def create_document(self, title: str, content: str) -> Dict[str, Any]:
        """
        Create a Google Doc.
        
        Args:
            title: Document title
            content: Document content (plain text)
            
        Returns:
            Document metadata with ID and URL
        """
        try:
            # Create document
            doc = self.service.documents().create(body={"title": title}).execute()
            doc_id = doc["documentId"]
            
            # Insert content
            if content:
                requests = [{
                    "insertText": {
                        "location": {"index": 1},
                        "text": content
                    }
                }]
                self.service.documents().batchUpdate(
                    documentId=doc_id,
                    body={"requests": requests}
                ).execute()
            
            return {
                "id": doc_id,
                "title": title,
                "url": f"https://docs.google.com/document/d/{doc_id}/edit"
            }
            
        except Exception as e:
            logger.error(f"Failed to create document: {e}")
            raise


def create_google_docs_tool(credentials: Credentials) -> Tool:
    """
    Create Google Docs tool.
    
    Args:
        credentials: Google OAuth2 credentials
        
    Returns:
        LangChain Tool instance
    """
    docs_api = GoogleDocsAPI(credentials)
    
    def create_doc_wrapper(input_str: str) -> str:
        """
        Create a Google Doc.
        
        Input format: "title: <title>, content: <content>"
        """
        try:
            # Parse input
            parts = input_str.split(", content: ", 1)
            if len(parts) != 2:
                return "Invalid input format. Use: 'title: <title>, content: <content>'"
            
            title = parts[0].replace("title: ", "").strip()
            content = parts[1].strip()
            
            # Create document
            result = docs_api.create_document(title, content)
            
            return f"Document created successfully!\nTitle: {result['title']}\nURL: {result['url']}"
            
        except Exception as e:
            logger.error(f"Google Docs tool failed: {e}")
            return f"Failed to create document: {str(e)}"
    
    return Tool(
        name="create_google_doc",
        description=(
            "Create a Google Docs document. "
            "Input must be in format: 'title: <title>, content: <content>'. "
            "Returns the document URL."
        ),
        func=create_doc_wrapper,
    )


__all__ = ["GoogleDocsAPI", "create_google_docs_tool"]
