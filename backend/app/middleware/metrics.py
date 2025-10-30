"""Metrics collection middleware."""

import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.metrics import (
    http_request_duration_seconds,
    http_requests_total,
    http_request_size_bytes,
    http_response_size_bytes,
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware for collecting HTTP metrics."""

    def _get_path_template(self, request: Request) -> str:
        """
        Get path template for metrics.

        Args:
            request: HTTP request

        Returns:
            Path template (e.g., /api/v1/chats/{chat_id})
        """
        # Try to get route from request
        if request.scope.get("route"):
            return request.scope["route"].path

        # Fall back to actual path
        return request.url.path

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request with metrics collection.

        Args:
            request: HTTP request
            call_next: Next middleware/route handler

        Returns:
            HTTP response
        """
        # Get path template for metrics
        path_template = self._get_path_template(request)
        method = request.method

        # Record request size
        if request.headers.get("content-length"):
            request_size = int(request.headers["content-length"])
            http_request_size_bytes.labels(
                method=method, endpoint=path_template
            ).observe(request_size)

        # Start timer
        start_time = time.time()

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration = time.time() - start_time

        # Record metrics
        http_requests_total.labels(
            method=method,
            endpoint=path_template,
            status_code=response.status_code,
        ).inc()

        http_request_duration_seconds.labels(
            method=method, endpoint=path_template
        ).observe(duration)

        # Record response size
        if response.headers.get("content-length"):
            response_size = int(response.headers["content-length"])
            http_response_size_bytes.labels(
                method=method, endpoint=path_template
            ).observe(response_size)

        return response
