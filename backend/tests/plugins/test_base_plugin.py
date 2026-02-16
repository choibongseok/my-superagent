"""Tests for base plugin primitives."""

import pytest

from app.plugins.base import BasePlugin, PluginManifest


class OptionalStringSchemaPlugin(BasePlugin):
    """Plugin using legacy string schemas for inputs."""

    async def initialize(self) -> None:
        return None

    async def execute(self, inputs):
        return inputs

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="optional-string-schema",
            version="1.0.0",
            description="Test plugin",
            author="tests",
            permissions=[],
            inputs={
                "query": "string (required)",
                "locale": "string (optional)",
            },
            outputs={"ok": "boolean"},
        )


class StructuredSchemaPlugin(BasePlugin):
    """Plugin using structured dict schemas for inputs."""

    async def initialize(self) -> None:
        return None

    async def execute(self, inputs):
        return inputs

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="structured-schema",
            version="1.0.0",
            description="Test plugin",
            author="tests",
            permissions=[],
            inputs={
                "message": {"type": "string", "required": True},
                "tone": {"type": "string", "required": False},
                "priority": {
                    "type": "integer",
                    "required": False,
                },
                "mode": {
                    "type": "string",
                    "required": False,
                    "choices": ["draft", "final"],
                },
            },
            outputs={"ok": "boolean"},
            config_schema={
                "api_key": "string",
                "timeout_seconds": {"type": "integer", "default": 10},
            },
        )


class ConstrainedSchemaPlugin(BasePlugin):
    """Plugin using structured schemas with additional bounds/pattern constraints."""

    async def initialize(self) -> None:
        return None

    async def execute(self, inputs):
        return inputs

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="constrained-schema",
            version="1.0.0",
            description="Schema constraints plugin",
            author="tests",
            permissions=[],
            inputs={
                "slug": {
                    "type": "string",
                    "required": True,
                    "pattern": r"^[a-z0-9-]+$",
                },
                "priority": {
                    "type": "integer",
                    "required": False,
                    "minimum": 1,
                    "maximum": 5,
                },
                "summary": {
                    "type": "string",
                    "required": False,
                    "min_length": 5,
                    "max_length": 40,
                },
                "tags": {
                    "type": "array",
                    "required": False,
                    "max_length": 3,
                },
                "reviewers": {
                    "type": "array",
                    "required": False,
                    "min_items": 1,
                    "max_items": 2,
                },
                "metadata": {
                    "type": "object",
                    "required": False,
                    "min_properties": 1,
                    "max_properties": 2,
                },
                "temperature": {
                    "type": "number",
                    "required": False,
                    "multiple_of": 0.5,
                },
            },
            outputs={"ok": "boolean"},
        )


class InvalidMultipleOfSchemaPlugin(BasePlugin):
    """Plugin exposing invalid multiple_of schema metadata."""

    async def initialize(self) -> None:
        return None

    async def execute(self, inputs):
        return inputs

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="invalid-multiple-of",
            version="1.0.0",
            description="Invalid numeric multiple_of constraints",
            author="tests",
            permissions=[],
            inputs={
                "count": {
                    "type": "number",
                    "required": True,
                    "multiple_of": 0,
                }
            },
            outputs={"ok": "boolean"},
        )


class FlatConfigSchemaPlugin(BasePlugin):
    """Plugin with legacy flat config schema entries."""

    async def initialize(self) -> None:
        return None

    async def execute(self, inputs):
        return inputs

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="flat-config-schema",
            version="1.0.0",
            description="Config validation plugin",
            author="tests",
            permissions=[],
            inputs={"query": "string (required)"},
            outputs={"ok": "boolean"},
            config_schema={
                "api_key": "string (required)",
                "timeout_seconds": {
                    "type": "integer",
                    "required": False,
                    "default": 15,
                    "minimum": 1,
                },
                "mode": {
                    "type": "string",
                    "required": False,
                    "choices": ["safe", "fast"],
                },
            },
        )


class JsonSchemaConfigPlugin(BasePlugin):
    """Plugin with JSON-schema style config payload."""

    async def initialize(self) -> None:
        return None

    async def execute(self, inputs):
        return inputs

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="json-config-schema",
            version="1.0.0",
            description="JSON-schema config validation plugin",
            author="tests",
            permissions=[],
            inputs={"query": "string (required)"},
            outputs={"ok": "boolean"},
            config_schema={
                "type": "object",
                "properties": {
                    "api_key": {"type": "string"},
                    "retry_count": {
                        "type": "integer",
                        "default": 2,
                        "minimum": 0,
                    },
                },
                "required": ["api_key"],
            },
        )


