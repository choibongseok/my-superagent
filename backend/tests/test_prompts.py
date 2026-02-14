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


def test_register_prompt_rejects_undeclared_template_variables(temp_registry):
    """Register should fail fast when placeholders are not declared."""
    with pytest.raises(ValueError, match="undeclared variables: missing"):
        temp_registry.register(
            name="invalid_prompt",
            template="Hello {name} from {missing}",
            variables=["name"],
            version="v1",
        )


def test_register_prompt_allows_nested_placeholders_with_declared_base(temp_registry):
    """Nested lookups should only require declaring the top-level variable."""
    prompt = temp_registry.register(
        name="nested_prompt",
        template="Owner: {user.name}",
        variables=["user"],
        version="v1",
    )

    assert prompt is not None
    assert prompt.variables == ["user"]


def test_register_prompt_rejects_positional_placeholders(temp_registry):
    """Prompt templates must use named placeholders for dict-style rendering."""
    with pytest.raises(ValueError, match="positional"):
        temp_registry.register(
            name="positional_prompt",
            template="Value: {}",
            variables=[],
            version="v1",
        )


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


def test_render_prompt_with_declared_variables(temp_registry):
    """Render should inject variables into the selected prompt version."""
    temp_registry.register(
        name="greeting_prompt",
        template="Hello {name}! Welcome to {team}.",
        variables=["name", "team"],
        version="v1",
    )

    rendered = temp_registry.render(
        "greeting_prompt",
        variables={"name": "Codex", "team": "AgentHQ"},
    )

    assert rendered == "Hello Codex! Welcome to AgentHQ."


def test_render_prompt_requires_all_declared_variables(temp_registry):
    """Render should fail fast when required variables are missing."""
    temp_registry.register(
        name="summary_prompt",
        template="Topic: {topic}\nAudience: {audience}",
        variables=["topic", "audience"],
        version="v1",
    )

    with pytest.raises(ValueError, match="Missing prompt variables"):
        temp_registry.render(
            "summary_prompt",
            variables={"topic": "Roadmap"},
        )


def test_render_prompt_rejects_unexpected_variables_in_strict_mode(temp_registry):
    """Strict render mode should prevent undeclared variables from slipping in."""
    temp_registry.register(
        name="strict_prompt",
        template="Only {value}",
        variables=["value"],
        version="v1",
    )

    with pytest.raises(ValueError, match="Unexpected prompt variables"):
        temp_registry.render(
            "strict_prompt",
            variables={"value": "ok", "extra": "not-allowed"},
        )


def test_render_prompt_allows_extra_variables_when_not_strict(temp_registry):
    """Non-strict mode should ignore undeclared extra values."""
    temp_registry.register(
        name="non_strict_prompt",
        template="Value: {value}",
        variables=["value"],
        version="v1",
    )

    rendered = temp_registry.render(
        "non_strict_prompt",
        variables={"value": "42", "extra": "ignored"},
        strict=False,
    )

    assert rendered == "Value: 42"


def test_render_prompt_raises_for_unknown_prompt_name(temp_registry):
    """Rendering should fail when prompt name/version does not exist."""
    with pytest.raises(ValueError, match="was not found"):
        temp_registry.render("missing_prompt", variables={"value": "x"})


def test_render_many_renders_each_variable_set_in_order(temp_registry):
    """Bulk rendering should preserve input order and values."""
    temp_registry.register(
        name="bulk_prompt",
        template="Hello {name} from {team}",
        variables=["name", "team"],
        version="v1",
    )

    rendered = temp_registry.render_many(
        "bulk_prompt",
        [
            {"name": "Codex", "team": "AgentHQ"},
            {"name": "Planner", "team": "Ops"},
        ],
    )

    assert rendered == [
        "Hello Codex from AgentHQ",
        "Hello Planner from Ops",
    ]


def test_render_many_allows_extra_variables_when_not_strict(temp_registry):
    """Non-strict render_many mode should ignore undeclared variables."""
    temp_registry.register(
        name="bulk_non_strict",
        template="Value={value}",
        variables=["value"],
        version="v1",
    )

    rendered = temp_registry.render_many(
        "bulk_non_strict",
        [
            {"value": 1, "ignored": True},
            {"value": 2, "ignored": False},
        ],
        strict=False,
    )

    assert rendered == ["Value=1", "Value=2"]


def test_render_many_reports_item_index_for_missing_variables(temp_registry):
    """Bulk errors should identify the failing variable set index."""
    temp_registry.register(
        name="bulk_missing",
        template="{title}: {body}",
        variables=["title", "body"],
        version="v1",
    )

    with pytest.raises(ValueError, match="at index 1"):
        temp_registry.render_many(
            "bulk_missing",
            [
                {"title": "ok", "body": "first"},
                {"title": "missing body"},
            ],
        )


def test_render_many_rejects_non_mapping_items(temp_registry):
    """render_many should fail fast for invalid variable entries."""
    temp_registry.register(
        name="bulk_invalid",
        template="{value}",
        variables=["value"],
        version="v1",
    )

    with pytest.raises(TypeError, match="variable set"):
        temp_registry.render_many(
            "bulk_invalid",
            [
                {"value": "ok"},
                "not-a-mapping",  # type: ignore[list-item]
            ],
        )


def test_render_many_can_render_specific_version(temp_registry):
    """Bulk rendering should support explicit version selection."""
    temp_registry.register(
        name="versioned_bulk",
        template="v1:{item}",
        variables=["item"],
        version="v1",
    )
    temp_registry.register(
        name="versioned_bulk",
        template="v2:{item}",
        variables=["item"],
        version="v2",
    )

    rendered = temp_registry.render_many(
        "versioned_bulk",
        [{"item": "A"}, {"item": "B"}],
        version="v1",
    )

    assert rendered == ["v1:A", "v1:B"]


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
