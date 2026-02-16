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


class NullableSchemaPlugin(BasePlugin):
    """Plugin using nullable structured schema fields."""

    async def initialize(self) -> None:
        return None

    async def execute(self, inputs):
        return inputs

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="nullable-schema",
            version="1.0.0",
            description="Nullable schema plugin",
            author="tests",
            permissions=[],
            inputs={
                "required_nullable": {
                    "type": "string",
                    "required": True,
                    "nullable": True,
                },
                "required_nullable_union": {
                    "type": ["string", "null"],
                    "required": True,
                },
                "required_strict": {
                    "type": "string",
                    "required": True,
                },
            },
            outputs={"ok": "boolean"},
            config_schema={
                "api_key": {
                    "type": "string",
                    "required": True,
                    "nullable": True,
                },
                "fallback_model": {
                    "type": ["string", "null"],
                    "required": False,
                },
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


class ExclusiveBoundsSchemaPlugin(BasePlugin):
    """Plugin using exclusive numeric bound constraints."""

    async def initialize(self) -> None:
        return None

    async def execute(self, inputs):
        return inputs

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="exclusive-bounds",
            version="1.0.0",
            description="Exclusive numeric bounds plugin",
            author="tests",
            permissions=[],
            inputs={
                "confidence": {
                    "type": "number",
                    "required": True,
                    "exclusiveMinimum": 0,
                    "exclusiveMaximum": 1,
                },
                "attempts": {
                    "type": "integer",
                    "required": False,
                    "exclusive_minimum": 0,
                    "exclusive_maximum": 4,
                },
            },
            outputs={"ok": "boolean"},
        )


class InvalidExclusiveBoundsSchemaPlugin(BasePlugin):
    """Plugin exposing conflicting exclusive numeric bounds metadata."""

    async def initialize(self) -> None:
        return None

    async def execute(self, inputs):
        return inputs

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="invalid-exclusive-bounds",
            version="1.0.0",
            description="Invalid exclusive numeric bounds constraints",
            author="tests",
            permissions=[],
            inputs={
                "confidence": {
                    "type": "number",
                    "required": True,
                    "minimum": 0,
                    "exclusiveMaximum": 0,
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


class UniqueItemsSchemaPlugin(BasePlugin):
    """Plugin using unique-items array constraints."""

    async def initialize(self) -> None:
        return None

    async def execute(self, inputs):
        return inputs

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="unique-items-schema",
            version="1.0.0",
            description="Array uniqueness constraints plugin",
            author="tests",
            permissions=[],
            inputs={
                "tag_ids": {
                    "type": "array",
                    "required": True,
                    "unique_items": True,
                }
            },
            outputs={"ok": "boolean"},
        )


class InvalidUniqueItemsSchemaPlugin(BasePlugin):
    """Plugin exposing invalid unique_items schema metadata."""

    async def initialize(self) -> None:
        return None

    async def execute(self, inputs):
        return inputs

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="invalid-unique-items",
            version="1.0.0",
            description="Invalid array uniqueness constraints",
            author="tests",
            permissions=[],
            inputs={
                "tag_ids": {
                    "type": "array",
                    "required": True,
                    "uniqueItems": "yes",
                }
            },
            outputs={"ok": "boolean"},
        )


class FormatSchemaPlugin(BasePlugin):
    """Plugin using format constraints for string inputs."""

    async def initialize(self) -> None:
        return None

    async def execute(self, inputs):
        return inputs

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="format-schema",
            version="1.0.0",
            description="Format constraints plugin",
            author="tests",
            permissions=[],
            inputs={
                "email": {
                    "type": "string",
                    "required": True,
                    "format": "email",
                },
                "callback_url": {
                    "type": "string",
                    "required": False,
                    "format": "uri",
                },
                "request_id": {
                    "type": "string",
                    "required": False,
                    "format": "uuid",
                },
                "started_at": {
                    "type": "string",
                    "required": False,
                    "format": "date-time",
                },
            },
            outputs={"ok": "boolean"},
        )


class InvalidFormatSchemaPlugin(BasePlugin):
    """Plugin exposing invalid format schema metadata."""

    async def initialize(self) -> None:
        return None

    async def execute(self, inputs):
        return inputs

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="invalid-format-schema",
            version="1.0.0",
            description="Invalid format constraints plugin",
            author="tests",
            permissions=[],
            inputs={
                "email": {
                    "type": "string",
                    "required": True,
                    "format": [],
                },
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


class ConfigFormatConstraintPlugin(BasePlugin):
    """Plugin with format constraints in config schema."""

    async def initialize(self) -> None:
        return None

    async def execute(self, inputs):
        return inputs

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="config-format-constraints",
            version="1.0.0",
            description="Config format constraints plugin",
            author="tests",
            permissions=[],
            inputs={"query": "string (required)"},
            outputs={"ok": "boolean"},
            config_schema={
                "owner_email": {
                    "type": "string",
                    "required": True,
                    "format": "email",
                },
                "webhook_url": {
                    "type": "string",
                    "required": True,
                    "format": "uri",
                },
            },
        )


