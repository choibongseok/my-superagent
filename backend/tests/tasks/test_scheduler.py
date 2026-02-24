"""Tests for recurring scheduler task registration and timing helpers (#244)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.models.scheduled_task import ScheduleType
from app.tasks import scheduler


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------


def test_next_run_after_once_returns_none():
    anchor = datetime(2026, 2, 20, 9, 0, tzinfo=timezone.utc)
    next_at = scheduler._next_run_after(
        ScheduleType.ONCE,
        anchor,
        None,
        datetime(2026, 2, 20, 10, 0, tzinfo=timezone.utc),
    )
    assert next_at is None


def test_next_run_after_daily_adds_one_day():
    last_run = datetime(2026, 2, 20, 9, 0, tzinfo=timezone.utc)
    next_at = scheduler._next_run_after(
        ScheduleType.DAILY,
        datetime(2026, 2, 20, 9, 0, tzinfo=timezone.utc),
        None,
        last_run,
    )
    assert next_at == datetime(2026, 2, 21, 9, 0, tzinfo=timezone.utc)


def test_next_run_after_weekly_adds_week():
    last_run = datetime(2026, 2, 21, 9, 0, tzinfo=timezone.utc)
    next_at = scheduler._next_run_after(
        ScheduleType.WEEKLY,
        datetime(2026, 2, 14, 9, 0, tzinfo=timezone.utc),
        None,
        last_run,
    )
    assert next_at == datetime(2026, 2, 28, 9, 0, tzinfo=timezone.utc)


def test_next_run_after_invalid_cron_without_expression_returns_none():
    last_run = datetime(2026, 2, 20, 9, 0, tzinfo=timezone.utc)
    assert (
        scheduler._next_run_after(
            ScheduleType.CRON,
            datetime(2026, 2, 20, 9, 0, tzinfo=timezone.utc),
            None,
            last_run,
        )
        is None
    )


def test_scheduler_task_registered_in_celery_beat():
    # Importing celery_app should include scheduler task registration.
    from app.agents.celery_app import celery_app

    assert "execute-due-schedules-every-60s" in celery_app.conf.beat_schedule
    entry = celery_app.conf.beat_schedule["execute-due-schedules-every-60s"]
    assert entry["task"] == "scheduler.execute_due_schedules"
    assert entry["schedule"] == 60.0
