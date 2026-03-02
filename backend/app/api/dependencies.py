"""API dependencies."""

from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status, Request, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User

security = HTTPBearer(auto_error=False)  # Don't auto-error, we'll check API key too


async def get_current_user(
    request: Request,
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
    x_api_key: Optional[str] = Header(None),
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Get current authenticated user from JWT token OR API key.
    
    Supports two authentication methods:
    1. JWT Bearer token (Authorization: Bearer <token>)
    2. API key (X-API-Key: <key>)
    
    Args:
        request: FastAPI request object
        credentials: HTTP Bearer credentials (optional)
        x_api_key: API key from header (optional)
        db: Database session
        
    Returns:
        User: Authenticated user
        
    Raises:
        HTTPException: If authentication fails
    """
    # Try API key authentication first
    if x_api_key:
        from app.middleware.api_key_auth import get_current_user_from_api_key
        
        user = await get_current_user_from_api_key(
            request=request,
            x_api_key=x_api_key,
            db=db
        )
        
        if user:
            return user
        
        # API key provided but invalid
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    # Try JWT authentication
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No authentication credentials provided",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    
    payload = decode_token(token)
    
    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("sub")
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user


async def require_admin(
    current_user: Annotated[User, Depends(get_current_user)]
) -> User:
    """
    Require that the current user is an administrator.
    
    Args:
        current_user: The authenticated user
        
    Returns:
        User: The authenticated admin user
        
    Raises:
        HTTPException: If the user is not an admin
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    
    return current_user
