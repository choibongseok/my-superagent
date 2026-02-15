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


def test_render_prompt_uses_default_variables_for_missing_values(temp_registry):
    """default_variables should provide fallback values for omitted inputs."""
    temp_registry.register(
        name="fallback_prompt",
        template="Hello {name} from {team}",
        variables=["name", "team"],
        version="v1",
    )

    rendered = temp_registry.render(
        "fallback_prompt",
        variables={"name": "Codex"},
        default_variables={"team": "AgentHQ"},
    )

    assert rendered == "Hello Codex from AgentHQ"


def test_render_prompt_prefers_runtime_variables_over_defaults(temp_registry):
    """Explicit render inputs should override fallback default_variables."""
    temp_registry.register(
        name="fallback_override_prompt",
        template="{name} @ {team}",
        variables=["name", "team"],
        version="v1",
    )

    rendered = temp_registry.render(
        "fallback_override_prompt",
        variables={"name": "Codex", "team": "Runtime Team"},
        default_variables={"team": "Default Team"},
    )

    assert rendered == "Codex @ Runtime Team"


def test_render_prompt_rejects_unexpected_default_variables(temp_registry):
    """default_variables should only include declared prompt placeholders."""
    temp_registry.register(
        name="invalid_defaults_prompt",
        template="Task: {task}",
        variables=["task"],
        version="v1",
    )

    with pytest.raises(ValueError, match="Unexpected default prompt variables"):
        temp_registry.render(
            "invalid_defaults_prompt",
            variables={"task": "Plan"},
            default_variables={"extra": "nope"},
        )


def test_render_prompt_rejects_non_mapping_default_variables(temp_registry):
    """default_variables should fail fast when callers pass invalid types."""
    temp_registry.register(
        name="non_mapping_defaults_prompt",
        template="{value}",
        variables=["value"],
        version="v1",
    )

    with pytest.raises(TypeError, match="default_variables must be a mapping"):
        temp_registry.render(
            "non_mapping_defaults_prompt",
            variables={"value": "ok"},
            default_variables=[("value", "fallback")],  # type: ignore[arg-type]
        )


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


def test_render_many_uses_shared_default_variables(temp_registry):
    """render_many should apply default_variables to every variable set."""
    temp_registry.register(
        name="bulk_defaults",
        template="{greeting}, {name}!",
        variables=["greeting", "name"],
        version="v1",
    )

    rendered = temp_registry.render_many(
        "bulk_defaults",
        [
            {"name": "Codex"},
            {"name": "Planner", "greeting": "Welcome"},
        ],
        default_variables={"greeting": "Hello"},
    )

    assert rendered == ["Hello, Codex!", "Welcome, Planner!"]


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


def test_render_many_safe_collects_per_item_failures_without_raising(temp_registry):
    """render_many_safe should preserve order while reporting per-item errors."""
    temp_registry.register(
        name="bulk_safe",
        template="{title}: {body}",
        variables=["title", "body"],
        version="v1",
    )

    rows = temp_registry.render_many_safe(
        "bulk_safe",
        [
            {"title": "ok", "body": "first"},
            {"title": "missing body"},
            "not-a-mapping",  # type: ignore[list-item]
        ],
    )

    assert rows == [
        {
            "index": 0,
            "ok": True,
            "rendered": "ok: first",
            "error": None,
        },
        {
            "index": 1,
            "ok": False,
            "rendered": None,
            "error": "Missing prompt variables for 'bulk_safe' at index 1: body",
        },
        {
            "index": 2,
            "ok": False,
            "rendered": None,
            "error": "render_many_safe expects each variable set to be a mapping",
        },
    ]


def test_render_many_safe_supports_non_strict_mode_and_default_variables(temp_registry):
    """render_many_safe should reuse render semantics for strict/default options."""
    temp_registry.register(
        name="bulk_safe_defaults",
        template="{greeting}, {name}",
        variables=["greeting", "name"],
        version="v1",
    )

    rows = temp_registry.render_many_safe(
        "bulk_safe_defaults",
        [
            {"name": "Codex", "extra": "ignored"},
            {"name": "Planner", "greeting": "Welcome"},
        ],
        strict=False,
        default_variables={"greeting": "Hello"},
    )

    assert rows == [
        {
            "index": 0,
            "ok": True,
            "rendered": "Hello, Codex",
            "error": None,
        },
        {
            "index": 1,
            "ok": True,
            "rendered": "Welcome, Planner",
            "error": None,
        },
    ]


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


