"""Tests for #260 Smart Exit Hints — GET /api/v1/tasks/{id}/smart-exit-hints."""

from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.task import Task as TaskModel
from app.models.task import TaskStatus, TaskType
from app.models.user import User


def _user(email: str = "smart-hints@example.com") -> User:
    return User(
        id=uuid4(),
        email=email,
        is_active=True,
    )


def _token(user: User) -> str:
    return create_access_token({"sub": str(user.id)})


def _frontend_base() -> str:
    return (settings.FRONTEND_URL or "").rstrip("/")


@pytest_asyncio.fixture
async def async_client(db: AsyncSession):
    app.dependency_overrides[get_db] = lambda: (yield db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_completed_task_returns_share_and_schedule_hints(
    db: AsyncSession,
    async_client: AsyncClient,
):
    user = _user()
    db.add(user)
    await db.commit()

    task = TaskModel(
        id=uuid4(),
        user_id=user.id,
        prompt="Draft summary doc",
        task_type=TaskType.DOCS,
        status=TaskStatus.COMPLETED,
    )
    db.add(task)
    await db.commit()

    response = await async_client.get(
        f"/api/v1/tasks/{task.id}/smart-exit-hints",
        headers={"Authorization": f"Bearer {_token(user)}"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["task_id"] == str(task.id)
    assert payload["status"] == "completed"
    assert payload["task_type"] == "docs"
    assert payload["next_focus"] == "Share or schedule this outcome"
    assert [a["id"] for a in payload["actions"]] == [
        "view",
        "share",
        "schedule",
    ]
    assert payload["actions"][0]["deep_link"] == f"{_frontend_base()}/tasks/{task.id}"
    assert payload["actions"][1]["path"].endswith(f"/api/v1/tasks/{task.id}/share")
    assert payload["actions"][1]["deep_link"] == f"{_frontend_base()}/tasks/{task.id}/share"
    assert payload["actions"][2]["path"].endswith(f"/api/v1/tasks/{task.id}/schedule")
    assert payload["actions"][2]["deep_link"] == f"{_frontend_base()}/tasks/{task.id}/schedule"


@pytest.mark.asyncio
async def test_failed_task_returns_recovery_hint_actions(
    db: AsyncSession,
    async_client: AsyncClient,
):
    user = _user("failed@example.com")
    db.add(user)
    await db.commit()

    task = TaskModel(
        id=uuid4(),
        user_id=user.id,
        prompt="Build report",
        task_type=TaskType.RESEARCH,
        status=TaskStatus.FAILED,
        error_message="TimeoutError: operation timed out",
    )
    db.add(task)
    await db.commit()

    response = await async_client.get(
        f"/api/v1/tasks/{task.id}/smart-exit-hints",
        headers={"Authorization": f"Bearer {_token(user)}"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["status"] == "failed"
    assert payload["next_focus"] == "Recover and rerun with fixes"
    assert [a["id"] for a in payload["actions"]] == [
        "view",
        "recovery_deck",
        "retry",
    ]
    assert payload["actions"][0]["deep_link"] == f"{_frontend_base()}/tasks/{task.id}"
    assert payload["actions"][1]["path"].endswith(f"/api/v1/tasks/{task.id}/recovery-deck")
    assert payload["actions"][1]["deep_link"] == f"{_frontend_base()}/tasks/{task.id}/recovery-deck"
    assert payload["actions"][2]["deep_link"] == f"{_frontend_base()}/tasks/{task.id}/retry"


@pytest.mark.asyncio
async def test_pending_task_returns_monitor_or_cancel(
    db: AsyncSession,
    async_client: AsyncClient,
):
    user = _user("running@example.com")
    db.add(user)
    await db.commit()

    task = TaskModel(
        id=uuid4(),
        user_id=user.id,
        prompt="Refresh dashboard",
        task_type=TaskType.SLIDES,
        status=TaskStatus.PENDING,
    )
    db.add(task)
    await db.commit()

    response = await async_client.get(
        f"/api/v1/tasks/{task.id}/smart-exit-hints",
        headers={"Authorization": f"Bearer {_token(user)}"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["status"] == "pending"
    assert payload["next_focus"] == "Monitor progress or cancel"
    assert [a["id"] for a in payload["actions"]] == [
        "view",
        "poll",
        "cancel",
    ]
    assert payload["actions"][0]["deep_link"] == f"{_frontend_base()}/tasks/{task.id}"
    assert payload["actions"][1]["deep_link"] == f"{_frontend_base()}/tasks/{task.id}"
    assert payload["actions"][2]["deep_link"] == f"{_frontend_base()}/tasks/{task.id}/cancel"


@pytest.mark.asyncio
async def test_smart_exit_hints_hidden_from_other_users(db: AsyncSession, async_client: AsyncClient):
    owner = _user("owner@example.com")
    other = _user("other@example.com")
    db.add(owner)
    db.add(other)
    await db.commit()

    task = TaskModel(
        id=uuid4(),
        user_id=owner.id,
        prompt="Summarize notes",
        task_type=TaskType.DOCS,
        status=TaskStatus.COMPLETED,
    )
    db.add(task)
    await db.commit()

    response = await async_client.get(
        f"/api/v1/tasks/{task.id}/smart-exit-hints",
        headers={"Authorization": f"Bearer {_token(other)}"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_smart_exit_hints_requires_auth(db: AsyncSession, async_client: AsyncClient):
    user = _user("noauth@example.com")
    db.add(user)
    await db.commit()

    task = TaskModel(
        id=uuid4(),
        user_id=user.id,
        prompt="Summarize notes",
        task_type=TaskType.DOCS,
        status=TaskStatus.COMPLETED,
    )
    db.add(task)
    await db.commit()

    response = await async_client.get(f"/api/v1/tasks/{task.id}/smart-exit-hints")

    assert response.status_code in (401, 403)
