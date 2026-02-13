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
            },
            outputs={"ok": "boolean"},
            config_schema={
                "api_key": "string",
                "timeout_seconds": {"type": "integer", "default": 10},
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


def test_manifest_to_dict_includes_config_schema():
    plugin = StructuredSchemaPlugin()
    manifest_dict = plugin.get_manifest().to_dict()

    assert "config_schema" in manifest_dict
    assert manifest_dict["config_schema"]["api_key"] == "string"
