"""Workspace management endpoints with RBAC."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.services.email_service import email_service
from app.models.workspace import Workspace
from app.models.workspace_member import MemberRole, WorkspaceMember
from app.models.workspace_invitation import InvitationStatus, WorkspaceInvitation
from app.models.task import Task, TaskStatus
from app.schemas.workspace import (
    InvitationAcceptRequest,
    InvitationAcceptResponse,
    InvitationCreate,
    InvitationListResponse,
    InvitationResponse,
    WorkspaceCreate,
    WorkspaceListResponse,
    WorkspaceMemberCreate,
    WorkspaceMemberListResponse,
    WorkspaceMemberResponse,
    WorkspaceMemberUpdate,
    WorkspaceResponse,
    WorkspaceTrustRingResponse,
    WorkspaceUpdate,
)

router = APIRouter(tags=["workspaces"])


# ============================================================================
# Helper Functions
# ============================================================================

async def get_workspace_or_404(
    workspace_id: UUID,
    db: AsyncSession,
) -> Workspace:
    """Get workspace by ID or raise 404."""
    result = await db.execute(
        select(Workspace)
        .where(Workspace.id == workspace_id)
        .options(selectinload(Workspace.members))
    )
    workspace = result.scalar_one_or_none()
    
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found"
        )
    
    return workspace


async def get_member_or_404(
    workspace_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> WorkspaceMember:
    """Get workspace member or raise 404."""
    result = await db.execute(
        select(WorkspaceMember)
        .where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id
        )
    )
    member = result.scalar_one_or_none()
    
    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this workspace"
        )
    
    return member


async def check_permission(
    workspace_id: UUID,
    user: User,
    required_role: MemberRole,
    db: AsyncSession,
) -> WorkspaceMember:
    """Check if user has required permission level in workspace."""
    member = await get_member_or_404(workspace_id, user.id, db)
    
    if not member.has_permission(required_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions. Required: {required_role.value}"
        )
    
    return member


def _safe_score(value: float) -> float:
    """Clamp score into the 0~100 range and round for stable API output."""
    return round(max(0.0, min(100.0, value)), 2)


def _build_trust_ring_recommendations(
    total_tasks: int,
    trust_score: float,
    stability_score: float,
    speed_score: float,
    repeatability_score: float,
    failure_categories: dict,
) -> list[str]:
    """Return actionable recommendations from computed metrics."""
    recommendations: list[str] = []

    if total_tasks == 0:
        return [
            "No workspace activity in the selected period. Share a task or start a chain "
            "to begin trust scoring."
        ]

    if trust_score < 70:
        recommendations.append(
            "Trust dropped below target. Review failed tasks and reuse the Recovery Deck before rerunning."
        )

    if stability_score < 75:
        recommendations.append(
            "Repeated failures detected. Suggest enabling preflight checks for retry workflows."
        )

    if speed_score < 55:
        recommendations.append(
            "Execution speed is slower than expected. Break large prompts and run smaller batches."
        )

    if repeatability_score < 80 and failure_categories:
        recommendations.append(
            "Top failure category is recurring. Consider creating a dedicated template for it."
        )

    if not recommendations:
        recommendations.append("Workspace is operating smoothly. Keep the current process.")

    return recommendations


# ============================================================================
# Workspace CRUD Endpoints
# ============================================================================

@router.post("/", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    workspace_data: WorkspaceCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Create a new workspace.
    
    The creator automatically becomes the owner with OWNER role.
    """
    # Create workspace
    workspace = Workspace(
        name=workspace_data.name,
        description=workspace_data.description,
        owner_id=current_user.id,
        max_members=workspace_data.max_members,
    )
    
    db.add(workspace)
    await db.flush()  # Get workspace.id
    
    # Add creator as OWNER member
    member = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=current_user.id,
        role=MemberRole.OWNER.value,
    )
    
    db.add(member)
    await db.commit()
    await db.refresh(workspace)
    
    # Build response with member count
    response_data = WorkspaceResponse.model_validate(workspace)
    response_data.member_count = 1
    
    return response_data


