"""Metrics collection middleware."""

from __future__ import annotations

import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.metrics import (
    http_request_duration_seconds,
    http_request_size_bytes,
    http_requests_total,
    http_response_size_bytes,
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware for collecting HTTP metrics."""

    def _get_path_template(self, request: Request) -> str:
        """Resolve route template path used for metric labels."""
        route = request.scope.get("route")
        if route is not None:
            route_path = getattr(route, "path", None)
            if isinstance(route_path, str) and route_path:
                return route_path

        return request.url.path

    @staticmethod
    def _parse_content_length(value: str | None) -> int | None:
        """Parse optional ``Content-Length`` header values safely."""
        if value is None:
            return None

        try:
            parsed_value = int(value)
        except (TypeError, ValueError):
            return None

        if parsed_value < 0:
            return None

        return parsed_value

    def _response_size(self, response: Response) -> int | None:
        """Resolve response size from headers with body fallback."""
        header_size = self._parse_content_length(response.headers.get("content-length"))
        if header_size is not None:
            return header_size

        response_body = getattr(response, "body", None)
        if isinstance(response_body, bytes):
            return len(response_body)
        if isinstance(response_body, bytearray):
            return len(response_body)

        return None

    @staticmethod
    def _record_base_metrics(
        *,
        method: str,
        endpoint: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        """Record request counter + latency histogram samples."""
        http_requests_total.labels(
            method=method,
            endpoint=endpoint,
            status_code=status_code,
        ).inc()

        http_request_duration_seconds.labels(
            method=method,
            endpoint=endpoint,
        ).observe(duration_seconds)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and record request/response metrics."""
        path_template = self._get_path_template(request)
        method = request.method

        request_size = self._parse_content_length(request.headers.get("content-length"))
        if request_size is not None:
            http_request_size_bytes.labels(
                method=method,
                endpoint=path_template,
            ).observe(request_size)

        start_time = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            duration_seconds = time.perf_counter() - start_time
            self._record_base_metrics(
                method=method,
                endpoint=path_template,
                status_code=500,
                duration_seconds=duration_seconds,
            )
            raise

        duration_seconds = time.perf_counter() - start_time
        self._record_base_metrics(
            method=method,
            endpoint=path_template,
            status_code=response.status_code,
            duration_seconds=duration_seconds,
        )

        response_size = self._response_size(response)
        if response_size is not None:
            http_response_size_bytes.labels(
                method=method,
                endpoint=path_template,
            ).observe(response_size)

        return response
