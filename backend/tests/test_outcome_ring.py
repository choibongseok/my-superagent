"""Tests for Follow-Through Ring — GET /api/v1/analytics/outcome-ring.

Covers:
- Auth enforcement
- Ring payload shape for mixed outcomes
- Action suggestions for completed vs failed tasks
- Status filtering
- User scoping
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
    u = User(id=uuid4(), email=email or f"ring-{uuid4().hex[:6]}@x.com", is_active=True)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _make_task(
    db: AsyncSession,
    user: User,
    *,
    status: TaskStatus = TaskStatus.COMPLETED,
    task_type: TaskType = TaskType.DOCS,
    created_at: datetime | None = None,
    completed_at: datetime | None = None,
    error_message: str | None = None,
    prompt: str = "Draft weekly summary",
    result_content: str | None = "Done",
) -> TaskModel:
    t = TaskModel(
        id=uuid4(),
        user_id=user.id,
        prompt=prompt,
        task_type=task_type,
        status=status,
        result={"content": result_content} if result_content is not None else None,
        completed_at=completed_at,
        created_at=created_at or datetime.now(timezone.utc),
        error_message=error_message,
        document_url="https://docs.google.com/document/d/sample" if status == TaskStatus.COMPLETED else None,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


def _auth_headers(user: User) -> dict:
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


# ── tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_outcome_ring_requires_auth(async_client: AsyncClient, db: AsyncSession):
    resp = await async_client.get("/api/v1/analytics/outcome-ring")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_outcome_ring_builds_cards_with_follow_actions(async_client: AsyncClient, db: AsyncSession):
    user = await _make_user(db)

    now = datetime.now(timezone.utc)
    long_output = "A" * 400

    completed = await _make_task(
        db,
        user,
        status=TaskStatus.COMPLETED,
        created_at=now - timedelta(hours=1),
        completed_at=now - timedelta(minutes=58),
        result_content=long_output,
        prompt="Finalize onboarding docs",
    )

    failed = await _make_task(
        db,
        user,
        status=TaskStatus.FAILED,
        created_at=now - timedelta(hours=2),
        error_message="Request timed out while creating spreadsheet.",
        result_content=None,
        prompt="Generate KPI deck",
    )

    resp = await async_client.get(
        "/api/v1/analytics/outcome-ring?period_days=3",
        headers=_auth_headers(user),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["period_days"] == 3
    assert data["total_outcomes"] == 2
    assert data["status_breakdown"][TaskStatus.COMPLETED.value] == 1
    assert data["status_breakdown"][TaskStatus.FAILED.value] == 1

    by_status = {card["status"]: card for card in data["cards"]}
    completed_card = by_status[TaskStatus.COMPLETED.value]
    failed_card = by_status[TaskStatus.FAILED.value]

    assert completed_card["task_id"] == str(completed.id)
    assert completed_card["result_preview"].endswith("…")
    assert completed_card["completion_seconds"] is not None
    assert completed_card["completion_seconds"] > 0
    action_ids = {a["id"] for a in completed_card["actions"]}
    assert {"share", "schedule", "view-task"}.issubset(action_ids)

    assert failed_card["task_id"] == str(failed.id)
    assert failed_card["failure_category"] in {"timeout", "network", "unknown"}
    failed_actions = {a["id"] for a in failed_card["actions"]}
    assert {"recovery", "retry", "view-task"}.issubset(failed_actions)


@pytest.mark.asyncio
async def test_outcome_ring_status_filter(async_client: AsyncClient, db: AsyncSession):
    user = await _make_user(db)
    now = datetime.now(timezone.utc)

    await _make_task(
        db,
        user,
        status=TaskStatus.COMPLETED,
        created_at=now,
        completed_at=now,
    )
    await _make_task(
        db,
        user,
        status=TaskStatus.FAILED,
        created_at=now,
        error_message="Google API error",
    )

    resp = await async_client.get(
        "/api/v1/analytics/outcome-ring?status=failed",
        headers=_auth_headers(user),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["total_outcomes"] == 1
    assert data["cards"][0]["status"] == TaskStatus.FAILED.value
    assert data["status_breakdown"][TaskStatus.FAILED.value] == 1
    assert TaskStatus.COMPLETED.value not in data["status_breakdown"]


@pytest.mark.asyncio
async def test_outcome_ring_is_user_scoped(async_client: AsyncClient, db: AsyncSession):
    owner = await _make_user(db, email="owner@example.com")
    other = await _make_user(db, email="other@example.com")

    await _make_task(db, owner, status=TaskStatus.COMPLETED, prompt="Owner task")
    await _make_task(db, other, status=TaskStatus.COMPLETED, prompt="Other task")

    resp = await async_client.get(
        "/api/v1/analytics/outcome-ring",
        headers=_auth_headers(owner),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["total_outcomes"] == 1
    assert data["cards"][0]["prompt"].startswith("Owner")
