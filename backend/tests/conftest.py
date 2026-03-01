"""
Pytest configuration and fixtures
"""
import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import get_db, AsyncSessionLocal, engine, Base

# Set test environment variables
os.environ.setdefault("OPENAI_API_KEY", "test_openai_key_12345")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_anthropic_key_67890")
os.environ.setdefault("LANGFUSE_SECRET_KEY", "test_langfuse_secret")
os.environ.setdefault("LANGFUSE_PUBLIC_KEY", "test_langfuse_public")
os.environ.setdefault("LANGFUSE_HOST", "https://cloud.langfuse.com")


@pytest.fixture(scope="session")
async def setup_database():
    """Create test database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db(setup_database):
    """Create test database session"""
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()


@pytest.fixture
def client():
    """Create test client"""
    with TestClient(app) as test_client:
        yield test_client
