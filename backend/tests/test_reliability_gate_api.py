"""Tests for #261 Pre-Run Reliability Gate.

Endpoint: POST /api/v1/tasks/reliability-gate

The gate evaluates execution risk before creating/updating queued tasks.
"""

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

def _user(email: str = "gate@example.com") -> User:
    return User(
        id=uuid4(),
        email=email,
        is_active=True,
    )


def _token(user: User) -> str:
    return create_access_token({"sub": str(user.id)})


# Async client fixture (same pattern as other API tests in this repo)
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
async def test_reliability_gate_flags_missing_google_credentials(
    db: AsyncSession,
    async_client: AsyncClient,
):
    user = _user()
    db.add(user)
    await db.commit()

    resp = await async_client.post(
        "/api/v1/tasks/reliability-gate",
        json={"task_type": "docs", "prompt": "Create a short meeting summary"},
        headers={"Authorization": f"Bearer {_token(user)}"},
    )

    assert resp.status_code == 200, resp.text
    payload = resp.json()

    assert payload["go_no_go"] is False
    assert payload["risk_level"] == "high"
    assert payload["reliability_score"] < 65
    assert any(
        check["id"] == "google_auth" and check["status"] == "fail"
        for check in payload["checks"]
    )


@pytest.mark.asyncio
async def test_reliability_gate_passes_with_healthy_history(
    db: AsyncSession,
    async_client: AsyncClient,
):
    user = User(id=uuid4(), email="healthy@example.com", is_active=True, google_access_token="token")
    db.add(user)
    await db.commit()

    # Positive signal: recent success history and short prompt.
    db.add(
        TaskModel(
            id=uuid4(),
            user_id=user.id,
            prompt="Draft a short weekly update",
            task_type=TaskType.RESEARCH,
            status=TaskStatus.COMPLETED,
        )
    )
    await db.commit()

    resp = await async_client.post(
        "/api/v1/tasks/reliability-gate",
        json={"task_type": "research", "prompt": "Draft a short weekly update"},
        headers={"Authorization": f"Bearer {_token(user)}"},
    )

    assert resp.status_code == 200, resp.text
    payload = resp.json()

    assert payload["task_type"] == "research"
    assert payload["go_no_go"] is True
    assert payload["reliability_score"] >= 65
    assert payload["failure_probability"] <= 0.35
    assert payload["risk_level"] in {"low", "medium"}


@pytest.mark.asyncio
async def test_reliability_gate_increases_risk_for_repeated_failures(
    db: AsyncSession,
    async_client: AsyncClient,
):
    user = User(
        id=uuid4(),
        email="flaky@example.com",
        is_active=True,
        google_access_token="token",
    )
    db.add(user)
    await db.commit()

    # Build a history of repeated failures for the exact same task.
    for _ in range(5):
        db.add(
            TaskModel(
                id=uuid4(),
                user_id=user.id,
                prompt="Summarize Q4 performance metrics",
                task_type=TaskType.SLIDES,
                status=TaskStatus.FAILED,
                error_message="Google API error: quota exceeded",
            )
        )
    await db.commit()

    resp = await async_client.post(
        "/api/v1/tasks/reliability-gate",
        json={
            "task_type": "slides",
            "prompt": "Summarize Q4 performance metrics",
        },
        headers={"Authorization": f"Bearer {_token(user)}"},
    )

    assert resp.status_code == 200, resp.text
    payload = resp.json()

    assert payload["go_no_go"] is False
    assert payload["recent_failures"] == 5
    assert payload["repeat_failure_count"] == 5
    assert payload["reliability_score"] < 65
    assert any(check["id"] == "repeated_prompt" for check in payload["checks"])
    assert any(
        check["id"] == "execution_readiness" and check["status"] == "fail"
        for check in payload["checks"]
    )


@pytest.mark.asyncio
async def test_reliability_gate_requires_auth(
    db: AsyncSession,
    async_client: AsyncClient,
):
    resp = await async_client.post(
        "/api/v1/tasks/reliability-gate",
        json={"task_type": "research", "prompt": "Some prompt"},
    )

    assert resp.status_code in (401, 403)
