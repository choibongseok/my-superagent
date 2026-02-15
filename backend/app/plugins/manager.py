"""Plugin manager for loading, managing, and executing plugins."""

import importlib
import logging
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

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
                raise ValueError(f"Plugin class must inherit from BasePlugin")

            # Instantiate plugin
            plugin = plugin_class(config or {})

            # Get and validate manifest
            manifest = plugin.get_manifest()
            if not isinstance(manifest, PluginManifest):
                raise ValueError(f"Plugin manifest must be a PluginManifest instance")

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

    @staticmethod
    def _normalize_module_selector(selector: str) -> str:
        """Normalize include/exclude selectors to a plugin module stem."""
        if not isinstance(selector, str):
            raise ValueError("Plugin selectors must be strings")

        normalized_selector = selector.strip()
        if not normalized_selector:
            raise ValueError("Plugin selectors cannot be blank")

        if normalized_selector.endswith(".py"):
            normalized_selector = normalized_selector[:-3]

        if normalized_selector.startswith("app.plugins."):
            normalized_selector = normalized_selector.split(".")[-1]

        return normalized_selector

    @staticmethod
    def _normalize_required_permissions(
        required_permissions: Optional[Sequence[str]],
    ) -> Optional[set[str]]:
        """Normalize optional required-permission filters."""
        if required_permissions is None:
            return None

        normalized_permissions: set[str] = set()
        for permission in required_permissions:
            if not isinstance(permission, str):
                raise ValueError("required_permissions must contain only strings")

            normalized_permission = permission.strip()
            if not normalized_permission:
                raise ValueError("required_permissions cannot contain blank values")

            normalized_permissions.add(normalized_permission)

        return normalized_permissions

    @staticmethod
    def _permission_requirement_matches(
        plugin_permissions: set[str],
        required_permission: str,
    ) -> bool:
        """Return whether a plugin permission set satisfies one requirement.

        ``required_permission`` supports glob patterns (for example,
        ``"network.*"``).
        """
        if any(token in required_permission for token in "*?["):
            return any(
                fnmatchcase(plugin_permission, required_permission)
                for plugin_permission in plugin_permissions
            )

        return required_permission in plugin_permissions

    @classmethod
    def _has_required_permissions(
        cls,
        plugin_permissions: Sequence[str],
        required_permissions: Optional[set[str]],
        *,
        match_any_permissions: bool = False,
    ) -> bool:
        """Return whether a plugin permission set satisfies permission filters.

        By default, all required permissions must match. When
        ``match_any_permissions`` is ``True``, matching any one requirement is
        sufficient.
        """
        if required_permissions is None:
            return True

        if not isinstance(match_any_permissions, bool):
            raise ValueError("match_any_permissions must be a boolean")

        normalized_plugin_permissions = {
            str(permission) for permission in plugin_permissions
        }
        matches = (
            cls._permission_requirement_matches(
                normalized_plugin_permissions,
                required_permission,
            )
            for required_permission in required_permissions
        )

        if match_any_permissions:
            return any(matches)

        return all(matches)

    async def load_plugins_from_directory(
        self,
        directory: Optional[Path] = None,
        plugin_configs: Optional[Mapping[str, Mapping[str, Any]]] = None,
        *,
        include_plugins: Optional[Sequence[str]] = None,
        exclude_plugins: Optional[Sequence[str]] = None,
        required_permissions: Optional[Sequence[str]] = None,
        match_any_permissions: bool = False,
        stop_on_error: bool = False,
    ) -> List[str]:
        """
        Load all plugins from a directory.

        Args:
            directory: Directory to scan (default: self.plugin_dir)
            plugin_configs: Optional per-plugin configs keyed by module name
                (e.g., "weather_tool") or full module path
                (e.g., "app.plugins.weather_tool")
            include_plugins: Optional allowlist of plugin selectors. Selectors
                may be module stems ("weather_tool"), module paths
                ("app.plugins.weather_tool"), or filenames
                ("weather_tool.py"). Glob patterns are also supported
                (for example, ``"weather_*"``). When provided, only
                matching plugins are considered.
            exclude_plugins: Optional denylist of plugin selectors in the same
                format as ``include_plugins``.
            required_permissions: Optional permission filter. When provided,
                only plugins that satisfy all listed permissions in their
                manifest are kept loaded. Exact permission names and glob
                patterns (for example, ``"network.*"``) are supported.
            match_any_permissions: When ``True``, plugin permission filtering
                becomes an OR match (any required permission). Defaults to
                ``False`` (all required permissions).
            stop_on_error: If True, fail fast when a plugin cannot be loaded.

        Returns:
            List of loaded plugin names
        """
        scan_dir = directory or self.plugin_dir
        loaded: List[str] = []
        config_map: Mapping[str, Mapping[str, Any]] = plugin_configs or {}

        include_selectors = (
            {self._normalize_module_selector(selector) for selector in include_plugins}
            if include_plugins is not None
            else None
        )
        exclude_selectors = {
            self._normalize_module_selector(selector)
            for selector in (exclude_plugins or [])
        }
        normalized_required_permissions = self._normalize_required_permissions(
            required_permissions
        )

        if not isinstance(match_any_permissions, bool):
            raise ValueError("match_any_permissions must be a boolean")

        if include_selectors is not None:
            overlap = include_selectors & exclude_selectors
            if overlap:
                conflicting = ", ".join(sorted(overlap))
                raise ValueError(
                    f"Plugins cannot be both included and excluded: {conflicting}"
                )

        logger.info(f"Scanning for plugins in: {scan_dir}")

        if not scan_dir.exists():
            logger.warning(f"Plugin directory does not exist: {scan_dir}")
            return loaded

        # Find all .py files except package/module internals.
        plugin_files = sorted(
            plugin_file
            for plugin_file in scan_dir.glob("*.py")
            if plugin_file.name not in ("__init__.py", "base.py", "manager.py")
        )

        for plugin_file in plugin_files:
            module_name = plugin_file.stem
            module_path = f"app.plugins.{module_name}"

            if include_selectors is not None and not any(
                fnmatchcase(module_name, selector) for selector in include_selectors
            ):
                logger.debug("Skipping plugin %s (not in include list)", module_name)
                continue

            if any(
                fnmatchcase(module_name, selector) for selector in exclude_selectors
            ):
                logger.debug("Skipping plugin %s (in exclude list)", module_name)
                continue

            config = config_map.get(module_path) or config_map.get(module_name)

            try:
                plugin = await self.load_plugin(module_path, config=dict(config or {}))
                manifest = plugin.get_manifest()

                if not self._has_required_permissions(
                    manifest.permissions,
                    normalized_required_permissions,
                    match_any_permissions=match_any_permissions,
                ):
                    logger.debug(
                        "Skipping plugin %s (missing required permissions)",
                        module_name,
                    )
                    await self.unload_plugin(manifest.name)
                    continue

                loaded.append(manifest.name)
            except Exception as e:
                logger.error(f"Failed to load plugin from {plugin_file}: {e}")
                if stop_on_error:
                    raise

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

    @staticmethod
    def _manifest_matches_selectors(
        manifest_name: str,
        module_path: str,
        selectors: set[str],
    ) -> bool:
        """Return whether a manifest/module identity matches any selector."""
        module_stem = module_path.split(".")[-1] if module_path else ""
        normalized_manifest = manifest_name.replace("-", "_")
        candidates = {
            candidate
            for candidate in (manifest_name, normalized_manifest, module_stem)
            if candidate
        }

        return any(
            fnmatchcase(candidate, selector)
            for selector in selectors
            for candidate in candidates
        )

    def list_plugins(
        self,
        required_permissions: Optional[Sequence[str]] = None,
        *,
        include_plugins: Optional[Sequence[str]] = None,
        exclude_plugins: Optional[Sequence[str]] = None,
        match_any_permissions: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        List loaded plugins with optional selector and permission filters.

        Args:
            required_permissions: If provided, only plugins with all listed
                permissions are returned. Exact permission names and glob
                patterns (for example, ``"network.*"``) are supported.
            match_any_permissions: When ``True``, permission filtering uses OR
                semantics (any required permission). Defaults to ``False`` for
                AND semantics.
            include_plugins: Optional allowlist of plugin selectors. Selectors
                may reference manifest names (for example ``"weather-plugin"``),
                module stems (``"weather_tool"``), module paths
                (``"app.plugins.weather_tool"``), filenames
                (``"weather_tool.py"``), or glob patterns.
            exclude_plugins: Optional denylist of selectors in the same format
                as ``include_plugins``.

        Returns:
            List of plugin manifests.
        """
        include_selectors = (
            {self._normalize_module_selector(selector) for selector in include_plugins}
            if include_plugins is not None
            else None
        )
        exclude_selectors = {
            self._normalize_module_selector(selector)
            for selector in (exclude_plugins or [])
        }
        normalized_required_permissions = self._normalize_required_permissions(
            required_permissions
        )

        if not isinstance(match_any_permissions, bool):
            raise ValueError("match_any_permissions must be a boolean")

        if include_selectors is not None:
            overlap = include_selectors & exclude_selectors
            if overlap:
                conflicting = ", ".join(sorted(overlap))
                raise ValueError(
                    f"Plugins cannot be both included and excluded: {conflicting}"
                )

        manifests = list(self.manifests.values())

        if include_selectors is not None or exclude_selectors:
            filtered_manifests: List[PluginManifest] = []
            for manifest in manifests:
                plugin = self.plugins.get(manifest.name)
                module_path = plugin.__class__.__module__ if plugin else ""

                if (
                    include_selectors is not None
                    and not self._manifest_matches_selectors(
                        manifest.name,
                        module_path,
                        include_selectors,
                    )
                ):
                    continue

                if exclude_selectors and self._manifest_matches_selectors(
                    manifest.name,
                    module_path,
                    exclude_selectors,
                ):
                    continue

                filtered_manifests.append(manifest)

            manifests = filtered_manifests

        if normalized_required_permissions is not None:
            manifests = [
                manifest
                for manifest in manifests
                if self._has_required_permissions(
                    manifest.permissions,
                    normalized_required_permissions,
                    match_any_permissions=match_any_permissions,
                )
            ]

        return [manifest.to_dict() for manifest in manifests]

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

    async def reload_plugin(
        self,
        plugin_name: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> BasePlugin:
        """Reload a plugin by unloading and loading its module again.

        Args:
            plugin_name: Loaded plugin name to reload
            config: Optional replacement configuration. When omitted, the
                currently loaded plugin configuration is reused.

        Returns:
            Reloaded plugin instance.

        Raises:
            ValueError: If plugin is not loaded.
            Exception: If unload/load fails.
        """
        plugin = self.get_plugin(plugin_name)
        if plugin is None:
            raise ValueError(f"Plugin not found: {plugin_name}")

        module_path = plugin.__class__.__module__
        resolved_config: Dict[str, Any] = dict(
            config if config is not None else plugin.config
        )

        await self.unload_plugin(plugin_name)
        reloaded_plugin = await self.load_plugin(module_path, resolved_config)

        logger.info(f"Plugin reloaded: {plugin_name}")
        return reloaded_plugin

    @staticmethod
    def _normalize_plugin_config_overrides(
        plugin_configs: Optional[Mapping[str, Mapping[str, Any]]],
    ) -> Mapping[str, Mapping[str, Any]]:
        """Validate plugin config overrides used by bulk reload helpers."""
        if plugin_configs is None:
            return {}

        if not isinstance(plugin_configs, Mapping):
            raise ValueError("plugin_configs must be a mapping")

        normalized_configs: Dict[str, Mapping[str, Any]] = {}
        for key, value in plugin_configs.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("plugin_configs keys must be non-empty strings")
            if not isinstance(value, Mapping):
                raise ValueError(
                    "plugin_configs values must be mapping configuration objects"
                )

            normalized_configs[key.strip()] = value

        return normalized_configs

    @staticmethod
    def _resolve_plugin_override_config(
        *,
        manifest_name: str,
        module_path: str,
        overrides: Mapping[str, Mapping[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Resolve optional override config for a specific plugin identity."""
        module_stem = module_path.split(".")[-1] if module_path else ""
        normalized_manifest_name = manifest_name.replace("-", "_")

        for config_key in (
            manifest_name,
            normalized_manifest_name,
            module_path,
            module_stem,
        ):
            if not config_key:
                continue

            if config_key in overrides:
                return dict(overrides[config_key])

        return None

    async def reload_plugins(
        self,
        *,
        include_plugins: Optional[Sequence[str]] = None,
        exclude_plugins: Optional[Sequence[str]] = None,
        plugin_configs: Optional[Mapping[str, Mapping[str, Any]]] = None,
        stop_on_error: bool = False,
    ) -> List[str]:
        """Reload loaded plugins in bulk with optional selectors and overrides.

        Args:
            include_plugins: Optional allowlist of selectors (manifest name,
                module stem/path, filename, or glob pattern).
            exclude_plugins: Optional denylist of selectors in the same format
                as ``include_plugins``.
            plugin_configs: Optional configuration overrides applied per plugin.
                Keys may reference manifest name (e.g. ``"weather-plugin"``),
                normalized manifest name (``"weather_plugin"``), module path
                (``"app.plugins.weather_tool"``), or module stem
                (``"weather_tool"``).
            stop_on_error: If ``True``, re-raise the first reload failure.

        Returns:
            List of successfully reloaded plugin names.
        """
        include_selectors = (
            {self._normalize_module_selector(selector) for selector in include_plugins}
            if include_plugins is not None
            else None
        )
        exclude_selectors = {
            self._normalize_module_selector(selector)
            for selector in (exclude_plugins or [])
        }

        if include_selectors is not None:
            overlap = include_selectors & exclude_selectors
            if overlap:
                conflicting = ", ".join(sorted(overlap))
                raise ValueError(
                    f"Plugins cannot be both included and excluded: {conflicting}"
                )

        overrides = self._normalize_plugin_config_overrides(plugin_configs)
        reloaded_plugins: List[str] = []

        for manifest in sorted(self.manifests.values(), key=lambda item: item.name):
            plugin = self.plugins.get(manifest.name)
            if plugin is None:
                continue

            module_path = plugin.__class__.__module__

            if include_selectors is not None and not self._manifest_matches_selectors(
                manifest.name,
                module_path,
                include_selectors,
            ):
                continue

            if exclude_selectors and self._manifest_matches_selectors(
                manifest.name,
                module_path,
                exclude_selectors,
            ):
                continue

            override_config = self._resolve_plugin_override_config(
                manifest_name=manifest.name,
                module_path=module_path,
                overrides=overrides,
            )

            try:
                await self.reload_plugin(manifest.name, override_config)
                reloaded_plugins.append(manifest.name)
            except Exception:
                logger.error(
                    "Failed to reload plugin: %s", manifest.name, exc_info=True
                )
                if stop_on_error:
                    raise

        logger.info(
            "Reloaded %d plugin(s): %s", len(reloaded_plugins), reloaded_plugins
        )
        return reloaded_plugins

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
        *,
        match_any_permissions: bool = False,
    ) -> bool:
        """
        Validate plugin has required permissions.

        ``required_permissions`` supports glob patterns (for example,
        ``["network.*"]``).

        Args:
            plugin_name: Plugin name
            required_permissions: Required permissions or patterns
            match_any_permissions: When ``True``, return ``True`` if any
                required permission matches. Defaults to ``False`` (all must
                match).

        Returns:
            True if plugin satisfies required permission filters
        """
        manifest = self.get_manifest(plugin_name)

        if not manifest:
            return False

        normalized_required_permissions = self._normalize_required_permissions(
            required_permissions
        )

        return self._has_required_permissions(
            manifest.permissions,
            normalized_required_permissions,
            match_any_permissions=match_any_permissions,
        )


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
