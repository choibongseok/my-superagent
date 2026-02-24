"""Smart Error Recovery UX (#225).

Maps technical error messages to user-friendly messages with actionable
recovery suggestions.  Designed to reduce user frustration and support
ticket volume by giving users clear next steps when tasks fail.

Usage:
    from app.services.error_recovery import classify_error

    friendly = classify_error("Rate limit exceeded: 429 Too Many Requests")
    # friendly.message  -> "We're sending requests too quickly..."
    # friendly.actions  -> [{"label": "Wait & Retry", "action": "retry", ...}]
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class ErrorCategory(str, Enum):
    """Broad error categories for telemetry and grouping."""

    AUTH_EXPIRED = "auth_expired"
    RATE_LIMIT = "rate_limit"
    QUOTA_EXCEEDED = "quota_exceeded"
    NETWORK = "network"
    TIMEOUT = "timeout"
    INVALID_INPUT = "invalid_input"
    GOOGLE_API = "google_api"
    LLM_ERROR = "llm_error"
    CELERY_ERROR = "celery_error"
    PERMISSION = "permission"
    NOT_FOUND = "not_found"
    INTERNAL = "internal"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RecoveryAction:
    """A single recovery action the user (or frontend) can take."""

    label: str
    action: str  # machine-readable action key
    description: str
    auto: bool = False  # if True, frontend can auto-execute


@dataclass(frozen=True)
class FriendlyError:
    """User-facing error with actionable recovery steps."""

    category: ErrorCategory
    message: str
    detail: str
    actions: list[RecoveryAction] = field(default_factory=list)
    retry_after_seconds: int | None = None
    original_error: str | None = None


# ── Pattern-based classifier ────────────────────────────────────────

_PATTERNS: list[tuple[re.Pattern[str], ErrorCategory]] = [
    # ── Specific services first (before generic network/auth) ───────
    # Celery / worker (must precede network — "broker unreachable", "kombu connection")
    (re.compile(r"(celery|worker\s*pool|task.*revoked|broker|kombu)", re.I), ErrorCategory.CELERY_ERROR),
    # LLM / AI (must precede rate_limit — "anthropic rate limit")
    (re.compile(r"(openai|anthropic|llm|model.*overloaded|context.*length|max.*tokens|content.*filter)", re.I), ErrorCategory.LLM_ERROR),
    # Google API specifics (must precede not_found — "spreadsheet not found")
    (re.compile(r"(google.*api.*error|spreadsheet.*not\s*found|presentation.*not\s*found|drive.*error|HttpError\s*4)", re.I), ErrorCategory.GOOGLE_API),
    # Auth / credentials (must precede internal — "RefreshError" contains "error")
    (re.compile(r"(token\s*(has\s*)?(been\s*)?(expired|revoked)|invalid.*credential|401|unauthenticated|refresh.*token|RefreshError)", re.I), ErrorCategory.AUTH_EXPIRED),
    (re.compile(r"(permission\s*denied|403|forbidden|insufficient.*scope|access.*denied)", re.I), ErrorCategory.PERMISSION),
    # Rate limiting
    (re.compile(r"(rate\s*limit|429|too\s*many\s*requests|quota.*per.*minute)", re.I), ErrorCategory.RATE_LIMIT),
    (re.compile(r"(quota\s*(exceeded|exhausted)|billing|usage\s*limit|resource\s*exhausted)", re.I), ErrorCategory.QUOTA_EXCEEDED),
    # Network / timeout
    (re.compile(r"(timeout|timed?\s*out|deadline\s*exceeded|504|408)", re.I), ErrorCategory.TIMEOUT),
    (re.compile(r"(connection\s*(refused|reset|error|closed)|network\s*error|dns|unreachable|502|503)", re.I), ErrorCategory.NETWORK),
    # Not found
    (re.compile(r"(not\s*found|404|does\s*not\s*exist|no\s*such)", re.I), ErrorCategory.NOT_FOUND),
    # Input validation
    (re.compile(r"(invalid.*input|validation.*error|422|malformed|missing.*required|field.*required)", re.I), ErrorCategory.INVALID_INPUT),
    # Internal catch-all (most generic — must be last)
    (re.compile(r"(internal.*server|500|unexpected|traceback)", re.I), ErrorCategory.INTERNAL),
]

# ── Recovery recipes per category ───────────────────────────────────

_RECIPES: dict[ErrorCategory, FriendlyError] = {
    ErrorCategory.AUTH_EXPIRED: FriendlyError(
        category=ErrorCategory.AUTH_EXPIRED,
        message="Your session has expired.",
        detail="Your Google account authorization needs to be refreshed. This usually happens after a period of inactivity.",
        actions=[
            RecoveryAction(
                label="Reconnect Google Account",
                action="reauth_google",
                description="Sign in again to refresh your credentials.",
            ),
            RecoveryAction(
                label="Retry Task",
                action="retry",
                description="Try again after reconnecting.",
            ),
        ],
    ),
    ErrorCategory.PERMISSION: FriendlyError(
        category=ErrorCategory.PERMISSION,
        message="Access denied.",
        detail="The operation requires permissions that aren't currently granted. You may need to re-authorize with additional scopes.",
        actions=[
            RecoveryAction(
                label="Review Permissions",
                action="reauth_google",
                description="Re-authorize to grant the needed permissions.",
            ),
        ],
    ),
    ErrorCategory.RATE_LIMIT: FriendlyError(
        category=ErrorCategory.RATE_LIMIT,
        message="We're sending requests too quickly.",
        detail="The service is temporarily limiting our request rate. This resolves on its own within a minute or two.",
        actions=[
            RecoveryAction(
                label="Wait & Retry",
                action="retry_delayed",
                description="Automatically retry in 60 seconds.",
                auto=True,
            ),
        ],
        retry_after_seconds=60,
    ),
    ErrorCategory.QUOTA_EXCEEDED: FriendlyError(
        category=ErrorCategory.QUOTA_EXCEEDED,
        message="Usage limit reached.",
        detail="The daily or monthly API quota has been exceeded. Quotas typically reset at midnight Pacific Time.",
        actions=[
            RecoveryAction(
                label="Check Usage",
                action="open_dashboard",
                description="View your current usage on the analytics dashboard.",
            ),
            RecoveryAction(
                label="Try Tomorrow",
                action="dismiss",
                description="Quotas reset daily — try again after the reset.",
            ),
        ],
    ),
    ErrorCategory.TIMEOUT: FriendlyError(
        category=ErrorCategory.TIMEOUT,
        message="The operation took too long.",
        detail="The task couldn't complete within the time limit. This can happen with very complex requests or when external services are slow.",
        actions=[
            RecoveryAction(
                label="Retry",
                action="retry",
                description="Try again — it may work on a second attempt.",
            ),
            RecoveryAction(
                label="Simplify Request",
                action="edit_prompt",
                description="Try a shorter or simpler prompt to reduce processing time.",
            ),
        ],
    ),
    ErrorCategory.NETWORK: FriendlyError(
        category=ErrorCategory.NETWORK,
        message="Connection problem.",
        detail="We couldn't reach the external service. This is usually a temporary network issue.",
        actions=[
            RecoveryAction(
                label="Retry",
                action="retry",
                description="Try again in a moment.",
                auto=True,
            ),
        ],
        retry_after_seconds=15,
    ),
    ErrorCategory.GOOGLE_API: FriendlyError(
        category=ErrorCategory.GOOGLE_API,
        message="Google Workspace error.",
        detail="Something went wrong while communicating with Google's API. The document or spreadsheet may have been moved or deleted.",
        actions=[
            RecoveryAction(
                label="Retry",
                action="retry",
                description="Try the operation again.",
            ),
            RecoveryAction(
                label="Reconnect Google",
                action="reauth_google",
                description="Re-authorize if the problem persists.",
            ),
        ],
    ),
    ErrorCategory.LLM_ERROR: FriendlyError(
        category=ErrorCategory.LLM_ERROR,
        message="AI model issue.",
        detail="The language model encountered a problem processing your request. This may be due to high demand or an overly complex prompt.",
        actions=[
            RecoveryAction(
                label="Retry",
                action="retry",
                description="Try again — model availability fluctuates.",
            ),
            RecoveryAction(
                label="Simplify Prompt",
                action="edit_prompt",
                description="A shorter prompt may avoid context length limits.",
            ),
        ],
        retry_after_seconds=10,
    ),
    ErrorCategory.CELERY_ERROR: FriendlyError(
        category=ErrorCategory.CELERY_ERROR,
        message="Background processing error.",
        detail="The task processing queue encountered an issue. This typically resolves automatically as workers restart.",
        actions=[
            RecoveryAction(
                label="Retry",
                action="retry",
                description="Re-queue the task.",
                auto=True,
            ),
        ],
        retry_after_seconds=30,
    ),
    ErrorCategory.INVALID_INPUT: FriendlyError(
        category=ErrorCategory.INVALID_INPUT,
        message="Invalid request.",
        detail="Something in the request wasn't quite right. Check the prompt and any metadata fields.",
        actions=[
            RecoveryAction(
                label="Edit & Retry",
                action="edit_prompt",
                description="Fix the input and try again.",
            ),
        ],
    ),
    ErrorCategory.NOT_FOUND: FriendlyError(
        category=ErrorCategory.NOT_FOUND,
        message="Resource not found.",
        detail="The requested item doesn't exist or may have been deleted.",
        actions=[
            RecoveryAction(
                label="Go to Tasks",
                action="navigate_tasks",
                description="Return to your task list.",
            ),
        ],
    ),
    ErrorCategory.INTERNAL: FriendlyError(
        category=ErrorCategory.INTERNAL,
        message="Something went wrong on our end.",
        detail="An unexpected error occurred. Our team is notified automatically. Please try again.",
        actions=[
            RecoveryAction(
                label="Retry",
                action="retry",
                description="Try the operation again.",
            ),
        ],
    ),
    ErrorCategory.UNKNOWN: FriendlyError(
        category=ErrorCategory.UNKNOWN,
        message="An unexpected error occurred.",
        detail="We couldn't determine the exact cause. Please try again, and if the problem persists, contact support.",
        actions=[
            RecoveryAction(
                label="Retry",
                action="retry",
                description="Try the operation again.",
            ),
        ],
    ),
}


def classify_error(raw_error: str | None) -> FriendlyError:
    """Classify a raw error string into a user-friendly error with recovery actions.

    Args:
        raw_error: The technical error message (e.g. from task.error_message).

    Returns:
        FriendlyError with user-friendly message, detail, and actionable steps.
    """
    if not raw_error:
        return FriendlyError(
            category=ErrorCategory.UNKNOWN,
            message="An error occurred.",
            detail="No error details are available.",
            actions=_RECIPES[ErrorCategory.UNKNOWN].actions,
            original_error=raw_error,
        )

    text = str(raw_error)
    for pattern, category in _PATTERNS:
        if pattern.search(text):
            recipe = _RECIPES[category]
            return FriendlyError(
                category=recipe.category,
                message=recipe.message,
                detail=recipe.detail,
                actions=recipe.actions,
                retry_after_seconds=recipe.retry_after_seconds,
                original_error=text,
            )

    # Fallback
    fallback = _RECIPES[ErrorCategory.UNKNOWN]
    return FriendlyError(
        category=fallback.category,
        message=fallback.message,
        detail=fallback.detail,
        actions=fallback.actions,
        original_error=text,
    )


def error_to_dict(friendly: FriendlyError) -> dict:
    """Serialize a FriendlyError to a JSON-safe dict for API responses."""
    return {
        "category": friendly.category.value,
        "message": friendly.message,
        "detail": friendly.detail,
        "actions": [
            {
                "label": a.label,
                "action": a.action,
                "description": a.description,
                "auto": a.auto,
            }
            for a in friendly.actions
        ],
        "retry_after_seconds": friendly.retry_after_seconds,
    }


# ── Recovery deck helper for /tasks/{id}/recovery-deck ────────────

_RECOVERY_DECK_PROFILES = {
    ErrorCategory.AUTH_EXPIRED: {
        "qa_failure_class": "google_auth",
        "failure_stage": "workspace_auth",
        "checklist": [
            "Reconnect Google account from Settings",
            "Verify app has required Workspace scopes",
            "Retry once auth token refresh succeeds",
        ],
        "rewrite_suggestions": [
            "Keep the same prompt but retry after re-auth",
            "Switch to a simpler prompt that avoids advanced permissions",
        ],
    },
    ErrorCategory.PERMISSION: {
        "qa_failure_class": "google_api",
        "failure_stage": "workspace_permissions",
        "checklist": [
            "Check the target file/folder exists",
            "Re-authorize with file-level permissions",
            "Retry operation after confirming Google workspace scope",
        ],
        "rewrite_suggestions": [
            "Ask for explicit file name and avoid deprecated paths",
            "Try again after granting Drive/Docs read-write access",
        ],
    },
    ErrorCategory.GOOGLE_API: {
        "qa_failure_class": "google_api",
        "failure_stage": "workspace_apis",
        "checklist": [
            "Confirm the referenced document exists",
            "Verify sharing settings allow this operation",
            "Retry after a short delay",
        ],
        "rewrite_suggestions": [
            "Rename ambiguous IDs in your prompt",
            "Use a fresh document target rather than deleted references",
        ],
    },
    ErrorCategory.RATE_LIMIT: {
        "qa_failure_class": "llm",
        "failure_stage": "llm_provider",
        "checklist": [
            "Wait for cooldown period",
            "Retry with the same prompt",
            "If repeated, shorten prompt complexity",
        ],
        "rewrite_suggestions": [
            "Trim non-essential context before retry",
            "Break large task into smaller steps",
        ],
    },
    ErrorCategory.QUOTA_EXCEEDED: {
        "qa_failure_class": "llm",
        "failure_stage": "llm_provider",
        "checklist": [
            "Confirm active billing quota",
            "Retry after quota window reset",
            "Notify admin if quota repeatedly exceeded",
        ],
        "rewrite_suggestions": [
            "Reduce token-heavy tasks temporarily",
            "Batch similar requests outside peak windows",
        ],
    },
    ErrorCategory.TIMEOUT: {
        "qa_failure_class": "llm",
        "failure_stage": "execution_timeout",
        "checklist": [
            "Retry once with same prompt",
            "Check if request is too broad or data-heavy",
            "Split prompt into smaller tasks if still failing",
        ],
        "rewrite_suggestions": [
            "Shorten prompt to one concrete output",
            "Drop optional context and retry",
        ],
    },
    ErrorCategory.NETWORK: {
        "qa_failure_class": "rpa",
        "failure_stage": "connectivity",
        "checklist": [
            "Confirm backend can reach external dependency",
            "Retry after network jitter window",
            "Retry after network-sensitive step completes",
        ],
        "rewrite_suggestions": [
            "Retry in a few minutes",
            "Avoid parallel heavy uploads in same window",
        ],
    },
    ErrorCategory.CELERY_ERROR: {
        "qa_failure_class": "workflow",
        "failure_stage": "background_queue",
        "checklist": [
            "Retry task from UI once",
            "Check worker health if repeated",
            "Fallback to manual execution if urgent",
        ],
        "rewrite_suggestions": [
            "Retry 1-minute later",
            "Keep one task retry at a time",
        ],
    },
    ErrorCategory.INVALID_INPUT: {
        "qa_failure_class": "input_validation",
        "failure_stage": "input",
        "checklist": [
            "Review required fields and format",
            "Ensure prompt is non-empty and actionable",
            "Retry after fixing metadata/attachments",
        ],
        "rewrite_suggestions": [
            "Use a clear, minimal prompt template",
            "Provide explicit output format",
        ],
    },
    ErrorCategory.NOT_FOUND: {
        "qa_failure_class": "rpa",
        "failure_stage": "resource_lookup",
        "checklist": [
            "Verify all referenced files/IDs exist",
            "Check permission to referenced resources",
            "Retry with corrected identifiers",
        ],
        "rewrite_suggestions": [
            "Search exact title before creating workflow",
            "Use stable IDs when available",
        ],
    },
    ErrorCategory.INTERNAL: {
        "qa_failure_class": "workflow",
        "failure_stage": "internal_system",
        "checklist": [
            "Retry once after a short delay",
            "Check system status in operations channel",
            "Escalate if failures continue",
        ],
        "rewrite_suggestions": [
            "Retry with the same prompt",
            "Contact support with task id if still failing",
        ],
    },
    ErrorCategory.UNKNOWN: {
        "qa_failure_class": "unknown",
        "failure_stage": "general",
        "checklist": [
            "Retry once as-is",
            "Try again with a simpler prompt",
            "Save logs and escalate if this repeats",
        ],
        "rewrite_suggestions": [
            "Try a simpler goal statement",
            "Remove ambiguous constraints",
        ],
    },
}


def build_recovery_deck(
    raw_error: str | None,
    *,
    repeat_failure_count: int = 0,
) -> dict:
    """Build a structured recovery-deck payload for failed tasks.

    The payload is intentionally opinionated: it combines classification,
    checklist actions, and immediate rewrite suggestions to support "fail-first"
    recovery UX and one-click rerun workflows.
    """
    friendly = classify_error(raw_error)
    profile = _RECOVERY_DECK_PROFILES.get(
        friendly.category,
        _RECOVERY_DECK_PROFILES[ErrorCategory.UNKNOWN],
    )

    checklist = list(profile["checklist"])
    rewrite_suggestions = list(profile["rewrite_suggestions"])

    # Add one suggestion from machine-generated actions if available, keeping total <=3
    action_suggestions = [a.description for a in friendly.actions if a.description]
    for suggestion in action_suggestions:
        if len(rewrite_suggestions) >= 3:
            break
        if suggestion not in rewrite_suggestions:
            rewrite_suggestions.append(suggestion)

    auto_retry = any(action.auto for action in friendly.actions)

    return {
        "qa_failure_class": profile["qa_failure_class"],
        "failure_stage": profile["failure_stage"],
        "failure_signal": friendly.message,
        "failure_detail": friendly.detail,
        "checklist": checklist,
        "rewrite_suggestions": rewrite_suggestions[:3],
        "auto_retry_available": auto_retry,
        "repeat_failure_count": repeat_failure_count,
        "one_click_retry": {
            "enabled": bool(friendly.actions),
            "label": "Retry task",
            "expected_action": "POST /api/v1/tasks/{task_id}/retry",
        },
    }
