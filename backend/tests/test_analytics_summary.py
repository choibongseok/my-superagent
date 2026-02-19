"""Tests for #214 One-Metric Dashboard — GET /api/v1/analytics/summary.

Covers:
- Returns 200 with correct shape for authenticated user
- Returns 401 when unauthenticated
- Empty user (no tasks) → zeros
- Only counts tasks owned by the requesting user
- success_rate calculation
- avg_completion_time_seconds calculation
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.task import Task as TaskModel, TaskStatus, TaskType
from app.models.user import User


# ── helpers ───────────────────────────────────────────────────────────────────


async def _make_user(db: AsyncSession, email: str | None = None) -> User:
    u = User(id=uuid4(), email=email or f"u-{uuid4().hex[:6]}@x.com", is_active=True)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _make_task(
    db: AsyncSession,
    user: User,
    status: TaskStatus = TaskStatus.COMPLETED,
    completed_at: datetime | None = None,
) -> TaskModel:
    t = TaskModel(
        id=uuid4(),
        user_id=user.id,
        prompt="Test",
        task_type=TaskType.RESEARCH,
        status=status,
        result={"content": "ok"},
        completed_at=completed_at,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


def _auth_headers(user: User) -> dict:
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


# ── GET /api/v1/analytics/summary ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_summary_requires_auth(async_client: AsyncClient, db: AsyncSession):
    """GET /analytics/summary without auth returns 403."""
    resp = await async_client.get("/api/v1/analytics/summary")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_summary_empty_user(async_client: AsyncClient, db: AsyncSession):
    """User with no tasks gets all-zero summary."""
    user = await _make_user(db)
    resp = await async_client.get(
        "/api/v1/analytics/summary",
        headers=_auth_headers(user),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["total_tasks"] == 0
    assert data["completed_tasks"] == 0
    assert data["success_rate"] == 0.0
    assert data["avg_completion_time_seconds"] == 0.0


@pytest.mark.asyncio
async def test_summary_response_shape(async_client: AsyncClient, db: AsyncSession):
    """Response has the four required keys with correct types."""
    user = await _make_user(db)
    await _make_task(db, user, status=TaskStatus.COMPLETED)

    resp = await async_client.get(
        "/api/v1/analytics/summary",
        headers=_auth_headers(user),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert "total_tasks" in data
    assert "completed_tasks" in data
    assert "success_rate" in data
    assert "avg_completion_time_seconds" in data

    assert isinstance(data["total_tasks"], int)
    assert isinstance(data["completed_tasks"], int)
    assert isinstance(data["success_rate"], float)
    assert isinstance(data["avg_completion_time_seconds"], float)


@pytest.mark.asyncio
async def test_summary_counts_correct(async_client: AsyncClient, db: AsyncSession):
    """total_tasks and completed_tasks are correct across mixed statuses."""
    user = await _make_user(db)

    await _make_task(db, user, status=TaskStatus.COMPLETED)
    await _make_task(db, user, status=TaskStatus.COMPLETED)
    await _make_task(db, user, status=TaskStatus.FAILED)
    await _make_task(db, user, status=TaskStatus.PENDING)

    resp = await async_client.get(
        "/api/v1/analytics/summary",
        headers=_auth_headers(user),
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_tasks"] == 4
    assert data["completed_tasks"] == 2
    assert abs(data["success_rate"] - 0.5) < 1e-4


@pytest.mark.asyncio
async def test_summary_success_rate_all_complete(async_client: AsyncClient, db: AsyncSession):
    """success_rate == 1.0 when all tasks are completed."""
    user = await _make_user(db)
    for _ in range(3):
        await _make_task(db, user, status=TaskStatus.COMPLETED)

    resp = await async_client.get(
        "/api/v1/analytics/summary",
        headers=_auth_headers(user),
    )
    assert resp.status_code == 200
    assert resp.json()["success_rate"] == 1.0


@pytest.mark.asyncio
async def test_summary_only_own_tasks(async_client: AsyncClient, db: AsyncSession):
    """Summary is scoped to the authenticated user's tasks only."""
    user_a = await _make_user(db)
    user_b = await _make_user(db)

    # 3 tasks for user_a
    for _ in range(3):
        await _make_task(db, user_a, status=TaskStatus.COMPLETED)

    # 1 task for user_b
    await _make_task(db, user_b, status=TaskStatus.COMPLETED)

    resp = await async_client.get(
        "/api/v1/analytics/summary",
        headers=_auth_headers(user_a),
    )
    assert resp.status_code == 200
    assert resp.json()["total_tasks"] == 3

    resp_b = await async_client.get(
        "/api/v1/analytics/summary",
        headers=_auth_headers(user_b),
    )
    assert resp_b.status_code == 200
    assert resp_b.json()["total_tasks"] == 1


@pytest.mark.asyncio
async def test_summary_avg_completion_time(async_client: AsyncClient, db: AsyncSession):
    """avg_completion_time_seconds is calculated from (completed_at - created_at)."""
    user = await _make_user(db)
    now = datetime.now(tz=timezone.utc)

    # Task 1: completed_at is 100s after now (created_at will be approximately now)
    t1 = await _make_task(
        db, user,
        status=TaskStatus.COMPLETED,
        completed_at=now + timedelta(seconds=100),
    )

    # Task 2: completed_at is 300s after now
    t2 = await _make_task(
        db, user,
        status=TaskStatus.COMPLETED,
        completed_at=now + timedelta(seconds=300),
    )

    resp = await async_client.get(
        "/api/v1/analytics/summary",
        headers=_auth_headers(user),
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["completed_tasks"] == 2
    # avg_completion_time > 0 (since completed_at > created_at)
    assert data["avg_completion_time_seconds"] > 0.0


@pytest.mark.asyncio
async def test_summary_avg_zero_when_no_completed_at(async_client: AsyncClient, db: AsyncSession):
    """avg_completion_time_seconds is 0.0 when completed tasks have no completed_at."""
    user = await _make_user(db)
    # Task completed but completed_at is None
    await _make_task(db, user, status=TaskStatus.COMPLETED)

    resp = await async_client.get(
        "/api/v1/analytics/summary",
        headers=_auth_headers(user),
    )
    assert resp.status_code == 200
    assert resp.json()["avg_completion_time_seconds"] == 0.0
