"""Base plugin interface for AgentHQ plugin system."""

from abc import ABC, abstractmethod
import copy
import math
import re
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
        4. Optional schema constraints (bounds, length, and regex patterns)

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

            self._validate_schema_constraints(
                key=key,
                value=value,
                schema=schema,
                expected_type=expected_type,
            )

        return True

    def validate_config(
        self,
        config: Optional[Dict[str, Any]] = None,
        *,
        apply_defaults: bool = False,
    ) -> Dict[str, Any]:
        """Validate runtime config against the manifest's ``config_schema``.

        Supports both legacy flat schema dictionaries and JSON-schema style
        payloads using top-level ``properties`` / ``required`` fields.
        Unknown config keys are preserved for backward compatibility.
        """
        resolved_config = self.config if config is None else config
        if resolved_config is None:
            resolved_config = {}

        if not isinstance(resolved_config, dict):
            raise ValueError("config must be a dictionary")

        normalized_config = dict(resolved_config)
        manifest = self.get_manifest()
        schema_fields, required_fields = self._extract_config_schema_fields(
            manifest.config_schema
        )

        missing_required_fields: list[str] = []
        for field_name in sorted(required_fields):
            if field_name in normalized_config:
                continue

            field_schema = schema_fields.get(field_name)
            if (
                apply_defaults
                and isinstance(field_schema, dict)
                and "default" in field_schema
            ):
                normalized_config[field_name] = copy.deepcopy(field_schema["default"])
                continue

            missing_required_fields.append(field_name)

        if missing_required_fields:
            raise ValueError(f"Missing required config: {set(missing_required_fields)}")

        for field_name, field_schema in schema_fields.items():
            if field_name not in normalized_config:
                if (
                    apply_defaults
                    and isinstance(field_schema, dict)
                    and "default" in field_schema
                ):
                    normalized_config[field_name] = copy.deepcopy(
                        field_schema["default"]
                    )
                continue

            field_value = normalized_config[field_name]
            if field_value is None:
                if field_name in required_fields:
                    raise ValueError(f"Config '{field_name}' cannot be null")
                continue

            expected_type = self._get_schema_type(field_schema)
            if expected_type and not self._value_matches_type(
                field_value,
                expected_type,
            ):
                raise ValueError(
                    f"Invalid type for config '{field_name}': expected {expected_type}"
                )

            choices = self._get_schema_choices(field_schema)
            if choices and not self._value_in_choices(field_value, choices):
                raise ValueError(
                    f"Invalid value for config '{field_name}': expected one of {choices}"
                )

            self._validate_schema_constraints(
                key=field_name,
                value=field_value,
                schema=field_schema,
                expected_type=expected_type,
            )

        return normalized_config

    @classmethod
    def _extract_config_schema_fields(
        cls,
        config_schema: Any,
    ) -> tuple[Dict[str, Any], set[str]]:
        """Normalize config schema payloads into fields + required set."""
        if not isinstance(config_schema, dict):
            return {}, set()

        properties = config_schema.get("properties")
        if isinstance(properties, dict):
            field_schemas: Dict[str, Any] = {}
            for key, value in properties.items():
                if not isinstance(key, str) or not key.strip():
                    raise ValueError(
                        "config_schema properties keys must be non-empty strings"
                    )
                field_schemas[key.strip()] = value

            required_fields: set[str] = set()
            raw_required = config_schema.get("required")
            if raw_required is not None:
                if not isinstance(raw_required, (list, tuple, set)):
                    raise ValueError(
                        "config_schema required must be a list of field names"
                    )
                for raw_key in raw_required:
                    if not isinstance(raw_key, str) or not raw_key.strip():
                        raise ValueError(
                            "config_schema required must contain non-empty strings"
                        )
                    required_fields.add(raw_key.strip())

            for field_name, field_schema in field_schemas.items():
                if cls._is_input_required(field_schema, default_required=False):
                    required_fields.add(field_name)

            return field_schemas, required_fields

        field_schemas: Dict[str, Any] = {}
        required_fields: set[str] = set()
        for raw_key, field_schema in config_schema.items():
            if not isinstance(raw_key, str) or not raw_key.strip():
                raise ValueError("config_schema keys must be non-empty strings")

            field_name = raw_key.strip()
            field_schemas[field_name] = field_schema
            if cls._is_input_required(field_schema):
                required_fields.add(field_name)

        return field_schemas, required_fields

    @staticmethod
    def _is_input_required(schema: Any, *, default_required: bool = True) -> bool:
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
        return default_required

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

    @classmethod
    def _validate_schema_constraints(
        cls,
        *,
        key: str,
        value: Any,
        schema: Any,
        expected_type: Optional[str],
    ) -> None:
        """Validate optional structured schema constraints for an input value."""
        if not isinstance(schema, dict):
            return

        cls._validate_numeric_bounds(
            key=key,
            value=value,
            schema=schema,
            expected_type=expected_type,
        )
        cls._validate_numeric_multiple_of(
            key=key,
            value=value,
            schema=schema,
            expected_type=expected_type,
        )
        cls._validate_length_bounds(
            key=key,
            value=value,
            schema=schema,
            expected_type=expected_type,
        )
        cls._validate_pattern_constraint(
            key=key,
            value=value,
            schema=schema,
            expected_type=expected_type,
        )

    @staticmethod
    def _coerce_numeric_constraint(
        schema: Dict[str, Any],
        *,
        key: str,
        aliases: tuple[str, ...],
        label: str,
    ) -> float | None:
        """Extract and validate a numeric constraint value from schema aliases."""
        for alias in aliases:
            if alias not in schema:
                continue

            raw_constraint = schema[alias]
            if isinstance(raw_constraint, bool):
                raise ValueError(
                    f"Invalid schema for input '{key}': {label} must be a number"
                )

            try:
                return float(raw_constraint)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Invalid schema for input '{key}': {label} must be a number"
                ) from error

        return None

    @staticmethod
    def _coerce_numeric_value(value: Any) -> float:
        """Coerce numeric payload values (including numeric strings) into floats."""
        if isinstance(value, bool):
            raise ValueError("numeric values cannot be boolean")

        if isinstance(value, (int, float)):
            return float(value)

        if isinstance(value, str):
            stripped_value = value.strip()
            if not stripped_value:
                raise ValueError("numeric values cannot be blank")
            return float(stripped_value)

        raise ValueError("numeric value expected")

    @classmethod
    def _validate_numeric_bounds(
        cls,
        *,
        key: str,
        value: Any,
        schema: Dict[str, Any],
        expected_type: Optional[str],
    ) -> None:
        """Validate minimum/maximum constraints for numeric schema fields."""
        minimum = cls._coerce_numeric_constraint(
            schema,
            key=key,
            aliases=("minimum", "min"),
            label="minimum",
        )
        maximum = cls._coerce_numeric_constraint(
            schema,
            key=key,
            aliases=("maximum", "max"),
            label="maximum",
        )

        if minimum is None and maximum is None:
            return

        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError(
                f"Invalid schema for input '{key}': minimum cannot be greater than maximum"
            )

        if expected_type not in {"integer", "number"}:
            return

        numeric_value = cls._coerce_numeric_value(value)

        if minimum is not None and numeric_value < minimum:
            raise ValueError(
                f"Invalid value for input '{key}': must be greater than or equal to {minimum:g}"
            )

        if maximum is not None and numeric_value > maximum:
            raise ValueError(
                f"Invalid value for input '{key}': must be less than or equal to {maximum:g}"
            )

    @classmethod
    def _validate_numeric_multiple_of(
        cls,
        *,
        key: str,
        value: Any,
        schema: Dict[str, Any],
        expected_type: Optional[str],
    ) -> None:
        """Validate optional numeric ``multiple_of`` constraints."""
        multiple_of = cls._coerce_numeric_constraint(
            schema,
            key=key,
            aliases=("multiple_of", "multipleOf"),
            label="multiple_of",
        )
        if multiple_of is None:
            return

        if not math.isfinite(multiple_of) or multiple_of <= 0:
            raise ValueError(
                f"Invalid schema for input '{key}': multiple_of must be a number greater than 0"
            )

        if expected_type not in {"integer", "number"}:
            return

        numeric_value = cls._coerce_numeric_value(value)
        quotient = numeric_value / multiple_of
        nearest_multiple = round(quotient)

        if not math.isclose(
            quotient,
            nearest_multiple,
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            raise ValueError(
                f"Invalid value for input '{key}': must be a multiple of {multiple_of:g}"
            )

    @staticmethod
    def _coerce_length_constraint(
        schema: Dict[str, Any],
        *,
        key: str,
        aliases: tuple[str, ...],
        label: str,
    ) -> int | None:
        """Extract and validate non-negative integer length constraints."""
        for alias in aliases:
            if alias not in schema:
                continue

            raw_constraint = schema[alias]
            if isinstance(raw_constraint, bool):
                raise ValueError(
                    f"Invalid schema for input '{key}': {label} must be a non-negative integer"
                )

            try:
                parsed_constraint = int(raw_constraint)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Invalid schema for input '{key}': {label} must be a non-negative integer"
                ) from error

            if parsed_constraint < 0:
                raise ValueError(
                    f"Invalid schema for input '{key}': {label} must be a non-negative integer"
                )

            return parsed_constraint

        return None

    @classmethod
    def _validate_length_bounds(
        cls,
        *,
        key: str,
        value: Any,
        schema: Dict[str, Any],
        expected_type: Optional[str],
    ) -> None:
        """Validate optional length/item/property constraints for sized values."""
        if expected_type == "array":
            min_aliases = ("min_items", "minItems", "min_length", "minLength")
            max_aliases = ("max_items", "maxItems", "max_length", "maxLength")
            min_label = "min_items"
            max_label = "max_items"
            min_error = "must include at least {limit} items"
            max_error = "must include at most {limit} items"
        elif expected_type == "object":
            min_aliases = (
                "min_properties",
                "minProperties",
                "min_length",
                "minLength",
            )
            max_aliases = (
                "max_properties",
                "maxProperties",
                "max_length",
                "maxLength",
            )
            min_label = "min_properties"
            max_label = "max_properties"
            min_error = "must include at least {limit} properties"
            max_error = "must include at most {limit} properties"
        else:
            min_aliases = ("min_length", "minLength")
            max_aliases = ("max_length", "maxLength")
            min_label = "min_length"
            max_label = "max_length"
            min_error = "length must be at least {limit}"
            max_error = "length must be at most {limit}"

        min_length = cls._coerce_length_constraint(
            schema,
            key=key,
            aliases=min_aliases,
            label=min_label,
        )
        max_length = cls._coerce_length_constraint(
            schema,
            key=key,
            aliases=max_aliases,
            label=max_label,
        )

        if min_length is None and max_length is None:
            return

        if (
            min_length is not None
            and max_length is not None
            and min_length > max_length
        ):
            raise ValueError(
                f"Invalid schema for input '{key}': {min_label} cannot be greater than {max_label}"
            )

        try:
            value_length = len(value)
        except TypeError as error:
            raise ValueError(
                f"Invalid value for input '{key}': does not support length constraints"
            ) from error

        if min_length is not None and value_length < min_length:
            raise ValueError(
                f"Invalid value for input '{key}': {min_error.format(limit=min_length)}"
            )

        if max_length is not None and value_length > max_length:
            raise ValueError(
                f"Invalid value for input '{key}': {max_error.format(limit=max_length)}"
            )

    @staticmethod
    def _validate_pattern_constraint(
        *,
        key: str,
        value: Any,
        schema: Dict[str, Any],
        expected_type: Optional[str],
    ) -> None:
        """Validate regex pattern constraints for string values."""
        if "pattern" not in schema:
            return

        raw_pattern = schema["pattern"]
        if not isinstance(raw_pattern, str) or not raw_pattern:
            raise ValueError(
                f"Invalid schema for input '{key}': pattern must be a non-empty string"
            )

        if expected_type not in {None, "string"}:
            return

        if not isinstance(value, str):
            raise ValueError(
                f"Invalid value for input '{key}': pattern constraints require a string"
            )

        try:
            compiled_pattern = re.compile(raw_pattern)
        except re.error as error:
            raise ValueError(
                f"Invalid schema for input '{key}': pattern is not a valid regular expression"
            ) from error

        if compiled_pattern.search(value) is None:
            raise ValueError(
                f"Invalid value for input '{key}': must match pattern {raw_pattern!r}"
            )

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
