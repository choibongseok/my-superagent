"""Tests for HTTP metrics middleware behavior."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from starlette.requests import Request
from starlette.responses import Response

from app.middleware.metrics import MetricsMiddleware


class _FakeMetricChild:
    """Metric label handle capturing ``inc`` / ``observe`` calls."""

    def __init__(self, sink: list[dict[str, Any]], labels: dict[str, Any]) -> None:
        self._sink = sink
        self._labels = labels

    def inc(self, value: float = 1.0) -> None:
        self._sink.append(
            {
                "operation": "inc",
                "labels": self._labels,
                "value": value,
            }
        )

    def observe(self, value: float) -> None:
        self._sink.append(
            {
                "operation": "observe",
                "labels": self._labels,
                "value": value,
            }
        )


class _FakeMetric:
    """Fake Prometheus metric collector used to inspect middleware output."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def labels(self, **labels: Any) -> _FakeMetricChild:
        return _FakeMetricChild(self.events, labels)


async def _noop_app(scope, receive, send) -> None:  # pragma: no cover - helper only
    return None


def _build_request(
    *,
    path: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    route_path: str | None = None,
) -> Request:
    """Construct a minimal ASGI request object for middleware tests."""

    encoded_headers = [
        (name.lower().encode("latin-1"), value.encode("latin-1"))
        for name, value in (headers or {}).items()
    ]

    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": encoded_headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }

    if route_path is not None:
        scope["route"] = SimpleNamespace(path=route_path)

    async def _receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, _receive)


@pytest.mark.asyncio
async def test_dispatch_records_success_metrics_with_path_template(monkeypatch):
    """Successful requests should emit count/duration/request-size/response-size."""

    requests_total = _FakeMetric()
    request_duration = _FakeMetric()
    request_size = _FakeMetric()
    response_size = _FakeMetric()

    monkeypatch.setattr("app.middleware.metrics.http_requests_total", requests_total)
    monkeypatch.setattr(
        "app.middleware.metrics.http_request_duration_seconds", request_duration
    )
    monkeypatch.setattr("app.middleware.metrics.http_request_size_bytes", request_size)
    monkeypatch.setattr(
        "app.middleware.metrics.http_response_size_bytes", response_size
    )

    middleware = MetricsMiddleware(_noop_app)
    request = _build_request(
        path="/api/v1/items/123",
        method="POST",
        headers={"content-length": "11"},
        route_path="/api/v1/items/{item_id}",
    )

    async def call_next(_request: Request) -> Response:
        return Response(
            content="ok",
            status_code=201,
            headers={"content-length": "2"},
        )

    response = await middleware.dispatch(request, call_next)

    assert response.status_code == 201
    assert request_size.events == [
        {
            "operation": "observe",
            "labels": {"method": "POST", "endpoint": "/api/v1/items/{item_id}"},
            "value": 11,
        }
    ]
    assert response_size.events == [
        {
            "operation": "observe",
            "labels": {"method": "POST", "endpoint": "/api/v1/items/{item_id}"},
            "value": 2,
        }
    ]
    assert requests_total.events == [
        {
            "operation": "inc",
            "labels": {
                "method": "POST",
                "endpoint": "/api/v1/items/{item_id}",
                "status_code": 201,
            },
            "value": 1.0,
        }
    ]
    assert len(request_duration.events) == 1
    assert request_duration.events[0]["operation"] == "observe"


@pytest.mark.asyncio
async def test_dispatch_ignores_invalid_content_length_headers(monkeypatch):
    """Invalid size headers should be ignored instead of raising parsing errors."""

    requests_total = _FakeMetric()
    request_duration = _FakeMetric()
    request_size = _FakeMetric()
    response_size = _FakeMetric()

    monkeypatch.setattr("app.middleware.metrics.http_requests_total", requests_total)
    monkeypatch.setattr(
        "app.middleware.metrics.http_request_duration_seconds", request_duration
    )
    monkeypatch.setattr("app.middleware.metrics.http_request_size_bytes", request_size)
    monkeypatch.setattr(
        "app.middleware.metrics.http_response_size_bytes", response_size
    )

    middleware = MetricsMiddleware(_noop_app)
    request = _build_request(
        path="/health",
        headers={"content-length": "not-a-number"},
    )

    async def call_next(_request: Request) -> Response:
        response = Response(content="ok", status_code=200)
        response.headers["content-length"] = "NaN"
        return response

    response = await middleware.dispatch(request, call_next)

    assert response.status_code == 200
    assert request_size.events == []
    assert response_size.events == [
        {
            "operation": "observe",
            "labels": {"method": "GET", "endpoint": "/health"},
            "value": 2,
        }
    ]
    assert len(requests_total.events) == 1
    assert len(request_duration.events) == 1


@pytest.mark.asyncio
async def test_dispatch_uses_body_fallback_when_response_header_missing(monkeypatch):
    """Response body length should be used when Content-Length header is absent."""

    requests_total = _FakeMetric()
    request_duration = _FakeMetric()
    request_size = _FakeMetric()
    response_size = _FakeMetric()

    monkeypatch.setattr("app.middleware.metrics.http_requests_total", requests_total)
    monkeypatch.setattr(
        "app.middleware.metrics.http_request_duration_seconds", request_duration
    )
    monkeypatch.setattr("app.middleware.metrics.http_request_size_bytes", request_size)
    monkeypatch.setattr(
        "app.middleware.metrics.http_response_size_bytes", response_size
    )

    middleware = MetricsMiddleware(_noop_app)
    request = _build_request(path="/fallback-size")

    async def call_next(_request: Request) -> Response:
        response = Response(content="hello", status_code=200)
        del response.headers["content-length"]
        return response

    await middleware.dispatch(request, call_next)

    assert request_size.events == []
    assert response_size.events == [
        {
            "operation": "observe",
            "labels": {"method": "GET", "endpoint": "/fallback-size"},
            "value": 5,
        }
    ]


@pytest.mark.asyncio
async def test_dispatch_records_500_metrics_when_handler_raises(monkeypatch):
    """Middleware should still emit duration/count metrics when handler fails."""

    requests_total = _FakeMetric()
    request_duration = _FakeMetric()
    request_size = _FakeMetric()
    response_size = _FakeMetric()

    monkeypatch.setattr("app.middleware.metrics.http_requests_total", requests_total)
    monkeypatch.setattr(
        "app.middleware.metrics.http_request_duration_seconds", request_duration
    )
    monkeypatch.setattr("app.middleware.metrics.http_request_size_bytes", request_size)
    monkeypatch.setattr(
        "app.middleware.metrics.http_response_size_bytes", response_size
    )

    middleware = MetricsMiddleware(_noop_app)
    request = _build_request(path="/explode", method="PATCH")

    async def call_next(_request: Request) -> Response:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await middleware.dispatch(request, call_next)

    assert request_size.events == []
    assert response_size.events == []
    assert requests_total.events == [
        {
            "operation": "inc",
            "labels": {
                "method": "PATCH",
                "endpoint": "/explode",
                "status_code": 500,
            },
            "value": 1.0,
        }
    ]
    assert len(request_duration.events) == 1
