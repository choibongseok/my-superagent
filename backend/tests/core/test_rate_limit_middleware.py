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


def test_rate_limit_middleware_applies_exact_path_request_costs(
    fake_cache: InMemoryAsyncCache,
    frozen_time: dict[str, float],
) -> None:
    del fake_cache, frozen_time

    app = FastAPI()

    @app.get("/reports")
    async def reports() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=60,
        burst_size=5,
        request_costs={"GET": 1},
        path_request_costs={"/reports": 4},
    )

    with TestClient(app) as client:
        response = client.get("/reports")
        assert response.status_code == 200
        assert response.headers["X-RateLimit-Request-Cost"] == "4"
        assert response.headers["X-RateLimit-Remaining"] == "1"


def test_rate_limit_middleware_applies_longest_prefix_path_request_cost(
    fake_cache: InMemoryAsyncCache,
    frozen_time: dict[str, float],
) -> None:
    del fake_cache, frozen_time

    app = FastAPI()

    @app.get("/api/v1/tasks/{task_id}")
    async def read_task(task_id: str) -> dict[str, str]:
        return {"task_id": task_id}

    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=60,
        burst_size=6,
        path_request_costs={
            "/api/*": 2,
            "/api/v1/tasks/*": 5,
        },
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/tasks/abc")
        assert response.status_code == 200
        assert response.headers["X-RateLimit-Request-Cost"] == "5"
        assert response.headers["X-RateLimit-Remaining"] == "1"


def test_rate_limit_middleware_supports_glob_path_request_costs(
    fake_cache: InMemoryAsyncCache,
    frozen_time: dict[str, float],
) -> None:
    del fake_cache, frozen_time

    app = FastAPI()

    @app.get("/api/v1/teams/{team_id}/reports/{report_id}")
    async def read_team_report(team_id: str, report_id: str) -> dict[str, str]:
        return {"team_id": team_id, "report_id": report_id}

    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=60,
        burst_size=6,
        path_request_costs={"/api/*/teams/*/reports/*": 4},
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/teams/alpha/reports/daily")
        assert response.status_code == 200
        assert response.headers["X-RateLimit-Request-Cost"] == "4"
        assert response.headers["X-RateLimit-Remaining"] == "2"


def test_rate_limit_middleware_prioritizes_exact_over_prefix_and_glob_costs(
    fake_cache: InMemoryAsyncCache,
    frozen_time: dict[str, float],
) -> None:
    del fake_cache, frozen_time

    app = FastAPI()

    @app.get("/api/v1/reports/snapshot")
    async def report_snapshot() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=60,
        burst_size=8,
        path_request_costs={
            "/api/*/reports/*": 2,
            "/api/v1/*": 4,
            "/api/v1/reports/snapshot": 7,
        },
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/reports/snapshot")
        assert response.status_code == 200
        assert response.headers["X-RateLimit-Request-Cost"] == "7"
        assert response.headers["X-RateLimit-Remaining"] == "1"


def test_rate_limit_middleware_supports_method_scoped_path_request_costs(
    fake_cache: InMemoryAsyncCache,
    frozen_time: dict[str, float],
) -> None:
    del fake_cache, frozen_time

    app = FastAPI()

    @app.get("/reports")
    async def get_reports() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/reports")
    async def create_report() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=60,
        burst_size=6,
        request_costs={"POST": 3},
        path_request_costs={
            "/reports": 2,
            "POST /reports": 5,
        },
    )

    with TestClient(app) as client:
        post_response = client.post("/reports")
        assert post_response.status_code == 200
        assert post_response.headers["X-RateLimit-Request-Cost"] == "5"
        assert post_response.headers["X-RateLimit-Remaining"] == "1"

        get_response = client.get("/reports")
        assert get_response.status_code == 429
        assert get_response.headers["X-RateLimit-Request-Cost"] == "2"


