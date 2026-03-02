"""
FastAPI middleware for API rate limiting.
"""
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Dict, Optional
import logging
from datetime import datetime

from app.core.redis_rate_limiter import get_rate_limiter
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.rate_limit_override import RateLimitOverride
from sqlalchemy import select

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware with per-user and per-endpoint limits.
    
    Features:
    - Global rate limits (100 req/min, 1000 req/hour)
    - Per-endpoint overrides (e.g., /tasks/create -> 10/min)
    - Admin bypass capability
    - Standard rate limit headers (X-RateLimit-*)
    - 429 Too Many Requests with Retry-After
    """
    
    # Default rate limits
    DEFAULT_LIMITS = {
        "default": {"limit": 100, "window": 60},  # 100 req/minute
        "hourly": {"limit": 1000, "window": 3600},  # 1000 req/hour
    }
    
    # Per-endpoint overrides (stricter limits for expensive operations)
    ENDPOINT_LIMITS = {
        "/api/v1/tasks/create": {"limit": 10, "window": 60},
        "/api/v1/agents/research": {"limit": 20, "window": 60},
        "/api/v1/agents/docs": {"limit": 15, "window": 60},
        "/api/v1/agents/sheets": {"limit": 15, "window": 60},
        "/api/v1/agents/slides": {"limit": 10, "window": 60},
        "/api/v1/fact-check": {"limit": 30, "window": 60},
    }
    
    # Paths exempt from rate limiting
    EXEMPT_PATHS = [
        "/api/health",
        "/api/docs",
        "/api/openapi.json",
        "/api/v1/auth/callback",  # OAuth callbacks
    ]
    
    async def dispatch(self, request: Request, call_next):
        """Process request and apply rate limiting."""
        
        # Skip rate limiting for exempt paths
        if any(request.url.path.startswith(path) for path in self.EXEMPT_PATHS):
            return await call_next(request)
        
        # Get user ID from request (from JWT token or session)
        user_id = self._get_user_id(request)
        
        if not user_id:
            # Anonymous requests - use IP address
            user_id = f"anon:{request.client.host}"
        
        # Check if user is admin (bypass rate limits)
        if self._is_admin_user(request):
            response = await call_next(request)
            response.headers["X-RateLimit-Bypass"] = "admin"
            return response
        
        # Get rate limiter
        limiter = get_rate_limiter()
        
        if not limiter:
            # Rate limiter not initialized - allow request
            logger.warning("Rate limiter not initialized, allowing request")
            return await call_next(request)
        
        # Determine rate limit for this endpoint
        endpoint = request.url.path
        
        # Check for admin override in database
        override_limit = await self._get_override_limit(user_id, endpoint)
        if override_limit:
            limit_config = {"limit": override_limit, "window": 60}
            logger.info(f"Using override limit {override_limit} for user {user_id} on {endpoint}")
        else:
            limit_config = self.ENDPOINT_LIMITS.get(endpoint, self.DEFAULT_LIMITS["default"])
        
        # Check minute-level limit
        allowed, remaining, reset_time = limiter.check_rate_limit(
            user_id=user_id,
            endpoint=endpoint,
            limit=limit_config["limit"],
            window_seconds=limit_config["window"]
        )
        
        if not allowed:
            # Rate limit exceeded
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Please try again later.",
                    "error_code": "RATE_LIMIT_EXCEEDED",
                    "retry_after": reset_time
                },
                headers={
                    "X-RateLimit-Limit": str(limit_config["limit"]),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_time),
                    "Retry-After": str(limit_config["window"])
                }
            )
        
        # Check hourly limit (additional check)
        hourly_allowed, hourly_remaining, hourly_reset = limiter.check_rate_limit(
            user_id=user_id,
            endpoint=f"{endpoint}:hourly",
            limit=self.DEFAULT_LIMITS["hourly"]["limit"],
            window_seconds=self.DEFAULT_LIMITS["hourly"]["window"]
        )
        
        if not hourly_allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Hourly rate limit exceeded. Please try again later.",
                    "error_code": "HOURLY_RATE_LIMIT_EXCEEDED",
                    "retry_after": hourly_reset
                },
                headers={
                    "X-RateLimit-Limit": str(self.DEFAULT_LIMITS["hourly"]["limit"]),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(hourly_reset),
                    "Retry-After": str(self.DEFAULT_LIMITS["hourly"]["window"])
                }
            )
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers to response
        response.headers["X-RateLimit-Limit"] = str(limit_config["limit"])
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_time)
        
        return response
    
    def _get_user_id(self, request: Request) -> Optional[str]:
        """Extract user ID from request (JWT token or session)."""
        # Try to get from request state (set by auth middleware)
        if hasattr(request.state, "user"):
            user = request.state.user
            if hasattr(user, "id"):
                return str(user.id)
            elif hasattr(user, "email"):
                return user.email
        
        # Try to get from Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            # In production, decode JWT token here
            # For now, return None (will use IP)
            pass
        
        return None
    
    def _is_admin_user(self, request: Request) -> bool:
        """Check if user has admin privileges."""
        if hasattr(request.state, "user"):
            user = request.state.user
            if hasattr(user, "is_admin"):
                return user.is_admin
            if hasattr(user, "role"):
                return user.role == "admin"
        
        return False
    
    async def _get_override_limit(self, user_id: str, endpoint: str) -> Optional[int]:
        """
        Check database for admin-configured rate limit overrides.
        
        Args:
            user_id: User identifier
            endpoint: API endpoint path
            
        Returns:
            Custom rate limit if override exists and is active, None otherwise
        """
        # Skip database lookup for anonymous users
        if user_id.startswith("anon:"):
            return None
        
        try:
            async with AsyncSessionLocal() as db:
                # Query for active overrides that match this user and endpoint
                result = await db.execute(
                    select(RateLimitOverride).filter(
                        RateLimitOverride.user_id == user_id
                    )
                )
                overrides = result.scalars().all()
                
                # Check each override to see if it matches and is active
                for override in overrides:
                    if override.is_active() and override.matches_endpoint(endpoint):
                        return override.custom_limit
                
                return None
            
        except Exception as e:
            logger.warning(f"Error checking rate limit override: {e}")
            return None
