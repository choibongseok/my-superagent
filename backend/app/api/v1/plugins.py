"""
Plugin Management API

Endpoints:
- GET /plugins - List available plugins
- POST /plugins/{name}/configure - Configure a plugin
- GET /plugins/{name}/status - Check plugin connection
- POST /plugins/{name}/action - Execute plugin-specific action
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Any, Dict, List
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_user
from app.models.user import User
from app.plugins import registry, NotionPlugin
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/plugins", tags=["plugins"])


# ============================================================================
# Request/Response Schemas
# ============================================================================

class PluginConfigRequest(BaseModel):
    """Configuration for a plugin."""
    api_key: str = Field(..., description="API key for the service")
    config: Dict[str, Any] = Field(default_factory=dict, description="Additional config")


class PluginStatusResponse(BaseModel):
    """Plugin connection status."""
    name: str
    connected: bool
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class PluginActionRequest(BaseModel):
    """Execute a plugin action."""
    action: str = Field(..., description="Action name (e.g., 'search', 'create_page')")
    parameters: Dict[str, Any] = Field(..., description="Action parameters")


class PluginListResponse(BaseModel):
    """List of available plugins."""
    plugins: List[str]
    enabled: List[str]


# ============================================================================
# Endpoints
# ============================================================================

@router.get("", response_model=PluginListResponse)
async def list_plugins(
    current_user: User = Depends(get_current_user)
):
    """
    List all available plugins.
    
    Returns:
        PluginListResponse with all and enabled plugin names
    """
    return PluginListResponse(
        plugins=registry.list(),
        enabled=registry.list_enabled()
    )


@router.post("/{plugin_name}/configure", response_model=PluginStatusResponse)
async def configure_plugin(
    plugin_name: str,
    config: PluginConfigRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Configure and register a plugin.
    
    Args:
        plugin_name: Name of the plugin (e.g., 'notion')
        config: Plugin configuration (API key, etc.)
    
    Returns:
        PluginStatusResponse with connection status
    """
    # Currently only Notion is supported
    if plugin_name.lower() != "notion":
        raise HTTPException(
            status_code=400,
            detail=f"Plugin '{plugin_name}' not supported. Available: notion"
        )
    
    try:
        # Initialize plugin
        plugin = NotionPlugin(api_key=config.api_key)
        
        # Authenticate
        auth_success = await plugin.authenticate()
        if not auth_success:
            raise HTTPException(
                status_code=401,
                detail="Authentication failed. Check API key."
            )
        
        # Register in global registry
        registry.register(plugin)
        
        # Test connection
        status = await plugin.test_connection()
        
        logger.info(f"Plugin '{plugin_name}' configured for user {current_user.id}")
        
        return PluginStatusResponse(
            name=plugin_name,
            **status
        )
    
    except Exception as e:
        logger.error(f"Failed to configure plugin '{plugin_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{plugin_name}/status", response_model=PluginStatusResponse)
async def check_plugin_status(
    plugin_name: str,
    current_user: User = Depends(get_current_user)
):
    """
    Check plugin connection status.
    
    Args:
        plugin_name: Name of the plugin
    
    Returns:
        PluginStatusResponse with connection details
    """
    plugin = registry.get(plugin_name)
    
    if not plugin:
        raise HTTPException(
            status_code=404,
            detail=f"Plugin '{plugin_name}' not found or not configured"
        )
    
    try:
        status = await plugin.test_connection()
        return PluginStatusResponse(
            name=plugin_name,
            **status
        )
    except Exception as e:
        logger.error(f"Failed to check status for '{plugin_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{plugin_name}/action")
async def execute_plugin_action(
    plugin_name: str,
    request: PluginActionRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Execute a plugin-specific action.
    
    Args:
        plugin_name: Name of the plugin
        request: Action name and parameters
    
    Returns:
        Action result (plugin-specific)
    
    Examples:
        - Notion search: {"action": "search", "parameters": {"query": "meeting notes"}}
        - Notion create page: {"action": "create_page", "parameters": {"parent_id": "...", "title": "New Page"}}
    """
    plugin = registry.get(plugin_name)
    
    if not plugin:
        raise HTTPException(
            status_code=404,
            detail=f"Plugin '{plugin_name}' not found or not configured"
        )
    
    # Verify action is supported
    capabilities = await plugin.get_capabilities()
    if request.action not in capabilities:
        raise HTTPException(
            status_code=400,
            detail=f"Action '{request.action}' not supported. Available: {capabilities}"
        )
    
    try:
        # Call the corresponding method
        method = getattr(plugin, request.action)
        result = await method(**request.parameters)
        
        logger.info(f"Executed {plugin_name}.{request.action} for user {current_user.id}")
        
        return {"success": True, "result": result}
    
    except AttributeError:
        raise HTTPException(
            status_code=500,
            detail=f"Action '{request.action}' not implemented in plugin"
        )
    except Exception as e:
        logger.error(f"Failed to execute {plugin_name}.{request.action}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
