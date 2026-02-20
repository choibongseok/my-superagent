"""Tests for #223 Task Health Monitor — GET /health/tasks

Covers:
- Returns 200 with correct shape (healthy when no tasks)
- Counts tasks by status correctly
- Failure rate calculation
- Stuck task detection (processing > 30 min)
- health_status derivation: healthy / warning / critical
- include_failures flag returns recent failed tasks
- include_stuck flag returns stuck task details
- window parameter scopes the look-back range
- failure_limit caps the returned failures list
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.models.task import Task as TaskModel, TaskStatus, TaskType
from app.models.user import User


# ── helpers ──────────────────────────────────────────────────────────────────


async def _make_user(db, email: str | None = None) -> User:
    u = User(id=uuid4(), email=email or f"u-{uuid4().hex[:6]}@test.com", is_active=True)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _make_task(
    db,
    user: User,
    status: TaskStatus = TaskStatus.COMPLETED,
    task_type: TaskType = TaskType.RESEARCH,
    prompt: str = "test prompt",
    error_message: str | None = None,
    created_at: datetime | None = None,
) -> TaskModel:
    t = TaskModel(
        id=uuid4(),
        user_id=user.id,
        prompt=prompt,
        task_type=task_type,
        status=status,
        error_message=error_message,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    # Override created_at if requested (after commit so default is set)
    if created_at is not None:
        t.created_at = created_at
        await db.commit()
        await db.refresh(t)
    return t


# ── basic shape ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_task_health_returns_200(async_client: AsyncClient, db):
    resp = await async_client.get("/api/v1/health/tasks")
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_task_health_empty_is_healthy(async_client: AsyncClient, db):
    resp = await async_client.get("/api/v1/health/tasks")
    data = resp.json()
    assert data["health_status"] == "healthy"
    assert data["counts"]["total"] == 0
    assert data["failure_rate"] == 0.0
    assert data["stuck_tasks"] == 0


@pytest.mark.asyncio
async def test_task_health_response_shape(async_client: AsyncClient, db):
    resp = await async_client.get("/api/v1/health/tasks")
    data = resp.json()
    assert "health_status" in data
    assert "window_minutes" in data
    assert "counts" in data
    assert "failure_rate" in data
    assert "stuck_tasks" in data
    counts = data["counts"]
    for key in ("total", "completed", "failed", "pending", "processing", "cancelled"):
        assert key in counts


# ── counting ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_task_health_counts_statuses(async_client: AsyncClient, db):
    user = await _make_user(db)
    await _make_task(db, user, status=TaskStatus.COMPLETED)
    await _make_task(db, user, status=TaskStatus.COMPLETED)
    await _make_task(db, user, status=TaskStatus.FAILED, error_message="boom")
    await _make_task(db, user, status=TaskStatus.PENDING)

    resp = await async_client.get("/api/v1/health/tasks")
    data = resp.json()
    assert data["counts"]["total"] == 4
    assert data["counts"]["completed"] == 2
    assert data["counts"]["failed"] == 1
    assert data["counts"]["pending"] == 1


# ── failure rate ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_failure_rate_calculation(async_client: AsyncClient, db):
    user = await _make_user(db)
    # 1 failed out of 4 => 0.25
    await _make_task(db, user, status=TaskStatus.COMPLETED)
    await _make_task(db, user, status=TaskStatus.COMPLETED)
    await _make_task(db, user, status=TaskStatus.COMPLETED)
    await _make_task(db, user, status=TaskStatus.FAILED, error_message="err")

    resp = await async_client.get("/api/v1/health/tasks")
    data = resp.json()
    assert data["failure_rate"] == 0.25


# ── health status derivation ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_status_healthy(async_client: AsyncClient, db):
    user = await _make_user(db)
    # 0% failure rate, no stuck
    for _ in range(5):
        await _make_task(db, user, status=TaskStatus.COMPLETED)

    resp = await async_client.get("/api/v1/health/tasks")
    assert resp.json()["health_status"] == "healthy"


@pytest.mark.asyncio
async def test_health_status_warning_on_high_failure_rate(async_client: AsyncClient, db):
    user = await _make_user(db)
    # 2 failed out of 5 = 40% > 20% warning threshold
    await _make_task(db, user, status=TaskStatus.COMPLETED)
    await _make_task(db, user, status=TaskStatus.COMPLETED)
    await _make_task(db, user, status=TaskStatus.COMPLETED)
    await _make_task(db, user, status=TaskStatus.FAILED, error_message="e1")
    await _make_task(db, user, status=TaskStatus.FAILED, error_message="e2")

    resp = await async_client.get("/api/v1/health/tasks")
    data = resp.json()
    assert data["health_status"] in ("warning", "critical")


@pytest.mark.asyncio
async def test_health_status_critical_on_majority_failures(async_client: AsyncClient, db):
    user = await _make_user(db)
    # 3 failed out of 4 = 75% > 50% critical threshold
    await _make_task(db, user, status=TaskStatus.COMPLETED)
    await _make_task(db, user, status=TaskStatus.FAILED, error_message="e1")
    await _make_task(db, user, status=TaskStatus.FAILED, error_message="e2")
    await _make_task(db, user, status=TaskStatus.FAILED, error_message="e3")

    resp = await async_client.get("/api/v1/health/tasks")
    assert resp.json()["health_status"] == "critical"


# ── stuck task detection ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stuck_task_detected(async_client: AsyncClient, db):
    user = await _make_user(db)
    old_time = datetime.now(timezone.utc) - timedelta(minutes=45)
    await _make_task(db, user, status=TaskStatus.PROCESSING, created_at=old_time)

    resp = await async_client.get("/api/v1/health/tasks")
    data = resp.json()
    assert data["stuck_tasks"] >= 1
    assert data["health_status"] in ("warning", "critical")


@pytest.mark.asyncio
async def test_recent_processing_not_stuck(async_client: AsyncClient, db):
    user = await _make_user(db)
    # Created 5 minutes ago — not stuck
    recent = datetime.now(timezone.utc) - timedelta(minutes=5)
    await _make_task(db, user, status=TaskStatus.PROCESSING, created_at=recent)

    resp = await async_client.get("/api/v1/health/tasks")
    data = resp.json()
    assert data["stuck_tasks"] == 0


# ── include_failures ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_include_failures_returns_list(async_client: AsyncClient, db):
    user = await _make_user(db)
    await _make_task(db, user, status=TaskStatus.FAILED, error_message="something broke")

    resp = await async_client.get("/api/v1/health/tasks?include_failures=true")
    data = resp.json()
    assert "recent_failures" in data
    assert len(data["recent_failures"]) == 1
    assert data["recent_failures"][0]["error_message"] == "something broke"


@pytest.mark.asyncio
async def test_include_failures_not_present_by_default(async_client: AsyncClient, db):
    resp = await async_client.get("/api/v1/health/tasks")
    assert "recent_failures" not in resp.json()


@pytest.mark.asyncio
async def test_failure_limit_caps_results(async_client: AsyncClient, db):
    user = await _make_user(db)
    for i in range(5):
        await _make_task(db, user, status=TaskStatus.FAILED, error_message=f"err-{i}")

    resp = await async_client.get("/api/v1/health/tasks?include_failures=true&failure_limit=2")
    data = resp.json()
    assert len(data["recent_failures"]) == 2


# ── include_stuck ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_include_stuck_returns_details(async_client: AsyncClient, db):
    user = await _make_user(db)
    old_time = datetime.now(timezone.utc) - timedelta(minutes=60)
    await _make_task(
        db, user, status=TaskStatus.PROCESSING, created_at=old_time, prompt="stuck task here"
    )

    resp = await async_client.get("/api/v1/health/tasks?include_stuck=true")
    data = resp.json()
    assert "stuck_task_details" in data
    assert len(data["stuck_task_details"]) >= 1
    stuck = data["stuck_task_details"][0]
    assert "minutes_elapsed" in stuck
    assert stuck["minutes_elapsed"] >= 30


@pytest.mark.asyncio
async def test_include_stuck_not_present_by_default(async_client: AsyncClient, db):
    resp = await async_client.get("/api/v1/health/tasks")
    assert "stuck_task_details" not in resp.json()


# ── window parameter ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_window_scopes_results(async_client: AsyncClient, db):
    user = await _make_user(db)
    # Task created 2 hours ago — outside 60-min window
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    await _make_task(db, user, status=TaskStatus.FAILED, error_message="old", created_at=old)
    # Task created 10 min ago — inside window
    await _make_task(db, user, status=TaskStatus.COMPLETED)

    resp = await async_client.get("/api/v1/health/tasks?window=60")
    data = resp.json()
    # Only the recent task should count
    assert data["counts"]["total"] == 1
    assert data["counts"]["failed"] == 0
    assert data["window_minutes"] == 60


@pytest.mark.asyncio
async def test_large_window_includes_older_tasks(async_client: AsyncClient, db):
    user = await _make_user(db)
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    await _make_task(db, user, status=TaskStatus.FAILED, error_message="old", created_at=old)
    await _make_task(db, user, status=TaskStatus.COMPLETED)

    resp = await async_client.get("/api/v1/health/tasks?window=180")
    data = resp.json()
    assert data["counts"]["total"] == 2
