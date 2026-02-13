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
    async def test_use_template_handles_escaped_braces(
        self, service_with_mock_db
    ):
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
