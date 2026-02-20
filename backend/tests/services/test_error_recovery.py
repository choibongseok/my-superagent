"""Tests for app.services.error_recovery — Smart Error Recovery UX (#225)."""

import pytest

from app.services.error_recovery import (
    ErrorCategory,
    FriendlyError,
    RecoveryAction,
    classify_error,
    error_to_dict,
)


# ── classify_error: pattern matching ────────────────────────────────


class TestClassifyErrorPatterns:
    """Verify each error category is matched by appropriate raw messages."""

    @pytest.mark.parametrize(
        "raw,expected_category",
        [
            ("Token has expired", ErrorCategory.AUTH_EXPIRED),
            ("Invalid credential provided", ErrorCategory.AUTH_EXPIRED),
            ("HTTP 401 Unauthenticated", ErrorCategory.AUTH_EXPIRED),
            ("Refresh token failed to renew", ErrorCategory.AUTH_EXPIRED),
        ],
    )
    def test_auth_expired(self, raw: str, expected_category: ErrorCategory):
        result = classify_error(raw)
        assert result.category == expected_category

    @pytest.mark.parametrize(
        "raw,expected_category",
        [
            ("Permission denied for resource", ErrorCategory.PERMISSION),
            ("HTTP 403 Forbidden", ErrorCategory.PERMISSION),
            ("Insufficient scope for operation", ErrorCategory.PERMISSION),
            ("Access denied to spreadsheet", ErrorCategory.PERMISSION),
        ],
    )
    def test_permission(self, raw: str, expected_category: ErrorCategory):
        result = classify_error(raw)
        assert result.category == expected_category

    @pytest.mark.parametrize(
        "raw,expected_category",
        [
            ("Rate limit exceeded: 429 Too Many Requests", ErrorCategory.RATE_LIMIT),
            ("Too many requests, slow down", ErrorCategory.RATE_LIMIT),
            ("429", ErrorCategory.RATE_LIMIT),
            ("Quota per minute exceeded", ErrorCategory.RATE_LIMIT),
        ],
    )
    def test_rate_limit(self, raw: str, expected_category: ErrorCategory):
        result = classify_error(raw)
        assert result.category == expected_category

    @pytest.mark.parametrize(
        "raw,expected_category",
        [
            ("Quota exceeded for project", ErrorCategory.QUOTA_EXCEEDED),
            ("Billing account not active", ErrorCategory.QUOTA_EXCEEDED),
            ("Usage limit reached for this API", ErrorCategory.QUOTA_EXCEEDED),
            ("Resource exhausted", ErrorCategory.QUOTA_EXCEEDED),
        ],
    )
    def test_quota_exceeded(self, raw: str, expected_category: ErrorCategory):
        result = classify_error(raw)
        assert result.category == expected_category

    @pytest.mark.parametrize(
        "raw,expected_category",
        [
            ("Request timeout after 30s", ErrorCategory.TIMEOUT),
            ("Operation timed out", ErrorCategory.TIMEOUT),
            ("Deadline exceeded", ErrorCategory.TIMEOUT),
            ("HTTP 504 Gateway Timeout", ErrorCategory.TIMEOUT),
            ("HTTP 408 Request Timeout", ErrorCategory.TIMEOUT),
        ],
    )
    def test_timeout(self, raw: str, expected_category: ErrorCategory):
        result = classify_error(raw)
        assert result.category == expected_category

    @pytest.mark.parametrize(
        "raw,expected_category",
        [
            ("Connection refused by server", ErrorCategory.NETWORK),
            ("Connection reset by peer", ErrorCategory.NETWORK),
            ("Network error during request", ErrorCategory.NETWORK),
            ("DNS resolution failed", ErrorCategory.NETWORK),
            ("HTTP 502 Bad Gateway", ErrorCategory.NETWORK),
            ("HTTP 503 Service Unavailable", ErrorCategory.NETWORK),
        ],
    )
    def test_network(self, raw: str, expected_category: ErrorCategory):
        result = classify_error(raw)
        assert result.category == expected_category

    @pytest.mark.parametrize(
        "raw,expected_category",
        [
            ("Google API error: invalid sheet range", ErrorCategory.GOOGLE_API),
            ("Spreadsheet not found", ErrorCategory.GOOGLE_API),
            ("Presentation not found in Drive", ErrorCategory.GOOGLE_API),
            ("Drive error: file too large", ErrorCategory.GOOGLE_API),
            ("HttpError 400: bad request", ErrorCategory.GOOGLE_API),
        ],
    )
    def test_google_api(self, raw: str, expected_category: ErrorCategory):
        result = classify_error(raw)
        assert result.category == expected_category

    @pytest.mark.parametrize(
        "raw,expected_category",
        [
            ("OpenAI API returned an error", ErrorCategory.LLM_ERROR),
            ("Anthropic service error", ErrorCategory.LLM_ERROR),
            ("LLM call failed", ErrorCategory.LLM_ERROR),
            ("Model overloaded, try later", ErrorCategory.LLM_ERROR),
            ("Context length exceeded: max 128000 tokens", ErrorCategory.LLM_ERROR),
            ("Content filter triggered", ErrorCategory.LLM_ERROR),
        ],
    )
    def test_llm_error(self, raw: str, expected_category: ErrorCategory):
        result = classify_error(raw)
        assert result.category == expected_category

    @pytest.mark.parametrize(
        "raw,expected_category",
        [
            ("Celery worker crashed", ErrorCategory.CELERY_ERROR),
            ("Worker pool exhausted", ErrorCategory.CELERY_ERROR),
            ("Task revoked", ErrorCategory.CELERY_ERROR),
            ("Broker unreachable", ErrorCategory.CELERY_ERROR),
            ("Kombu connection error", ErrorCategory.CELERY_ERROR),
        ],
    )
    def test_celery_error(self, raw: str, expected_category: ErrorCategory):
        result = classify_error(raw)
        assert result.category == expected_category

    @pytest.mark.parametrize(
        "raw,expected_category",
        [
            ("Invalid input: prompt too short", ErrorCategory.INVALID_INPUT),
            ("Validation error on field 'email'", ErrorCategory.INVALID_INPUT),
            ("HTTP 422 Unprocessable Entity", ErrorCategory.INVALID_INPUT),
            ("Malformed JSON body", ErrorCategory.INVALID_INPUT),
            ("Missing required field: task_type", ErrorCategory.INVALID_INPUT),
        ],
    )
    def test_invalid_input(self, raw: str, expected_category: ErrorCategory):
        result = classify_error(raw)
        assert result.category == expected_category

    @pytest.mark.parametrize(
        "raw,expected_category",
        [
            ("Internal server error", ErrorCategory.INTERNAL),
            ("HTTP 500", ErrorCategory.INTERNAL),
            ("Unexpected exception in handler", ErrorCategory.INTERNAL),
        ],
    )
    def test_internal(self, raw: str, expected_category: ErrorCategory):
        result = classify_error(raw)
        assert result.category == expected_category

    def test_unknown_error(self):
        result = classify_error("some completely novel error XYZ123")
        assert result.category == ErrorCategory.UNKNOWN
        assert result.original_error == "some completely novel error XYZ123"

    def test_none_error(self):
        result = classify_error(None)
        assert result.category == ErrorCategory.UNKNOWN
        assert "No error details" in result.detail

    def test_empty_error(self):
        result = classify_error("")
        assert result.category == ErrorCategory.UNKNOWN


