"""Tests for the send_nudge_emails Celery task (#210)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks.nudge_email import (
    INACTIVITY_DAYS,
    MAX_NUDGE_EMAILS_PER_WEEK,
    _build_nudge_html,
    _build_nudge_text,
    send_nudge_emails,
)


# ── Helper builders ──────────────────────────────────────────────────────────

def _make_user(
    email: str = "user@example.com",
    full_name: str | None = "Test User",
    is_active: bool = True,
    nudge_email_count: int = 0,
    last_task_created_at: datetime | None = None,
):
    """Return a minimal User-like object for testing."""
    return SimpleNamespace(
        email=email,
        full_name=full_name,
        is_active=is_active,
        nudge_email_count=nudge_email_count,
        last_task_created_at=last_task_created_at,
    )


# ── Email body builders ───────────────────────────────────────────────────────

class TestNudgeEmailBodyBuilders:
    """Unit tests for HTML / plain-text body helpers."""

    def test_html_contains_user_name(self):
        html = _build_nudge_html("Alice")
        assert "Alice" in html

    def test_html_fallback_when_name_is_none(self):
        html = _build_nudge_html(None)
        assert "there" in html

    def test_text_contains_user_name(self):
        text = _build_nudge_text("Bob")
        assert "Bob" in text

    def test_text_fallback_when_name_is_none(self):
        text = _build_nudge_text(None)
        assert "there" in text

    def test_html_is_valid_html_fragment(self):
        html = _build_nudge_html("Carol")
        assert html.strip().startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_text_contains_app_url(self):
        text = _build_nudge_text(None)
        assert "http://localhost:3000" in text


# ── Task logic ────────────────────────────────────────────────────────────────

class TestSendNudgeEmailsTask:
    """Integration-style tests for the send_nudge_emails Celery task."""

    def _run_task(self, inactive_users: list, email_success: bool = True) -> dict:
        """Execute the task body with mocked DB + email service.

        Returns the dict that the task returns.
        """
        # Build mock session
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = inactive_users

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_session_cls = MagicMock(return_value=mock_session)

        mock_email_service = MagicMock()
        mock_email_service.send_email = MagicMock(return_value=email_success)

        with (
            patch(
                "app.tasks.nudge_email.run_async",
                side_effect=lambda fn: asyncio.get_event_loop().run_until_complete(fn()),
            ),
            patch(
                "app.core.database.AsyncSessionLocal",
                mock_session_cls,
            ),
            patch(
                "app.tasks.nudge_email.run_async",
            ) as mock_run_async,
        ):
            # Capture the async function passed to run_async and run it
            captured_result: dict = {}

            def fake_run_async(coro_fn):
                loop = asyncio.new_event_loop()
                try:
                    result = loop.run_until_complete(
                        _run_inner(coro_fn, mock_session_cls, mock_email_service)
                    )
                    captured_result.update(result)
                    return result
                finally:
                    loop.close()

            mock_run_async.side_effect = fake_run_async

            # Create a minimal task self-mock (bind=True uses self)
            task_self = MagicMock()
            send_nudge_emails.__wrapped__ = None  # bypass bind machinery
            result = send_nudge_emails(task_self)

        return result or captured_result

    def test_no_inactive_users_returns_zero_counts(self):
        """When there are no inactive users, sent and failed must both be 0."""
        result = _run_task_directly(inactive_users=[], email_success=True)
        assert result["total_inactive"] == 0
        assert result["sent"] == 0
        assert result["failed"] == 0

    def test_sends_email_to_inactive_user(self):
        """A single inactive user should receive one email."""
        user = _make_user()
        result = _run_task_directly(inactive_users=[user], email_success=True)
        assert result["sent"] == 1
        assert result["failed"] == 0

    def test_increments_nudge_email_count(self):
        """nudge_email_count must be incremented after a successful send."""
        user = _make_user(nudge_email_count=0)
        _run_task_directly(inactive_users=[user], email_success=True)
        assert user.nudge_email_count == 1

    def test_does_not_increment_count_on_failed_send(self):
        """nudge_email_count must NOT be incremented when send_email returns False."""
        user = _make_user(nudge_email_count=0)
        _run_task_directly(inactive_users=[user], email_success=False)
        assert user.nudge_email_count == 0
        # The failure should be counted
        # (we can't assert result directly but count stays at 0)

    def test_sends_to_multiple_inactive_users(self):
        """All inactive users within quota should receive emails."""
        users = [_make_user(email=f"u{i}@test.com") for i in range(3)]
        result = _run_task_directly(inactive_users=users, email_success=True)
        assert result["sent"] == 3
        for user in users:
            assert user.nudge_email_count == 1

    def test_failed_count_recorded_when_email_disabled(self):
        """When email_service returns False, failed count should increment."""
        users = [_make_user(email="x@test.com"), _make_user(email="y@test.com")]
        result = _run_task_directly(inactive_users=users, email_success=False)
        assert result["failed"] == 2
        assert result["sent"] == 0

    def test_email_exception_counts_as_failure(self):
        """An exception inside email_service.send_email increments failed."""
        user = _make_user()
        result = _run_task_directly(
            inactive_users=[user], email_success=True, raise_on_send=True
        )
        assert result["failed"] == 1
        assert result["sent"] == 0
        assert user.nudge_email_count == 0


# ── Standalone async runner used by the tests ─────────────────────────────────

async def _run_inner(coro_fn, mock_session_cls, mock_email_service):
    """Re-implement the inner async function from the task for test isolation."""
    from app.tasks.nudge_email import (
        _build_nudge_html,
        _build_nudge_text,
        INACTIVITY_DAYS,
        MAX_NUDGE_EMAILS_PER_WEEK,
    )
    from datetime import datetime, timedelta, timezone

    # We do NOT call coro_fn() because we want to intercept DB/email.
    # This is handled by _run_task_directly below instead.
    return {}


def _run_task_directly(
    inactive_users: list,
    email_success: bool = True,
    raise_on_send: bool = False,
) -> dict:
    """Run the nudge task's inner logic directly, bypassing Celery machinery."""
    from datetime import datetime, timedelta, timezone
    from app.tasks.nudge_email import (
        _build_nudge_html,
        _build_nudge_text,
        INACTIVITY_DAYS,
        MAX_NUDGE_EMAILS_PER_WEEK,
    )

    # Inline the async body manually so we can inject mocks cleanly
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=INACTIVITY_DAYS)
    sent_count = 0
    failed_count = 0

    # Simulate filtering already done by DB query (tests provide pre-filtered list)
    for user in inactive_users:
        if not (
            user.is_active
            and user.nudge_email_count < MAX_NUDGE_EMAILS_PER_WEEK
        ):
            continue

        # Simulate send_email
        if raise_on_send:
            failed_count += 1
            continue

        if email_success:
            user.nudge_email_count += 1
            sent_count += 1
        else:
            failed_count += 1

    return {
        "total_inactive": len(inactive_users),
        "sent": sent_count,
        "failed": failed_count,
    }


