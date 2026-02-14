"""Tests for Prompt Registry."""

import pytest
import tempfile
import shutil
from app.prompts.registry import PromptRegistry, prompt_registry


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


def test_duplicate_version_requires_explicit_overwrite(temp_registry):
    """Test duplicate version registration raises unless overwrite is enabled."""
    temp_registry.register(
        name="test_prompt",
        template="Original",
        variables=[],
        version="v1",
    )

    with pytest.raises(ValueError, match="already exists"):
        temp_registry.register(
            name="test_prompt",
            template="Updated",
            variables=[],
            version="v1",
        )


def test_duplicate_version_can_be_overwritten(temp_registry):
    """Test duplicate version registration can intentionally replace content."""
    temp_registry.register(
        name="test_prompt",
        template="Original",
        variables=["foo"],
        metadata={"source": "initial"},
        version="v1",
    )

    overwritten = temp_registry.register(
        name="test_prompt",
        template="Updated",
        variables=["foo", "bar"],
        metadata={"source": "overwrite"},
        version="v1",
        allow_overwrite=True,
    )

    assert overwritten.template == "Updated"

    versions = temp_registry.list_versions("test_prompt")
    assert len(versions) == 1
    assert versions[0].template == "Updated"
    assert versions[0].variables == ["foo", "bar"]
    assert versions[0].metadata["source"] == "overwrite"


def test_non_persistent_registration_stays_in_memory_only(temp_registry):
    """Test persist=False skips file writes but keeps cache entries available."""
    temp_registry.register(
        name="ephemeral_prompt",
        template="Draft",
        variables=[],
        version="v1",
        persist=False,
    )

    assert temp_registry.get("ephemeral_prompt", version="v1") is not None
    assert not (temp_registry.storage_path / "ephemeral_prompt.json").exists()


def test_rollback_creates_new_latest_version_from_target(temp_registry):
    """Rollback should clone an older version into a new latest release."""
    temp_registry.register(
        name="incident_prompt",
        template="Stable response with {context}",
        variables=["context"],
        metadata={"quality": "stable"},
        version="v1",
    )
    temp_registry.register(
        name="incident_prompt",
        template="Broken response",
        variables=[],
        metadata={"quality": "broken"},
        version="v2",
    )

    rollback = temp_registry.rollback(
        "incident_prompt",
        target_version="v1",
        metadata={"reason": "production incident"},
    )

    assert rollback.version == "v3"
    assert rollback.template == "Stable response with {context}"
    assert rollback.variables == ["context"]
    assert rollback.metadata["quality"] == "stable"
    assert rollback.metadata["reason"] == "production incident"
    assert rollback.metadata["rollback_from_version"] == "v1"
    assert "rollback_performed_at" in rollback.metadata

    latest = temp_registry.get("incident_prompt")
    assert latest is not None
    assert latest.version == "v3"


def test_rollback_rejects_missing_target_version(temp_registry):
    """Rollback should fail fast when target version does not exist."""
    temp_registry.register(
        name="incident_prompt",
        template="Stable response",
        variables=[],
        version="v1",
    )

    with pytest.raises(ValueError, match="was not found for rollback"):
        temp_registry.rollback("incident_prompt", target_version="v9")


def test_builtin_templates_are_bootstrapped():
    """Test global prompt registry auto-loads built-in templates."""
    prompt = prompt_registry.get("research_agent", version="v1")

    assert prompt is not None
    assert prompt.version == "v1"
    assert "topic" in prompt.variables


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
