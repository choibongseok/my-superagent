"""Tests for rate limiting middleware and token bucket behavior."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware import rate_limit as rate_limit_module
from app.middleware.rate_limit import RateLimitMiddleware, TokenBucket


class InMemoryAsyncCache:
    """Minimal async cache stub for rate limit tests."""

    def __init__(self) -> None:
        self._values: dict[str, Any] = {}

    async def get(self, key: str) -> Any:
        return self._values.get(key)

    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        del ttl  # TTL is intentionally ignored for deterministic tests.
        self._values[key] = value
        return True


@pytest.fixture
def fake_cache(monkeypatch: pytest.MonkeyPatch) -> InMemoryAsyncCache:
    """Patch rate-limit module cache with in-memory async cache."""
    cache = InMemoryAsyncCache()
    monkeypatch.setattr(rate_limit_module, "cache", cache)
    return cache


@pytest.fixture
def frozen_time(monkeypatch: pytest.MonkeyPatch) -> dict[str, float]:
    """Freeze ``time.time`` for deterministic token refill calculations."""
    current = {"value": 1_700_000_000.0}
    monkeypatch.setattr(rate_limit_module.time, "time", lambda: current["value"])
    return current


@pytest.mark.asyncio
async def test_token_bucket_rejects_token_cost_over_capacity(
    fake_cache: InMemoryAsyncCache,
    frozen_time: dict[str, float],
) -> None:
    del fake_cache, frozen_time

    bucket = TokenBucket(capacity=2, refill_rate=1.0)

    assert await bucket.consume("client", tokens=3) is False
    assert await bucket.get_remaining("client") == pytest.approx(2.0)


@pytest.mark.asyncio
async def test_token_bucket_reports_retry_after_for_multi_token_request(
    fake_cache: InMemoryAsyncCache,
    frozen_time: dict[str, float],
) -> None:
    del fake_cache

    bucket = TokenBucket(capacity=4, refill_rate=2.0)

    assert await bucket.consume("client", tokens=4) is True

    retry_after = await bucket.get_retry_after("client", tokens=3)
    assert retry_after == pytest.approx(1.5)

    frozen_time["value"] += 1.0
    retry_after_after_refill = await bucket.get_retry_after("client", tokens=3)
    assert retry_after_after_refill == pytest.approx(0.5)


def test_rate_limit_middleware_applies_method_specific_request_costs(
    fake_cache: InMemoryAsyncCache,
    frozen_time: dict[str, float],
) -> None:
    del fake_cache, frozen_time

    app = FastAPI()

    @app.get("/items")
    async def get_items() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/items")
    async def post_items() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=60,
        burst_size=3,
        request_costs={"POST": 2},
    )

    with TestClient(app) as client:
        post_response = client.post("/items")
        assert post_response.status_code == 200
        assert post_response.headers["X-RateLimit-Request-Cost"] == "2"
        assert post_response.headers["X-RateLimit-Remaining"] == "1"

        get_response = client.get("/items")
        assert get_response.status_code == 200
        assert get_response.headers["X-RateLimit-Request-Cost"] == "1"
        assert get_response.headers["X-RateLimit-Remaining"] == "0"

        limited_response = client.get("/items")
        assert limited_response.status_code == 429
        assert limited_response.json()["retry_after"] == 1
        assert limited_response.headers["X-RateLimit-Request-Cost"] == "1"


def test_rate_limit_middleware_rejects_invalid_request_costs() -> None:
    app = FastAPI()

    with pytest.raises(
        ValueError,
        match="request_costs values must be positive integer token costs",
    ):
        RateLimitMiddleware(app, request_costs={"POST": 0})

    with pytest.raises(
        ValueError, match="request_costs values cannot exceed burst_size"
    ):
        RateLimitMiddleware(app, burst_size=2, request_costs={"POST": 3})
