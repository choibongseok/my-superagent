"""Workspace schemas."""
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.workspace_member import MemberRole


# ============================================================================
# Workspace Schemas
# ============================================================================

class WorkspaceCreate(BaseModel):
    """Request schema for creating a workspace."""
    name: str = Field(..., description="Workspace name")
    description: Optional[str] = Field(None, description="Workspace description")
    color: Optional[str] = Field(None, description="Hex color code")
    icon: Optional[str] = Field(None, description="Emoji or icon name")
    max_members: int = Field(10, description="Maximum number of members")


class WorkspaceUpdate(BaseModel):
    """Request schema for updating a workspace."""
    name: Optional[str] = Field(None, description="Workspace name")
    description: Optional[str] = Field(None, description="Workspace description")
    color: Optional[str] = Field(None, description="Hex color code")
    icon: Optional[str] = Field(None, description="Emoji or icon name")
    is_active: Optional[bool] = Field(None, description="Whether workspace is active")
    max_members: Optional[int] = Field(None, description="Maximum number of members")


class WorkspaceResponse(BaseModel):
    """Response schema for a workspace."""
    id: UUID
    name: str
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    owner_id: UUID
    is_default: bool = False
    is_archived: bool = False
    is_active: bool = True
    max_members: int = 10
    template_type: Optional[str] = None
    last_activity_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    member_count: int = 0

    class Config:
        from_attributes = True


class WorkspaceListResponse(BaseModel):
    """Response schema for a list of workspaces."""
    workspaces: List[WorkspaceResponse]
    total: int


# ============================================================================
# Workspace Member Schemas
# ============================================================================

class WorkspaceMemberCreate(BaseModel):
    """Request schema for adding a workspace member."""
    user_id: UUID
    role: MemberRole = MemberRole.MEMBER


class WorkspaceMemberUpdate(BaseModel):
    """Request schema for updating a workspace member."""
    role: MemberRole


class WorkspaceMemberResponse(BaseModel):
    """Response schema for a workspace member."""
    id: UUID
    workspace_id: UUID
    user_id: UUID
    role: str
    joined_at: datetime
    updated_at: datetime
    user_email: Optional[str] = None
    user_name: Optional[str] = None

    class Config:
        from_attributes = True


class WorkspaceMemberListResponse(BaseModel):
    """Response schema for a list of workspace members."""
    members: List[WorkspaceMemberResponse]
    total: int


# ============================================================================
# Workspace Invitation Schemas
# ============================================================================

class InvitationCreate(BaseModel):
    """Request schema for creating an invitation."""
    invitee_email: str = Field(..., description="Email address to invite")
    role: MemberRole = Field(MemberRole.MEMBER, description="Role to assign")


class InvitationResponse(BaseModel):
    """Response schema for a workspace invitation."""
    id: UUID
    workspace_id: UUID
    inviter_id: UUID
    invitee_email: str
    role: str
    status: str
    token: str
    expires_at: datetime
    created_at: datetime
    accepted_at: Optional[datetime] = None
    is_expired: bool = False
    workspace_name: Optional[str] = None
    inviter_name: Optional[str] = None

    class Config:
        from_attributes = True


class InvitationListResponse(BaseModel):
    """Response schema for a list of invitations."""
    invitations: List[InvitationResponse]
    total: int


class InvitationAcceptRequest(BaseModel):
    """Request schema for accepting an invitation."""
    token: str = Field(..., description="Invitation token")


class InvitationAcceptResponse(BaseModel):
    """Response schema for accepting an invitation."""
    success: bool
    message: str
    workspace_id: UUID
    member: WorkspaceMemberResponse


# ============================================================================
# Workspace Insight Schemas (existing)
# ============================================================================

class WorkspaceInsightResponse(BaseModel):
    """Response schema for workspace insights."""
    id: int
    user_id: int
    analyzed_at: datetime
    total_files: int
    total_size_bytes: int
    duplicate_files: Optional[List[Dict[str, Any]]] = None
    stale_files: Optional[List[Dict[str, Any]]] = None
    storage_breakdown: Optional[Dict[str, Any]] = None
    organization_suggestions: Optional[List[Dict[str, Any]]] = None

    class Config:
        from_attributes = True


class WorkspaceCleanupRequest(BaseModel):
    """Request schema for workspace cleanup operations."""
    insight_id: int = Field(..., description="ID of the workspace insight")
    suggestion_type: str = Field(
        ...,
        description="Type of organization operation"
    )


class WorkspaceCleanupResponse(BaseModel):
    """Response schema for workspace cleanup operations."""
    id: int
    user_id: int
    insight_id: Optional[int] = None
    operation_type: str
    performed_at: datetime
    files_affected: int
    bytes_freed: int
    details: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True