def test_delete_version_removes_target_and_persists_remaining_versions(temp_registry):
    """delete_version should remove one version without touching others."""
    temp_registry.register(
        name="cleanup_prompt",
        template="v1",
        variables=[],
        version="v1",
    )
    temp_registry.register(
        name="cleanup_prompt",
        template="v2",
        variables=[],
        version="v2",
    )

    deleted = temp_registry.delete_version("cleanup_prompt", "v1")

    assert deleted is True
    versions = temp_registry.list_versions("cleanup_prompt")
    assert [version.version for version in versions] == ["v2"]

    reloaded = PromptRegistry(storage_path=str(temp_registry.storage_path))
    persisted_versions = reloaded.list_versions("cleanup_prompt")
    assert [version.version for version in persisted_versions] == ["v2"]


def test_delete_version_returns_false_when_version_is_missing(temp_registry):
    """delete_version should be a no-op when the target does not exist."""
    temp_registry.register(
        name="cleanup_prompt",
        template="v1",
        variables=[],
        version="v1",
    )

    deleted = temp_registry.delete_version("cleanup_prompt", "v9")

    assert deleted is False
    assert [
        version.version for version in temp_registry.list_versions("cleanup_prompt")
    ] == ["v1"]


def test_delete_version_removes_storage_when_last_version_is_deleted(temp_registry):
    """Deleting the final version should clear cache and remove backing file."""
    temp_registry.register(
        name="single_prompt",
        template="only",
        variables=[],
        version="v1",
    )

    deleted = temp_registry.delete_version("single_prompt", "v1")

    assert deleted is True
    assert temp_registry.list_versions("single_prompt") == []
    assert "single_prompt" not in temp_registry._cache
    assert not (temp_registry.storage_path / "single_prompt.json").exists()


def test_delete_prompt_clears_all_versions_and_returns_count(temp_registry):
    """delete_prompt should remove all versions and return how many were deleted."""
    temp_registry.register(
        name="archive_prompt",
        template="v1",
        variables=[],
        version="v1",
    )
    temp_registry.register(
        name="archive_prompt",
        template="v2",
        variables=[],
        version="v2",
    )

    removed_count = temp_registry.delete_prompt("archive_prompt")

    assert removed_count == 2
    assert temp_registry.list_versions("archive_prompt") == []
    assert not (temp_registry.storage_path / "archive_prompt.json").exists()


def test_list_prompt_names_includes_cache_and_persisted_prompts(temp_registry):
    """Name listing should merge cache-only and persisted prompt sources."""
    temp_registry.register(
        name="cache_only",
        template="draft",
        variables=[],
        version="v1",
        persist=False,
    )

    disk_registry = PromptRegistry(storage_path=str(temp_registry.storage_path))
    disk_registry.register(
        name="disk_only",
        template="stable",
        variables=[],
        version="v1",
    )

    assert temp_registry.list_prompt_names() == ["cache_only", "disk_only"]


def test_list_prompt_names_supports_filtering_and_pagination(temp_registry):
    """Name listing should support prefix/pattern filters and slicing controls."""
    temp_registry.register(
        name="agent_alpha",
        template="A",
        variables=[],
        version="v1",
    )
    temp_registry.register(
        name="agent_beta",
        template="B",
        variables=[],
        version="v1",
    )
    temp_registry.register(
        name="ops_gamma",
        template="C",
        variables=[],
        version="v1",
    )

    assert temp_registry.list_prompt_names(prefix="agent") == [
        "agent_alpha",
        "agent_beta",
    ]
    assert temp_registry.list_prompt_names(pattern="*beta") == ["agent_beta"]
    assert temp_registry.list_prompt_names(descending=True, offset=1, limit=1) == [
        "agent_beta"
    ]