class ConfigLengthConstraintPlugin(BasePlugin):
    """Plugin with array/object config length constraints."""

    async def initialize(self) -> None:
        return None

    async def execute(self, inputs):
        return inputs

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="config-length-constraints",
            version="1.0.0",
            description="Config length constraints plugin",
            author="tests",
            permissions=[],
            inputs={"query": "string (required)"},
            outputs={"ok": "boolean"},
            config_schema={
                "labels": {
                    "type": "array",
                    "min_items": 1,
                    "max_items": 2,
                },
                "limits": {
                    "type": "object",
                    "min_properties": 1,
                    "max_properties": 2,
                },
            },
        )


@pytest.mark.asyncio
async def test_validate_inputs_accepts_optional_string_field():
    plugin = OptionalStringSchemaPlugin()

    assert await plugin.validate_inputs({"query": "hello"}) is True


@pytest.mark.asyncio
async def test_validate_inputs_rejects_missing_required_string_field():
    plugin = OptionalStringSchemaPlugin()

    with pytest.raises(ValueError, match="Missing required inputs"):
        await plugin.validate_inputs({"locale": "ko-KR"})


@pytest.mark.asyncio
async def test_validate_inputs_accepts_structured_optional_field():
    plugin = StructuredSchemaPlugin()

    assert await plugin.validate_inputs({"message": "ping"}) is True


@pytest.mark.asyncio
async def test_validate_inputs_rejects_missing_required_structured_field():
    plugin = StructuredSchemaPlugin()

    with pytest.raises(ValueError, match="Missing required inputs"):
        await plugin.validate_inputs({"tone": "friendly"})


@pytest.mark.asyncio
async def test_validate_inputs_rejects_invalid_structured_type():
    plugin = StructuredSchemaPlugin()

    with pytest.raises(ValueError, match="Invalid type for input 'priority'"):
        await plugin.validate_inputs({"message": "ok", "priority": "high"})


@pytest.mark.asyncio
async def test_validate_inputs_accepts_numeric_string_for_integer_type():
    plugin = StructuredSchemaPlugin()

    assert await plugin.validate_inputs({"message": "ok", "priority": "10"}) is True


@pytest.mark.asyncio
async def test_validate_inputs_rejects_value_outside_choices():
    plugin = StructuredSchemaPlugin()

    with pytest.raises(ValueError, match="Invalid value for input 'mode'"):
        await plugin.validate_inputs({"message": "ok", "mode": "preview"})


@pytest.mark.asyncio
async def test_validate_inputs_accepts_case_insensitive_choice_strings():
    plugin = StructuredSchemaPlugin()

    assert await plugin.validate_inputs({"message": "ok", "mode": "FINAL"}) is True


@pytest.mark.asyncio
async def test_validate_inputs_accepts_structured_schema_constraints():
    plugin = ConstrainedSchemaPlugin()

    assert (
        await plugin.validate_inputs(
            {
                "slug": "agenthq-release-1",
                "priority": "3",
                "summary": "Launch readiness checklist",
                "tags": ["ops", "release"],
                "temperature": "21.5",
            }
        )
        is True
    )


@pytest.mark.asyncio
async def test_validate_inputs_rejects_values_outside_numeric_bounds():
    plugin = ConstrainedSchemaPlugin()

    with pytest.raises(
        ValueError,
        match="Invalid value for input 'priority': must be less than or equal to 5",
    ):
        await plugin.validate_inputs(
            {
                "slug": "agenthq-release-1",
                "priority": 6,
            }
        )


@pytest.mark.asyncio
async def test_validate_inputs_rejects_values_that_do_not_match_pattern_constraint():
    plugin = ConstrainedSchemaPlugin()

    with pytest.raises(
        ValueError,
        match="Invalid value for input 'slug': must match pattern",
    ):
        await plugin.validate_inputs(
            {
                "slug": "AgentHQ Release 1",
            }
        )


@pytest.mark.asyncio
async def test_validate_inputs_rejects_values_outside_length_bounds():
    plugin = ConstrainedSchemaPlugin()

    with pytest.raises(
        ValueError,
        match="Invalid value for input 'summary': length must be at least 5",
    ):
        await plugin.validate_inputs(
            {
                "slug": "agenthq-release-1",
                "summary": "tiny",
            }
        )

    with pytest.raises(
        ValueError,
        match="Invalid value for input 'tags': must include at most 3 items",
    ):
        await plugin.validate_inputs(
            {
                "slug": "agenthq-release-1",
                "tags": ["ops", "release", "qa", "infra"],
            }
        )


