"""API key management endpoints."""

from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.models.user import User
from app.models.api_key import ApiKey
from app.models.api_key_usage import ApiKeyUsage

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


# Schemas
class ApiKeyCreate(BaseModel):
    """API key creation request."""
    name: str = Field(..., min_length=1, max_length=255, description="User-friendly name for the key")
    scopes: List[str] = Field(default=["read"], description="List of scopes (read, write, admin)")
    expires_in_days: Optional[int] = Field(None, ge=1, le=365, description="Number of days until expiration")


class ApiKeyResponse(BaseModel):
    """API key response (without the actual key)."""
    id: UUID
    name: str
    key_prefix: str
    scopes: List[str]
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    is_active: bool
    usage_count: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class ApiKeyCreateResponse(ApiKeyResponse):
    """Response when creating a new API key (includes the actual key)."""
    api_key: str = Field(..., description="The actual API key (only shown once!)")


class ApiKeyUpdate(BaseModel):
    """API key update request."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    scopes: Optional[List[str]] = None
    is_active: Optional[bool] = None


class ApiKeyStats(BaseModel):
    """API key usage statistics."""
    total_requests: int
    requests_by_endpoint: dict[str, int]
    requests_by_status: dict[int, int]
    last_24h_requests: int
    last_7d_requests: int


# Endpoints
@router.post("", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    request: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiKeyCreateResponse:
    """Create a new API key.
    
    **Important**: The actual API key is only shown once during creation.
    Store it securely - you won't be able to retrieve it again.
    """
    # Validate scopes
    valid_scopes = {"read", "write", "admin"}
    if not all(scope in valid_scopes for scope in request.scopes):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid scopes. Allowed: {valid_scopes}"
        )
    
    # Only admins can create admin-scoped keys
    if "admin" in request.scopes and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can create API keys with 'admin' scope"
        )
    
    # Generate key
    api_key, key_hash = ApiKey.generate_key()
    key_prefix = api_key[:8]
    
    # Calculate expiration
    expires_at = None
    if request.expires_in_days:
        expires_at = datetime.utcnow() + timedelta(days=request.expires_in_days)
    
    # Create API key
    db_api_key = ApiKey(
        user_id=current_user.id,
        name=request.name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        scopes=",".join(request.scopes),
        expires_at=expires_at,
    )
    
    db.add(db_api_key)
    await db.commit()
    await db.refresh(db_api_key)
    
    # Return response with actual key (only time it's shown)
    return ApiKeyCreateResponse(
        id=db_api_key.id,
        name=db_api_key.name,
        key_prefix=db_api_key.key_prefix,
        scopes=db_api_key.scope_list,
        expires_at=db_api_key.expires_at,
        last_used_at=db_api_key.last_used_at,
        is_active=db_api_key.is_active,
        usage_count=db_api_key.usage_count,
        created_at=db_api_key.created_at,
        api_key=api_key,  # Only shown once!
    )


@router.get("", response_model=List[ApiKeyResponse])
async def list_api_keys(
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[ApiKeyResponse]:
    """List all API keys for the current user."""
    query = select(ApiKey).where(ApiKey.user_id == current_user.id)
    
    if not include_inactive:
        query = query.where(ApiKey.is_active == True)
    
    query = query.order_by(ApiKey.created_at.desc())
    
    result = await db.execute(query)
    api_keys = result.scalars().all()
    
    return [
        ApiKeyResponse(
            id=key.id,
            name=key.name,
            key_prefix=key.key_prefix,
            scopes=key.scope_list,
            expires_at=key.expires_at,
            last_used_at=key.last_used_at,
            is_active=key.is_active,
            usage_count=key.usage_count,
            created_at=key.created_at,
        )
        for key in api_keys
    ]


@router.get("/{key_id}", response_model=ApiKeyResponse)
async def get_api_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiKeyResponse:
    """Get details of a specific API key."""
    query = select(ApiKey).where(
        and_(
            ApiKey.id == key_id,
            ApiKey.user_id == current_user.id
        )
    )
    
    result = await db.execute(query)
    api_key = result.scalar_one_or_none()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    return ApiKeyResponse(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        scopes=api_key.scope_list,
        expires_at=api_key.expires_at,
        last_used_at=api_key.last_used_at,
        is_active=api_key.is_active,
        usage_count=api_key.usage_count,
        created_at=api_key.created_at,
    )


@router.patch("/{key_id}", response_model=ApiKeyResponse)
async def update_api_key(
    key_id: UUID,
    request: ApiKeyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiKeyResponse:
    """Update an API key (name, scopes, or activation status)."""
    query = select(ApiKey).where(
        and_(
            ApiKey.id == key_id,
            ApiKey.user_id == current_user.id
        )
    )
    
    result = await db.execute(query)
    api_key = result.scalar_one_or_none()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    # Update fields
    if request.name is not None:
        api_key.name = request.name
    
    if request.scopes is not None:
        # Validate scopes
        valid_scopes = {"read", "write", "admin"}
        if not all(scope in valid_scopes for scope in request.scopes):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid scopes. Allowed: {valid_scopes}"
            )
        
        # Only admins can set admin scope
        if "admin" in request.scopes and not current_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators can set 'admin' scope"
            )
        
        api_key.scopes = ",".join(request.scopes)
    
    if request.is_active is not None:
        api_key.is_active = request.is_active
    
    await db.commit()
    await db.refresh(api_key)
    
    return ApiKeyResponse(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        scopes=api_key.scope_list,
        expires_at=api_key.expires_at,
        last_used_at=api_key.last_used_at,
        is_active=api_key.is_active,
        usage_count=api_key.usage_count,
        created_at=api_key.created_at,
    )


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete an API key (cannot be undone)."""
    query = select(ApiKey).where(
        and_(
            ApiKey.id == key_id,
            ApiKey.user_id == current_user.id
        )
    )
    
    result = await db.execute(query)
    api_key = result.scalar_one_or_none()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    await db.delete(api_key)
    await db.commit()


