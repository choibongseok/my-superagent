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
