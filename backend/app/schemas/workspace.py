"""Workspace schemas for API requests/responses."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.workspace_member import MemberRole
from app.models.workspace_invitation import InvitationStatus


# ============================================================================
# Workspace Schemas
# ============================================================================

class WorkspaceBase(BaseModel):
    """Base workspace schema."""
    
    name: str = Field(..., min_length=1, max_length=255, description="Workspace name")
    description: Optional[str] = Field(None, description="Workspace description")


class WorkspaceCreate(WorkspaceBase):
    """Schema for creating a workspace."""
    
    max_members: int = Field(10, ge=1, le=1000, description="Maximum number of members")


class WorkspaceUpdate(BaseModel):
    """Schema for updating a workspace."""
    
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    max_members: Optional[int] = Field(None, ge=1, le=1000)


class WorkspaceResponse(WorkspaceBase):
    """Schema for workspace response."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    owner_id: UUID
    is_active: bool
    max_members: int
    created_at: datetime
    updated_at: datetime
    member_count: int = Field(0, description="Number of current members")


class WorkspaceListResponse(BaseModel):
    """Schema for workspace list response."""
    
    workspaces: List[WorkspaceResponse]
    total: int


# ============================================================================
# Workspace Member Schemas
# ============================================================================

class WorkspaceMemberBase(BaseModel):
    """Base workspace member schema."""
    
    user_id: UUID
    role: MemberRole = Field(MemberRole.MEMBER, description="Member role")


class WorkspaceMemberCreate(WorkspaceMemberBase):
    """Schema for adding a member to workspace."""
    
    pass


class WorkspaceMemberUpdate(BaseModel):
    """Schema for updating member role."""
    
    role: MemberRole = Field(..., description="New member role")
    
    @field_validator('role')
    @classmethod
    def validate_role(cls, v: MemberRole) -> MemberRole:
        """Validate that role is not OWNER (owner cannot be changed via API)."""
        if v == MemberRole.OWNER:
            raise ValueError("Cannot set role to OWNER via API")
        return v


class WorkspaceMemberResponse(BaseModel):
    """Schema for workspace member response."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    workspace_id: UUID
    user_id: UUID
    role: str
    joined_at: datetime
    updated_at: datetime
    
    # Include basic user info
    user_email: Optional[str] = None
    user_name: Optional[str] = None


class WorkspaceMemberListResponse(BaseModel):
    """Schema for workspace member list response."""
    
    members: List[WorkspaceMemberResponse]
    total: int


# ============================================================================
# Workspace Invitation Schemas
# ============================================================================

class InvitationBase(BaseModel):
    """Base invitation schema."""
    
    invitee_email: str = Field(..., description="Email of person to invite")
    role: MemberRole = Field(MemberRole.MEMBER, description="Role to assign")


class InvitationCreate(InvitationBase):
    """Schema for creating an invitation."""
    
    @field_validator('role')
    @classmethod
    def validate_role(cls, v: MemberRole) -> MemberRole:
        """Validate that role is not OWNER."""
        if v == MemberRole.OWNER:
            raise ValueError("Cannot invite as OWNER")
        return v


class InvitationResponse(BaseModel):
    """Schema for invitation response."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    workspace_id: UUID
    inviter_id: UUID
    invitee_email: str
    role: str
    status: str
    token: str
    created_at: datetime
    expires_at: datetime
    
    # Computed fields
    is_expired: bool = False
    workspace_name: Optional[str] = None
    inviter_name: Optional[str] = None


class InvitationListResponse(BaseModel):
    """Schema for invitation list response."""
    
    invitations: List[InvitationResponse]
    total: int


class InvitationAcceptRequest(BaseModel):
    """Schema for accepting an invitation."""
    
    token: str = Field(..., description="Invitation token")


class InvitationAcceptResponse(BaseModel):
    """Schema for invitation acceptance response."""
    
    success: bool
    message: str
    workspace_id: UUID
    member: WorkspaceMemberResponse