class ExclusiveBoundsConfigPlugin(BasePlugin):
    """Plugin with exclusive numeric bounds in config schema."""

    async def initialize(self) -> None:
        return None

    async def execute(self, inputs):
        return inputs

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="exclusive-bounds-config",
            version="1.0.0",
            description="Exclusive numeric config bounds plugin",
            author="tests",
            permissions=[],
            inputs={"query": "string (required)"},
            outputs={"ok": "boolean"},
            config_schema={
                "threshold": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "exclusiveMaximum": 1,
                }
            },
        )


class UniqueItemsConfigPlugin(BasePlugin):
    """Plugin with unique-items array constraints in config schema."""

    async def initialize(self) -> None:
        return None

    async def execute(self, inputs):
        return inputs

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="unique-items-config",
            version="1.0.0",
            description="Unique items config constraints plugin",
            author="tests",
            permissions=[],
            inputs={"query": "string (required)"},
            outputs={"ok": "boolean"},
            config_schema={
                "labels": {
                    "type": "array",
                    "unique_items": True,
                }
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
async def test_validate_inputs_accepts_null_for_required_nullable_fields():
    plugin = NullableSchemaPlugin()

    assert (
        await plugin.validate_inputs(
            {
                "required_nullable": None,
                "required_nullable_union": None,
                "required_strict": "ready",
            }
        )
        is True
    )


@pytest.mark.asyncio
async def test_validate_inputs_still_requires_nullable_fields_to_be_present():
    plugin = NullableSchemaPlugin()

    with pytest.raises(ValueError, match="Missing required inputs"):
        await plugin.validate_inputs(
            {
                "required_strict": "ready",
            }
        )


@pytest.mark.asyncio
async def test_validate_inputs_rejects_null_for_non_nullable_required_fields():
    plugin = NullableSchemaPlugin()

    with pytest.raises(ValueError, match="Input 'required_strict' cannot be null"):
        await plugin.validate_inputs(
            {
                "required_nullable": "ok",
                "required_nullable_union": "ok",
                "required_strict": None,
            }
        )


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
async def test_validate_inputs_accepts_values_within_exclusive_bounds():
    plugin = ExclusiveBoundsSchemaPlugin()

    assert (
        await plugin.validate_inputs(
            {
                "confidence": 0.5,
                "attempts": 2,
            }
        )
        is True
    )


@pytest.mark.asyncio
async def test_validate_inputs_rejects_values_at_exclusive_boundaries():
    plugin = ExclusiveBoundsSchemaPlugin()

    with pytest.raises(
        ValueError,
        match="Invalid value for input 'confidence': must be greater than 0",
    ):
        await plugin.validate_inputs({"confidence": 0})

    with pytest.raises(
        ValueError,
        match="Invalid value for input 'confidence': must be less than 1",
    ):
        await plugin.validate_inputs({"confidence": 1})

    with pytest.raises(
        ValueError,
        match="Invalid value for input 'attempts': must be greater than 0",
    ):
        await plugin.validate_inputs({"confidence": 0.5, "attempts": 0})


@pytest.mark.asyncio
async def test_validate_inputs_rejects_conflicting_exclusive_bounds_schema():
    plugin = InvalidExclusiveBoundsSchemaPlugin()

    with pytest.raises(
        ValueError,
        match=(
            "Invalid schema for input 'confidence': "
            "numeric lower bounds conflict with upper bounds"
        ),
    ):
        await plugin.validate_inputs({"confidence": 0})


@pytest.mark.asyncio
async def test_validate_inputs_rejects_invalid_multiple_of_schema():
    plugin = InvalidMultipleOfSchemaPlugin()

    with pytest.raises(
        ValueError,
        match="Invalid schema for input 'count': multiple_of must be a number greater than 0",
    ):
        await plugin.validate_inputs({"count": 2})


@pytest.mark.asyncio
async def test_validate_inputs_accepts_unique_array_items_constraint():
    plugin = UniqueItemsSchemaPlugin()

    assert await plugin.validate_inputs({"tag_ids": ["ops", "release"]}) is True


@pytest.mark.asyncio
async def test_validate_inputs_rejects_duplicate_array_items_when_unique_items_enabled():
    plugin = UniqueItemsSchemaPlugin()

    with pytest.raises(
        ValueError,
        match="Invalid value for input 'tag_ids': array items must be unique",
    ):
        await plugin.validate_inputs(
            {
                "tag_ids": [
                    {"name": "ops"},
                    {"name": "ops"},
                ]
            }
        )


@pytest.mark.asyncio
async def test_validate_inputs_rejects_invalid_unique_items_schema_values():
    plugin = InvalidUniqueItemsSchemaPlugin()

    with pytest.raises(
        ValueError,
        match="Invalid schema for input 'tag_ids': unique_items must be a boolean",
    ):
        await plugin.validate_inputs({"tag_ids": ["ops"]})


@pytest.mark.asyncio
async def test_validate_inputs_accepts_supported_format_constraints():
    plugin = FormatSchemaPlugin()

    assert (
        await plugin.validate_inputs(
            {
                "email": "owner@example.com",
                "callback_url": "https://example.com/hooks/agenthq",
                "request_id": "3f84b64a-872a-4604-b577-f8000e4939b7",
                "started_at": "2026-02-16T20:00:00Z",
            }
        )
        is True
    )


@pytest.mark.asyncio
async def test_validate_inputs_rejects_invalid_format_values():
    plugin = FormatSchemaPlugin()

    with pytest.raises(
        ValueError,
        match="Invalid value for input 'email': must be a valid email",
    ):
        await plugin.validate_inputs({"email": "owner-at-example.com"})

    with pytest.raises(
        ValueError,
        match="Invalid value for input 'request_id': must be a valid uuid",
    ):
        await plugin.validate_inputs(
            {
                "email": "owner@example.com",
                "request_id": "not-a-uuid",
            }
        )


@pytest.mark.asyncio
async def test_validate_inputs_rejects_invalid_format_schema_values():
    plugin = InvalidFormatSchemaPlugin()

    with pytest.raises(
        ValueError,
        match="Invalid schema for input 'email': format must be a non-empty string",
    ):
        await plugin.validate_inputs({"email": "owner@example.com"})


def test_manifest_to_dict_includes_config_schema():
    plugin = StructuredSchemaPlugin()
    manifest_dict = plugin.get_manifest().to_dict()

    assert "config_schema" in manifest_dict
    assert manifest_dict["config_schema"]["api_key"] == "string"


def test_validate_config_rejects_missing_required_fields_for_flat_schema():
    plugin = FlatConfigSchemaPlugin()

    with pytest.raises(ValueError, match="Missing required config"):
        plugin.validate_config({"mode": "safe"})


def test_validate_config_accepts_null_for_nullable_required_and_optional_fields():
    plugin = NullableSchemaPlugin()

    validated_config = plugin.validate_config(
        {
            "api_key": None,
            "fallback_model": None,
        }
    )

    assert validated_config == {
        "api_key": None,
        "fallback_model": None,
    }


def test_validate_config_rejects_null_for_non_nullable_required_fields():
    plugin = FlatConfigSchemaPlugin()

    with pytest.raises(ValueError, match="Config 'api_key' cannot be null"):
        plugin.validate_config(
            {
                "api_key": None,
                "mode": "safe",
            }
        )


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


def test_validate_config_supports_format_constraints():
    plugin = ConfigFormatConstraintPlugin()

    validated_config = plugin.validate_config(
        {
            "owner_email": "ops@example.com",
            "webhook_url": "https://example.com/webhooks/release",
        }
    )

    assert validated_config == {
        "owner_email": "ops@example.com",
        "webhook_url": "https://example.com/webhooks/release",
    }


def test_validate_config_rejects_format_constraint_violations():
    plugin = ConfigFormatConstraintPlugin()

    with pytest.raises(
        ValueError,
        match="Invalid value for input 'owner_email': must be a valid email",
    ):
        plugin.validate_config(
            {
                "owner_email": "ops-at-example.com",
                "webhook_url": "https://example.com/webhooks/release",
            }
        )

    with pytest.raises(
        ValueError,
        match="Invalid value for input 'webhook_url': must be a valid uri",
    ):
        plugin.validate_config(
            {
                "owner_email": "ops@example.com",
                "webhook_url": "example.com/webhooks/release",
            }
        )


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


def test_validate_config_supports_exclusive_numeric_bounds():
    plugin = ExclusiveBoundsConfigPlugin()

    validated_config = plugin.validate_config(
        {
            "threshold": 0.5,
        }
    )

    assert validated_config == {
        "threshold": 0.5,
    }


def test_validate_config_rejects_values_at_exclusive_numeric_bounds():
    plugin = ExclusiveBoundsConfigPlugin()

    with pytest.raises(
        ValueError,
        match="Invalid value for input 'threshold': must be greater than 0",
    ):
        plugin.validate_config(
            {
                "threshold": 0,
            }
        )

    with pytest.raises(
        ValueError,
        match="Invalid value for input 'threshold': must be less than 1",
    ):
        plugin.validate_config(
            {
                "threshold": 1,
            }
        )


def test_validate_config_supports_unique_items_array_constraint():
    plugin = UniqueItemsConfigPlugin()

    validated_config = plugin.validate_config(
        {
            "labels": ["release", "qa"],
        }
    )

    assert validated_config == {
        "labels": ["release", "qa"],
    }


def test_validate_config_rejects_duplicates_when_unique_items_constraint_enabled():
    plugin = UniqueItemsConfigPlugin()

    with pytest.raises(
        ValueError,
        match="Invalid value for input 'labels': array items must be unique",
    ):
        plugin.validate_config(
            {
                "labels": ["release", "release"],
            }
        )
