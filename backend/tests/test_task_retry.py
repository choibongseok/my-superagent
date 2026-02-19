"""Tests for #203 Task Retry — POST /api/v1/tasks/{id}/retry."""

from unittest.mock import AsyncMock, MagicMock, patch
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(email: str = "retry@example.com") -> User:
    return User(
        id=uuid4(),
        email=email,
        full_name="Retry User",
        is_active=True,
    )


def _make_token(user: User) -> str:
    return create_access_token({"sub": str(user.id)})


# ---------------------------------------------------------------------------
# Async client fixture
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def async_client(db: AsyncSession):
    app.dependency_overrides[get_db] = lambda: (yield db)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_failed_task_creates_new_task(db: AsyncSession, async_client: AsyncClient):
    """Retrying a failed task should create a new PENDING/PROCESSING clone."""
    user = _make_user()
    db.add(user)
    await db.commit()

    failed_task = TaskModel(
        id=uuid4(),
        user_id=user.id,
        prompt="Research quantum computing",
        task_type=TaskType.RESEARCH,
        status=TaskStatus.FAILED,
        error_message="timeout",
        task_metadata=None,
    )
    db.add(failed_task)
    await db.commit()

    token = _make_token(user)

    # Patch Celery so the queue call succeeds without a real broker
    mock_celery_result = MagicMock()
    mock_celery_result.id = "celery-retry-abc"

    with patch(
        "app.agents.celery_app.process_research_task"
    ) as mock_celery:
        mock_celery.apply_async.return_value = mock_celery_result

        resp = await async_client.post(
            f"/api/v1/tasks/{failed_task.id}/retry",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 201, resp.text
    data = resp.json()

    # Must be a brand-new task (different id)
    assert data["id"] != str(failed_task.id)
    assert data["prompt"] == failed_task.prompt
    assert data["task_type"] == "research"
    assert data["status"] in ("pending", "processing")


@pytest.mark.asyncio
async def test_retry_non_failed_task_returns_400(db: AsyncSession, async_client: AsyncClient):
    """Retrying a task that is not in FAILED state must return HTTP 400."""
    user = _make_user()
    db.add(user)
    await db.commit()

    pending_task = TaskModel(
        id=uuid4(),
        user_id=user.id,
        prompt="Write a doc",
        task_type=TaskType.DOCS,
        status=TaskStatus.PENDING,
        task_metadata=None,
    )
    db.add(pending_task)
    await db.commit()

    token = _make_token(user)

    resp = await async_client.post(
        f"/api/v1/tasks/{pending_task.id}/retry",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 400
    assert "failed" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_retry_completed_task_returns_400(db: AsyncSession, async_client: AsyncClient):
    """Retrying a COMPLETED task must return HTTP 400."""
    user = _make_user()
    db.add(user)
    await db.commit()

    completed_task = TaskModel(
        id=uuid4(),
        user_id=user.id,
        prompt="Build a spreadsheet",
        task_type=TaskType.SHEETS,
        status=TaskStatus.COMPLETED,
        task_metadata=None,
    )
    db.add(completed_task)
    await db.commit()

    token = _make_token(user)

    resp = await async_client.post(
        f"/api/v1/tasks/{completed_task.id}/retry",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_retry_task_not_found_returns_404(db: AsyncSession, async_client: AsyncClient):
    """Retrying a non-existent task ID must return HTTP 404."""
    user = _make_user()
    db.add(user)
    await db.commit()

    token = _make_token(user)
    fake_id = uuid4()

    resp = await async_client.post(
        f"/api/v1/tasks/{fake_id}/retry",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_retry_task_owned_by_other_user_returns_404(db: AsyncSession, async_client: AsyncClient):
    """A user must not be able to retry another user's task."""
    owner = _make_user()
    requester = _make_user(email="other@example.com")
    db.add(owner)
    db.add(requester)
    await db.commit()

    task = TaskModel(
        id=uuid4(),
        user_id=owner.id,
        prompt="Slides deck",
        task_type=TaskType.SLIDES,
        status=TaskStatus.FAILED,
        task_metadata=None,
    )
    db.add(task)
    await db.commit()

    token = _make_token(requester)

    resp = await async_client.post(
        f"/api/v1/tasks/{task.id}/retry",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_retry_requires_auth(db: AsyncSession, async_client: AsyncClient):
    """Retry endpoint must reject unauthenticated requests."""
    resp = await async_client.post(f"/api/v1/tasks/{uuid4()}/retry")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_retry_when_celery_fails_marks_retry_task_failed(
    db: AsyncSession, async_client: AsyncClient
):
    """If Celery queuing raises, the retry task should be marked FAILED."""
    user = _make_user()
    db.add(user)
    await db.commit()

    failed_task = TaskModel(
        id=uuid4(),
        user_id=user.id,
        prompt="Research topic",
        task_type=TaskType.RESEARCH,
        status=TaskStatus.FAILED,
        error_message="original failure",
        task_metadata=None,
    )
    db.add(failed_task)
    await db.commit()

    token = _make_token(user)

    with patch(
        "app.agents.celery_app.process_research_task"
    ) as mock_celery:
        mock_celery.apply_async.side_effect = RuntimeError("broker unavailable")

        resp = await async_client.post(
            f"/api/v1/tasks/{failed_task.id}/retry",
            headers={"Authorization": f"Bearer {token}"},
        )

    # The endpoint still returns 201 with a new task in FAILED state
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "failed"
    assert "broker unavailable" in data["error_message"]