@router.get("/", response_model=WorkspaceListResponse)
async def list_workspaces(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    List all workspaces where user is a member.
    
    Returns workspaces with pagination.
    """
    # Get workspace IDs where user is a member
    member_query = select(WorkspaceMember.workspace_id).where(
        WorkspaceMember.user_id == current_user.id
    )
    
    # Count total
    count_query = select(func.count()).select_from(member_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()
    
    # Get workspaces with pagination
    offset = (page - 1) * page_size
    
    result = await db.execute(
        select(Workspace)
        .where(Workspace.id.in_(member_query))
        .options(selectinload(Workspace.members))
        .offset(offset)
        .limit(page_size)
    )
    workspaces = result.scalars().all()
    
    # Build response with member counts
    workspace_responses = []
    for workspace in workspaces:
        response_data = WorkspaceResponse.model_validate(workspace)
        response_data.member_count = len(workspace.members)
        workspace_responses.append(response_data)
    
    return WorkspaceListResponse(
        workspaces=workspace_responses,
        total=total
    )


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get workspace details.

    Requires: VIEWER role (any member can view)
    """
    workspace = await get_workspace_or_404(workspace_id, db)

    # Check membership
    await get_member_or_404(workspace_id, current_user.id, db)

    # Build response with member count
    response_data = WorkspaceResponse.model_validate(workspace)
    response_data.member_count = len(workspace.members)

    return response_data


@router.get("/{workspace_id}/trust-ring", response_model=WorkspaceTrustRingResponse)
async def get_workspace_trust_ring(
    workspace_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    period_days: int = Query(30, ge=1, le=180),
):
    """Get workspace trust-ring analytics for multi-user collaboration.

    Exposes operational readiness metrics in 4 dimensions:
    trust, stability, speed, and repeatability.
    """
    # Only workspace members can view trust-ring metrics.
    await get_member_or_404(workspace_id, current_user.id, db)

    workspace = await get_workspace_or_404(workspace_id, db)
    period_start = datetime.now(UTC) - timedelta(days=period_days)
    period_end = datetime.now(UTC)

    member_rows = (await db.execute(
        select(WorkspaceMember.user_id)
        .where(WorkspaceMember.workspace_id == workspace_id)
    )).all()
    member_user_ids = [row[0] for row in member_rows]

    # Keep an explicit fallback when workspace data is temporarily inconsistent.
    if not member_user_ids:
        return WorkspaceTrustRingResponse(
            workspace_id=workspace.id,
            workspace_name=workspace.name,
            period_days=period_days,
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
            total_tasks=0,
            completed_tasks=0,
            failed_tasks=0,
            cancelled_tasks=0,
            pending_tasks=0,
            in_progress_tasks=0,
            avg_completion_time_seconds=0.0,
            trust_score=0.0,
            stability_score=0.0,
            speed_score=0.0,
            repeatability_score=0.0,
            failure_categories={},
            top_recommendations=[
                "No workspace members are available. Invite members to begin trust tracking."
            ],
            member_health=[],
        )

    tasks_result = await db.execute(
        select(Task)
        .where(
            Task.user_id.in_(member_user_ids),
            Task.created_at >= period_start,
            Task.created_at <= period_end,
        )
        .order_by(Task.created_at.asc())
    )
    tasks = tasks_result.scalars().all()

    total = len(tasks)
    completed = [t for t in tasks if t.status == TaskStatus.COMPLETED]
    failed = [t for t in tasks if t.status == TaskStatus.FAILED]
    cancelled = [t for t in tasks if t.status == TaskStatus.CANCELLED]
    pending = [t for t in tasks if t.status == TaskStatus.PENDING]
    processing = [t for t in tasks if t.status == TaskStatus.IN_PROGRESS]

    completion_durations = [
        (t.completed_at - t.created_at).total_seconds()
        for t in completed
        if t.completed_at is not None
    ]
    avg_completion_seconds = (
        round(sum(completion_durations) / len(completion_durations), 2)
        if completion_durations else 0.0
    )

    # Failure pattern distribution.
    from app.services.error_recovery import classify_error

    failure_categories: dict[str, int] = defaultdict(int)
    for t in failed:
        try:
            category = classify_error(t.error_message).category.value
        except Exception:
            category = "unknown"
        failure_categories[category] += 1

    repeated_failure_count = 0
    for count in failure_categories.values():
        if count > 1:
            repeated_failure_count += count - 1

    # Score calculations are intentionally simple and bounded.
    trust_rate = len(completed) / total if total else 0.0
    failure_rate = len(failed) / total if total else 0.0
    repeat_ratio = repeated_failure_count / len(failed) if failed else 0.0

    trust_score = _safe_score(trust_rate * 100)
    stability_score = _safe_score(100 - (failure_rate * 85 + repeat_ratio * 15))
    speed_score = 0.0 if not completion_durations else _safe_score(
        100 - min(avg_completion_seconds / 120.0 * 100, 100)
    )
    repeatability_score = _safe_score(
        100.0 if not failed else 100 - min(repeat_ratio * 100, 100)
    )

    # Build per-member health summaries.
    members = (await db.execute(
        select(WorkspaceMember, User.email)
        .join(User, WorkspaceMember.user_id == User.id)
        .where(WorkspaceMember.workspace_id == workspace_id)
    )).all()

    tasks_by_user: dict[UUID, list[Task]] = defaultdict(list)
    for t in tasks:
        tasks_by_user[t.user_id].append(t)

    member_health = []
    for member, user_email in members:
        member_tasks = tasks_by_user.get(member.user_id, [])
        m_total = len(member_tasks)
        m_completed = [t for t in member_tasks if t.status == TaskStatus.COMPLETED]
        m_failed = [t for t in member_tasks if t.status == TaskStatus.FAILED]

        m_completion = [
            (t.completed_at - t.created_at).total_seconds()
            for t in m_completed
            if t.completed_at is not None
        ]
        m_avg_completion = (
            round(sum(m_completion) / len(m_completion), 2) if m_completion else 0.0
        )

        member_health.append(
            {
                "user_id": member.user_id,
                "user_email": user_email,
                "total_tasks": m_total,
                "completed_tasks": len(m_completed),
                "failed_tasks": len(m_failed),
                "success_rate": round(len(m_completed) / m_total, 4) if m_total else 0.0,
                "avg_completion_time_seconds": m_avg_completion,
            }
        )

    recommendations = _build_trust_ring_recommendations(
        total,
        trust_score,
        stability_score,
        speed_score,
        repeatability_score,
        dict(failure_categories),
    )

    return WorkspaceTrustRingResponse(
        workspace_id=workspace.id,
        workspace_name=workspace.name,
        period_days=period_days,
        period_start=period_start.isoformat(),
        period_end=period_end.isoformat(),
        total_tasks=total,
        completed_tasks=len(completed),
        failed_tasks=len(failed),
        cancelled_tasks=len(cancelled),
        pending_tasks=len(pending),
        in_progress_tasks=len(processing),
        avg_completion_time_seconds=avg_completion_seconds,
        trust_score=trust_score,
        stability_score=stability_score,
        speed_score=speed_score,
        repeatability_score=repeatability_score,
        failure_categories=dict(failure_categories),
        top_recommendations=recommendations,
        member_health=member_health,
    )


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: UUID,
    workspace_data: WorkspaceUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Update workspace details.
    
    Requires: ADMIN role
    """
    workspace = await get_workspace_or_404(workspace_id, db)
    
    # Check permission
    await check_permission(workspace_id, current_user, MemberRole.ADMIN, db)
    
    # Update fields
    if workspace_data.name is not None:
        workspace.name = workspace_data.name
    if workspace_data.description is not None:
        workspace.description = workspace_data.description
    if workspace_data.is_active is not None:
        workspace.is_active = workspace_data.is_active
    if workspace_data.max_members is not None:
        workspace.max_members = workspace_data.max_members
    
    await db.commit()
    await db.refresh(workspace)
    
    # Build response with member count
    response_data = WorkspaceResponse.model_validate(workspace)
    response_data.member_count = len(workspace.members)
    
    return response_data


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Delete workspace.
    
    Requires: OWNER role
    """
    workspace = await get_workspace_or_404(workspace_id, db)
    
    # Check permission
    await check_permission(workspace_id, current_user, MemberRole.OWNER, db)
    
    await db.delete(workspace)
    await db.commit()


# ============================================================================
# Workspace Member Management
# ============================================================================

@router.get("/{workspace_id}/members", response_model=WorkspaceMemberListResponse)
async def list_members(
    workspace_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    List workspace members.
    
    Requires: VIEWER role (any member can view)
    """
    # Check membership
    await get_member_or_404(workspace_id, current_user.id, db)
    
    # Count total
    count_query = select(func.count()).select_from(WorkspaceMember).where(
        WorkspaceMember.workspace_id == workspace_id
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()
    
    # Get members with pagination
    offset = (page - 1) * page_size
    
    result = await db.execute(
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .options(selectinload(WorkspaceMember.user))
        .offset(offset)
        .limit(page_size)
    )
    members = result.scalars().all()
    
    # Build response with user info
    member_responses = []
    for member in members:
        response_data = WorkspaceMemberResponse.model_validate(member)
        if member.user:
            response_data.user_email = member.user.email
            response_data.user_name = member.user.full_name
        member_responses.append(response_data)
    
    return WorkspaceMemberListResponse(
        members=member_responses,
        total=total
    )


@router.post("/{workspace_id}/members", response_model=WorkspaceMemberResponse, status_code=status.HTTP_201_CREATED)
async def add_member(
    workspace_id: UUID,
    member_data: WorkspaceMemberCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Add a member to workspace (direct add, bypasses invitation).
    
    Requires: ADMIN role
    """
    workspace = await get_workspace_or_404(workspace_id, db)
    
    # Check permission
    await check_permission(workspace_id, current_user, MemberRole.ADMIN, db)
    
    # Check if member already exists
    existing = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == member_data.user_id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already a member"
        )
    
    # Check workspace capacity
    if len(workspace.members) >= workspace.max_members:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workspace has reached maximum member capacity"
        )
    
    # Verify user exists
    user_result = await db.execute(
        select(User).where(User.id == member_data.user_id)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Create member
    member = WorkspaceMember(
        workspace_id=workspace_id,
        user_id=member_data.user_id,
        role=member_data.role.value,
    )
    
    db.add(member)
    await db.commit()
    await db.refresh(member)
    
    # Build response with user info
    response_data = WorkspaceMemberResponse.model_validate(member)
    response_data.user_email = user.email
    response_data.user_name = user.full_name
    
    return response_data


@router.patch("/{workspace_id}/members/{user_id}", response_model=WorkspaceMemberResponse)
async def update_member_role(
    workspace_id: UUID,
    user_id: UUID,
    member_data: WorkspaceMemberUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Update member role.
    
    Requires: ADMIN role
    Cannot change OWNER role.
    """
    # Check permission
    await check_permission(workspace_id, current_user, MemberRole.ADMIN, db)
    
    # Get member
    member = await get_member_or_404(workspace_id, user_id, db)
    
    # Cannot change OWNER role
    if member.role == MemberRole.OWNER.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change OWNER role"
        )
    
    # Update role
    member.role = member_data.role.value
    
    await db.commit()
    await db.refresh(member)
    
    # Build response with user info
    response_data = WorkspaceMemberResponse.model_validate(member)
    if member.user:
        response_data.user_email = member.user.email
        response_data.user_name = member.user.full_name
    
    return response_data


@router.delete("/{workspace_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    workspace_id: UUID,
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Remove member from workspace.
    
    Requires: ADMIN role
    Cannot remove OWNER.
    """
    # Check permission
    await check_permission(workspace_id, current_user, MemberRole.ADMIN, db)
    
    # Get member
    member = await get_member_or_404(workspace_id, user_id, db)
    
    # Cannot remove OWNER
    if member.role == MemberRole.OWNER.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove OWNER from workspace"
        )
    
    await db.delete(member)
    await db.commit()


# ============================================================================
# Workspace Invitation Management
# ============================================================================

@router.post("/{workspace_id}/invitations", response_model=InvitationResponse, status_code=status.HTTP_201_CREATED)
async def create_invitation(
    workspace_id: UUID,
    invitation_data: InvitationCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Create workspace invitation.
    
    Requires: ADMIN role
    """
    workspace = await get_workspace_or_404(workspace_id, db)
    
    # Check permission
    await check_permission(workspace_id, current_user, MemberRole.ADMIN, db)
    
    # Check if user is already a member
    existing_member = await db.execute(
        select(WorkspaceMember)
        .join(User)
        .where(
            WorkspaceMember.workspace_id == workspace_id,
            User.email == invitation_data.invitee_email
        )
    )
    if existing_member.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already a member"
        )
    
    # Check for existing pending invitation
    existing_invitation = await db.execute(
        select(WorkspaceInvitation).where(
            WorkspaceInvitation.workspace_id == workspace_id,
            WorkspaceInvitation.invitee_email == invitation_data.invitee_email,
            WorkspaceInvitation.status == InvitationStatus.PENDING.value
        )
    )
    if existing_invitation.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation already exists for this email"
        )
    
    # Generate unique token
    token = secrets.token_urlsafe(32)
    
    # Create invitation
    invitation = WorkspaceInvitation(
        workspace_id=workspace_id,
        inviter_id=current_user.id,
        invitee_email=invitation_data.invitee_email,
        role=invitation_data.role.value,
        token=token,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    
    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)
    
    # Build response
    response_data = InvitationResponse.model_validate(invitation)
    response_data.is_expired = invitation.is_expired
    response_data.workspace_name = workspace.name
    response_data.inviter_name = current_user.full_name
    
    # Send invitation email
    invitation_link = f"{settings.FRONTEND_URL}/invitations/accept?token={token}"
    
    email_sent = email_service.send_workspace_invitation(
        to_email=invitation_data.invitee_email,
        workspace_name=workspace.name,
        inviter_name=current_user.full_name or "A team member",
        invitation_link=invitation_link,
        role=invitation_data.role.value,
        expires_in_days=7,
    )
    
    if not email_sent:
        # Log warning but don't fail the request
        # (invitation can still be shared via link)
        pass
    
    return response_data


@router.get("/{workspace_id}/invitations", response_model=InvitationListResponse)
async def list_invitations(
    workspace_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    List workspace invitations.
    
    Requires: ADMIN role
    """
    # Check permission
    await check_permission(workspace_id, current_user, MemberRole.ADMIN, db)
    
    # Count total
    count_query = select(func.count()).select_from(WorkspaceInvitation).where(
        WorkspaceInvitation.workspace_id == workspace_id
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()
    
    # Get invitations with pagination
    offset = (page - 1) * page_size
    
    result = await db.execute(
        select(WorkspaceInvitation)
        .where(WorkspaceInvitation.workspace_id == workspace_id)
        .options(
            selectinload(WorkspaceInvitation.workspace),
            selectinload(WorkspaceInvitation.inviter)
        )
        .offset(offset)
        .limit(page_size)
    )
    invitations = result.scalars().all()
    
    # Build response
    invitation_responses = []
    for invitation in invitations:
        response_data = InvitationResponse.model_validate(invitation)
        response_data.is_expired = invitation.is_expired
        if invitation.workspace:
            response_data.workspace_name = invitation.workspace.name
        if invitation.inviter:
            response_data.inviter_name = invitation.inviter.full_name
        invitation_responses.append(response_data)
    
    return InvitationListResponse(
        invitations=invitation_responses,
        total=total
    )


@router.post("/invitations/accept", response_model=InvitationAcceptResponse)
async def accept_invitation(
    request_data: InvitationAcceptRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Accept workspace invitation.
    
    Any authenticated user can accept an invitation sent to their email.
    """
    # Find invitation by token
    result = await db.execute(
        select(WorkspaceInvitation)
        .where(WorkspaceInvitation.token == request_data.token)
        .options(selectinload(WorkspaceInvitation.workspace))
    )
    invitation = result.scalar_one_or_none()
    
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found"
        )
    
    # Verify invitation is for current user's email
    if invitation.invitee_email != current_user.email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invitation is for a different email address"
        )
    
    # Check invitation status
    if invitation.status != InvitationStatus.PENDING.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invitation is {invitation.status}"
        )
    
    # Check expiration
    if invitation.is_expired:
        invitation.status = InvitationStatus.EXPIRED.value
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has expired"
        )
    
    # Check workspace capacity
    workspace = invitation.workspace
    member_count_query = select(func.count()).select_from(WorkspaceMember).where(
        WorkspaceMember.workspace_id == workspace.id
    )
    count_result = await db.execute(member_count_query)
    member_count = count_result.scalar_one()
    
    if member_count >= workspace.max_members:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workspace has reached maximum member capacity"
        )
    
    # Check if already a member
    existing = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == current_user.id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already a member of this workspace"
        )
    
    # Create member
    member = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=current_user.id,
        role=invitation.role,
    )
    
    db.add(member)
    
    # Update invitation status
    invitation.status = InvitationStatus.ACCEPTED.value
    invitation.accepted_at = datetime.now(UTC)
    
    await db.commit()
    await db.refresh(member)
    
    # Build response
    member_response = WorkspaceMemberResponse.model_validate(member)
    member_response.user_email = current_user.email
    member_response.user_name = current_user.full_name
    
    return InvitationAcceptResponse(
        success=True,
        message="Successfully joined workspace",
        workspace_id=workspace.id,
        member=member_response
    )
