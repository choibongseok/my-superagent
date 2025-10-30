"""Plugin system for AgentHQ.

This module provides a flexible plugin system for extending AgentHQ with:
- Custom agents
- Custom tools
- Third-party integrations
- Custom UI components
"""

from app.plugins.base import (
    AgentPlugin,
    BasePlugin,
    IntegrationPlugin,
    PluginManifest,
    ToolPlugin,
)
from app.plugins.manager import PluginManager, get_plugin_manager

__all__ = [
    "BasePlugin",
    "PluginManifest",
    "AgentPlugin",
    "ToolPlugin",
    "IntegrationPlugin",
    "PluginManager",
    "get_plugin_manager",
]
