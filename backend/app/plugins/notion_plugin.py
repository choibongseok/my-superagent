"""
Notion Plugin

Integrates with Notion API for:
- Page creation/editing
- Database queries
- Block manipulation
- Search

Requires: NOTION_API_KEY in environment or config
"""

from typing import Any, Dict, List, Optional
from notion_client import AsyncClient
from notion_client.errors import APIResponseError
import logging

from .base import Plugin, PluginConfig, PluginType

logger = logging.getLogger(__name__)


class NotionPlugin(Plugin):
    """
    Notion integration plugin.
    
    Capabilities:
    - create_page: Create new pages
    - search: Search across workspace
    - query_database: Query database with filters
    - append_blocks: Add content to pages
    - get_page: Retrieve page properties
    """
    
    def __init__(self, api_key: str):
        config = PluginConfig(
            name="notion",
            display_name="Notion",
            type=PluginType.COLLABORATION,
            api_key=api_key,
        )
        super().__init__(config)
        self.client: Optional[AsyncClient] = None
    
    async def authenticate(self) -> bool:
        """Initialize Notion client with API key."""
        try:
            self.client = AsyncClient(auth=self.config.api_key)
            # Test connection
            await self.client.users.me()
            logger.info("Notion plugin authenticated successfully")
            return True
        except Exception as e:
            logger.error(f"Notion authentication failed: {e}")
            return False
    
    async def test_connection(self) -> Dict[str, Any]:
        """Test Notion API connection."""
        if not self.client:
            return {
                "connected": False,
                "message": "Client not initialized. Call authenticate() first.",
                "details": {}
            }
        
        try:
            user = await self.client.users.me()
            return {
                "connected": True,
                "message": "Connection successful",
                "details": {
                    "user_id": user.get("id"),
                    "bot": user.get("bot", {}),
                }
            }
        except APIResponseError as e:
            return {
                "connected": False,
                "message": f"API error: {e.message}",
                "details": {"code": e.code, "status": e.status}
            }
        except Exception as e:
            return {
                "connected": False,
                "message": f"Unexpected error: {str(e)}",
                "details": {}
            }
    
    async def get_capabilities(self) -> List[str]:
        """List supported operations."""
        return [
            "create_page",
            "search",
            "query_database",
            "append_blocks",
            "get_page",
            "update_page",
        ]
    
    # ========================================================================
    # Notion-specific methods
    # ========================================================================
    
    async def create_page(
        self,
        parent_id: str,
        title: str,
        content: Optional[List[Dict[str, Any]]] = None,
        properties: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new page in Notion.
        
        Args:
            parent_id: Parent page or database ID
            title: Page title
            content: List of block objects (optional)
            properties: Page properties for database pages (optional)
        
        Returns:
            Created page object
        """
        if not self.client:
            raise RuntimeError("Client not authenticated")
        
        # Build page object
        page_data = {
            "parent": {"page_id": parent_id} if not properties else {"database_id": parent_id},
            "properties": {
                "title": {
                    "title": [{"text": {"content": title}}]
                }
            }
        }
        
        # Add custom properties for database pages
        if properties:
            page_data["properties"].update(properties)
        
        # Add content blocks
        if content:
            page_data["children"] = content
        
        try:
            response = await self.client.pages.create(**page_data)
            logger.info(f"Created Notion page: {response['id']}")
            return response
        except APIResponseError as e:
            logger.error(f"Failed to create page: {e.message}")
            raise
    
    async def search(
        self,
        query: str,
        filter_type: Optional[str] = None,
        sort: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search Notion workspace.
        
        Args:
            query: Search query string
            filter_type: Filter by "page" or "database" (optional)
            sort: Sort options (optional)
        
        Returns:
            List of matching pages/databases
        """
        if not self.client:
            raise RuntimeError("Client not authenticated")
        
        search_params = {"query": query}
        
        if filter_type:
            search_params["filter"] = {"property": "object", "value": filter_type}
        
        if sort:
            search_params["sort"] = sort
        
        try:
            response = await self.client.search(**search_params)
            return response.get("results", [])
        except APIResponseError as e:
            logger.error(f"Search failed: {e.message}")
            raise
    
    async def append_blocks(
        self,
        page_id: str,
        blocks: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Append blocks to a page.
        
        Args:
            page_id: Target page ID
            blocks: List of block objects
        
        Returns:
            Updated block list
        """
        if not self.client:
            raise RuntimeError("Client not authenticated")
        
        try:
            response = await self.client.blocks.children.append(
                block_id=page_id,
                children=blocks
            )
            logger.info(f"Appended {len(blocks)} blocks to page {page_id}")
            return response
        except APIResponseError as e:
            logger.error(f"Failed to append blocks: {e.message}")
            raise
    
    async def get_page(self, page_id: str) -> Dict[str, Any]:
        """
        Retrieve page properties.
        
        Args:
            page_id: Page ID
        
        Returns:
            Page object
        """
        if not self.client:
            raise RuntimeError("Client not authenticated")
        
        try:
            return await self.client.pages.retrieve(page_id=page_id)
        except APIResponseError as e:
            logger.error(f"Failed to get page: {e.message}")
            raise
    
    async def query_database(
        self,
        database_id: str,
        filter_conditions: Optional[Dict[str, Any]] = None,
        sorts: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Query a Notion database.
        
        Args:
            database_id: Database ID
            filter_conditions: Filter object (optional)
            sorts: Sort array (optional)
        
        Returns:
            List of database pages
        """
        if not self.client:
            raise RuntimeError("Client not authenticated")
        
        query_params = {"database_id": database_id}
        
        if filter_conditions:
            query_params["filter"] = filter_conditions
        
        if sorts:
            query_params["sorts"] = sorts
        
        try:
            response = await self.client.databases.query(**query_params)
            return response.get("results", [])
        except APIResponseError as e:
            logger.error(f"Database query failed: {e.message}")
            raise