def test_rate_limit_middleware_prioritizes_method_scoped_prefix_path_costs(
    fake_cache: InMemoryAsyncCache,
    frozen_time: dict[str, float],
) -> None:
    del fake_cache, frozen_time

    app = FastAPI()

    @app.get("/api/v1/jobs/{job_id}")
    async def read_job(job_id: str) -> dict[str, str]:
        return {"job_id": job_id}

    @app.post("/api/v1/jobs/{job_id}")
    async def update_job(job_id: str) -> dict[str, str]:
        return {"job_id": job_id}

    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=60,
        burst_size=8,
        path_request_costs={
            "/api/*": 2,
            "POST /api/v1/jobs/*": 6,
        },
    )

    with TestClient(app) as client:
        post_response = client.post("/api/v1/jobs/1")
        assert post_response.status_code == 200
        assert post_response.headers["X-RateLimit-Request-Cost"] == "6"

        get_response = client.get("/api/v1/jobs/1")
        assert get_response.status_code == 200
        assert get_response.headers["X-RateLimit-Request-Cost"] == "2"


def test_rate_limit_middleware_rejects_invalid_path_request_costs() -> None:
    app = FastAPI()

    with pytest.raises(
        ValueError,
        match="path_request_costs keys must start with '/'",
    ):
        RateLimitMiddleware(app, path_request_costs={"tasks": 1})

    with pytest.raises(
        ValueError,
        match="path_request_costs method prefix must be alphabetic",
    ):
        RateLimitMiddleware(app, path_request_costs={"P0ST /tasks": 1})

    with pytest.raises(
        ValueError,
        match="path_request_costs values cannot exceed burst_size",
    ):
        RateLimitMiddleware(app, burst_size=2, path_request_costs={"/tasks": 3})


def test_rate_limit_middleware_allows_custom_exact_exclude_paths(
    fake_cache: InMemoryAsyncCache,
    frozen_time: dict[str, float],
) -> None:
    del fake_cache, frozen_time

    app = FastAPI()

    @app.get("/internal/ping")
    async def internal_ping() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/limited")
    async def limited() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=60,
        burst_size=1,
        exclude_paths=["/internal/ping"],
    )

    with TestClient(app) as client:
        excluded_first = client.get("/internal/ping")
        excluded_second = client.get("/internal/ping")

        assert excluded_first.status_code == 200
        assert excluded_second.status_code == 200
        assert "X-RateLimit-Remaining" not in excluded_first.headers

        limited_first = client.get("/limited")
        limited_second = client.get("/limited")

        assert limited_first.status_code == 200
        assert limited_second.status_code == 429


def test_rate_limit_middleware_supports_method_scoped_exclude_path_prefixes(
    fake_cache: InMemoryAsyncCache,
    frozen_time: dict[str, float],
) -> None:
    del fake_cache, frozen_time

    app = FastAPI()

    @app.get("/admin/tasks/1")
    async def admin_get() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/admin/tasks/1")
    async def admin_post() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=60,
        burst_size=1,
        exclude_paths=["GET /admin/*"],
    )

    with TestClient(app) as client:
        assert client.get("/admin/tasks/1").status_code == 200
        assert client.get("/admin/tasks/1").status_code == 200

        post_first = client.post("/admin/tasks/1")
        post_second = client.post("/admin/tasks/1")

        assert post_first.status_code == 200
        assert post_second.status_code == 429


def test_rate_limit_middleware_supports_method_scoped_glob_exclude_paths(
    fake_cache: InMemoryAsyncCache,
    frozen_time: dict[str, float],
) -> None:
    del fake_cache, frozen_time

    app = FastAPI()

    @app.get("/admin/v1/team/health")
    async def admin_health_get() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/admin/v1/team/health")
    async def admin_health_post() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=60,
        burst_size=1,
        exclude_paths=["GET /admin/*/team/health"],
    )

    with TestClient(app) as client:
        assert client.get("/admin/v1/team/health").status_code == 200
        assert client.get("/admin/v1/team/health").status_code == 200

        post_first = client.post("/admin/v1/team/health")
        post_second = client.post("/admin/v1/team/health")

        assert post_first.status_code == 200
        assert post_second.status_code == 429


def test_rate_limit_middleware_uses_client_id_header_for_bucket_isolation(
    fake_cache: InMemoryAsyncCache,
    frozen_time: dict[str, float],
) -> None:
    del fake_cache, frozen_time

    app = FastAPI()

    @app.get("/limited")
    async def limited() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=60,
        burst_size=1,
        client_id_header="X-API-Key",
    )

    with TestClient(app) as client:
        first_alpha = client.get("/limited", headers={"X-API-Key": "alpha"})
        second_alpha = client.get("/limited", headers={"X-API-Key": "alpha"})
        first_beta = client.get("/limited", headers={"X-API-Key": "beta"})

        assert first_alpha.status_code == 200
        assert second_alpha.status_code == 429
        assert first_beta.status_code == 200


