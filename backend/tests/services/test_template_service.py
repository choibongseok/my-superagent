"""Tests for TemplateService template rendering behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services.template_service import TemplateService


class TestTemplateServiceUseTemplate:
    """Template rendering and output selection tests."""

    @pytest.fixture
    def service_with_mock_db(self):
        db = AsyncMock()
        db.commit = AsyncMock()
        return TemplateService(db), db

    @pytest.mark.asyncio
    async def test_use_template_renders_prompt_and_honors_output_override(
        self, service_with_mock_db
    ):
        """Explicit output_type should override template category."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Summarize {topic} for {audience}",
            category="research",
            usage_count=10,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {"topic": "AI", "audience": "engineering leaders"},
                user_id,
                output_type="slides",
            )

        assert result["template_id"] == str(template_id)
        assert result["prompt"] == "Summarize AI for engineering leaders"
        assert result["output_type"] == "slides"
        assert template.usage_count == 11
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_validates_missing_required_inputs(
        self, service_with_mock_db
    ):
        """Missing prompt variables should raise a clear validation error."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Write about {topic} in {language}",
            category="research",
            usage_count=0,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            with pytest.raises(ValueError, match="Missing template inputs: language"):
                await service.use_template(
                    template_id,
                    {"topic": "AI"},
                    user_id,
                )

        assert template.usage_count == 0
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_use_template_handles_escaped_braces(self, service_with_mock_db):
        """Escaped braces should stay literal and not count as variables."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Literal {{topic}} + real value {topic}",
            category="research",
            usage_count=3,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {"topic": "AGI safety"},
                user_id,
            )

        assert result["prompt"] == "Literal {topic} + real value AGI safety"
        assert result["output_type"] == "research"
        assert template.usage_count == 4
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_supports_nested_dot_notation_inputs(
        self, service_with_mock_db
    ):
        """Nested dictionaries should render with dot notation in templates."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Write a memo for {user.name} in {user.department}",
            category="docs",
            usage_count=0,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {
                    "user": {
                        "name": "Mina",
                        "department": "Product",
                    }
                },
                user_id,
            )

        assert result["prompt"] == "Write a memo for Mina in Product"
        assert template.usage_count == 1
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_supports_nested_list_and_dict_bracket_access(
        self, service_with_mock_db
    ):
        """List indexing and nested dict access should both render correctly."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template=(
                "Top insight: {items[0][title]} (owner: {items[0][owner][name]})"
            ),
            category="research",
            usage_count=7,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {
                    "items": [
                        {
                            "title": "Agent quality",
                            "owner": {"name": "Jin"},
                        }
                    ]
                },
                user_id,
            )

        assert result["prompt"] == "Top insight: Agent quality (owner: Jin)"
        assert template.usage_count == 8
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_applies_default_value_for_missing_optional_field(
        self, service_with_mock_db
    ):
        """Optional fields can define defaults via the field|default syntax."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Summarize {topic} for {audience|general audience}",
            category="research",
            usage_count=1,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {"topic": "agent orchestration"},
                user_id,
            )

        assert result["prompt"] == "Summarize agent orchestration for general audience"
        assert template.usage_count == 2
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_prefers_explicit_value_over_default(
        self, service_with_mock_db
    ):
        """Provided inputs should override fallback defaults."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Summarize {topic} for {audience|general audience}",
            category="research",
            usage_count=4,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {
                    "topic": "agent orchestration",
                    "audience": "backend engineers",
                },
                user_id,
            )

        assert result["prompt"] == "Summarize agent orchestration for backend engineers"
        assert template.usage_count == 5
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_supports_default_for_missing_nested_value(
        self, service_with_mock_db
    ):
        """Nested field lookups should fall back to defaults when data is absent."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Hi {user.name|there}, your plan is ready.",
            category="docs",
            usage_count=0,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {},
                user_id,
            )

        assert result["prompt"] == "Hi there, your plan is ready."
        assert template.usage_count == 1
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("provided_name", [None, "", "   "])
    async def test_use_template_applies_default_for_blank_or_null_values(
        self,
        service_with_mock_db,
        provided_name,
    ):
        """Defaults should apply when optional values are null or blank strings."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Hello {name|friend}!",
            category="docs",
            usage_count=2,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {"name": provided_name},
                user_id,
            )

        assert result["prompt"] == "Hello friend!"
        assert template.usage_count == 3
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("provided_name", [0, False])
    async def test_use_template_keeps_falsey_non_string_values_over_default(
        self,
        service_with_mock_db,
        provided_name,
    ):
        """Defaults should not replace explicit falsey values like 0 or False."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Score: {value|n/a}",
            category="docs",
            usage_count=5,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {"value": provided_name},
                user_id,
            )

        assert result["prompt"] == f"Score: {provided_name}"
        assert template.usage_count == 6
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_applies_text_transforms(self, service_with_mock_db):
        """Templates can normalize text via ->transform directives."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Audience: {audience->strip->upper}",
            category="docs",
            usage_count=0,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {"audience": "  engineering leaders  "},
                user_id,
            )

        assert result["prompt"] == "Audience: ENGINEERING LEADERS"
        assert template.usage_count == 1
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_applies_default_before_text_transform(
        self, service_with_mock_db
    ):
        """Fallback defaults should still flow through requested transforms."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Hello {name|friend->title}!",
            category="docs",
            usage_count=9,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(template_id, {}, user_id)

        assert result["prompt"] == "Hello Friend!"
        assert template.usage_count == 10
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_supports_snake_case_transform(
        self, service_with_mock_db
    ):
        """snake_case transform should normalize words and camelCase inputs."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Slug: {name->snake_case}",
            category="docs",
            usage_count=2,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {"name": "AgentHQ Launch Plan"},
                user_id,
            )

        assert result["prompt"] == "Slug: agent_hq_launch_plan"
        assert template.usage_count == 3
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_supports_kebab_case_transform(
        self, service_with_mock_db
    ):
        """kebab_case transform should normalize punctuation and spacing."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Route: {title->kebab_case}",
            category="docs",
            usage_count=0,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {"title": "  AI @ Scale: Q1 Update!  "},
                user_id,
            )

        assert result["prompt"] == "Route: ai-scale-q1-update"
        assert template.usage_count == 1
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_supports_dot_case_transform(self, service_with_mock_db):
        """dot_case transform should normalize words into dot-delimited keys."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Metric key: {name->dot_case}",
            category="docs",
            usage_count=0,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {"name": " AgentHQ launch_plan "},
                user_id,
            )

        assert result["prompt"] == "Metric key: agent.hq.launch.plan"
        assert template.usage_count == 1
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_supports_constant_case_transform(
        self, service_with_mock_db
    ):
        """constant_case transform should normalize values into screaming snake case."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Env key: {name->constant_case}",
            category="docs",
            usage_count=0,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {"name": "AgentHQ launch-plan"},
                user_id,
            )

        assert result["prompt"] == "Env key: AGENT_HQ_LAUNCH_PLAN"
        assert template.usage_count == 1
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_supports_camel_case_transform(
        self, service_with_mock_db
    ):
        """camel_case transform should normalize mixed spacing and casing."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Identifier: {name->camel_case}",
            category="docs",
            usage_count=1,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {"name": " AgentHQ launch_plan "},
                user_id,
            )

        assert result["prompt"] == "Identifier: agentHqLaunchPlan"
        assert template.usage_count == 2
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_supports_pascal_case_transform(
        self, service_with_mock_db
    ):
        """pascal_case transform should normalize punctuation and casing."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Class: {name->pascal_case}",
            category="docs",
            usage_count=0,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {"name": "agent_hq launch-plan"},
                user_id,
            )

        assert result["prompt"] == "Class: AgentHqLaunchPlan"
        assert template.usage_count == 1
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_supports_truncate_transform(self, service_with_mock_db):
        """truncate transform should cap text length while preserving readability."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Summary: {summary->strip->truncate(24)}",
            category="docs",
            usage_count=0,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {"summary": "  Build a reliable multi-region control plane  "},
                user_id,
            )

        assert result["prompt"] == "Summary: Build a reliable multi-…"
        assert template.usage_count == 1
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_supports_json_transform(self, service_with_mock_db):
        """json transform should serialize nested values into compact JSON."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Payload: {payload->json}",
            category="docs",
            usage_count=0,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {"payload": {"topic": "안전", "count": 2, "items": ["a", "b"]}},
                user_id,
            )

        assert result["prompt"] == 'Payload: {"count":2,"items":["a","b"],"topic":"안전"}'
        assert template.usage_count == 1
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_supports_pretty_json_transform(
        self, service_with_mock_db
    ):
        """json_pretty transform should serialize with indentation and newlines."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Payload:\n{payload->json_pretty}",
            category="docs",
            usage_count=4,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {"payload": {"topic": "AgentHQ", "items": ["one", "two"]}},
                user_id,
            )

        assert '"topic": "AgentHQ"' in result["prompt"]
        assert '"items": [' in result["prompt"]
        assert '\n  "items":' in result["prompt"]
        assert template.usage_count == 5
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_supports_replace_transform(self, service_with_mock_db):
        """replace transform should substitute a target substring in-place."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template='Title: {title->replace("Agent", "Assistant")}',
            category="docs",
            usage_count=1,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {"title": "Agent roadmap"},
                user_id,
            )

        assert result["prompt"] == "Title: Assistant roadmap"
        assert template.usage_count == 2
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_supports_join_transform_with_default_separator(
        self, service_with_mock_db
    ):
        """join() should join iterable values using a readable default separator."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Tags: {tags->join()}",
            category="docs",
            usage_count=0,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {"tags": ["agent", "automation", "safety"]},
                user_id,
            )

        assert result["prompt"] == "Tags: agent, automation, safety"
        assert template.usage_count == 1
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_supports_join_transform_with_custom_separator(
        self, service_with_mock_db
    ):
        """join(separator) should support CSV-quoted custom separators."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template='Owners: {owners->join(" | ")}',
            category="docs",
            usage_count=2,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {"owners": ["Mina", "Jin"]},
                user_id,
            )

        assert result["prompt"] == "Owners: Mina | Jin"
        assert template.usage_count == 3
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_supports_sort_transform_for_strings(
        self, service_with_mock_db
    ):
        """sort should normalize iterable ordering before downstream transforms."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template='Tags: {tags->sort->join(" | ")}',
            category="docs",
            usage_count=0,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {"tags": ["beta", "Alpha", "gamma"]},
                user_id,
            )

        assert result["prompt"] == "Tags: Alpha | beta | gamma"
        assert template.usage_count == 1
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_supports_sort_transform_descending_order(
        self, service_with_mock_db
    ):
        """sort(desc) should reverse deterministic ordering for iterables."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template='Priorities: {priorities->sort(desc)->join(",")}',
            category="docs",
            usage_count=1,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {"priorities": [2, 1, 5, 3]},
                user_id,
            )

        assert result["prompt"] == "Priorities: 5,3,2,1"
        assert template.usage_count == 2
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_supports_unique_sort_and_join_chaining(
        self, service_with_mock_db
    ):
        """sort should compose cleanly with unique/join transform pipelines."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template='Tags: {tags->unique->sort(desc)->join(" | ")}',
            category="docs",
            usage_count=2,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {"tags": ["agent", "safety", "agent", "automation"]},
                user_id,
            )

        assert result["prompt"] == "Tags: safety | automation | agent"
        assert template.usage_count == 3
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_supports_unique_transform_before_join(
        self, service_with_mock_db
    ):
        """unique should deduplicate iterables in first-seen order for chaining."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template='Tags: {tags->unique->join(" | ")}',
            category="docs",
            usage_count=3,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {"tags": ["agent", "safety", "agent", "automation", "safety"]},
                user_id,
            )

        assert result["prompt"] == "Tags: agent | safety | automation"
        assert template.usage_count == 4
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_supports_unique_transform_for_unhashable_values(
        self, service_with_mock_db
    ):
        """unique should handle dict/list items by equality when values are unhashable."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Records: {records->unique->json}",
            category="docs",
            usage_count=0,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {
                    "records": [
                        {"name": "Mina", "score": 1},
                        {"name": "Mina", "score": 1},
                        {"name": "Jin", "score": 2},
                    ]
                },
                user_id,
            )

        assert (
            result["prompt"]
            == 'Records: [{"name":"Mina","score":1},{"name":"Jin","score":2}]'
        )
        assert template.usage_count == 1
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_rejects_unique_transform_for_string_values(
        self, service_with_mock_db
    ):
        """unique should reject plain strings to avoid character-by-character output."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Tags: {tags->unique}",
            category="docs",
            usage_count=6,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            with pytest.raises(
                ValueError,
                match="Failed to apply template transform 'unique'",
            ):
                await service.use_template(
                    template_id,
                    {"tags": "agent"},
                    user_id,
                )

        assert template.usage_count == 6
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_use_template_rejects_sort_transform_for_string_values(
        self, service_with_mock_db
    ):
        """sort should reject plain strings to avoid character-level sorting."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Tags: {tags->sort}",
            category="docs",
            usage_count=0,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            with pytest.raises(
                ValueError,
                match="Failed to apply template transform 'sort'",
            ):
                await service.use_template(
                    template_id,
                    {"tags": "agent"},
                    user_id,
                )

        assert template.usage_count == 0
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_use_template_rejects_sort_transform_with_invalid_argument(
        self, service_with_mock_db
    ):
        """sort should allow only asc/desc argument values."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Tags: {tags->sort(random)}",
            category="docs",
            usage_count=1,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            with pytest.raises(
                ValueError,
                match=r"Failed to apply template transform 'sort\(random\)'",
            ):
                await service.use_template(
                    template_id,
                    {"tags": ["agent", "automation"]},
                    user_id,
                )

        assert template.usage_count == 1
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_use_template_rejects_join_transform_for_non_iterable_values(
        self, service_with_mock_db
    ):
        """join should fail fast when applied to non-iterable scalar values."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Owners: {owners->join()}",
            category="docs",
            usage_count=1,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            with pytest.raises(
                ValueError,
                match=r"Failed to apply template transform 'join\(\)'",
            ):
                await service.use_template(
                    template_id,
                    {"owners": 42},
                    user_id,
                )

        assert template.usage_count == 1
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_use_template_rejects_join_transform_with_too_many_arguments(
        self, service_with_mock_db
    ):
        """join should reject argument lists longer than one separator value."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template='Owners: {owners->join(", ", " and ")}',
            category="docs",
            usage_count=4,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            with pytest.raises(
                ValueError,
                match="Failed to apply template transform 'join",
            ):
                await service.use_template(
                    template_id,
                    {"owners": ["Mina", "Jin"]},
                    user_id,
                )

        assert template.usage_count == 4
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_use_template_supports_case_insensitive_transform_names(
        self, service_with_mock_db
    ):
        """Transform names should remain case-insensitive for template authors."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Slug: {name->SNAKE_CASE}",
            category="docs",
            usage_count=0,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {"name": "AgentHQ Launch Plan"},
                user_id,
            )

        assert result["prompt"] == "Slug: agent_hq_launch_plan"
        assert template.usage_count == 1
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_supports_length_transform_for_collections(
        self, service_with_mock_db
    ):
        """length should return collection size for list/string/map values."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template=(
                "Owners: {owners->length}, title chars: {title->length}, "
                "meta keys: {metadata->length}"
            ),
            category="docs",
            usage_count=0,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {
                    "owners": ["Mina", "Jin", "Alex"],
                    "title": "AgentHQ",
                    "metadata": {"priority": "high", "region": "seoul"},
                },
                user_id,
            )

        assert result["prompt"] == "Owners: 3, title chars: 7, meta keys: 2"
        assert template.usage_count == 1
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_supports_length_transform_for_generators(
        self, service_with_mock_db
    ):
        """length should count generator values even when len() is unavailable."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Queued tasks: {tasks->length}",
            category="docs",
            usage_count=1,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {"tasks": (f"task-{idx}" for idx in range(4))},
                user_id,
            )

        assert result["prompt"] == "Queued tasks: 4"
        assert template.usage_count == 2
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_supports_first_and_last_transforms(
        self, service_with_mock_db
    ):
        """first/last should pick boundary values from iterable inputs."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template=("First task: {tasks->first}, Last task: {tasks->last}"),
            category="docs",
            usage_count=0,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {
                    "tasks": ["collect requirements", "design flow", "ship v1"],
                },
                user_id,
            )

        assert (
            result["prompt"] == "First task: collect requirements, Last task: ship v1"
        )
        assert template.usage_count == 1
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_supports_last_transform_for_generators(
        self, service_with_mock_db
    ):
        """last should consume iterables like generators and return the tail value."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Final item: {items->last}",
            category="docs",
            usage_count=2,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {"items": (f"item-{index}" for index in range(4))},
                user_id,
            )

        assert result["prompt"] == "Final item: item-3"
        assert template.usage_count == 3
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_supports_reverse_transform_for_iterables(
        self, service_with_mock_db
    ):
        """reverse should invert iterable ordering before downstream transforms."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template='Roadmap: {steps->reverse->join(", ")}',
            category="docs",
            usage_count=1,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {"steps": ["Discover", "Build", "Launch"]},
                user_id,
            )

        assert result["prompt"] == "Roadmap: Launch, Build, Discover"
        assert template.usage_count == 2
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_supports_reverse_transform_for_strings(
        self, service_with_mock_db
    ):
        """reverse should support string inputs for lightweight text inversion."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Code: {code->reverse}",
            category="docs",
            usage_count=0,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {"code": "AGENT42"},
                user_id,
            )

        assert result["prompt"] == "Code: 24TNEGA"
        assert template.usage_count == 1
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_supports_slice_transform_for_strings(
        self, service_with_mock_db
    ):
        """slice(start,end) should return the expected substring window."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Snippet: {text->slice(0,5)}",
            category="docs",
            usage_count=3,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {"text": "Agentic workflows"},
                user_id,
            )

        assert result["prompt"] == "Snippet: Agent"
        assert template.usage_count == 4
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_supports_slice_transform_for_iterables(
        self, service_with_mock_db
    ):
        """slice should compose with join for list-style prompt fragments."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template='Focus: {steps->slice(1,3)->join(" | ")}',
            category="docs",
            usage_count=0,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            result = await service.use_template(
                template_id,
                {"steps": ["Discover", "Design", "Build", "Launch"]},
                user_id,
            )

        assert result["prompt"] == "Focus: Design | Build"
        assert template.usage_count == 1
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_template_rejects_slice_transform_with_invalid_arguments(
        self, service_with_mock_db
    ):
        """slice should fail fast when boundaries are not valid integers."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Window: {text->slice(two,5)}",
            category="docs",
            usage_count=4,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            with pytest.raises(
                ValueError,
                match=r"Failed to apply template transform 'slice\(two,5\)'",
            ):
                await service.use_template(
                    template_id,
                    {"text": "agent"},
                    user_id,
                )

        assert template.usage_count == 4
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_use_template_rejects_reverse_transform_for_non_iterable_values(
        self, service_with_mock_db
    ):
        """reverse should fail for scalar values that cannot be iterated."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Value: {value->reverse}",
            category="docs",
            usage_count=4,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            with pytest.raises(
                ValueError,
                match="Failed to apply template transform 'reverse'",
            ):
                await service.use_template(
                    template_id,
                    {"value": 123},
                    user_id,
                )

        assert template.usage_count == 4
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_use_template_rejects_first_transform_for_empty_iterables(
        self, service_with_mock_db
    ):
        """first should fail fast when iterable input is empty."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="First owner: {owners->first}",
            category="docs",
            usage_count=5,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            with pytest.raises(
                ValueError,
                match="Failed to apply template transform 'first'",
            ):
                await service.use_template(
                    template_id,
                    {"owners": []},
                    user_id,
                )

        assert template.usage_count == 5
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_use_template_rejects_length_transform_for_non_iterable_values(
        self, service_with_mock_db
    ):
        """length should fail fast for scalars that are neither sized nor iterable."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Count: {value->length}",
            category="docs",
            usage_count=3,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            with pytest.raises(
                ValueError,
                match="Failed to apply template transform 'length'",
            ):
                await service.use_template(
                    template_id,
                    {"value": object()},
                    user_id,
                )

        assert template.usage_count == 3
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_use_template_reports_transform_execution_errors(
        self, service_with_mock_db
    ):
        """Transform failures should bubble up as clear ValueError messages."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Payload: {payload->json}",
            category="docs",
            usage_count=3,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            with pytest.raises(
                ValueError,
                match="Failed to apply template transform 'json'",
            ):
                await service.use_template(
                    template_id,
                    {"payload": {"unsupported": {1, 2, 3}}},
                    user_id,
                )

        assert template.usage_count == 3
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_use_template_rejects_invalid_replace_arguments(
        self, service_with_mock_db
    ):
        """replace should fail fast unless exactly two arguments are provided."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Title: {title->replace(Agent)}",
            category="docs",
            usage_count=2,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            with pytest.raises(
                ValueError,
                match="Failed to apply template transform 'replace\\(Agent\\)'",
            ):
                await service.use_template(
                    template_id,
                    {"title": "Agent roadmap"},
                    user_id,
                )

        assert template.usage_count == 2
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_use_template_rejects_invalid_truncate_argument(
        self, service_with_mock_db
    ):
        """truncate should fail fast when max length is not numeric."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Summary: {summary->truncate(abc)}",
            category="docs",
            usage_count=1,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            with pytest.raises(
                ValueError,
                match=r"Failed to apply template transform 'truncate\(abc\)'",
            ):
                await service.use_template(
                    template_id,
                    {"summary": "control-plane rollout"},
                    user_id,
                )

        assert template.usage_count == 1
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_use_template_rejects_unsupported_transform(
        self, service_with_mock_db
    ):
        """Unknown transform directives should fail with a clear error."""
        service, db = service_with_mock_db
        template_id = uuid4()
        user_id = uuid4()
        template = SimpleNamespace(
            id=template_id,
            prompt_template="Name: {name->rot13}",
            category="docs",
            usage_count=2,
        )

        with patch.object(service, "get_template", AsyncMock(return_value=template)):
            with pytest.raises(
                ValueError,
                match="Unsupported template transform: rot13",
            ):
                await service.use_template(
                    template_id,
                    {"name": "Agent HQ"},
                    user_id,
                )

        assert template.usage_count == 2
        db.commit.assert_not_awaited()
