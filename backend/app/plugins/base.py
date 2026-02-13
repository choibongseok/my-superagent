"""Base plugin interface for AgentHQ plugin system."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

_TRUE_VALUES = {"true", "1", "yes", "on"}
_FALSE_VALUES = {"false", "0", "no", "off"}


class PluginManifest:
    """Plugin manifest with metadata."""

    def __init__(
        self,
        name: str,
        version: str,
        description: str,
        author: str,
        permissions: List[str],
        inputs: Dict[str, Any],
        outputs: Dict[str, Any],
        config_schema: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize plugin manifest.

        Args:
            name: Plugin name
            version: Semantic version (e.g., "1.0.0")
            description: Plugin description
            author: Plugin author
            permissions: Required permissions
            inputs: Input schema (name: schema)
            outputs: Output schema (name: schema)
            config_schema: Optional plugin configuration schema
        """
        self.name = name
        self.version = version
        self.description = description
        self.author = author
        self.permissions = permissions
        self.inputs = inputs
        self.outputs = outputs
        self.config_schema = config_schema or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert manifest to dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "permissions": self.permissions,
            "config_schema": self.config_schema,
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
        """Validate plugin inputs against the manifest schema.

        Validation behavior:
        1. Required-field validation (legacy behavior)
        2. Optional schema-driven type validation for declared fields
        3. Optional enum/choices validation for structured dict schemas

        Unknown input keys are ignored for backward compatibility.
        """
        manifest = self.get_manifest()
        required_keys = {
            key
            for key, schema in manifest.inputs.items()
            if self._is_input_required(schema)
        }
        provided_keys = set(inputs.keys())

        if not required_keys.issubset(provided_keys):
            missing = sorted(required_keys - provided_keys)
            raise ValueError(f"Missing required inputs: {set(missing)}")

        for key, value in inputs.items():
            schema = manifest.inputs.get(key)
            if schema is None:
                continue

            if value is None:
                if self._is_input_required(schema):
                    raise ValueError(f"Input '{key}' cannot be null")
                continue

            expected_type = self._get_schema_type(schema)
            if expected_type and not self._value_matches_type(value, expected_type):
                raise ValueError(
                    f"Invalid type for input '{key}': expected {expected_type}"
                )

            choices = self._get_schema_choices(schema)
            if choices and not self._value_in_choices(value, choices):
                raise ValueError(
                    f"Invalid value for input '{key}': expected one of {choices}"
                )

        return True

    @staticmethod
    def _is_input_required(schema: Any) -> bool:
        """Determine if an input schema marks a field as required."""
        if isinstance(schema, dict) and "required" in schema:
            return bool(schema["required"])

        if isinstance(schema, str):
            lowered = schema.lower()
            if "optional" in lowered:
                return False
            if "required" in lowered:
                return True

        # Backward compatible default: fields are required unless marked optional
        return True

    @staticmethod
    def _get_schema_type(schema: Any) -> Optional[str]:
        """Extract a normalized type string from legacy or structured schema."""
        declared_type: Optional[str] = None

        if isinstance(schema, dict):
            raw_type = schema.get("type")
            if isinstance(raw_type, str):
                declared_type = raw_type.strip().lower()
        elif isinstance(schema, str):
            token = schema.strip().split(" ", 1)[0]
            declared_type = token.strip("(),").lower()

        if not declared_type:
            return None

        aliases = {
            "str": "string",
            "text": "string",
            "int": "integer",
            "float": "number",
            "double": "number",
            "bool": "boolean",
            "dict": "object",
            "map": "object",
            "list": "array",
            "tuple": "array",
        }

        return aliases.get(declared_type, declared_type)

    @staticmethod
    def _get_schema_choices(schema: Any) -> Optional[List[Any]]:
        """Extract enum-style allowed values from structured schemas."""
        if not isinstance(schema, dict):
            return None

        for key in ("enum", "choices"):
            values = schema.get(key)
            if isinstance(values, (list, tuple, set)):
                return list(values)

        return None

    @staticmethod
    def _value_matches_type(value: Any, expected_type: str) -> bool:
        """Return whether a value conforms to a normalized schema type."""
        if expected_type in {"any", "*"}:
            return True

        if expected_type == "string":
            return isinstance(value, str)

        if expected_type == "integer":
            if isinstance(value, bool):
                return False
            if isinstance(value, int):
                return True
            if isinstance(value, str):
                stripped = value.strip()
                if stripped.startswith(("+", "-")):
                    stripped = stripped[1:]
                return stripped.isdigit()
            return False

        if expected_type == "number":
            if isinstance(value, bool):
                return False
            if isinstance(value, (int, float)):
                return True
            if isinstance(value, str):
                try:
                    float(value.strip())
                    return True
                except ValueError:
                    return False
            return False

        if expected_type == "boolean":
            if isinstance(value, bool):
                return True
            if isinstance(value, str):
                lowered = value.strip().lower()
                return lowered in _TRUE_VALUES or lowered in _FALSE_VALUES
            return False

        if expected_type == "object":
            return isinstance(value, dict)

        if expected_type == "array":
            return isinstance(value, (list, tuple))

        # Unknown schema types are treated as non-blocking for compatibility.
        return True

    @staticmethod
    def _value_in_choices(value: Any, choices: List[Any]) -> bool:
        """Validate membership against choice lists (case-insensitive for strings)."""
        if value in choices:
            return True

        if isinstance(value, str) and all(isinstance(item, str) for item in choices):
            normalized_choices = {item.casefold() for item in choices}
            return value.casefold() in normalized_choices

        return False

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
