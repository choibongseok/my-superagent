"""
Tests for Plugin System

Tests:
1. Base plugin architecture
2. Notion plugin functionality
3. Plugin registry
4. API endpoints
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.plugins.base import Plugin, PluginConfig, PluginRegistry, PluginType
from app.plugins.notion_plugin import NotionPlugin


# ============================================================================
# 1. Base Plugin Architecture Tests
# ============================================================================

class TestPluginBase:
    """Test base plugin infrastructure."""
    
    def test_plugin_config_creation(self):
        """Test creating plugin configuration."""
        config = PluginConfig(
            name="test_plugin",
            display_name="Test Plugin",
            type=PluginType.COLLABORATION,
            api_key="test_key_123",
            config={"timeout": 30}
        )
        
        assert config.name == "test_plugin"
        assert config.display_name == "Test Plugin"
        assert config.type == PluginType.COLLABORATION
        assert config.enabled is True  # Default
        assert config.api_key == "test_key_123"
        assert config.config["timeout"] == 30
    
    def test_plugin_registry(self):
        """Test plugin registry operations."""
        registry = PluginRegistry()
        
        # Create mock plugin
        config = PluginConfig(
            name="mock_plugin",
            display_name="Mock",
            type=PluginType.COLLABORATION
        )
        mock_plugin = MagicMock(spec=Plugin)
        mock_plugin.config = config
        
        # Register plugin
        registry.register(mock_plugin)
        
        # Verify registration
        assert "mock_plugin" in registry.list()
        assert registry.get("mock_plugin") == mock_plugin
        assert registry.get("nonexistent") is None
    
    def test_plugin_registry_enabled_filter(self):
        """Test filtering enabled plugins."""
        registry = PluginRegistry()
        
        # Create two plugins (one disabled)
        config1 = PluginConfig(
            name="plugin1",
            display_name="Plugin 1",
            type=PluginType.COLLABORATION,
            enabled=True
        )
        plugin1 = MagicMock(spec=Plugin)
        plugin1.config = config1
        
        config2 = PluginConfig(
            name="plugin2",
            display_name="Plugin 2",
            type=PluginType.ISSUE_TRACKING,
            enabled=False
        )
        plugin2 = MagicMock(spec=Plugin)
        plugin2.config = config2
        
        registry.register(plugin1)
        registry.register(plugin2)
        
        # Check lists
        assert len(registry.list()) == 2
        assert len(registry.list_enabled()) == 1
        assert "plugin1" in registry.list_enabled()
        assert "plugin2" not in registry.list_enabled()


# ============================================================================
# 2. Notion Plugin Tests
# ============================================================================

class TestNotionPlugin:
    """Test Notion plugin functionality."""
    
    @pytest.mark.asyncio
    @patch('app.plugins.notion_plugin.AsyncClient')
    async def test_notion_authentication_success(self, mock_client_class):
        """Test successful Notion authentication."""
        # Mock AsyncClient
        mock_client = AsyncMock()
        mock_client.users.me.return_value = {"id": "user_123", "type": "bot"}
        mock_client_class.return_value = mock_client
        
        # Create plugin
        plugin = NotionPlugin(api_key="test_notion_key")
        
        # Authenticate
        result = await plugin.authenticate()
        
        assert result is True
        assert plugin.client is not None
        mock_client.users.me.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('app.plugins.notion_plugin.AsyncClient')
    async def test_notion_authentication_failure(self, mock_client_class):
        """Test failed Notion authentication."""
        # Mock AsyncClient that raises error
        mock_client = AsyncMock()
        mock_client.users.me.side_effect = Exception("Invalid API key")
        mock_client_class.return_value = mock_client
        
        plugin = NotionPlugin(api_key="invalid_key")
        
        result = await plugin.authenticate()
        
        assert result is False
    
    @pytest.mark.asyncio
    @patch('app.plugins.notion_plugin.AsyncClient')
    async def test_notion_test_connection(self, mock_client_class):
        """Test Notion connection test."""
        # Mock AsyncClient
        mock_client = AsyncMock()
        mock_client.users.me.return_value = {
            "id": "user_123",
            "bot": {"owner": {"type": "workspace"}}
        }
        mock_client_class.return_value = mock_client
        
        plugin = NotionPlugin(api_key="test_key")
        await plugin.authenticate()
        
        # Test connection
        status = await plugin.test_connection()
        
        assert status["connected"] is True
        assert status["message"] == "Connection successful"
        assert "user_id" in status["details"]
    
    @pytest.mark.asyncio
    async def test_notion_get_capabilities(self):
        """Test Notion plugin capabilities."""
        plugin = NotionPlugin(api_key="test_key")
        
        capabilities = await plugin.get_capabilities()
        
        # Check expected capabilities
        assert "create_page" in capabilities
        assert "search" in capabilities
        assert "query_database" in capabilities
        assert "append_blocks" in capabilities
        assert "get_page" in capabilities
        assert "update_page" in capabilities
    
    @pytest.mark.asyncio
    @patch('app.plugins.notion_plugin.AsyncClient')
    async def test_notion_search(self, mock_client_class):
        """Test Notion search functionality."""
        # Mock AsyncClient
        mock_client = AsyncMock()
        mock_results = {
            "results": [
                {"id": "page_1", "object": "page"},
                {"id": "page_2", "object": "page"}
            ]
        }
        mock_client.search.return_value = mock_results
        mock_client_class.return_value = mock_client
        
        plugin = NotionPlugin(api_key="test_key")
        plugin.client = mock_client  # Skip authentication
        
        # Execute search
        results = await plugin.search("meeting notes")
        
        assert len(results) == 2
        assert results[0]["id"] == "page_1"
        mock_client.search.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('app.plugins.notion_plugin.AsyncClient')
    async def test_notion_create_page(self, mock_client_class):
        """Test Notion page creation."""
        # Mock AsyncClient
        mock_client = AsyncMock()
        mock_response = {
            "id": "new_page_123",
            "object": "page",
            "created_time": "2026-02-25T00:00:00.000Z"
        }
        mock_client.pages.create.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        plugin = NotionPlugin(api_key="test_key")
        plugin.client = mock_client
        
        # Create page
        result = await plugin.create_page(
            parent_id="parent_123",
            title="Test Page",
            content=[
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": "Hello"}}]
                    }
                }
            ]
        )
        
        assert result["id"] == "new_page_123"
        assert result["object"] == "page"
        mock_client.pages.create.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_notion_client_not_initialized(self):
        """Test that methods fail without authentication."""
        plugin = NotionPlugin(api_key="test_key")
        # Don't authenticate
        
        with pytest.raises(RuntimeError, match="Client not authenticated"):
            await plugin.search("test")


# ============================================================================
# 3. Integration Tests (API Endpoints)
# ============================================================================

@pytest.mark.asyncio
class TestPluginAPI:
    """Test plugin API endpoints."""
    
    # Note: These require a full FastAPI test client setup
    # For now, we'll test the core logic
    
    @patch('app.api.v1.plugins.registry')
    async def test_list_plugins_empty(self, mock_registry):
        """Test listing plugins when none are registered."""
        mock_registry.list.return_value = []
        mock_registry.list_enabled.return_value = []
        
        # Simulate endpoint logic
        from app.api.v1.plugins import PluginListResponse
        response = PluginListResponse(
            plugins=mock_registry.list(),
            enabled=mock_registry.list_enabled()
        )
        
        assert response.plugins == []
        assert response.enabled == []
    
    @patch('app.api.v1.plugins.registry')
    async def test_list_plugins_with_data(self, mock_registry):
        """Test listing plugins with registered plugins."""
        mock_registry.list.return_value = ["notion", "jira"]
        mock_registry.list_enabled.return_value = ["notion"]
        
        from app.api.v1.plugins import PluginListResponse
        response = PluginListResponse(
            plugins=mock_registry.list(),
            enabled=mock_registry.list_enabled()
        )
        
        assert len(response.plugins) == 2
        assert len(response.enabled) == 1
        assert "notion" in response.plugins


# ============================================================================
# 4. Error Handling Tests
# ============================================================================

class TestPluginErrors:
    """Test error handling in plugins."""
    
    @pytest.mark.asyncio
    @patch('app.plugins.notion_plugin.AsyncClient')
    async def test_notion_api_response_error(self, mock_client_class):
        """Test handling of Notion API errors."""
        from notion_client.errors import APIResponseError
        
        # Mock client that raises API error
        mock_client = AsyncMock()
        mock_client.search.side_effect = APIResponseError(
            response=MagicMock(status_code=401),
            message="Unauthorized",
            code="unauthorized"
        )
        mock_client_class.return_value = mock_client
        
        plugin = NotionPlugin(api_key="invalid_key")
        plugin.client = mock_client
        
        # Should propagate the error
        with pytest.raises(APIResponseError):
            await plugin.search("test")
    
    @pytest.mark.asyncio
    async def test_plugin_action_without_client(self):
        """Test that plugin actions fail gracefully without client."""
        plugin = NotionPlugin(api_key="test_key")
        
        # Try to execute action without authenticating
        with pytest.raises(RuntimeError):
            await plugin.get_page("page_123")
