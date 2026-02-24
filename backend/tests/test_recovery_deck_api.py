"""Tests for #256 Recovery Deck — GET /api/v1/tasks/{id}/recovery-deck."""

from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.task import Task as TaskModel
from app.models.task import TaskStatus, TaskType
from app.models.user import User


def _user(email: str = "recover@example.com") -> User:
    return User(
        id=uuid4(),
        email=email,
        is_active=True,
    )


def _token(user: User) -> str:
    return create_access_token({"sub": str(user.id)})


@pytest_asyncio.fixture
async def async_client(db: AsyncSession):
    app.dependency_overrides[get_db] = lambda: (yield db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_recovery_deck_for_failed_task_returns_guidance(db: AsyncSession, async_client: AsyncClient):
    user = _user()
    db.add(user)
    await db.commit()

    task = TaskModel(
        id=uuid4(),
        user_id=user.id,
        prompt="Summarize latest quarterly KPIs",
        task_type=TaskType.RESEARCH,
        status=TaskStatus.FAILED,
        error_message="TimeoutError: operation timed out",
        task_metadata=None,
    )
    db.add(task)
    await db.commit()

    response = await async_client.get(
        f"/api/v1/tasks/{task.id}/recovery-deck",
        headers={"Authorization": f"Bearer {_token(user)}"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["task_id"] == str(task.id)
    assert payload["error"]["category"] == "timeout"

    deck = payload["recovery_deck"]
    assert deck["qa_failure_class"]
    assert isinstance(deck["checklist"], list)
    assert deck["checklist"]
    assert isinstance(deck["rewrite_suggestions"], list)
    assert len(deck["rewrite_suggestions"]) >= 1
    assert deck["one_click_retry"]["enabled"] is True
    assert deck["one_click_retry"]["path"].endswith(f"/api/v1/tasks/{task.id}/retry")


@pytest.mark.asyncio
async def test_recovery_deck_only_for_failed_tasks(db: AsyncSession, async_client: AsyncClient):
    user = _user("ok@example.com")
    db.add(user)
    await db.commit()

    task = TaskModel(
        id=uuid4(),
        user_id=user.id,
        prompt="Publish weekly summary",
        task_type=TaskType.DOCS,
        status=TaskStatus.COMPLETED,
        error_message=None,
        task_metadata=None,
    )
    db.add(task)
    await db.commit()

    response = await async_client.get(
        f"/api/v1/tasks/{task.id}/recovery-deck",
        headers={"Authorization": f"Bearer {_token(user)}"},
    )

    assert response.status_code == 400
    assert "failed" in response.text.lower()


@pytest.mark.asyncio
async def test_recovery_deck_hidden_from_other_users(db: AsyncSession, async_client: AsyncClient):
    owner = _user("owner@example.com")
    requester = _user("other@example.com")
    db.add(owner)
    db.add(requester)
    await db.commit()

    task = TaskModel(
        id=uuid4(),
        user_id=owner.id,
        prompt="Build dashboard",
        task_type=TaskType.SLIDES,
        status=TaskStatus.FAILED,
        error_message="Google API error",
        task_metadata=None,
    )
    db.add(task)
    await db.commit()

    response = await async_client.get(
        f"/api/v1/tasks/{task.id}/recovery-deck",
        headers={"Authorization": f"Bearer {_token(requester)}"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_resume_template_for_failed_task_returns_contextual_payload(db: AsyncSession, async_client: AsyncClient):
    user = _user("resume@example.com")
    db.add(user)
    await db.commit()

    task = TaskModel(
        id=uuid4(),
        user_id=user.id,
        prompt="Draft onboarding deck for Q3",
        task_type=TaskType.SLIDES,
        status=TaskStatus.FAILED,
        error_message="Google API error: spreadsheet not found",
        task_metadata={"template_id": "tmpl-1"},
    )
    db.add(task)
    await db.commit()

    response = await async_client.get(
        f"/api/v1/tasks/{task.id}/resume-template",
        headers={"Authorization": f"Bearer {_token(user)}"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["task_id"] == str(task.id)
    assert payload["task_type"] == "slides"
    assert payload["prompt"] == "Draft onboarding deck for Q3"
    assert payload["task_metadata"] == {"template_id": "tmpl-1"}

    retry = payload["retry"]
    assert retry["enabled"] is True
    assert retry["method"] == "POST"
    assert retry["path"].endswith(f"/api/v1/tasks/{task.id}/retry")

    assert payload["error"]["category"] in {"google_api", "not_found", "timeout", "network", "unknown"}
    assert "preflight" in payload
    assert isinstance(payload["recovery_deck"]["checklist"], list)
    assert payload["preflight"]["repeat_failure_count"] >= 0
    assert payload["preflight"]["auto_retry_available"] in {True, False}


@pytest.mark.asyncio
async def test_resume_template_only_for_failed_task(db: AsyncSession, async_client: AsyncClient):
    user = _user("resume2@example.com")
    db.add(user)
    await db.commit()

    task = TaskModel(
        id=uuid4(),
        user_id=user.id,
        prompt="Draft onboarding deck for Q3",
        task_type=TaskType.SLIDES,
        status=TaskStatus.COMPLETED,
        error_message=None,
        task_metadata=None,
    )
    db.add(task)
    await db.commit()

    response = await async_client.get(
        f"/api/v1/tasks/{task.id}/resume-template",
        headers={"Authorization": f"Bearer {_token(user)}"},
    )

    assert response.status_code == 400
    assert "failed" in response.text.lower()


@pytest.mark.asyncio
async def test_resume_template_hidden_from_other_users(db: AsyncSession, async_client: AsyncClient):
    owner = _user("resume-owner@example.com")
    requester = _user("resume-viewer@example.com")
    db.add(owner)
    db.add(requester)
    await db.commit()

    task = TaskModel(
        id=uuid4(),
        user_id=owner.id,
        prompt="Draft onboarding deck for Q3",
        task_type=TaskType.SLIDES,
        status=TaskStatus.FAILED,
        error_message="Timeout",
        task_metadata=None,
    )
    db.add(task)
    await db.commit()

    response = await async_client.get(
        f"/api/v1/tasks/{task.id}/resume-template",
        headers={"Authorization": f"Bearer {_token(requester)}"},
    )

    assert response.status_code == 404
