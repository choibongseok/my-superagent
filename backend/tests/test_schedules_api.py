"""Tests for recurring task schedule API (#244).

This suite covers the CRUD endpoints under /api/v1/schedules and the helper
route to create a schedule from an existing completed task.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.task import Task, TaskStatus, TaskType
from app.models.user import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _user(db: AsyncSession, email: str | None = None) -> User:
    u = User(id=uuid4(), email=email or f"sched-{uuid4().hex[:6]}@test.com", is_active=True)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


def _headers(user: User) -> dict:
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


async def _completed_task(db: AsyncSession, user: User) -> Task:
    task = Task(
        id=uuid4(),
        user_id=user.id,
        prompt="Weekly sales report",
        task_type=TaskType.DOCS,
        status=TaskStatus.COMPLETED,
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
        completed_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def _failed_task(db: AsyncSession, user: User) -> Task:
    task = Task(
        id=uuid4(),
        user_id=user.id,
        prompt="Broken task",
        task_type=TaskType.DOCS,
        status=TaskStatus.FAILED,
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def _create_schedule(async_client: AsyncClient, user: User, task: Task) -> dict:
    payload = {
        "name": "Weekly Report",
        "schedule_type": "weekly",
        "scheduled_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "timezone": "UTC",
    }
    resp = await async_client.post(
        f"/api/v1/tasks/{task.id}/schedule",
        json=payload,
        headers=_headers(user),
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# POST /tasks/{task_id}/schedule
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestScheduleCreate:

    async def test_create_schedule_from_completed_task(self, async_client: AsyncClient, db: AsyncSession):
        user = await _user(db)
        task = await _completed_task(db, user)

        payload = {
            "name": "Monday Weekly Sync",
            "schedule_type": "weekly",
            "scheduled_at": "2026-02-22T09:00:00Z",
            "timezone": "UTC",
        }
        resp = await async_client.post(
            f"/api/v1/tasks/{task.id}/schedule",
            json=payload,
            headers=_headers(user),
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Monday Weekly Sync"
        assert data["task_type"] == "docs"
        assert data["schedule_type"] == "weekly"
        assert data["is_active"] is True

    async def test_create_schedule_requires_completed_task(self, async_client: AsyncClient, db: AsyncSession):
        user = await _user(db)
        task = await _failed_task(db, user)

        payload = {
            "name": "Nope",
            "schedule_type": "weekly",
            "scheduled_at": "2026-02-22T09:00:00Z",
            "timezone": "UTC",
        }
        resp = await async_client.post(
            f"/api/v1/tasks/{task.id}/schedule",
            json=payload,
            headers=_headers(user),
        )

        assert resp.status_code == 400
        assert "completed" in resp.text.lower()

    async def test_create_schedule_rejects_invalid_cron_expression(self, async_client: AsyncClient, db: AsyncSession):
        user = await _user(db)
        task = await _completed_task(db, user)

        payload = {
            "name": "Bad Cron",
            "schedule_type": "cron",
            "scheduled_at": "2026-02-22T09:00:00Z",
            "cron_expression": "not-a-cron",
            "timezone": "UTC",
        }
        resp = await async_client.post(
            f"/api/v1/tasks/{task.id}/schedule",
            json=payload,
            headers=_headers(user),
        )
        assert resp.status_code == 400
        assert "cron_expression" in resp.text


# ---------------------------------------------------------------------------
# GET /schedules + GET /schedules/{id} + PATCH + DELETE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestScheduleLifecycle:

    async def test_schedule_list_get_update_delete(self, async_client: AsyncClient, db: AsyncSession):
        user = await _user(db)
        task = await _completed_task(db, user)

        created = await _create_schedule(async_client, user, task)
        schedule_id = created["id"]

        list_resp = await async_client.get("/api/v1/schedules", headers=_headers(user))
        assert list_resp.status_code == 200
        data = list_resp.json()
        assert data["total"] == 1
        assert len(data["schedules"]) == 1

        detail_resp = await async_client.get(f"/api/v1/schedules/{schedule_id}", headers=_headers(user))
        assert detail_resp.status_code == 200
        assert detail_resp.json()["id"] == schedule_id
        assert detail_resp.json()["name"] == "Weekly Report"

        update_resp = await async_client.patch(
            f"/api/v1/schedules/{schedule_id}",
            json={"is_active": False, "name": "Paused Weekly Report"},
            headers=_headers(user),
        )
        assert update_resp.status_code == 200
        updated = update_resp.json()
        assert updated["is_active"] is False
        assert updated["name"] == "Paused Weekly Report"

        list_active_resp = await async_client.get(
            "/api/v1/schedules",
            headers=_headers(user),
        )
        assert list_active_resp.status_code == 200
        assert list_active_resp.json()["total"] == 0

        # Include inactive schedules
        list_all_resp = await async_client.get(
            "/api/v1/schedules?active_only=false&page=1&page_size=20",
            headers=_headers(user),
        )
        assert list_all_resp.status_code == 200
        assert list_all_resp.json()["total"] == 1
        delete_resp = await async_client.delete(f"/api/v1/schedules/{schedule_id}", headers=_headers(user))
        assert delete_resp.status_code == 204

        final_list_resp = await async_client.get(
            "/api/v1/schedules?active_only=false",
            headers=_headers(user),
        )
        assert final_list_resp.status_code == 200
        assert final_list_resp.json()["total"] == 0