@router.post("/{key_id}/rotate", response_model=ApiKeyCreateResponse)
async def rotate_api_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiKeyCreateResponse:
    """Rotate an API key (generates a new key, invalidates the old one).
    
    **Important**: The new API key is only shown once. Store it securely.
    """
    query = select(ApiKey).where(
        and_(
            ApiKey.id == key_id,
            ApiKey.user_id == current_user.id
        )
    )
    
    result = await db.execute(query)
    api_key = result.scalar_one_or_none()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    # Generate new key
    new_api_key, new_key_hash = ApiKey.generate_key()
    new_key_prefix = new_api_key[:8]
    
    # Update the existing record
    api_key.key_hash = new_key_hash
    api_key.key_prefix = new_key_prefix
    api_key.usage_count = 0
    api_key.last_used_at = None
    
    await db.commit()
    await db.refresh(api_key)
    
    return ApiKeyCreateResponse(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        scopes=api_key.scope_list,
        expires_at=api_key.expires_at,
        last_used_at=api_key.last_used_at,
        is_active=api_key.is_active,
        usage_count=api_key.usage_count,
        created_at=api_key.created_at,
        api_key=new_api_key,  # Only shown once!
    )


@router.get("/{key_id}/stats", response_model=ApiKeyStats)
async def get_api_key_stats(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiKeyStats:
    """Get usage statistics for an API key."""
    # Verify ownership
    query = select(ApiKey).where(
        and_(
            ApiKey.id == key_id,
            ApiKey.user_id == current_user.id
        )
    )
    
    result = await db.execute(query)
    api_key = result.scalar_one_or_none()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    # Get usage stats
    total_query = select(func.count(ApiKeyUsage.id)).where(ApiKeyUsage.api_key_id == key_id)
    total_result = await db.execute(total_query)
    total_requests = total_result.scalar() or 0
    
    # Requests by endpoint
    endpoint_query = select(
        ApiKeyUsage.endpoint,
        func.count(ApiKeyUsage.id)
    ).where(ApiKeyUsage.api_key_id == key_id).group_by(ApiKeyUsage.endpoint)
    endpoint_result = await db.execute(endpoint_query)
    requests_by_endpoint = {row[0]: row[1] for row in endpoint_result}
    
    # Requests by status
    status_query = select(
        ApiKeyUsage.status_code,
        func.count(ApiKeyUsage.id)
    ).where(ApiKeyUsage.api_key_id == key_id).group_by(ApiKeyUsage.status_code)
    status_result = await db.execute(status_query)
    requests_by_status = {row[0]: row[1] for row in status_result}
    
    # Last 24h requests
    yesterday = datetime.utcnow() - timedelta(days=1)
    last_24h_query = select(func.count(ApiKeyUsage.id)).where(
        and_(
            ApiKeyUsage.api_key_id == key_id,
            ApiKeyUsage.created_at >= yesterday
        )
    )
    last_24h_result = await db.execute(last_24h_query)
    last_24h_requests = last_24h_result.scalar() or 0
    
    # Last 7d requests
    last_week = datetime.utcnow() - timedelta(days=7)
    last_7d_query = select(func.count(ApiKeyUsage.id)).where(
        and_(
            ApiKeyUsage.api_key_id == key_id,
            ApiKeyUsage.created_at >= last_week
        )
    )
    last_7d_result = await db.execute(last_7d_query)
    last_7d_requests = last_7d_result.scalar() or 0
    
    return ApiKeyStats(
        total_requests=total_requests,
        requests_by_endpoint=requests_by_endpoint,
        requests_by_status=requests_by_status,
        last_24h_requests=last_24h_requests,
        last_7d_requests=last_7d_requests,
    )
