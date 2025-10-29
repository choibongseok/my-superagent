"""Tests for Prompt Registry."""

import pytest
import tempfile
import shutil
from pathlib import Path
from app.prompts.registry import PromptRegistry, PromptVersion


@pytest.fixture
def temp_registry():
    """Create a temporary registry for testing."""
    temp_dir = tempfile.mkdtemp()
    registry = PromptRegistry(storage_path=temp_dir)
    yield registry
    shutil.rmtree(temp_dir)


def test_prompt_registry_creation(temp_registry):
    """Test prompt registry initialization."""
    assert temp_registry.storage_path.exists()
    assert temp_registry._cache == {}


def test_register_prompt(temp_registry):
    """Test registering a new prompt."""
    prompt = temp_registry.register(
        name="test_prompt",
        template="This is a {variable} template",
        variables=["variable"],
        metadata={"author": "test"},
        version="v1",
    )

    assert prompt.version == "v1"
    assert prompt.template == "This is a {variable} template"
    assert "variable" in prompt.variables
    assert prompt.metadata["author"] == "test"


def test_get_prompt(temp_registry):
    """Test retrieving a prompt."""
    # Register prompt
    temp_registry.register(
        name="test_prompt",
        template="Test {var}",
        variables=["var"],
        version="v1",
    )

    # Get prompt
    prompt = temp_registry.get("test_prompt", version="v1")
    assert prompt is not None
    assert prompt.version == "v1"


def test_get_latest_prompt(temp_registry):
    """Test getting latest version of prompt."""
    # Register multiple versions
    temp_registry.register(
        name="test_prompt",
        template="Version 1",
        variables=[],
        version="v1",
    )
    temp_registry.register(
        name="test_prompt",
        template="Version 2",
        variables=[],
        version="v2",
    )

    # Get latest (should be v2)
    latest = temp_registry.get("test_prompt")
    assert latest.version == "v2"
    assert latest.template == "Version 2"


def test_list_versions(temp_registry):
    """Test listing all versions of a prompt."""
    # Register multiple versions
    for i in range(1, 4):
        temp_registry.register(
            name="test_prompt",
            template=f"Version {i}",
            variables=[],
            version=f"v{i}",
        )

    # List versions
    versions = temp_registry.list_versions("test_prompt")
    assert len(versions) == 3
    assert versions[0].version == "v1"
    assert versions[2].version == "v3"


def test_auto_version_generation(temp_registry):
    """Test automatic version generation."""
    # Register without version
    prompt1 = temp_registry.register(
        name="test_prompt",
        template="First",
        variables=[],
    )
    assert prompt1.version == "v1"

    # Register another without version
    prompt2 = temp_registry.register(
        name="test_prompt",
        template="Second",
        variables=[],
    )
    assert prompt2.version == "v2"


def test_prompt_persistence(temp_registry):
    """Test that prompts are saved to disk."""
    # Register prompt
    temp_registry.register(
        name="test_prompt",
        template="Test",
        variables=[],
        version="v1",
    )

    # Check file exists
    file_path = temp_registry.storage_path / "test_prompt.json"
    assert file_path.exists()

    # Create new registry with same path (simulate restart)
    new_registry = PromptRegistry(storage_path=str(temp_registry.storage_path))

    # Should be able to load prompt
    prompt = new_registry.get("test_prompt", version="v1")
    assert prompt is not None
    assert prompt.version == "v1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
