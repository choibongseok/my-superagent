"""Tests for API cache middleware behavior."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from app.middleware import cache as cache_module
from app.middleware.cache import CacheMiddleware


class InMemoryAsyncCache:
    """Minimal async cache stub for middleware tests."""

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
    """Patch cache middleware module with in-memory async cache."""
    cache = InMemoryAsyncCache()
    monkeypatch.setattr(cache_module, "cache", cache)
    return cache


def test_cache_middleware_caches_plain_text_responses_and_reports_hit_miss(
    fake_cache: InMemoryAsyncCache,
) -> None:
    del fake_cache

    app = FastAPI()
    calls = {"count": 0}

    @app.get("/payload")
    async def payload() -> PlainTextResponse:
        calls["count"] += 1
        return PlainTextResponse(f"payload-{calls['count']}")

    app.add_middleware(CacheMiddleware, cache_ttl=30)

    with TestClient(app) as client:
        first_response = client.get("/payload")
        assert first_response.status_code == 200
        assert first_response.text == "payload-1"
        assert first_response.headers["X-Cache"] == "MISS"

        second_response = client.get("/payload")
        assert second_response.status_code == 200
        assert second_response.text == "payload-1"
        assert second_response.headers["X-Cache"] == "HIT"

    assert calls["count"] == 1


def test_cache_middleware_respects_no_store_and_pragma_no_cache_headers(
    fake_cache: InMemoryAsyncCache,
) -> None:
    del fake_cache

    app = FastAPI()
    calls = {"count": 0}

    @app.get("/counter")
    async def counter() -> dict[str, int]:
        calls["count"] += 1
        return {"count": calls["count"]}

    app.add_middleware(CacheMiddleware, cache_ttl=30)

    with TestClient(app) as client:
        baseline = client.get("/counter")
        assert baseline.status_code == 200
        assert baseline.json() == {"count": 1}
        assert baseline.headers["X-Cache"] == "MISS"

        bypass_no_store = client.get("/counter", headers={"Cache-Control": "no-store"})
        assert bypass_no_store.status_code == 200
        assert bypass_no_store.json() == {"count": 2}
        assert "X-Cache" not in bypass_no_store.headers

        bypass_pragma = client.get("/counter", headers={"Pragma": "no-cache"})
        assert bypass_pragma.status_code == 200
        assert bypass_pragma.json() == {"count": 3}
        assert "X-Cache" not in bypass_pragma.headers

        cached = client.get("/counter")
        assert cached.status_code == 200
        assert cached.json() == {"count": 1}
        assert cached.headers["X-Cache"] == "HIT"

    assert calls["count"] == 3


def test_cache_middleware_varies_cache_key_by_accept_language_header(
    fake_cache: InMemoryAsyncCache,
) -> None:
    del fake_cache

    app = FastAPI()
    calls = {"count": 0}

    @app.get("/localized")
    async def localized(request: Request) -> dict[str, Any]:
        calls["count"] += 1
        locale = request.headers.get("Accept-Language", "default").split(",", 1)[0]
        return {
            "locale": locale,
            "build": calls["count"],
        }

    app.add_middleware(CacheMiddleware, cache_ttl=30)

    with TestClient(app) as client:
        first_korean = client.get("/localized", headers={"Accept-Language": "ko-KR"})
        assert first_korean.status_code == 200
        assert first_korean.json() == {"locale": "ko-KR", "build": 1}
        assert first_korean.headers["X-Cache"] == "MISS"

        second_korean = client.get(
            "/localized",
            headers={"Accept-Language": "ko-KR"},
        )
        assert second_korean.status_code == 200
        assert second_korean.json() == {"locale": "ko-KR", "build": 1}
        assert second_korean.headers["X-Cache"] == "HIT"

        first_english = client.get("/localized", headers={"Accept-Language": "en-US"})
        assert first_english.status_code == 200
        assert first_english.json() == {"locale": "en-US", "build": 2}
        assert first_english.headers["X-Cache"] == "MISS"

        second_english = client.get(
            "/localized",
            headers={"Accept-Language": "en-US"},
        )
        assert second_english.status_code == 200
        assert second_english.json() == {"locale": "en-US", "build": 2}
        assert second_english.headers["X-Cache"] == "HIT"

    assert calls["count"] == 2


def test_cache_middleware_supports_disabling_vary_headers(
    fake_cache: InMemoryAsyncCache,
) -> None:
    del fake_cache

    app = FastAPI()
    calls = {"count": 0}

    @app.get("/localized")
    async def localized(request: Request) -> dict[str, Any]:
        calls["count"] += 1
        locale = request.headers.get("Accept-Language", "default").split(",", 1)[0]
        return {
            "locale": locale,
            "build": calls["count"],
        }

    app.add_middleware(CacheMiddleware, cache_ttl=30, vary_headers=())

    with TestClient(app) as client:
        first_korean = client.get("/localized", headers={"Accept-Language": "ko-KR"})
        assert first_korean.status_code == 200
        assert first_korean.json() == {"locale": "ko-KR", "build": 1}
        assert first_korean.headers["X-Cache"] == "MISS"

        english_request = client.get("/localized", headers={"Accept-Language": "en-US"})
        assert english_request.status_code == 200
        assert english_request.json() == {"locale": "ko-KR", "build": 1}
        assert english_request.headers["X-Cache"] == "HIT"

    assert calls["count"] == 1
