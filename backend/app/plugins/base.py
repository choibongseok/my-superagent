"""
Base Plugin Architecture

Defines the interface for all plugins and provides a registry system.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from enum import Enum


class PluginType(str, Enum):
    """Type of plugin (for categorization)."""
    COLLABORATION = "collaboration"  # Notion, Confluence
    ISSUE_TRACKING = "issue_tracking"  # Jira, Linear
    COMMUNICATION = "communication"  # Slack, Discord
    STORAGE = "storage"  # Dropbox, Box
    CRM = "crm"  # Salesforce, HubSpot


class PluginConfig(BaseModel):
    """Configuration for a plugin."""
    name: str = Field(..., description="Plugin identifier (e.g., 'notion')")
    display_name: str = Field(..., description="Human-readable name")
    type: PluginType = Field(..., description="Plugin category")
    enabled: bool = Field(default=True, description="Whether plugin is active")
    api_key: Optional[str] = Field(default=None, description="API key (encrypted)")
    config: Dict[str, Any] = Field(default_factory=dict, description="Plugin-specific config")


class Plugin(ABC):
    """
    Base class for all plugins.
    
    Plugins provide:
    1. Authentication (API keys, OAuth)
    2. Core operations (CRUD, search, etc.)
    3. Error handling
    4. Rate limiting
    """
    
    def __init__(self, config: PluginConfig):
        self.config = config
        self.client = None  # Initialized in authenticate()
    
    @abstractmethod
    async def authenticate(self) -> bool:
        """
        Authenticate with the external service.
        
        Returns:
            True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def test_connection(self) -> Dict[str, Any]:
        """
        Test the connection and return service status.
        
        Returns:
            Dict with keys: connected (bool), message (str), details (dict)
        """
        pass
    
    @abstractmethod
    async def get_capabilities(self) -> List[str]:
        """
        Return list of supported operations.
        
        Example: ["create_page", "search", "update_database"]
        """
        pass


class PluginRegistry:
    """
    Central registry for managing plugins.
    
    Supports:
    - Plugin registration
    - Dependency injection
    - Lifecycle management (enable/disable)
    """
    
    def __init__(self):
        self._plugins: Dict[str, Plugin] = {}
    
    def register(self, plugin: Plugin) -> None:
        """Register a new plugin."""
        self._plugins[plugin.config.name] = plugin
    
    def get(self, name: str) -> Optional[Plugin]:
        """Get a plugin by name."""
        return self._plugins.get(name)
    
    def list(self) -> List[str]:
        """List all registered plugin names."""
        return list(self._plugins.keys())
    
    def list_enabled(self) -> List[str]:
        """List only enabled plugins."""
        return [
            name for name, plugin in self._plugins.items()
            if plugin.config.enabled
        ]


# Global registry instance
registry = PluginRegistry()
