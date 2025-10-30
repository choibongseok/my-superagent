"""Base plugin interface for AgentHQ plugin system."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class PluginManifest:
    """Plugin manifest with metadata."""

    def __init__(
        self,
        name: str,
        version: str,
        description: str,
        author: str,
        permissions: List[str],
        inputs: Dict[str, str],
        outputs: Dict[str, str],
    ):
        """
        Initialize plugin manifest.

        Args:
            name: Plugin name
            version: Semantic version (e.g., "1.0.0")
            description: Plugin description
            author: Plugin author
            permissions: Required permissions
            inputs: Input schema (name: type)
            outputs: Output schema (name: type)
        """
        self.name = name
        self.version = version
        self.description = description
        self.author = author
        self.permissions = permissions
        self.inputs = inputs
        self.outputs = outputs

    def to_dict(self) -> Dict[str, Any]:
        """Convert manifest to dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "permissions": self.permissions,
            "inputs": self.inputs,
            "outputs": self.outputs,
        }


class BasePlugin(ABC):
    """
    Base class for all plugins.

    Plugins extend AgentHQ functionality with:
    - Custom agents
    - Custom tools
    - Third-party integrations
    - Custom UI components
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize plugin.

        Args:
            config: Plugin configuration
        """
        self.config = config or {}
        self.name = self.__class__.__name__
        self.version = "1.0.0"
        self._initialized = False

    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize plugin resources.

        This method is called once when the plugin is loaded.
        Use it to set up connections, load data, etc.

        Raises:
            Exception: If initialization fails
        """
        pass

    @abstractmethod
    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute plugin with inputs.

        Args:
            inputs: Input parameters matching plugin's input schema

        Returns:
            Output matching plugin's output schema

        Raises:
            ValueError: If inputs don't match schema
            Exception: If execution fails
        """
        pass

    @abstractmethod
    def get_manifest(self) -> PluginManifest:
        """
        Get plugin manifest.

        Returns:
            PluginManifest with plugin metadata
        """
        pass

    async def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        """
        Validate inputs against plugin schema.

        Args:
            inputs: Input parameters

        Returns:
            True if valid, False otherwise
        """
        manifest = self.get_manifest()
        required_keys = set(manifest.inputs.keys())
        provided_keys = set(inputs.keys())

        # Check all required inputs are provided
        if not required_keys.issubset(provided_keys):
            missing = required_keys - provided_keys
            raise ValueError(f"Missing required inputs: {missing}")

        return True

    async def cleanup(self) -> None:
        """
        Cleanup plugin resources.

        This method is called when the plugin is unloaded.
        Use it to close connections, save state, etc.
        """
        pass

    def is_initialized(self) -> bool:
        """Check if plugin is initialized."""
        return self._initialized

    def mark_initialized(self) -> None:
        """Mark plugin as initialized."""
        self._initialized = True


class AgentPlugin(BasePlugin):
    """
    Base class for agent plugins.

    Agent plugins provide custom AI agents with specialized capabilities.
    """

    @abstractmethod
    async def run_agent(self, prompt: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run agent with prompt.

        Args:
            prompt: User prompt
            context: Additional context

        Returns:
            Agent response with output and metadata
        """
        pass


class ToolPlugin(BasePlugin):
    """
    Base class for tool plugins.

    Tool plugins provide custom tools that agents can use.
    """

    @abstractmethod
    async def run_tool(self, tool_input: str) -> str:
        """
        Run tool with input.

        Args:
            tool_input: Tool input string

        Returns:
            Tool output string
        """
        pass

    @abstractmethod
    def get_tool_description(self) -> str:
        """
        Get tool description for agent.

        Returns:
            Tool description that tells agent when and how to use this tool
        """
        pass


class IntegrationPlugin(BasePlugin):
    """
    Base class for integration plugins.

    Integration plugins connect to third-party services.
    """

    @abstractmethod
    async def authenticate(self, credentials: Dict[str, Any]) -> bool:
        """
        Authenticate with third-party service.

        Args:
            credentials: Authentication credentials

        Returns:
            True if authentication successful
        """
        pass

    @abstractmethod
    async def sync_data(self, direction: str) -> Dict[str, Any]:
        """
        Sync data with third-party service.

        Args:
            direction: "import" or "export"

        Returns:
            Sync results
        """
        pass


__all__ = [
    "BasePlugin",
    "PluginManifest",
    "AgentPlugin",
    "ToolPlugin",
    "IntegrationPlugin",
]
