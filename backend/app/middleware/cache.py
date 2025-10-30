"""API response caching middleware."""

import hashlib
import json
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.cache import cache


class CacheMiddleware(BaseHTTPMiddleware):
    """Middleware for caching API responses."""

    def __init__(self, app, cache_ttl: int = 300):
        """
        Initialize cache middleware.

        Args:
            app: FastAPI application
            cache_ttl: Default cache TTL in seconds (default 5 minutes)
        """
        super().__init__(app)
        self.cache_ttl = cache_ttl
        self.cacheable_methods = {"GET"}
        self.cache_exclude_paths = {
            "/docs",
            "/redoc",
            "/openapi.json",
            "/health",
            "/api/v1/auth",  # Exclude auth endpoints
            "/api/v1/messages/ws",  # Exclude WebSocket
        }

    def _is_cacheable(self, request: Request) -> bool:
        """
        Check if request is cacheable.

        Args:
            request: HTTP request

        Returns:
            True if cacheable, False otherwise
        """
        # Only cache GET requests
        if request.method not in self.cacheable_methods:
            return False

        # Check if path is excluded
        path = request.url.path
        for excluded in self.cache_exclude_paths:
            if path.startswith(excluded):
                return False

        # Check for no-cache header
        if request.headers.get("Cache-Control") == "no-cache":
            return False

        return True

    def _generate_cache_key(self, request: Request) -> str:
        """
        Generate cache key from request.

        Args:
            request: HTTP request

        Returns:
            Cache key string
        """
        # Include method, path, and query parameters
        key_parts = [
            request.method,
            request.url.path,
            str(sorted(request.query_params.items())),
        ]

        # Include user ID from auth header if present
        auth_header = request.headers.get("Authorization")
        if auth_header:
            key_parts.append(auth_header)

        # Create hash of key parts
        key_string = ":".join(key_parts)
        key_hash = hashlib.sha256(key_string.encode()).hexdigest()

        return f"api:response:{key_hash}"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request with caching.

        Args:
            request: HTTP request
            call_next: Next middleware/route handler

        Returns:
            HTTP response
        """
        # Check if request is cacheable
        if not self._is_cacheable(request):
            return await call_next(request)

        # Generate cache key
        cache_key = self._generate_cache_key(request)

        # Try to get cached response
        try:
            cached_data = await cache.get(cache_key)
            if cached_data:
                # Return cached response
                return Response(
                    content=json.dumps(cached_data["body"]),
                    status_code=cached_data["status_code"],
                    headers=dict(cached_data["headers"]),
                    media_type="application/json",
                )
        except Exception:
            # If cache fails, continue without caching
            pass

        # Get response from handler
        response = await call_next(request)

        # Cache successful responses
        if response.status_code == 200:
            try:
                # Read response body
                body = b""
                async for chunk in response.body_iterator:
                    body += chunk

                # Parse JSON body
                body_json = json.loads(body.decode())

                # Prepare cache data
                cache_data = {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "body": body_json,
                }

                # Cache the response
                await cache.set(cache_key, cache_data, self.cache_ttl)

                # Return new response with body
                return Response(
                    content=body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                )
            except Exception:
                # If caching fails, return original response
                pass

        return response


def get_cache_middleware(cache_ttl: int = 300) -> CacheMiddleware:
    """
    Create cache middleware instance.

    Args:
        cache_ttl: Default cache TTL in seconds

    Returns:
        CacheMiddleware instance
    """
    return CacheMiddleware