def test_rate_limit_middleware_uses_forwarded_header_for_bucket_isolation(
    fake_cache: InMemoryAsyncCache,
    frozen_time: dict[str, float],
) -> None:
    del fake_cache, frozen_time

    app = FastAPI()

    @app.get("/limited")
    async def limited() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=60,
        burst_size=1,
    )

    with TestClient(app) as client:
        first_ipv6 = client.get(
            "/limited",
            headers={"Forwarded": 'for="[2001:db8::1]:1234";proto=https'},
        )
        second_same_ipv6 = client.get(
            "/limited",
            headers={"Forwarded": "for=[2001:db8::1]"},
        )
        first_other_ipv6 = client.get(
            "/limited",
            headers={"Forwarded": "for=[2001:db8::2]"},
        )

        assert first_ipv6.status_code == 200
        assert second_same_ipv6.status_code == 429
        assert first_other_ipv6.status_code == 200


def test_rate_limit_middleware_uses_x_real_ip_when_forwarded_headers_missing(
    fake_cache: InMemoryAsyncCache,
    frozen_time: dict[str, float],
) -> None:
    del fake_cache, frozen_time

    app = FastAPI()

    @app.get("/limited")
    async def limited() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=60,
        burst_size=1,
    )

    with TestClient(app) as client:
        first_internal = client.get("/limited", headers={"X-Real-IP": "10.0.0.1"})
        second_internal = client.get("/limited", headers={"X-Real-IP": "10.0.0.1"})
        first_other_internal = client.get(
            "/limited",
            headers={"X-Real-IP": "10.0.0.2"},
        )

        assert first_internal.status_code == 200
        assert second_internal.status_code == 429
        assert first_other_internal.status_code == 200


def test_rate_limit_middleware_uses_x_forwarded_for_and_normalizes_port_values(
    fake_cache: InMemoryAsyncCache,
    frozen_time: dict[str, float],
) -> None:
    del fake_cache, frozen_time

    app = FastAPI()

    @app.get("/limited")
    async def limited() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=60,
        burst_size=1,
    )

    with TestClient(app) as client:
        first = client.get(
            "/limited",
            headers={"X-Forwarded-For": "203.0.113.10:1200"},
        )
        second_same_ip_different_port = client.get(
            "/limited",
            headers={"X-Forwarded-For": "203.0.113.10:9800"},
        )
        first_other_ip = client.get(
            "/limited",
            headers={"X-Forwarded-For": "203.0.113.11:9800"},
        )

        assert first.status_code == 200
        assert second_same_ip_different_port.status_code == 429
        assert first_other_ip.status_code == 200


def test_rate_limit_middleware_skips_invalid_x_forwarded_for_candidates(
    fake_cache: InMemoryAsyncCache,
    frozen_time: dict[str, float],
) -> None:
    del fake_cache, frozen_time

    app = FastAPI()

    @app.get("/limited")
    async def limited() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=60,
        burst_size=1,
    )

    with TestClient(app) as client:
        first = client.get(
            "/limited",
            headers={"X-Forwarded-For": "unknown, _proxy, 198.51.100.7"},
        )
        second_same = client.get(
            "/limited",
            headers={"X-Forwarded-For": "_proxy, 198.51.100.7:443"},
        )
        first_other = client.get(
            "/limited",
            headers={"X-Forwarded-For": "unknown, 198.51.100.8"},
        )

        assert first.status_code == 200
        assert second_same.status_code == 429
        assert first_other.status_code == 200


def test_rate_limit_middleware_rejects_invalid_client_id_header() -> None:
    app = FastAPI()

    with pytest.raises(ValueError, match="client_id_header must be a non-empty string"):
        RateLimitMiddleware(app, client_id_header="")


def test_rate_limit_middleware_rejects_invalid_exclude_paths() -> None:
    app = FastAPI()

    with pytest.raises(
        ValueError,
        match="exclude_paths entries must start with '/'",
    ):
        RateLimitMiddleware(app, exclude_paths=["internal"])  # missing leading slash

    with pytest.raises(
        ValueError,
        match="exclude_paths must contain non-empty path pattern strings",
    ):
        RateLimitMiddleware(app, exclude_paths=[""])
