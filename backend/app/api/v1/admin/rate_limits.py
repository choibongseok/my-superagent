"""Admin endpoints for rate limit management."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_current_user, require_admin
from backend.app.core.database import get_db
from backend.app.models.rate_limit_override import RateLimitOverride
from backend.app.models.user import User


router = APIRouter()


# Schemas
class RateLimitOverrideCreate(BaseModel):
    """Schema for creating a rate limit override."""
    
    user_id: UUID = Field(..., description="User ID to apply override to")
    endpoint_pattern: str = Field(
        ..., 
        description="Endpoint pattern (e.g., '/api/v1/tasks/*' or '*' for all)",
        min_length=1,
        max_length=255
    )
    custom_limit: int = Field(
        ..., 
        description="Custom rate limit in requests per minute",
        gt=0,
        le=10000
    )
    expires_at: Optional[datetime] = Field(
        None,
        description="Optional expiration time for temporary overrides"
    )
    reason: Optional[str] = Field(
        None,
        description="Optional reason for the override",
        max_length=500
    )


class RateLimitOverrideUpdate(BaseModel):
    """Schema for updating a rate limit override."""
    
    custom_limit: Optional[int] = Field(
        None,
        description="Custom rate limit in requests per minute",
        gt=0,
        le=10000
    )
    expires_at: Optional[datetime] = Field(
        None,
        description="Optional expiration time for temporary overrides"
    )
    reason: Optional[str] = Field(
        None,
        description="Optional reason for the override",
        max_length=500
    )


class RateLimitOverrideResponse(BaseModel):
    """Schema for rate limit override response."""
    
    id: int
    user_id: UUID
    endpoint_pattern: str
    custom_limit: int
    expires_at: Optional[datetime]
    created_at: datetime
    created_by: UUID
    reason: Optional[str]
    is_active: bool
    
    class Config:
        from_attributes = True


# Endpoints
@router.get(
    "",
    response_model=List[RateLimitOverrideResponse],
    summary="List all rate limit overrides",
    description="Get a list of all rate limit overrides in the system. Admin only."
)
async def list_rate_limit_overrides(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
    user_id: Optional[UUID] = None,
    active_only: bool = True
) -> List[RateLimitOverrideResponse]:
    """
    List all rate limit overrides.
    
    - **user_id**: Optional filter by user ID
    - **active_only**: Only return active (non-expired) overrides
    """
    query = db.query(RateLimitOverride)
    
    if user_id:
        query = query.filter(RateLimitOverride.user_id == user_id)
    
    overrides = query.all()
    
    # Filter active if requested
    if active_only:
        overrides = [o for o in overrides if o.is_active()]
    
    return [
        RateLimitOverrideResponse(
            id=o.id,
            user_id=o.user_id,
            endpoint_pattern=o.endpoint_pattern,
            custom_limit=o.custom_limit,
            expires_at=o.expires_at,
            created_at=o.created_at,
            created_by=o.created_by,
            reason=o.reason,
            is_active=o.is_active()
        )
        for o in overrides
    ]


@router.post(
    "",
    response_model=RateLimitOverrideResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a rate limit override",
    description="Create a new rate limit override for a user. Admin only."
)
async def create_rate_limit_override(
    override_data: RateLimitOverrideCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> RateLimitOverrideResponse:
    """
    Create a new rate limit override.
    
    Allows administrators to grant custom rate limits to specific users.
    """
    # Verify user exists
    user = db.query(User).filter(User.id == override_data.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {override_data.user_id} not found"
        )
    
    # Check for existing override with same pattern
    existing = db.query(RateLimitOverride).filter(
        RateLimitOverride.user_id == override_data.user_id,
        RateLimitOverride.endpoint_pattern == override_data.endpoint_pattern
    ).first()
    
    if existing and existing.is_active():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Active override already exists for user {override_data.user_id} "
                   f"and endpoint pattern '{override_data.endpoint_pattern}'"
        )
    
    # Create override
    override = RateLimitOverride(
        user_id=override_data.user_id,
        endpoint_pattern=override_data.endpoint_pattern,
        custom_limit=override_data.custom_limit,
        expires_at=override_data.expires_at,
        created_by=current_user.id,
        reason=override_data.reason
    )
    
    db.add(override)
    db.commit()
    db.refresh(override)
    
    return RateLimitOverrideResponse(
        id=override.id,
        user_id=override.user_id,
        endpoint_pattern=override.endpoint_pattern,
        custom_limit=override.custom_limit,
        expires_at=override.expires_at,
        created_at=override.created_at,
        created_by=override.created_by,
        reason=override.reason,
        is_active=override.is_active()
    )


@router.get(
    "/{override_id}",
    response_model=RateLimitOverrideResponse,
    summary="Get a rate limit override",
    description="Get a specific rate limit override by ID. Admin only."
)
async def get_rate_limit_override(
    override_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> RateLimitOverrideResponse:
    """Get a specific rate limit override by ID."""
    override = db.query(RateLimitOverride).filter(RateLimitOverride.id == override_id).first()
    
    if not override:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rate limit override with ID {override_id} not found"
        )
    
    return RateLimitOverrideResponse(
        id=override.id,
        user_id=override.user_id,
        endpoint_pattern=override.endpoint_pattern,
        custom_limit=override.custom_limit,
        expires_at=override.expires_at,
        created_at=override.created_at,
        created_by=override.created_by,
        reason=override.reason,
        is_active=override.is_active()
    )


@router.patch(
    "/{override_id}",
    response_model=RateLimitOverrideResponse,
    summary="Update a rate limit override",
    description="Update an existing rate limit override. Admin only."
)
async def update_rate_limit_override(
    override_id: int,
    override_data: RateLimitOverrideUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> RateLimitOverrideResponse:
    """Update an existing rate limit override."""
    override = db.query(RateLimitOverride).filter(RateLimitOverride.id == override_id).first()
    
    if not override:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rate limit override with ID {override_id} not found"
        )
    
    # Update fields
    if override_data.custom_limit is not None:
        override.custom_limit = override_data.custom_limit
    if override_data.expires_at is not None:
        override.expires_at = override_data.expires_at
    if override_data.reason is not None:
        override.reason = override_data.reason
    
    db.commit()
    db.refresh(override)
    
    return RateLimitOverrideResponse(
        id=override.id,
        user_id=override.user_id,
        endpoint_pattern=override.endpoint_pattern,
        custom_limit=override.custom_limit,
        expires_at=override.expires_at,
        created_at=override.created_at,
        created_by=override.created_by,
        reason=override.reason,
        is_active=override.is_active()
    )


@router.delete(
    "/{override_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a rate limit override",
    description="Delete a rate limit override. Admin only."
)
async def delete_rate_limit_override(
    override_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> None:
    """Delete a rate limit override."""
    override = db.query(RateLimitOverride).filter(RateLimitOverride.id == override_id).first()
    
    if not override:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rate limit override with ID {override_id} not found"
        )
    
    db.delete(override)
    db.commit()
