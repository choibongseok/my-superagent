"""Tests for Developer API Mode (#219).

Covers:
- POST /api/v1/dev/api-keys  (JWT Bearer required)
- POST /api/v1/dev/tasks     (X-API-Key required)
- GET  /api/v1/dev/tasks/{id} (X-API-Key required)
- Auth edge-cases: missing key, invalid key, inactive key, inactive user
"""
from __future__ import annotations

import hashlib
from datetime import timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base, get_db, reset_engine
from app.core.security import create_access_token
from app.main import app
from app.models.api_key import ApiKey, generate_api_key, hash_api_key
from app.models.task import Task as TaskModel, TaskStatus, TaskType
from app.models.user import User

# ── helpers ──────────────────────────────────────────────────────────────────

import asyncio
import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


async def _make_user(name: str = "Dev User", email: str | None = None) -> tuple[User, str]:
    """Insert a user and return (user, jwt_token)."""
    async with _TestSession() as session:
        user = User(
            id=uuid4(),
            email=email or f"dev-{uuid4().hex[:8]}@example.com",
            full_name=name,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    token = create_access_token({"sub": str(user.id)})
    return user, token


async def _make_api_key(user: User, name: str = "test-key") -> tuple[ApiKey, str]:
    """Insert an ApiKey and return (api_key_obj, plaintext_key)."""
    plaintext = generate_api_key()
    key_hash = hash_api_key(plaintext)
    async with _TestSession() as session:
        api_key = ApiKey(
            id=uuid4(),
            user_id=user.id,
            key_hash=key_hash,
            name=name,
            is_active=True,
        )
        session.add(api_key)
        await session.commit()
        await session.refresh(api_key)
    return api_key, plaintext


# ── Unit tests: generate_api_key / hash_api_key ───────────────────────────────

def test_generate_api_key_prefix():
    key = generate_api_key()
    assert key.startswith("sk-"), f"Expected 'sk-' prefix, got: {key}"


def test_generate_api_key_uniqueness():
    keys = {generate_api_key() for _ in range(100)}
    assert len(keys) == 100, "Expected 100 unique API keys"


def test_hash_api_key_is_sha256():
    key = "sk-testkey"
    expected = hashlib.sha256(key.encode()).hexdigest()
    assert hash_api_key(key) == expected


def test_hash_api_key_deterministic():
    key = generate_api_key()
    assert hash_api_key(key) == hash_api_key(key)


def test_hash_api_key_different_keys():
    a = generate_api_key()
    b = generate_api_key()
    assert hash_api_key(a) != hash_api_key(b)


# ── POST /api/v1/dev/api-keys ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_api_key_success(ac: AsyncClient):
    user, token = await _make_user()
    resp = await ac.post(
        "/api/v1/dev/api-keys",
        json={"name": "my-key"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "my-key"
    assert data["key"].startswith("sk-")
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_create_api_key_requires_jwt(ac: AsyncClient):
    resp = await ac.post("/api/v1/dev/api-keys", json={"name": "x"})
    assert resp.status_code == 403  # HTTPBearer raises 403 on missing header


@pytest.mark.asyncio
async def test_create_api_key_invalid_jwt(ac: AsyncClient):
    resp = await ac.post(
        "/api/v1/dev/api-keys",
        json={"name": "x"},
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_api_key_missing_name(ac: AsyncClient):
    user, token = await _make_user()
    resp = await ac.post(
        "/api/v1/dev/api-keys",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


# ── POST /api/v1/dev/tasks ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dev_create_task_success(ac: AsyncClient):
    user, _ = await _make_user()
    _, plaintext = await _make_api_key(user)

    resp = await ac.post(
        "/api/v1/dev/tasks",
        json={"prompt": "Summarise AI trends", "task_type": "research"},
        headers={"X-API-Key": plaintext},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["prompt"] == "Summarise AI trends"
    assert data["task_type"] == "research"
    assert data["user_id"] == str(user.id)
    assert "id" in data


@pytest.mark.asyncio
async def test_dev_create_task_docs(ac: AsyncClient):
    user, _ = await _make_user()
    _, plaintext = await _make_api_key(user)

    resp = await ac.post(
        "/api/v1/dev/tasks",
        json={"prompt": "Write a project proposal", "task_type": "docs"},
        headers={"X-API-Key": plaintext},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["task_type"] == "docs"


@pytest.mark.asyncio
async def test_dev_create_task_sheets(ac: AsyncClient):
    user, _ = await _make_user()
    _, plaintext = await _make_api_key(user)

    resp = await ac.post(
        "/api/v1/dev/tasks",
        json={"prompt": "Monthly sales data", "task_type": "sheets"},
        headers={"X-API-Key": plaintext},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["task_type"] == "sheets"


@pytest.mark.asyncio
async def test_dev_create_task_slides(ac: AsyncClient):
    user, _ = await _make_user()
    _, plaintext = await _make_api_key(user)

    resp = await ac.post(
        "/api/v1/dev/tasks",
        json={"prompt": "Q3 investor pitch", "task_type": "slides"},
        headers={"X-API-Key": plaintext},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["task_type"] == "slides"


@pytest.mark.asyncio
async def test_dev_create_task_missing_api_key(ac: AsyncClient):
    resp = await ac.post(
        "/api/v1/dev/tasks",
        json={"prompt": "test", "task_type": "research"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_dev_create_task_invalid_api_key(ac: AsyncClient):
    resp = await ac.post(
        "/api/v1/dev/tasks",
        json={"prompt": "test", "task_type": "research"},
        headers={"X-API-Key": "sk-invalid-key-that-does-not-exist"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_dev_create_task_inactive_api_key(ac: AsyncClient):
    user, _ = await _make_user()
    plaintext = generate_api_key()
    async with _TestSession() as session:
        api_key = ApiKey(
            id=uuid4(),
            user_id=user.id,
            key_hash=hash_api_key(plaintext),
            name="inactive",
            is_active=False,
        )
        session.add(api_key)
        await session.commit()

    resp = await ac.post(
        "/api/v1/dev/tasks",
        json={"prompt": "test", "task_type": "research"},
        headers={"X-API-Key": plaintext},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_dev_create_task_invalid_task_type(ac: AsyncClient):
    user, _ = await _make_user()
    _, plaintext = await _make_api_key(user)

    resp = await ac.post(
        "/api/v1/dev/tasks",
        json={"prompt": "test", "task_type": "not_a_type"},
        headers={"X-API-Key": plaintext},
    )
    assert resp.status_code == 422


# ── GET /api/v1/dev/tasks/{id} ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dev_get_task_success(ac: AsyncClient):
    user, _ = await _make_user()
    _, plaintext = await _make_api_key(user)

    # Create task first
    create_resp = await ac.post(
        "/api/v1/dev/tasks",
        json={"prompt": "Test retrieval", "task_type": "research"},
        headers={"X-API-Key": plaintext},
    )
    assert create_resp.status_code == 201
    task_id = create_resp.json()["id"]

    # Fetch it
    get_resp = await ac.get(
        f"/api/v1/dev/tasks/{task_id}",
        headers={"X-API-Key": plaintext},
    )
    assert get_resp.status_code == 200, get_resp.text
    data = get_resp.json()
    assert data["id"] == task_id
    assert data["prompt"] == "Test retrieval"


@pytest.mark.asyncio
async def test_dev_get_task_not_found(ac: AsyncClient):
    user, _ = await _make_user()
    _, plaintext = await _make_api_key(user)

    resp = await ac.get(
        f"/api/v1/dev/tasks/{uuid4()}",
        headers={"X-API-Key": plaintext},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_dev_get_task_other_user_cannot_access(ac: AsyncClient):
    """A task owned by user A must not be visible to user B's API key."""
    user_a, _ = await _make_user(email="a@example.com")
    user_b, _ = await _make_user(email="b@example.com")
    _, key_a = await _make_api_key(user_a, name="key-a")
    _, key_b = await _make_api_key(user_b, name="key-b")

    create_resp = await ac.post(
        "/api/v1/dev/tasks",
        json={"prompt": "secret research", "task_type": "research"},
        headers={"X-API-Key": key_a},
    )
    assert create_resp.status_code == 201
    task_id = create_resp.json()["id"]

    # User B tries to fetch user A's task
    resp = await ac.get(
        f"/api/v1/dev/tasks/{task_id}",
        headers={"X-API-Key": key_b},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_dev_get_task_missing_api_key(ac: AsyncClient):
    resp = await ac.get(f"/api/v1/dev/tasks/{uuid4()}")
    assert resp.status_code == 401


# ── last_used_at updated after successful request ──────────────────────────────

@pytest.mark.asyncio
async def test_api_key_last_used_at_updated(ac: AsyncClient):
    user, _ = await _make_user()
    api_key_obj, plaintext = await _make_api_key(user)

    # last_used_at should be None initially
    async with _TestSession() as session:
        result = await session.get(ApiKey, api_key_obj.id)
        assert result is not None
        assert result.last_used_at is None

    # Make an authenticated request
    await ac.post(
        "/api/v1/dev/tasks",
        json={"prompt": "ping", "task_type": "research"},
        headers={"X-API-Key": plaintext},
    )

    async with _TestSession() as session:
        result = await session.get(ApiKey, api_key_obj.id)
        assert result is not None
        assert result.last_used_at is not None
