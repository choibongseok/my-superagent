"""Rate limiting middleware using Token Bucket algorithm."""

import math
import time
from typing import Callable, Mapping, Optional

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.cache import cache
from app.core.config import settings


class TokenBucket:
    """Token Bucket rate limiter."""

    STATE_TTL_SECONDS = 3600

    def __init__(self, capacity: int, refill_rate: float):
        """
        Initialize token bucket.

        Args:
            capacity: Maximum tokens in bucket
            refill_rate: Tokens added per second
        """
        if isinstance(capacity, bool) or capacity <= 0:
            raise ValueError("capacity must be greater than 0")
        if refill_rate <= 0:
            raise ValueError("refill_rate must be greater than 0")

        self.capacity = capacity
        self.refill_rate = refill_rate

    @staticmethod
    def _validate_tokens(tokens: int) -> int:
        """Validate requested token count for bucket operations."""
        if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens <= 0:
            raise ValueError("tokens must be a positive integer")
        return tokens

    async def _load_bucket(self, key: str, *, now: float) -> dict[str, float]:
        """Load and refill a bucket state for the provided key."""
        bucket_data = await cache.get(f"rate_limit:{key}")
        if not bucket_data:
            return {
                "tokens": float(self.capacity),
                "last_refill": now,
            }

        previous_tokens = float(bucket_data.get("tokens", self.capacity))
        previous_refill = float(bucket_data.get("last_refill", now))
        elapsed = max(0.0, now - previous_refill)
        refill_amount = elapsed * self.refill_rate
        current_tokens = min(self.capacity, previous_tokens + refill_amount)

        return {
            "tokens": current_tokens,
            "last_refill": now,
        }

    async def consume(self, key: str, tokens: int = 1) -> bool:
        """
        Try to consume tokens from bucket.

        Args:
            key: Bucket key (user_id or IP)
            tokens: Number of tokens to consume

        Returns:
            True if tokens consumed, False if rate limited
        """
        requested_tokens = self._validate_tokens(tokens)
        now = time.time()
        bucket_data = await self._load_bucket(key, now=now)

        if requested_tokens > self.capacity or bucket_data["tokens"] < requested_tokens:
            await cache.set(
                f"rate_limit:{key}",
                bucket_data,
                ttl=self.STATE_TTL_SECONDS,
            )
            return False

        bucket_data["tokens"] -= requested_tokens

        await cache.set(
            f"rate_limit:{key}",
            bucket_data,
            ttl=self.STATE_TTL_SECONDS,
        )
        return True

    async def get_remaining(self, key: str) -> float:
        """
        Get remaining tokens in bucket.

        Args:
            key: Bucket key

        Returns:
            Number of remaining tokens
        """
        bucket_data = await self._load_bucket(key, now=time.time())
        return bucket_data["tokens"]

    async def get_retry_after(self, key: str, tokens: int = 1) -> float:
        """Return seconds until ``tokens`` can be consumed."""
        requested_tokens = self._validate_tokens(tokens)
        if requested_tokens > self.capacity:
            return math.inf

        bucket_data = await self._load_bucket(key, now=time.time())
        deficit = requested_tokens - bucket_data["tokens"]
        if deficit <= 0:
            return 0.0

        return deficit / self.refill_rate


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware for API rate limiting."""

    def __init__(
        self,
        app,
        requests_per_minute: int = 60,
        burst_size: Optional[int] = None,
        request_costs: Optional[Mapping[str, int]] = None,
    ):
        """
        Initialize rate limit middleware.

        Args:
            app: FastAPI application
            requests_per_minute: Sustained request rate
            burst_size: Maximum burst requests (defaults to 2x rate)
            request_costs: Optional per-method token costs (e.g. {"POST": 2})
        """
        super().__init__(app)

        if isinstance(requests_per_minute, bool) or requests_per_minute <= 0:
            raise ValueError("requests_per_minute must be greater than 0")

        resolved_burst_size = burst_size or (requests_per_minute * 2)
        if isinstance(resolved_burst_size, bool) or resolved_burst_size <= 0:
            raise ValueError("burst_size must be greater than 0")

        self.requests_per_minute = requests_per_minute
        self.burst_size = resolved_burst_size
        self.request_costs = self._normalize_request_costs(request_costs)

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

    def _normalize_request_costs(
        self,
        request_costs: Optional[Mapping[str, int]],
    ) -> dict[str, int]:
        """Normalize and validate optional HTTP method token costs."""
        if request_costs is None:
            return {}

        normalized_costs: dict[str, int] = {}
        for method, cost in request_costs.items():
            if not isinstance(method, str) or not method.strip():
                raise ValueError("request_costs keys must be non-empty method strings")
            if isinstance(cost, bool) or not isinstance(cost, int) or cost <= 0:
                raise ValueError(
                    "request_costs values must be positive integer token costs"
                )
            if cost > self.burst_size:
                raise ValueError("request_costs values cannot exceed burst_size")

            normalized_costs[method.strip().upper()] = cost

        return normalized_costs

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

    def _get_request_cost(self, request: Request) -> int:
        """Resolve token cost for the current HTTP method."""
        return self.request_costs.get(request.method.upper(), 1)

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

        # Get client identifier and method-specific token cost
        client_id = self._get_client_id(request)
        request_cost = self._get_request_cost(request)

        # Try to consume token budget for this request
        allowed = await self.bucket.consume(client_id, tokens=request_cost)

        if not allowed:
            # Rate limited
            retry_after_seconds = await self.bucket.get_retry_after(
                client_id,
                tokens=request_cost,
            )
            retry_after = (
                max(1, math.ceil(retry_after_seconds))
                if math.isfinite(retry_after_seconds)
                else 3600
            )

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
                    "X-RateLimit-Request-Cost": str(request_cost),
                },
            )

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        remaining = await self.bucket.get_remaining(client_id)
        retry_after_seconds = await self.bucket.get_retry_after(client_id)
        reset_after = (
            max(0, math.ceil(retry_after_seconds))
            if math.isfinite(retry_after_seconds)
            else 3600
        )

        response.headers["X-RateLimit-Limit"] = str(self.burst_size)
        response.headers["X-RateLimit-Remaining"] = str(int(remaining))
        response.headers["X-RateLimit-Reset"] = str(int(time.time()) + reset_after)
        response.headers["X-RateLimit-Request-Cost"] = str(request_cost)

        return response


def get_rate_limit_middleware(
    requests_per_minute: Optional[int] = None,
    request_costs: Optional[Mapping[str, int]] = None,
):
    """
    Create rate limit middleware factory.

    Args:
        requests_per_minute: Request rate limit (defaults to settings)
        request_costs: Optional per-method token costs

    Returns:
        Callable middleware factory compatible with ``add_middleware``
    """
    rpm = requests_per_minute or settings.RATE_LIMIT_PER_MINUTE

    return lambda app: RateLimitMiddleware(
        app,
        requests_per_minute=rpm,
        request_costs=request_costs,
    )
