"""
API endpoint tests
"""
import pytest
from fastapi.testclient import TestClient


def test_root_endpoint(client: TestClient):
    """Test root endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "AgentHQ"
    assert data["version"] == "0.1.0"
    assert data["status"] == "running"


def test_health_endpoint(client: TestClient):
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "environment" in data


def test_api_docs_available(client: TestClient):
    """Test API documentation is accessible"""
    response = client.get("/docs")
    assert response.status_code == 200


def test_tasks_endpoint_requires_auth(client: TestClient):
    """Test tasks endpoint requires authentication.

    FastAPI's HTTPBearer returns 403 when no Authorization header is present
    (FastAPI >= 0.95 / Starlette behaviour).
    """
    response = client.get("/api/v1/tasks")
    assert response.status_code in (401, 403)


def test_create_task_requires_auth(client: TestClient):
    """Test task creation requires authentication."""
    response = client.post(
        "/api/v1/tasks",
        json={
            "type": "research",
            "prompt": "Test prompt",
            "config": {}
        }
    )
    assert response.status_code in (401, 403)