def test_list_prompt_names_can_include_version_metadata(temp_registry):
    """Metadata mode should expose version counts and latest version labels."""
    temp_registry.register(
        name="incident_prompt",
        template="v1",
        variables=[],
        version="v1",
    )
    temp_registry.register(
        name="incident_prompt",
        template="v2",
        variables=[],
        version="v2",
    )

    rows = temp_registry.list_prompt_names(
        include_version_count=True,
        include_latest_version=True,
    )

    assert rows == [
        {
            "name": "incident_prompt",
            "version_count": 2,
            "latest_version": "v2",
        }
    ]


def test_list_prompt_names_supports_version_count_filters(temp_registry):
    """Version count bounds should filter prompt discovery deterministically."""
    temp_registry.register(
        name="agent_alpha",
        template="v1",
        variables=[],
        version="v1",
    )
    temp_registry.register(
        name="agent_alpha",
        template="v2",
        variables=[],
        version="v2",
    )
    temp_registry.register(
        name="agent_beta",
        template="v1",
        variables=[],
        version="v1",
    )
    temp_registry.register(
        name="agent_gamma",
        template="v1",
        variables=[],
        version="v1",
    )
    temp_registry.register(
        name="agent_gamma",
        template="v2",
        variables=[],
        version="v2",
    )
    temp_registry.register(
        name="agent_gamma",
        template="v3",
        variables=[],
        version="v3",
    )

    assert temp_registry.list_prompt_names(min_version_count=2) == [
        "agent_alpha",
        "agent_gamma",
    ]
    assert temp_registry.list_prompt_names(max_version_count=1) == ["agent_beta"]
    assert temp_registry.list_prompt_names(min_version_count=2, max_version_count=2) == [
        "agent_alpha"
    ]


def test_list_prompt_names_version_count_filters_work_with_metadata_rows(temp_registry):
    """Version count filtering should be compatible with metadata listing mode."""
    temp_registry.register(
        name="incident_primary",
        template="v1",
        variables=[],
        version="v1",
    )
    temp_registry.register(
        name="incident_primary",
        template="v2",
        variables=[],
        version="v2",
    )
    temp_registry.register(
        name="incident_secondary",
        template="v1",
        variables=[],
        version="v1",
    )

    rows = temp_registry.list_prompt_names(
        include_version_count=True,
        include_latest_version=True,
        min_version_count=2,
    )

    assert rows == [
        {
            "name": "incident_primary",
            "version_count": 2,
            "latest_version": "v2",
        }
    ]


def test_list_prompt_names_validates_arguments(temp_registry):
    """Name listing should reject invalid filter and pagination arguments."""
    with pytest.raises(ValueError, match="offset must be greater than or equal to 0"):
        temp_registry.list_prompt_names(offset=-1)

    with pytest.raises(ValueError, match="limit must be greater than 0"):
        temp_registry.list_prompt_names(limit=0)

    with pytest.raises(ValueError, match="descending must be a boolean"):
        temp_registry.list_prompt_names(descending="yes")  # type: ignore[arg-type]

    with pytest.raises(
        ValueError,
        match="include_version_count must be a boolean",
    ):
        temp_registry.list_prompt_names(
            include_version_count="yes"  # type: ignore[arg-type]
        )

    with pytest.raises(
        ValueError,
        match="include_latest_version must be a boolean",
    ):
        temp_registry.list_prompt_names(
            include_latest_version=1  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="min_version_count must be an integer"):
        temp_registry.list_prompt_names(
            min_version_count=1.5  # type: ignore[arg-type]
        )

    with pytest.raises(
        ValueError,
        match="min_version_count must be greater than 0",
    ):
        temp_registry.list_prompt_names(min_version_count=0)

    with pytest.raises(ValueError, match="max_version_count must be an integer"):
        temp_registry.list_prompt_names(
            max_version_count="2"  # type: ignore[arg-type]
        )

    with pytest.raises(
        ValueError,
        match="max_version_count must be greater than 0",
    ):
        temp_registry.list_prompt_names(max_version_count=0)

    with pytest.raises(
        ValueError,
        match="min_version_count cannot be greater than max_version_count",
    ):
        temp_registry.list_prompt_names(min_version_count=3, max_version_count=2)


def test_builtin_templates_are_bootstrapped():
    """Test global prompt registry auto-loads built-in templates."""
    prompt = prompt_registry.get("research_agent", version="v1")

    assert prompt is not None
    assert prompt.version == "v1"
    assert "topic" in prompt.variables


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
