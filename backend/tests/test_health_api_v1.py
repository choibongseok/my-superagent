"""Tests for API v1 health endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.health import router


@pytest.fixture
def health_client() -> TestClient:
    """Create an isolated app that mounts only the health router."""
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        yield client


def test_status_returns_all_services_by_default(health_client: TestClient) -> None:
    """Default status responses should include all known services."""
    response = health_client.get("/status")

    assert response.status_code == 200
    assert response.json() == {
        "status": "operational",
        "services": {
            "api": "healthy",
            "database": "healthy",
            "redis": "healthy",
        },
    }


def test_status_can_filter_requested_services(health_client: TestClient) -> None:
    """Service filtering should keep requested services in user-provided order."""
    response = health_client.get("/status", params={"services": "redis,api,redis"})

    assert response.status_code == 200
    assert response.json() == {
        "status": "operational",
        "services": {
            "redis": "healthy",
            "api": "healthy",
        },
    }


def test_status_rejects_unknown_service_filters(health_client: TestClient) -> None:
    """Unknown services should return a clear validation error."""
    response = health_client.get("/status", params={"services": "api,search"})

    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "Unknown services: search. Supported services: api, database, redis."
    )


def test_status_includes_uptime_when_requested(
    health_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Status endpoint should expose deterministic uptime diagnostics."""
    monkeypatch.setattr("app.api.v1.health._START_TIME_MONOTONIC", 10.0)
    monkeypatch.setattr("app.api.v1.health.time.monotonic", lambda: 12.34567)

    response = health_client.get("/status", params={"include_uptime": True})

    assert response.status_code == 200
    assert response.json()["uptime_seconds"] == 2.346


def test_ping_can_include_uptime(
    health_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ping endpoint should support optional uptime diagnostics."""
    monkeypatch.setattr("app.api.v1.health._START_TIME_MONOTONIC", 100.0)
    monkeypatch.setattr("app.api.v1.health.time.monotonic", lambda: 100.75)

    response = health_client.get("/ping", params={"include_uptime": True})

    assert response.status_code == 200
    assert response.json() == {
        "message": "pong",
        "uptime_seconds": 0.75,
    }
