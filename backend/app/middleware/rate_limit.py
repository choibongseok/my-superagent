"""Rate limiting middleware using Token Bucket algorithm."""

import time
from typing import Callable, Optional

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.cache import cache
from app.core.config import settings


class TokenBucket:
    """Token Bucket rate limiter."""

    def __init__(self, capacity: int, refill_rate: float):
        """
        Initialize token bucket.

        Args:
            capacity: Maximum tokens in bucket
            refill_rate: Tokens added per second
        """
        self.capacity = capacity
        self.refill_rate = refill_rate

    async def consume(self, key: str, tokens: int = 1) -> bool:
        """
        Try to consume tokens from bucket.

        Args:
            key: Bucket key (user_id or IP)
            tokens: Number of tokens to consume

        Returns:
            True if tokens consumed, False if rate limited
        """
        now = time.time()

        # Get current bucket state
        bucket_data = await cache.get(f"rate_limit:{key}")

        if not bucket_data:
            # Initialize new bucket
            bucket_data = {
                "tokens": self.capacity - tokens,
                "last_refill": now,
            }
        else:
            # Refill tokens based on time elapsed
            elapsed = now - bucket_data["last_refill"]
            refill_amount = elapsed * self.refill_rate
            bucket_data["tokens"] = min(
                self.capacity, bucket_data["tokens"] + refill_amount
            )
            bucket_data["last_refill"] = now

            # Try to consume tokens
            if bucket_data["tokens"] >= tokens:
                bucket_data["tokens"] -= tokens
            else:
                # Rate limited - save state and return False
                await cache.set(f"rate_limit:{key}", bucket_data, ttl=3600)
                return False

        # Save updated bucket state
        await cache.set(f"rate_limit:{key}", bucket_data, ttl=3600)
        return True

    async def get_remaining(self, key: str) -> float:
        """
        Get remaining tokens in bucket.

        Args:
            key: Bucket key

        Returns:
            Number of remaining tokens
        """
        bucket_data = await cache.get(f"rate_limit:{key}")
        if not bucket_data:
            return self.capacity

        # Calculate current tokens with refill
        now = time.time()
        elapsed = now - bucket_data["last_refill"]
        refill_amount = elapsed * self.refill_rate
        current_tokens = min(self.capacity, bucket_data["tokens"] + refill_amount)

        return current_tokens


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware for API rate limiting."""

    def __init__(
        self,
        app,
        requests_per_minute: int = 60,
        burst_size: Optional[int] = None,
    ):
        """
        Initialize rate limit middleware.

        Args:
            app: FastAPI application
            requests_per_minute: Sustained request rate
            burst_size: Maximum burst requests (defaults to 2x rate)
        """
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size or (requests_per_minute * 2)

        # Token bucket: refills at requests_per_minute rate
        # Max capacity: burst_size
        self.bucket = TokenBucket(
            capacity=self.burst_size,
            refill_rate=requests_per_minute / 60.0,  # Convert to per-second
        )

        # Exclude health check and docs from rate limiting
        self.exclude_paths = {
            "/health",
            "/",
            "/docs",
            "/redoc",
            "/openapi.json",
        }

    def _get_client_id(self, request: Request) -> str:
        """
        Get client identifier for rate limiting.

        Args:
            request: HTTP request

        Returns:
            Client identifier (user_id or IP address)
        """
        # Try to get user ID from request state (set by auth middleware)
        if hasattr(request.state, "user_id"):
            return f"user:{request.state.user_id}"

        # Fall back to IP address
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"

        return f"ip:{client_ip}"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request with rate limiting.

        Args:
            request: HTTP request
            call_next: Next middleware/route handler

        Returns:
            HTTP response
        """
        # Skip rate limiting for excluded paths
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        # Get client identifier
        client_id = self._get_client_id(request)

        # Try to consume token
        allowed = await self.bucket.consume(client_id)

        if not allowed:
            # Rate limited
            remaining = await self.bucket.get_remaining(client_id)
            retry_after = int((1.0 - remaining) / self.bucket.refill_rate)

            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "Too many requests. Please try again later.",
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(self.burst_size),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + retry_after),
                },
            )

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        remaining = await self.bucket.get_remaining(client_id)
        response.headers["X-RateLimit-Limit"] = str(self.burst_size)
        response.headers["X-RateLimit-Remaining"] = str(int(remaining))
        response.headers["X-RateLimit-Reset"] = str(
            int(time.time() + (self.burst_size - remaining) / self.bucket.refill_rate)
        )

        return response


def get_rate_limit_middleware(
    requests_per_minute: Optional[int] = None,
) -> RateLimitMiddleware:
    """
    Create rate limit middleware instance.

    Args:
        requests_per_minute: Request rate limit (defaults to settings)

    Returns:
        RateLimitMiddleware instance
    """
    rpm = requests_per_minute or settings.RATE_LIMIT_PER_MINUTE
    return lambda app: RateLimitMiddleware(app, requests_per_minute=rpm)