@pytest.mark.asyncio
async def test_validate_inputs_rejects_array_item_bounds_when_using_min_max_items():
    plugin = ConstrainedSchemaPlugin()

    with pytest.raises(
        ValueError,
        match="Invalid value for input 'reviewers': must include at least 1 items",
    ):
        await plugin.validate_inputs(
            {
                "slug": "agenthq-release-1",
                "reviewers": [],
            }
        )

    with pytest.raises(
        ValueError,
        match="Invalid value for input 'reviewers': must include at most 2 items",
    ):
        await plugin.validate_inputs(
            {
                "slug": "agenthq-release-1",
                "reviewers": ["alice", "bob", "charlie"],
            }
        )


@pytest.mark.asyncio
async def test_validate_inputs_rejects_object_property_bounds_when_using_min_max_properties():
    plugin = ConstrainedSchemaPlugin()

    with pytest.raises(
        ValueError,
        match="Invalid value for input 'metadata': must include at least 1 properties",
    ):
        await plugin.validate_inputs(
            {
                "slug": "agenthq-release-1",
                "metadata": {},
            }
        )

    with pytest.raises(
        ValueError,
        match="Invalid value for input 'metadata': must include at most 2 properties",
    ):
        await plugin.validate_inputs(
            {
                "slug": "agenthq-release-1",
                "metadata": {
                    "owner": "ops",
                    "stage": "prod",
                    "region": "kr",
                },
            }
        )


@pytest.mark.asyncio
async def test_validate_inputs_rejects_values_outside_multiple_of_constraint():
    plugin = ConstrainedSchemaPlugin()

    with pytest.raises(
        ValueError,
        match="Invalid value for input 'temperature': must be a multiple of 0.5",
    ):
        await plugin.validate_inputs(
            {
                "slug": "agenthq-release-1",
                "temperature": 21.3,
            }
        )


@pytest.mark.asyncio
async def test_validate_inputs_rejects_invalid_multiple_of_schema():
    plugin = InvalidMultipleOfSchemaPlugin()

    with pytest.raises(
        ValueError,
        match="Invalid schema for input 'count': multiple_of must be a number greater than 0",
    ):
        await plugin.validate_inputs({"count": 2})


def test_manifest_to_dict_includes_config_schema():
    plugin = StructuredSchemaPlugin()
    manifest_dict = plugin.get_manifest().to_dict()

    assert "config_schema" in manifest_dict
    assert manifest_dict["config_schema"]["api_key"] == "string"


def test_validate_config_rejects_missing_required_fields_for_flat_schema():
    plugin = FlatConfigSchemaPlugin()

    with pytest.raises(ValueError, match="Missing required config"):
        plugin.validate_config({"mode": "safe"})


def test_validate_config_applies_defaults_and_preserves_unknown_keys():
    plugin = FlatConfigSchemaPlugin()

    validated_config = plugin.validate_config(
        {
            "api_key": "secret-token",
            "mode": "safe",
            "extra": True,
        },
        apply_defaults=True,
    )

    assert validated_config == {
        "api_key": "secret-token",
        "timeout_seconds": 15,
        "mode": "safe",
        "extra": True,
    }


def test_validate_config_rejects_invalid_choice_values():
    plugin = FlatConfigSchemaPlugin()

    with pytest.raises(ValueError, match="Invalid value for config 'mode'"):
        plugin.validate_config(
            {
                "api_key": "secret-token",
                "mode": "turbo",
            }
        )


def test_validate_config_supports_json_schema_style_required_and_defaults():
    plugin = JsonSchemaConfigPlugin()

    validated_config = plugin.validate_config(
        {
            "api_key": "abc123",
        },
        apply_defaults=True,
    )

    assert validated_config == {
        "api_key": "abc123",
        "retry_count": 2,
    }


def test_validate_config_supports_array_and_object_size_constraints():
    plugin = ConfigLengthConstraintPlugin()

    validated_config = plugin.validate_config(
        {
            "labels": ["release"],
            "limits": {"max": 5},
        }
    )

    assert validated_config == {
        "labels": ["release"],
        "limits": {"max": 5},
    }


def test_validate_config_rejects_array_and_object_size_constraint_violations():
    plugin = ConfigLengthConstraintPlugin()

    with pytest.raises(
        ValueError,
        match="Invalid value for input 'labels': must include at least 1 items",
    ):
        plugin.validate_config(
            {
                "labels": [],
                "limits": {"max": 5},
            }
        )

    with pytest.raises(
        ValueError,
        match="Invalid value for input 'limits': must include at most 2 properties",
    ):
        plugin.validate_config(
            {
                "labels": ["release"],
                "limits": {
                    "a": 1,
                    "b": 2,
                    "c": 3,
                },
            }
        )
