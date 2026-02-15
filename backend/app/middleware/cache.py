"""API response caching middleware."""

import base64
import hashlib
from collections.abc import Iterable
from typing import Any, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.cache import cache


class CacheMiddleware(BaseHTTPMiddleware):
    """Middleware for caching API responses."""

    DEFAULT_VARY_HEADERS = ("accept", "accept-language")

    def __init__(
        self,
        app,
        cache_ttl: int = 300,
        vary_headers: Iterable[str] | None = None,
    ):
        """
        Initialize cache middleware.

        Args:
            app: FastAPI application
            cache_ttl: Default cache TTL in seconds (default 5 minutes)
            vary_headers: Optional iterable of request header names used to
                segment cache entries (case-insensitive). Defaults to
                ``("accept", "accept-language")``.
        """
        super().__init__(app)
        self.cache_ttl = cache_ttl
        self.cache_vary_headers = self._normalize_vary_headers(vary_headers)
        self.cacheable_methods = {"GET"}
        self.cache_exclude_paths = {
            "/docs",
            "/redoc",
            "/openapi.json",
            "/health",
            "/api/v1/auth",  # Exclude auth endpoints
            "/api/v1/messages/ws",  # Exclude WebSocket
        }

    @classmethod
    def _normalize_vary_headers(
        cls,
        vary_headers: Iterable[str] | None,
    ) -> tuple[str, ...]:
        """Normalize optional vary-header names used by cache key generation."""
        if vary_headers is None:
            return cls.DEFAULT_VARY_HEADERS

        if isinstance(vary_headers, str):
            raise ValueError("vary_headers must be an iterable of header names")

        normalized_headers: list[str] = []
        seen: set[str] = set()
        for header_name in vary_headers:
            if not isinstance(header_name, str):
                raise ValueError("vary_headers must contain only string header names")

            normalized_header_name = header_name.strip().lower()
            if not normalized_header_name:
                raise ValueError("vary_headers cannot contain empty header names")

            if normalized_header_name in seen:
                continue

            seen.add(normalized_header_name)
            normalized_headers.append(normalized_header_name)

        return tuple(normalized_headers)

    @staticmethod
    def _cache_control_disables_caching(request: Request) -> bool:
        """Return whether request headers ask to bypass middleware cache."""
        cache_control = request.headers.get("Cache-Control", "")
        directives = {
            directive.strip().lower()
            for directive in cache_control.split(",")
            if directive.strip()
        }

        if {"no-cache", "no-store", "max-age=0"} & directives:
            return True

        pragma = request.headers.get("Pragma", "")
        return pragma.strip().lower() == "no-cache"

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

        # Check for no-cache directives
        if self._cache_control_disables_caching(request):
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

        # Segment cache entries by configured vary headers.
        for header_name in self.cache_vary_headers:
            header_value = request.headers.get(header_name, "")
            key_parts.append(f"header:{header_name}={header_value}")

        # Create hash of key parts
        key_string = ":".join(key_parts)
        key_hash = hashlib.sha256(key_string.encode()).hexdigest()

        return f"api:response:{key_hash}"

    @staticmethod
    def _decode_cached_body(cached_data: dict[str, Any]) -> tuple[bytes, str | None]:
        """Decode cached body payload with backwards compatibility."""
        if "body_base64" in cached_data:
            body = base64.b64decode(cached_data["body_base64"])
            media_type = cached_data.get("media_type")
            return body, media_type

        # Backwards compatibility with legacy JSON-only cache payloads.
        legacy_body = cached_data.get("body", "")
        if isinstance(legacy_body, bytes):
            body = legacy_body
        else:
            body = str(legacy_body).encode()

        return body, cached_data.get("media_type", "application/json")

    @staticmethod
    def _response_disables_caching(response: Response) -> bool:
        """Return whether response headers mark payload as non-cacheable."""
        cache_control = response.headers.get("Cache-Control", "")
        directives = {
            directive.strip().lower()
            for directive in cache_control.split(",")
            if directive.strip()
        }

        if {"no-cache", "no-store", "private", "max-age=0"} & directives:
            return True

        pragma = response.headers.get("Pragma", "")
        if pragma.strip().lower() == "no-cache":
            return True

        return "set-cookie" in response.headers

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
                body, media_type = self._decode_cached_body(cached_data)
                headers = dict(cached_data.get("headers", {}))
                headers["X-Cache"] = "HIT"

                return Response(
                    content=body,
                    status_code=cached_data["status_code"],
                    headers=headers,
                    media_type=media_type,
                )
        except Exception:
            # If cache fails, continue without caching
            pass

        # Get response from handler
        response = await call_next(request)

        # Cache successful responses unless response headers explicitly disable caching.
        if response.status_code == 200 and not self._response_disables_caching(response):
            body = b""
            async for chunk in response.body_iterator:
                body += chunk

            response_headers = dict(response.headers)
            response_headers["X-Cache"] = "MISS"

            try:
                # Prepare cache data (binary-safe to support non-JSON payloads)
                cache_data = {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "body_base64": base64.b64encode(body).decode("ascii"),
                    "media_type": response.media_type,
                }

                # Cache the response
                await cache.set(cache_key, cache_data, self.cache_ttl)
            except Exception:
                # If cache fails, continue returning the live response
                pass

            # Always return a replayable response because body_iterator was consumed.
            return Response(
                content=body,
                status_code=response.status_code,
                headers=response_headers,
                media_type=response.media_type,
            )

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
