"""API key authentication middleware and dependencies."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import Header, HTTPException, status, Request
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.models.api_key import ApiKey
from app.models.api_key_usage import ApiKeyUsage
from app.models.user import User


async def get_current_user_from_api_key(
    request: Request,
    x_api_key: Optional[str] = Header(None, description="API key for authentication"),
    db: AsyncSession = None,
) -> Optional[User]:
    """Authenticate user via API key from X-API-Key header.
    
    This is an alternative to JWT authentication.
    API keys should be provided in the X-API-Key header.
    
    Returns:
        User object if API key is valid, None otherwise
    """
    if not x_api_key:
        return None
    
    # Validate API key format
    if not x_api_key.startswith("ahq_"):
        return None
    
    # Get DB session if not provided
    if db is None:
        db = await anext(get_db())
    
    # Hash the provided key for lookup
    key_hash = ApiKey.hash_key(x_api_key)
    
    # Look up API key
    query = select(ApiKey).where(
        and_(
            ApiKey.key_hash == key_hash,
            ApiKey.is_active == True
        )
    ).options(
        # Eagerly load user
        selectinload(ApiKey.user)
    )
    
    try:
        result = await db.execute(query)
        api_key = result.scalar_one_or_none()
    except Exception:
        return None
    
    if not api_key:
        return None
    
    # Check if key is expired
    if api_key.is_expired():
        return None
    
    # Check if user is active
    if not api_key.user.is_active:
        return None
    
    # Store API key in request state for usage tracking
    request.state.api_key_id = api_key.id
    request.state.api_key_scopes = api_key.scope_list
    
    # Update last_used_at and usage_count (async, don't wait)
    # We'll do this in background to avoid slowing down the request
    api_key.last_used_at = datetime.utcnow()
    api_key.usage_count += 1
    
    # Log usage (async task, don't wait)
    try:
        usage_log = ApiKeyUsage(
            api_key_id=api_key.id,
            endpoint=request.url.path,
            method=request.method,
            status_code=200,  # Will be updated by middleware after response
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.add(usage_log)
        await db.commit()
    except Exception:
        # Don't fail request if usage logging fails
        pass
    
    return api_key.user


def require_api_key_scope(required_scope: str):
    """Dependency to require a specific API key scope.
    
    Usage:
        @router.get("/admin/stats", dependencies=[Depends(require_api_key_scope("admin"))])
        async def get_admin_stats():
            ...
    """
    async def check_scope(request: Request):
        # Check if request was authenticated via API key
        if not hasattr(request.state, "api_key_scopes"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This endpoint requires API key authentication with specific scopes"
            )
        
        scopes = request.state.api_key_scopes
        
        # Check if required scope is present (or if user has admin scope)
        if required_scope not in scopes and "admin" not in scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key missing required scope: {required_scope}"
            )
    
    return check_scope


class ApiKeyRateLimiter:
    """Rate limiter specifically for API key usage.
    
    This is separate from the user-based rate limiter and tracks
    usage per API key (not per user).
    """
    
    def __init__(self, redis_client):
        self.redis = redis_client
    
    async def check_limit(
        self,
        api_key_id: UUID,
        endpoint: str,
        limit: int = 1000,
        window_seconds: int = 3600,
    ) -> tuple[bool, int, int]:
        """Check if API key has exceeded rate limit.
        
        Args:
            api_key_id: The API key UUID
            endpoint: The endpoint being accessed
            limit: Max requests allowed in window
            window_seconds: Time window in seconds
        
        Returns:
            tuple[bool, int, int]: (allowed, remaining, reset_timestamp)
        """
        # Redis key for this API key + endpoint
        redis_key = f"api_key_rate_limit:{api_key_id}:{endpoint}"
        
        try:
            # Use Redis pipeline for atomic operations
            pipe = self.redis.pipeline()
            
            # Increment counter
            pipe.incr(redis_key)
            
            # Set expiry if key is new
            pipe.expire(redis_key, window_seconds)
            
            # Execute pipeline
            results = await pipe.execute()
            current_count = results[0]
            
            # Calculate remaining and reset time
            remaining = max(0, limit - current_count)
            reset_timestamp = int(datetime.utcnow().timestamp()) + window_seconds
            
            return current_count <= limit, remaining, reset_timestamp
            
        except Exception:
            # If Redis fails, allow the request (fail open)
            return True, limit, 0


# Middleware to track API key usage after response
async def api_key_usage_middleware(request: Request, call_next):
    """Middleware to update API key usage logs with response status code."""
    response = await call_next(request)
    
    # If request was authenticated via API key, update usage log status
    if hasattr(request.state, "api_key_id"):
        try:
            db = await anext(get_db())
            
            # Find the most recent usage log for this key
            query = select(ApiKeyUsage).where(
                ApiKeyUsage.api_key_id == request.state.api_key_id
            ).order_by(ApiKeyUsage.created_at.desc()).limit(1)
            
            result = await db.execute(query)
            usage_log = result.scalar_one_or_none()
            
            if usage_log:
                usage_log.status_code = response.status_code
                await db.commit()
        except Exception:
            # Don't fail response if logging fails
            pass
    
    return response
