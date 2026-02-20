"""API tests for the /tasks/{id}/recovery endpoint (#225)."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import status
from httpx import AsyncClient


@pytest.fixture
def mock_user():
    """Create a mock authenticated user."""
    from unittest.mock import MagicMock

    user = MagicMock()
    user.id = uuid4()
    user.email = "test@example.com"
    return user


@pytest.fixture
def mock_task_failed(mock_user):
    """Create a mock failed task."""
    from unittest.mock import MagicMock

    task = MagicMock()
    task.id = uuid4()
    task.user_id = mock_user.id
    task.status = "failed"
    task.error_message = "Rate limit exceeded: 429 Too Many Requests"
    return task


@pytest.fixture
def mock_task_completed(mock_user):
    """Create a mock completed task."""
    from unittest.mock import MagicMock

    task = MagicMock()
    task.id = uuid4()
    task.user_id = mock_user.id
    task.status = "completed"
    task.error_message = None
    return task


class TestRecoveryEndpoint:
    """Tests for GET /api/v1/tasks/{task_id}/recovery."""

    def test_classify_rate_limit(self):
        from app.services.error_recovery import classify_error, error_to_dict

        friendly = classify_error("Rate limit exceeded: 429 Too Many Requests")
        d = error_to_dict(friendly)

        assert d["category"] == "rate_limit"
        assert "too quickly" in d["message"].lower() or "rate" in d["message"].lower()
        assert d["retry_after_seconds"] == 60
        assert len(d["actions"]) >= 1
        assert any(a["action"] == "retry_delayed" for a in d["actions"])

    def test_classify_auth_expired(self):
        from app.services.error_recovery import classify_error, error_to_dict

        friendly = classify_error("google.auth.exceptions.RefreshError: Token has been expired or revoked")
        d = error_to_dict(friendly)

        # Google auth RefreshError contains "Token has been expired" → auth_expired
        assert d["category"] == "auth_expired"
        assert any(a["action"] == "reauth_google" for a in d["actions"])

    def test_classify_plain_token_expired(self):
        from app.services.error_recovery import classify_error, error_to_dict

        friendly = classify_error("Token expired")
        d = error_to_dict(friendly)

        assert d["category"] == "auth_expired"

    def test_classify_timeout(self):
        from app.services.error_recovery import classify_error, error_to_dict

        friendly = classify_error("TimeoutError: operation timed out after 120s")
        d = error_to_dict(friendly)

        assert d["category"] == "timeout"
        assert any(a["action"] == "retry" for a in d["actions"])
        assert any(a["action"] == "edit_prompt" for a in d["actions"])

    def test_classify_llm(self):
        from app.services.error_recovery import classify_error, error_to_dict

        friendly = classify_error("openai.error.RateLimitError: You exceeded your current quota")
        d = error_to_dict(friendly)

        # OpenAI matches LLM error first due to pattern order
        assert d["category"] in ("llm_error", "rate_limit", "quota_exceeded")

    def test_classify_celery_failure(self):
        from app.services.error_recovery import classify_error, error_to_dict

        friendly = classify_error("Failed to queue task: Celery broker unreachable")
        d = error_to_dict(friendly)

        assert d["category"] == "celery_error"
        assert any(a["auto"] for a in d["actions"])

    def test_classify_unknown_returns_generic(self):
        from app.services.error_recovery import classify_error, error_to_dict

        friendly = classify_error("Something weird happened (code 999)")
        d = error_to_dict(friendly)

        assert d["category"] == "unknown"
        assert any(a["action"] == "retry" for a in d["actions"])

    def test_classify_none(self):
        from app.services.error_recovery import classify_error, error_to_dict

        friendly = classify_error(None)
        d = error_to_dict(friendly)

        assert d["category"] == "unknown"
        assert d["retry_after_seconds"] is None

    def test_all_categories_serializable(self):
        """Every recipe serializes cleanly to JSON-safe dict."""
        import json

        from app.services.error_recovery import _RECIPES, error_to_dict

        for cat, recipe in _RECIPES.items():
            d = error_to_dict(recipe)
            # Must be JSON serializable
            serialized = json.dumps(d)
            assert serialized
            assert d["category"] == cat.value