# ── FriendlyError structure ─────────────────────────────────────────


class TestFriendlyErrorStructure:
    """Verify the structure of returned FriendlyError objects."""

    def test_has_message_and_detail(self):
        result = classify_error("Token has expired")
        assert result.message
        assert result.detail
        assert isinstance(result.message, str)
        assert isinstance(result.detail, str)

    def test_has_actions(self):
        result = classify_error("Rate limit exceeded")
        assert len(result.actions) >= 1
        for action in result.actions:
            assert isinstance(action, RecoveryAction)
            assert action.label
            assert action.action
            assert action.description

    def test_retry_after_on_rate_limit(self):
        result = classify_error("429 Too Many Requests")
        assert result.retry_after_seconds is not None
        assert result.retry_after_seconds > 0

    def test_no_retry_after_on_input_error(self):
        result = classify_error("Validation error")
        assert result.retry_after_seconds is None

    def test_original_error_preserved(self):
        raw = "Token has expired at 2026-02-20T12:00:00Z"
        result = classify_error(raw)
        assert result.original_error == raw

    def test_auto_retry_on_rate_limit(self):
        result = classify_error("429")
        auto_actions = [a for a in result.actions if a.auto]
        assert len(auto_actions) >= 1

    def test_reauth_action_on_auth_expired(self):
        result = classify_error("Token has expired")
        action_types = [a.action for a in result.actions]
        assert "reauth_google" in action_types


# ── error_to_dict serialization ─────────────────────────────────────


class TestErrorToDict:
    """Verify JSON serialization."""

    def test_basic_serialization(self):
        friendly = classify_error("Connection refused")
        d = error_to_dict(friendly)
        assert "category" in d
        assert "message" in d
        assert "detail" in d
        assert "actions" in d
        assert isinstance(d["actions"], list)

    def test_actions_have_correct_keys(self):
        friendly = classify_error("Token expired")
        d = error_to_dict(friendly)
        for action in d["actions"]:
            assert "label" in action
            assert "action" in action
            assert "description" in action
            assert "auto" in action

    def test_category_is_string(self):
        friendly = classify_error("Rate limit")
        d = error_to_dict(friendly)
        assert isinstance(d["category"], str)
        assert d["category"] == "rate_limit"

    def test_retry_after_included(self):
        friendly = classify_error("Rate limit exceeded")
        d = error_to_dict(friendly)
        assert "retry_after_seconds" in d
        assert d["retry_after_seconds"] == 60

    def test_retry_after_null_when_absent(self):
        friendly = classify_error("Invalid input: missing field")
        d = error_to_dict(friendly)
        assert d["retry_after_seconds"] is None

    def test_all_categories_have_recipes(self):
        """Every ErrorCategory should produce a valid FriendlyError."""
        from app.services.error_recovery import _RECIPES

        for cat in ErrorCategory:
            assert cat in _RECIPES, f"Missing recipe for {cat}"
            recipe = _RECIPES[cat]
            assert recipe.message
            assert recipe.detail


# ── Edge cases ──────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases and mixed signals."""

    def test_mixed_signals_picks_first_match(self):
        """When an error contains multiple keywords, the first matching pattern wins."""
        # "token expired" matches auth_expired before rate_limit
        result = classify_error("Token expired, also rate limit hit")
        assert result.category == ErrorCategory.AUTH_EXPIRED

    def test_case_insensitive(self):
        result = classify_error("TOKEN HAS EXPIRED")
        assert result.category == ErrorCategory.AUTH_EXPIRED

    def test_long_error_message(self):
        long_msg = "x" * 5000 + " connection refused " + "y" * 5000
        result = classify_error(long_msg)
        assert result.category == ErrorCategory.NETWORK

    def test_numeric_only(self):
        result = classify_error("429")
        assert result.category == ErrorCategory.RATE_LIMIT

    def test_not_found_category(self):
        result = classify_error("The file does not exist in the system")
        assert result.category == ErrorCategory.NOT_FOUND
