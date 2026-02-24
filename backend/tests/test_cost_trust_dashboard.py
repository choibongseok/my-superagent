"""Tests for cost-trust dashboard recommendations and trust-health insights."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.qa_result import QAResult
from app.models.task import Task as TaskModel, TaskStatus, TaskType
from app.models.user import User


async def _make_user(db: AsyncSession, email: str | None = None) -> User:
    user = User(
        id=uuid4(),
        email=email or f"user-{uuid4().hex[:8]}@example.com",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _make_task(
    db: AsyncSession,
    user: User,
    *,
    prompt: str = "Test task",
    task_type: TaskType = TaskType.DOCS,
    status: TaskStatus = TaskStatus.COMPLETED,
    estimated_cost_usd: float = 0.0,
    actual_cost_usd: float = 0.0,
    retry_depth: int = 0,
    created_at: datetime | None = None,
    completed_at: datetime | None = None,
    trust_score: float | None = None,
) -> TaskModel:
    now = datetime.now(timezone.utc)
    created = created_at or (now - timedelta(hours=1))
    done_at = completed_at
    if status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED} and done_at is None:
        done_at = created + timedelta(minutes=5)

    task = TaskModel(
        id=uuid4(),
        user_id=user.id,
        prompt=prompt,
        task_type=task_type,
        status=status,
        result={"metadata": {"model": "gpt-test"}} if status == TaskStatus.COMPLETED else None,
        created_at=created,
        completed_at=done_at,
        task_metadata={
            "estimated_cost_usd": estimated_cost_usd,
            "actual_cost_usd": actual_cost_usd,
            "retry_depth": retry_depth,
        },
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    if trust_score is not None:
        qa = QAResult(
            id=uuid4(),
            task_id=task.id,
            overall_score=trust_score,
        )
        db.add(qa)
        await db.commit()

    await db.refresh(task)
    return task


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_cost_trust_budget_warning_and_recommendations(async_client: AsyncClient, db: AsyncSession):
    user = await _make_user(db)
    now = datetime.now(timezone.utc)

    await _make_task(
        db,
        user,
        prompt="Big analysis task",
        actual_cost_usd=200.0,
        estimated_cost_usd=190.0,
        created_at=now - timedelta(hours=1),
    )
    await _make_task(
        db,
        user,
        prompt="Another high-cost task",
        actual_cost_usd=180.0,
        estimated_cost_usd=170.0,
        created_at=now - timedelta(hours=2),
    )

    resp = await async_client.get(
        "/api/v1/analytics/cost-trust?monthly_budget_usd=250",
        headers=_auth_headers(user),
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["budget_status"] == "exceeded"
    assert data["budget_warning"] is not None
    assert "Projected monthly spend may exceed budget" in data["budget_warning"]
    assert any("Overage" in item or "Estimated overage" in item for item in data["recommendations"])
    assert data["trust_health"] == "unknown"


@pytest.mark.asyncio
async def test_cost_trust_recommendations_low_trust_and_retry_failures(async_client: AsyncClient, db: AsyncSession):
    user = await _make_user(db)
    now = datetime.now(timezone.utc)

    await _make_task(
        db,
        user,
        prompt="Research task 1",
        task_type=TaskType.RESEARCH,
        actual_cost_usd=0.0,
        estimated_cost_usd=0.0,
        trust_score=52.0,
        created_at=now - timedelta(hours=1),
        retry_depth=1,
    )
    await _make_task(
        db,
        user,
        prompt="Research task 2",
        task_type=TaskType.RESEARCH,
        actual_cost_usd=0.0,
        estimated_cost_usd=0.0,
        trust_score=56.0,
        created_at=now - timedelta(hours=2),
        retry_depth=1,
    )
    await _make_task(
        db,
        user,
        prompt="Research failed task",
        task_type=TaskType.RESEARCH,
        status=TaskStatus.FAILED,
        actual_cost_usd=0.0,
        estimated_cost_usd=0.0,
        created_at=now - timedelta(hours=3),
        retry_depth=1,
    )

    resp = await async_client.get(
        "/api/v1/analytics/cost-trust",
        headers=_auth_headers(user),
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["trust_health"] == "needs_attention"
    assert any("Trust score is below 70" in item for item in data["recommendations"])
    assert any("High retry rate detected" in item for item in data["recommendations"])
    assert any("High failure rate detected" in item for item in data["recommendations"])
