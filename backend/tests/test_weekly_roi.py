"""Tests for #230 Workspace ROI Dashboard — GET /api/v1/analytics/weekly-roi."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.task import Task as TaskModel, TaskStatus, TaskType
from app.models.qa_result import QAResult
from app.models.user import User
from app.api.v1.analytics import _week_bounds


# ── helpers ───────────────────────────────────────────────────────────


async def _make_user(db: AsyncSession, email: str | None = None) -> User:
    u = User(id=uuid4(), email=email or f"roi-{uuid4().hex[:6]}@x.com", is_active=True)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _make_task(
    db: AsyncSession,
    user: User,
    task_type: TaskType = TaskType.DOCS,
    status: TaskStatus = TaskStatus.COMPLETED,
    created_at: datetime | None = None,
    prompt: str = "Test task",
) -> TaskModel:
    now = datetime.now(timezone.utc)
    ca = created_at or now - timedelta(hours=2)
    t = TaskModel(
        id=uuid4(),
        user_id=user.id,
        prompt=prompt,
        task_type=task_type,
        status=status,
        result={"content": "ok"} if status == TaskStatus.COMPLETED else None,
        completed_at=ca + timedelta(minutes=5) if status == TaskStatus.COMPLETED else None,
        created_at=ca,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


async def _make_qa(db: AsyncSession, task: TaskModel, score: float = 85.0) -> QAResult:
    q = QAResult(
        id=uuid4(),
        task_id=task.id,
        overall_score=score,
    )
    db.add(q)
    await db.commit()
    await db.refresh(q)
    return q


def _auth_headers(user: User) -> dict:
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


# ── unit tests ───────────────────────────────────────────────────────


def test_week_bounds():
    from app.api.v1.analytics import _week_bounds

    ref = datetime(2026, 2, 18, 12, 0, 0)  # Wednesday
    start, end = _week_bounds(ref)
    assert start.weekday() == 0  # Monday
    assert end.weekday() == 6    # Sunday
    assert start.day == 16
    assert end.day == 22


def test_manual_minutes_defaults():
    from app.api.v1.analytics import _MANUAL_MINUTES
    assert _MANUAL_MINUTES["docs"] == 30.0
    assert _MANUAL_MINUTES["sheets"] == 45.0
    assert _MANUAL_MINUTES["slides"] == 60.0
    assert _MANUAL_MINUTES["research"] == 90.0


def test_weekly_roi_model_fields():
    from app.api.v1.analytics import WeeklyROI
    fields = WeeklyROI.model_fields
    expected = {
        "period_start", "period_end", "total_tasks", "completed_tasks",
        "by_type", "time_saved_minutes", "time_saved_hours", "money_saved",
        "hourly_rate", "currency", "avg_quality_score", "best_task",
        "vs_previous_week",
    }
    assert expected.issubset(set(fields.keys()))


# ── API tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_roi_requires_auth(async_client: AsyncClient, db: AsyncSession):
    resp = await async_client.get("/api/v1/analytics/weekly-roi")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_roi_empty_user(async_client: AsyncClient, db: AsyncSession):
    user = await _make_user(db)
    resp = await async_client.get(
        "/api/v1/analytics/weekly-roi",
        headers=_auth_headers(user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_tasks"] == 0
    assert data["completed_tasks"] == 0
    assert data["time_saved_minutes"] == 0.0
    assert data["money_saved"] == 0.0
    assert data["avg_quality_score"] is None
    assert data["best_task"] is None
    assert data["vs_previous_week"] is None


@pytest.mark.asyncio
async def test_roi_with_completed_tasks(async_client: AsyncClient, db: AsyncSession):
    user = await _make_user(db)
    now = datetime.now(timezone.utc)
    # Use this week's Monday boundary so this test is stable across weekday boundaries.
    week_start, _ = _week_bounds(now.replace(tzinfo=None))
    week_start = week_start.replace(tzinfo=timezone.utc)

    t1 = await _make_task(db, user, TaskType.DOCS, TaskStatus.COMPLETED, week_start + timedelta(hours=1))
    t2 = await _make_task(db, user, TaskType.SHEETS, TaskStatus.COMPLETED, week_start + timedelta(hours=2))
    await _make_task(db, user, TaskType.RESEARCH, TaskStatus.FAILED, week_start + timedelta(hours=3))

    await _make_qa(db, t1, 92.0)
    await _make_qa(db, t2, 80.0)

    resp = await async_client.get(
        "/api/v1/analytics/weekly-roi?hourly_rate=100&currency=KRW",
        headers=_auth_headers(user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_tasks"] == 3
    assert data["completed_tasks"] == 2
    assert data["by_type"]["docs"] == 1
    assert data["by_type"]["sheets"] == 1
    # docs 30min + sheets 45min = 75min
    assert data["time_saved_minutes"] == 75.0
    assert data["time_saved_hours"] == 1.25
    assert data["money_saved"] == 125.0
    assert data["hourly_rate"] == 100.0
    assert data["currency"] == "KRW"
    assert data["avg_quality_score"] == 86.0
    assert data["best_task"]["quality_score"] == 92.0


@pytest.mark.asyncio
async def test_roi_default_hourly_rate(async_client: AsyncClient, db: AsyncSession):
    user = await _make_user(db)
    resp = await async_client.get(
        "/api/v1/analytics/weekly-roi",
        headers=_auth_headers(user),
    )
    assert resp.status_code == 200
    assert resp.json()["hourly_rate"] == 50.0
    assert resp.json()["currency"] == "USD"


@pytest.mark.asyncio
async def test_roi_period_dates_are_week_bounds(async_client: AsyncClient, db: AsyncSession):
    user = await _make_user(db)
    resp = await async_client.get(
        "/api/v1/analytics/weekly-roi",
        headers=_auth_headers(user),
    )
    assert resp.status_code == 200
    data = resp.json()
    from datetime import date as dt_date
    start = dt_date.fromisoformat(data["period_start"])
    end = dt_date.fromisoformat(data["period_end"])
    assert start.weekday() == 0  # Monday
    assert end.weekday() == 6    # Sunday
    assert (end - start).days == 6
