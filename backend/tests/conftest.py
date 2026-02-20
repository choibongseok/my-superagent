"""
Pytest configuration and fixtures.

DATABASE_URL is overridden to in-memory SQLite *before* any app module is
imported, so that database.py's lazy engine initialisation picks up the test
URL instead of the real PostgreSQL URL.
"""
from __future__ import annotations

import os

# ── Set test DB URL before importing anything from app ───────────────────────
# database.py creates the engine lazily, so this override takes effect as long
# as it happens before the first call to get_db() / _get_engine().
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

# ── Fake LLM API keys so client constructors don't raise ─────────────────────
# Tests that access agent.llm trigger lazy ChatOpenAI/ChatAnthropic construction.
# A non-empty placeholder prevents the "api_key must be set" error; actual LLM
# calls are always mocked (patch.object(agent, 'run', ...)) so no real requests
# are ever made.
os.environ.setdefault("OPENAI_API_KEY", "sk-test-placeholder-not-real")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-placeholder-not-real")

import asyncio  # noqa: E402
from typing import AsyncGenerator  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from httpx import AsyncClient, ASGITransport  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.database import Base, get_db, reset_engine, inject_engine  # noqa: E402
from app.main import app  # noqa: E402

# ── Async in-memory SQLite engine for tests ───────────────────────────────────
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestAsyncSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Inject the SAME engine into the app so that both conftest helpers and
# FastAPI route handlers operate on the same in-memory SQLite database.
# (reset_engine(URL) would create a different StaticPool instance.)
inject_engine(test_engine, TestAsyncSessionLocal)


# ── Schema helpers ────────────────────────────────────────────────────────────

async def _create_tables() -> None:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _drop_tables() -> None:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ── Session fixture ───────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    """Provide a clean async DB session per test; rolls back after each test."""
    await _create_tables()
    async with TestAsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.rollback()
    await _drop_tables()


# ── Sync-style fixture for legacy tests ──────────────────────────────────────

@pytest.fixture
def sync_db():
    """Synchronous fixture that wraps async db creation for legacy test code."""
    loop = asyncio.new_event_loop()
    loop.run_until_complete(_create_tables())

    async def _get():
        async with TestAsyncSessionLocal() as session:
            yield session

    gen = _get().__aiter__()
    session = loop.run_until_complete(gen.__anext__())
    try:
        yield session
    finally:
        loop.run_until_complete(session.rollback())
        loop.run_until_complete(_drop_tables())
        loop.close()


# Compatibility alias used by older tests.
@pytest.fixture
def db_session(sync_db):
    """Backward-compatible alias for fixtures expecting ``db_session``."""
    return sync_db


# ── Override FastAPI get_db ───────────────────────────────────────────────────

async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
    # IMPORTANT: use TestAsyncSessionLocal (test_engine) — NOT the lazy app engine.
    # Both conftest and routes must see the same in-memory SQLite instance.
    async with TestAsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@pytest.fixture
def client() -> TestClient:
    """Sync TestClient with DB override."""
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def async_client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client for async route tests.

    Depends on ``db`` to ensure tables are created before the first request.
    The ``db`` session is also available to tests that request both fixtures,
    allowing them to seed data that the endpoint can then query.
    """
    app.dependency_overrides[get_db] = _override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()
