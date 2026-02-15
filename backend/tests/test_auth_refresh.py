"""Authentication refresh endpoint tests."""

from uuid import uuid4
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import auth
from app.core.database import get_db
from app.models.user import User


@pytest.fixture
def mock_db():
    """Mock async database session."""
    return AsyncMock()


@pytest.fixture
def client(mock_db):
    """Create isolated test app for auth routes."""
    app = FastAPI()
    app.include_router(auth.router, prefix="/api/v1/auth")

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client


def test_refresh_token_accepts_refresh_token_only_payload(client, mock_db, monkeypatch):
    """Refresh endpoint should accept payload with only refresh_token."""
    user = User(email="refresh@example.com", full_name="Refresh User")
    user.id = uuid4()
    user.is_active = True

    mock_result = Mock()
    mock_result.scalar_one_or_none.return_value = user
    mock_db.execute.return_value = mock_result

    monkeypatch.setattr(
        "app.core.security.decode_token",
        lambda token, **_: {"sub": str(user.id), "type": "refresh"},
    )
    monkeypatch.setattr(auth, "create_access_token", lambda data: "new_access_token")
    monkeypatch.setattr(auth, "create_refresh_token", lambda data: "new_refresh_token")

    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "old_refresh_token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] == "new_access_token"
    assert data["refresh_token"] == "new_refresh_token"
    assert data["user"]["email"] == "refresh@example.com"


def test_refresh_token_requires_refresh_token_field(client):
    """Refresh endpoint should validate missing refresh_token."""
    response = client.post("/api/v1/auth/refresh", json={})
    assert response.status_code == 422


def test_oauth_callback_get_returns_popup_bridge_page(client):
    """GET callback should return HTML that posts OAuth payload to opener window."""
    response = client.get(
        "/api/v1/auth/callback",
        params={"code": "abc123", "state": "state-1"},
    )

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "agenthq:oauth:callback" in response.text
    assert '"code": "abc123"' in response.text


def test_oauth_callback_get_includes_error_payload(client):
    """GET callback should include OAuth errors for frontend handling."""
    response = client.get(
        "/api/v1/auth/callback",
        params={
            "error": "access_denied",
            "error_description": "User denied access",
        },
    )

    assert response.status_code == 200
    assert "agenthq:oauth:callback" in response.text
    assert '"error": "access_denied"' in response.text
