"""Tests for Onboarding Wizard (#224).

Covers:
- GET  /api/v1/onboarding/status       — initial + after steps
- GET  /api/v1/onboarding/use-cases    — static use-case list
- POST /api/v1/onboarding/use-case     — select use case
- POST /api/v1/onboarding/sample-task  — record sample task
- POST /api/v1/onboarding/complete     — finish wizard
- POST /api/v1/onboarding/skip         — skip wizard
- POST /api/v1/onboarding/reset        — reset wizard
- Auth edge-cases: missing auth returns 401
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-placeholder-not-real")

from app.core.database import Base, get_db, reset_engine
from app.core.security import create_access_token
from app.main import app
from app.models.onboarding import OnboardingStep, UseCase
from app.models.user import User

# ── test DB setup ────────────────────────────────────────────────────────────

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
_engine = create_async_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
reset_engine(TEST_DB_URL)


async def _create_tables():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _drop_tables():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _override_get_db():
    async with _TestSession() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await _create_tables()
    yield
    await _drop_tables()


@pytest_asyncio.fixture
async def ac() -> AsyncClient:
    app.dependency_overrides[get_db] = _override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
    app.dependency_overrides.clear()


# ── helpers ──────────────────────────────────────────────────────────────────


async def _seed_user(email: str = "onboard@test.com") -> tuple[User, dict]:
    """Create a user and return (user, auth_headers)."""
    user = User(id=uuid4(), email=email, full_name="Onboard Tester", is_active=True)
    async with _TestSession() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)
    token = create_access_token(data={"sub": str(user.id)})
    headers = {"Authorization": f"Bearer {token}"}
    return user, headers


# ── tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_requires_auth(ac: AsyncClient):
    """Unauthenticated request should get 401."""
    resp = await ac.get("/api/v1/onboarding/status")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_initial_status_is_welcome(ac: AsyncClient):
    """First call should auto-create progress at WELCOME step."""
    user, headers = await _seed_user()
    resp = await ac.get("/api/v1/onboarding/status", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_step"] == "welcome"
    assert data["is_completed"] is False
    assert data["use_case"] is None
    assert data["sample_task_id"] is None


@pytest.mark.asyncio
async def test_list_use_cases(ac: AsyncClient):
    """Use-cases endpoint should return 4 options."""
    user, headers = await _seed_user()
    resp = await ac.get("/api/v1/onboarding/use-cases", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 4
    keys = {item["key"] for item in data}
    assert keys == {"research", "documents", "data_analysis", "presentations"}
    # Each option should have expected fields
    for item in data:
        assert "title" in item
        assert "description" in item
        assert "icon" in item
        assert "sample_prompt" in item


@pytest.mark.asyncio
async def test_select_use_case_advances_step(ac: AsyncClient):
    """Selecting a use case should advance to SAMPLE_TASK and return prompts."""
    user, headers = await _seed_user()
    resp = await ac.post(
        "/api/v1/onboarding/use-case",
        headers=headers,
        json={"use_case": "research"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["next_step"] == "sample_task"
    assert len(data["suggestions"]) > 0
    assert data["suggestions"][0]["task_type"] == "research"

    # Status should now reflect the change
    resp2 = await ac.get("/api/v1/onboarding/status", headers=headers)
    assert resp2.json()["current_step"] == "sample_task"
    assert resp2.json()["use_case"] == "research"


@pytest.mark.asyncio
async def test_select_use_case_documents(ac: AsyncClient):
    """Verify docs use case returns docs-typed prompts."""
    user, headers = await _seed_user()
    resp = await ac.post(
        "/api/v1/onboarding/use-case",
        headers=headers,
        json={"use_case": "documents"},
    )
    assert resp.status_code == 200
    data = resp.json()
    for s in data["suggestions"]:
        assert s["task_type"] == "docs"


@pytest.mark.asyncio
async def test_select_use_case_data_analysis(ac: AsyncClient):
    """Verify data_analysis use case returns sheets-typed prompts."""
    user, headers = await _seed_user()
    resp = await ac.post(
        "/api/v1/onboarding/use-case",
        headers=headers,
        json={"use_case": "data_analysis"},
    )
    assert resp.status_code == 200
    data = resp.json()
    for s in data["suggestions"]:
        assert s["task_type"] == "sheets"


@pytest.mark.asyncio
async def test_select_use_case_presentations(ac: AsyncClient):
    """Verify presentations use case returns slides-typed prompts."""
    user, headers = await _seed_user()
    resp = await ac.post(
        "/api/v1/onboarding/use-case",
        headers=headers,
        json={"use_case": "presentations"},
    )
    assert resp.status_code == 200
    data = resp.json()
    for s in data["suggestions"]:
        assert s["task_type"] == "slides"


@pytest.mark.asyncio
async def test_record_sample_task_completes(ac: AsyncClient):
    """Recording a sample task should advance to COMPLETED."""
    user, headers = await _seed_user()
    # Step through use-case first
    await ac.post(
        "/api/v1/onboarding/use-case",
        headers=headers,
        json={"use_case": "research"},
    )
    task_id = str(uuid4())
    resp = await ac.post(
        "/api/v1/onboarding/sample-task",
        headers=headers,
        json={"task_id": task_id},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_step"] == "completed"
    assert data["is_completed"] is True
    assert data["sample_task_id"] == task_id
    assert data["completed_at"] is not None


@pytest.mark.asyncio
async def test_complete_returns_tips(ac: AsyncClient):
    """POST /complete should return tips."""
    user, headers = await _seed_user()
    resp = await ac.post("/api/v1/onboarding/complete", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "tips" in data
    assert len(data["tips"]) > 0
    assert "message" in data
    assert "🎉" in data["message"]


@pytest.mark.asyncio
async def test_complete_is_idempotent(ac: AsyncClient):
    """Calling complete twice should not error."""
    user, headers = await _seed_user()
    resp1 = await ac.post("/api/v1/onboarding/complete", headers=headers)
    resp2 = await ac.post("/api/v1/onboarding/complete", headers=headers)
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json() == resp2.json()


@pytest.mark.asyncio
async def test_skip_onboarding(ac: AsyncClient):
    """POST /skip should jump to COMPLETED."""
    user, headers = await _seed_user()
    resp = await ac.post("/api/v1/onboarding/skip", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_step"] == "completed"
    assert data["is_completed"] is True


@pytest.mark.asyncio
async def test_reset_onboarding(ac: AsyncClient):
    """POST /reset should bring wizard back to WELCOME."""
    user, headers = await _seed_user()
    # Complete it first
    await ac.post("/api/v1/onboarding/skip", headers=headers)
    # Reset
    resp = await ac.post("/api/v1/onboarding/reset", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_step"] == "welcome"
    assert data["is_completed"] is False
    assert data["use_case"] is None
    assert data["sample_task_id"] is None
    assert data["completed_at"] is None


@pytest.mark.asyncio
async def test_full_wizard_flow(ac: AsyncClient):
    """Walk through the entire onboarding flow end-to-end."""
    user, headers = await _seed_user("flow@test.com")

    # 1. Initial status
    resp = await ac.get("/api/v1/onboarding/status", headers=headers)
    assert resp.json()["current_step"] == "welcome"

    # 2. Browse use cases
    resp = await ac.get("/api/v1/onboarding/use-cases", headers=headers)
    assert len(resp.json()) == 4

    # 3. Select use case
    resp = await ac.post(
        "/api/v1/onboarding/use-case",
        headers=headers,
        json={"use_case": "data_analysis"},
    )
    suggestions = resp.json()["suggestions"]
    assert len(suggestions) > 0

    # 4. Record sample task
    task_id = str(uuid4())
    resp = await ac.post(
        "/api/v1/onboarding/sample-task",
        headers=headers,
        json={"task_id": task_id},
    )
    assert resp.json()["is_completed"] is True

    # 5. Complete and get tips
    resp = await ac.post("/api/v1/onboarding/complete", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["tips"]) >= 3


@pytest.mark.asyncio
async def test_invalid_use_case_rejected(ac: AsyncClient):
    """Submitting an invalid use case should fail validation."""
    user, headers = await _seed_user()
    resp = await ac.post(
        "/api/v1/onboarding/use-case",
        headers=headers,
        json={"use_case": "nonexistent"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_invalid_task_id_rejected(ac: AsyncClient):
    """Submitting a non-UUID task_id should fail validation."""
    user, headers = await _seed_user()
    resp = await ac.post(
        "/api/v1/onboarding/sample-task",
        headers=headers,
        json={"task_id": "not-a-uuid"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_two_users_independent_progress(ac: AsyncClient):
    """Two different users should have independent onboarding states."""
    user1, h1 = await _seed_user("user1@test.com")
    user2, h2 = await _seed_user("user2@test.com")

    # User1 completes onboarding
    await ac.post("/api/v1/onboarding/skip", headers=h1)

    # User2 should still be at welcome
    resp = await ac.get("/api/v1/onboarding/status", headers=h2)
    assert resp.json()["current_step"] == "welcome"

    resp = await ac.get("/api/v1/onboarding/status", headers=h1)
    assert resp.json()["current_step"] == "completed"
