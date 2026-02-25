"""
Plugin System for my-superagent

Extensible architecture for integrating external tools and services.

Supported plugins:
- Notion: Page/database CRUD, search
- Jira (future)
- Confluence (future)
"""

from .base import Plugin, PluginConfig, PluginRegistry, registry
from .notion_plugin import NotionPlugin

__all__ = [
    "Plugin",
    "PluginConfig",
    "PluginRegistry",
    "registry",
    "NotionPlugin",
]