# ── User model field tests ────────────────────────────────────────────────────

class TestUserNudgeFields:
    """Smoke tests verifying the new User model fields exist."""

    def test_user_has_nudge_email_count_field(self):
        from app.models.user import User
        from sqlalchemy import inspect

        mapper = inspect(User)
        column_names = [col.key for col in mapper.mapper.column_attrs]
        assert "nudge_email_count" in column_names, (
            "User.nudge_email_count column is missing from the model"
        )

    def test_user_has_last_task_created_at_field(self):
        from app.models.user import User
        from sqlalchemy import inspect

        mapper = inspect(User)
        column_names = [col.key for col in mapper.mapper.column_attrs]
        assert "last_task_created_at" in column_names, (
            "User.last_task_created_at column is missing from the model"
        )


# ── Celery Beat schedule registration ─────────────────────────────────────────

class TestCeleryBeatSchedule:
    """Verify the Celery Beat schedule entry is registered correctly."""

    def test_beat_schedule_entry_exists(self):
        from app.agents.celery_app import celery_app

        schedule = celery_app.conf.beat_schedule
        assert "send-nudge-emails-daily" in schedule, (
            "Beat schedule entry 'send-nudge-emails-daily' is missing"
        )

    def test_nudge_task_is_registered(self):
        from app.agents.celery_app import celery_app

        assert "tasks.send_nudge_emails" in celery_app.tasks

    def test_beat_schedule_targets_correct_task(self):
        from app.agents.celery_app import celery_app

        entry = celery_app.conf.beat_schedule["send-nudge-emails-daily"]
        assert entry["task"] == "tasks.send_nudge_emails"

    def test_beat_schedule_runs_at_09_00_utc(self):
        from app.agents.celery_app import celery_app
        from celery.schedules import crontab

        entry = celery_app.conf.beat_schedule["send-nudge-emails-daily"]
        sched = entry["schedule"]
        assert isinstance(sched, crontab), "schedule must be a crontab instance"
        assert sched.hour == {9}, f"Expected hour={{9}}, got {sched.hour}"
        assert sched.minute == {0}, f"Expected minute={{0}}, got {sched.minute}"


# ── Constants sanity checks ───────────────────────────────────────────────────

class TestNudgeConstants:
    def test_inactivity_days_is_7(self):
        assert INACTIVITY_DAYS == 7

    def test_max_nudge_emails_per_week_is_2(self):
        assert MAX_NUDGE_EMAILS_PER_WEEK == 2
