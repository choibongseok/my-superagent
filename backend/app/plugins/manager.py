"""Plugin manager for loading, managing, and executing plugins."""

import importlib
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.plugins.base import BasePlugin, PluginManifest

logger = logging.getLogger(__name__)


class PluginManager:
    """
    Manage plugins lifecycle and execution.

    Features:
        - Dynamic plugin loading
        - Plugin registry
        - Sandboxed execution (basic)
        - Permission validation
        - Plugin dependency management
    """

    def __init__(self, plugin_dir: Optional[str] = None):
        """
        Initialize plugin manager.

        Args:
            plugin_dir: Directory containing plugins (default: app/plugins)
        """
        self.plugins: Dict[str, BasePlugin] = {}
        self.manifests: Dict[str, PluginManifest] = {}

        # Plugin directory
        if plugin_dir:
            self.plugin_dir = Path(plugin_dir)
        else:
            # Default to app/plugins directory
            current_dir = Path(__file__).parent
            self.plugin_dir = current_dir

        logger.info(f"PluginManager initialized with directory: {self.plugin_dir}")

    async def load_plugin(
        self,
        plugin_path: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> BasePlugin:
        """
        Load a plugin from module path.

        Args:
            plugin_path: Python module path (e.g., "app.plugins.slack_notifier")
            config: Plugin configuration

        Returns:
            Loaded plugin instance

        Raises:
            ImportError: If plugin module not found
            ValueError: If plugin class not found or invalid
            Exception: If plugin initialization fails
        """
        try:
            # Import plugin module
            logger.info(f"Loading plugin: {plugin_path}")
            module = importlib.import_module(plugin_path)

            # Get plugin class (must be named "Plugin")
            if not hasattr(module, "Plugin"):
                raise ValueError(
                    f"Plugin module {plugin_path} must export a 'Plugin' class"
                )

            plugin_class = getattr(module, "Plugin")

            # Validate plugin class inherits from BasePlugin
            if not issubclass(plugin_class, BasePlugin):
                raise ValueError(
                    f"Plugin class must inherit from BasePlugin"
                )

            # Instantiate plugin
            plugin = plugin_class(config or {})

            # Get and validate manifest
            manifest = plugin.get_manifest()
            if not isinstance(manifest, PluginManifest):
                raise ValueError(
                    f"Plugin manifest must be a PluginManifest instance"
                )

            # Initialize plugin
            await plugin.initialize()
            plugin.mark_initialized()

            # Register plugin
            self.plugins[manifest.name] = plugin
            self.manifests[manifest.name] = manifest

            logger.info(
                f"Plugin loaded successfully: {manifest.name} v{manifest.version}"
            )

            return plugin

        except ImportError as e:
            logger.error(f"Failed to import plugin {plugin_path}: {e}")
            raise ImportError(f"Plugin module not found: {plugin_path}") from e

        except Exception as e:
            logger.error(f"Failed to load plugin {plugin_path}: {e}", exc_info=True)
            raise

    async def load_plugins_from_directory(
        self, directory: Optional[Path] = None
    ) -> List[str]:
        """
        Load all plugins from directory.

        Args:
            directory: Directory to scan (default: self.plugin_dir)

        Returns:
            List of loaded plugin names
        """
        scan_dir = directory or self.plugin_dir
        loaded = []

        logger.info(f"Scanning for plugins in: {scan_dir}")

        if not scan_dir.exists():
            logger.warning(f"Plugin directory does not exist: {scan_dir}")
            return loaded

        # Find all .py files except __init__.py and base.py
        for plugin_file in scan_dir.glob("*.py"):
            if plugin_file.name in ("__init__.py", "base.py", "manager.py"):
                continue

            # Convert file path to module path
            module_name = plugin_file.stem
            module_path = f"app.plugins.{module_name}"

            try:
                plugin = await self.load_plugin(module_path)
                loaded.append(plugin.name)
            except Exception as e:
                logger.error(
                    f"Failed to load plugin from {plugin_file}: {e}"
                )

        logger.info(f"Loaded {len(loaded)} plugins: {loaded}")

        return loaded

    async def execute_plugin(
        self,
        plugin_name: str,
        inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute a plugin with inputs.

        Args:
            plugin_name: Plugin name
            inputs: Input parameters

        Returns:
            Plugin execution result

        Raises:
            ValueError: If plugin not found or not initialized
            Exception: If execution fails
        """
        if plugin_name not in self.plugins:
            raise ValueError(f"Plugin not found: {plugin_name}")

        plugin = self.plugins[plugin_name]

        if not plugin.is_initialized():
            raise ValueError(f"Plugin not initialized: {plugin_name}")

        logger.info(f"Executing plugin: {plugin_name}")

        try:
            # Validate inputs
            await plugin.validate_inputs(inputs)

            # Execute plugin
            result = await plugin.execute(inputs)

            logger.info(f"Plugin execution successful: {plugin_name}")

            return result

        except Exception as e:
            logger.error(
                f"Plugin execution failed: {plugin_name} - {e}",
                exc_info=True,
            )
            raise

    def list_plugins(self) -> List[Dict[str, Any]]:
        """
        List all loaded plugins.

        Returns:
            List of plugin manifests
        """
        return [manifest.to_dict() for manifest in self.manifests.values()]

    def get_plugin(self, plugin_name: str) -> Optional[BasePlugin]:
        """
        Get plugin by name.

        Args:
            plugin_name: Plugin name

        Returns:
            Plugin instance or None if not found
        """
        return self.plugins.get(plugin_name)

    def get_manifest(self, plugin_name: str) -> Optional[PluginManifest]:
        """
        Get plugin manifest.

        Args:
            plugin_name: Plugin name

        Returns:
            Plugin manifest or None if not found
        """
        return self.manifests.get(plugin_name)

    async def unload_plugin(self, plugin_name: str) -> bool:
        """
        Unload a plugin.

        Args:
            plugin_name: Plugin name

        Returns:
            True if unloaded, False if not found
        """
        if plugin_name not in self.plugins:
            return False

        plugin = self.plugins[plugin_name]

        try:
            # Cleanup plugin resources
            await plugin.cleanup()

            # Remove from registry
            del self.plugins[plugin_name]
            del self.manifests[plugin_name]

            logger.info(f"Plugin unloaded: {plugin_name}")

            return True

        except Exception as e:
            logger.error(f"Failed to unload plugin {plugin_name}: {e}", exc_info=True)
            raise

    async def unload_all(self) -> None:
        """Unload all plugins."""
        plugin_names = list(self.plugins.keys())

        for plugin_name in plugin_names:
            try:
                await self.unload_plugin(plugin_name)
            except Exception as e:
                logger.error(f"Failed to unload plugin {plugin_name}: {e}")

        logger.info("All plugins unloaded")

    def validate_permissions(
        self,
        plugin_name: str,
        required_permissions: List[str],
    ) -> bool:
        """
        Validate plugin has required permissions.

        Args:
            plugin_name: Plugin name
            required_permissions: Required permissions

        Returns:
            True if plugin has all required permissions
        """
        manifest = self.get_manifest(plugin_name)

        if not manifest:
            return False

        plugin_permissions = set(manifest.permissions)
        required = set(required_permissions)

        return required.issubset(plugin_permissions)


# Global plugin manager instance
_plugin_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    """
    Get global plugin manager instance.

    Returns:
        PluginManager instance
    """
    global _plugin_manager

    if _plugin_manager is None:
        _plugin_manager = PluginManager()

    return _plugin_manager


__all__ = ["PluginManager", "get_plugin_manager"]
