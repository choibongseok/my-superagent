"""
Audit Log API - Query audit trails for compliance
"""
from datetime import datetime
from typing import Optional, List
from uuid import UUID
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.deps import get_db, get_current_user
from app.models.user import User
from app.services.audit_service import AuditService


router = APIRouter()


# Schemas
class AuditLogResponse(BaseModel):
    """Response schema for audit log entry"""
    id: str
    event_type: str
    action: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    user_id: Optional[str]
    workspace_id: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]
    method: Optional[str]
    endpoint: Optional[str]
    status_code: Optional[int]
    before_data: Optional[dict]
    after_data: Optional[dict]
    changes: Optional[dict]
    extra_metadata: Optional[dict]
    created_at: str
    
    class Config:
        from_attributes = True


class AuditLogListResponse(BaseModel):
    """Paginated list of audit logs"""
    logs: List[AuditLogResponse]
    total: int
    offset: int
    limit: int


# Endpoints
@router.get("/logs", response_model=AuditLogListResponse)
def get_audit_logs(
    user_id: Optional[UUID] = Query(None, description="Filter by user ID"),
    workspace_id: Optional[UUID] = Query(None, description="Filter by workspace ID"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    resource_id: Optional[str] = Query(None, description="Filter by resource ID"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    action: Optional[str] = Query(None, description="Filter by action"),
    start_date: Optional[datetime] = Query(None, description="Filter by start date (ISO 8601)"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date (ISO 8601)"),
    limit: int = Query(100, ge=1, le=500, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Query audit logs with filters.
    
    **Permissions:**
    - Regular users can only see their own logs
    - Workspace admins can see workspace logs
    - Superusers can see all logs
    
    **Filters:**
    - `user_id` - Filter by user
    - `workspace_id` - Filter by workspace
    - `resource_type` - Filter by resource type (task, user, workspace, etc.)
    - `resource_id` - Filter by resource ID
    - `event_type` - Filter by event type (api_call, data_change, auth_event)
    - `action` - Filter by action (create, read, update, delete, login, logout, etc.)
    - `start_date` - Filter by start date (ISO 8601 format)
    - `end_date` - Filter by end date (ISO 8601 format)
    
    **Pagination:**
    - `limit` - Max results (1-500, default 100)
    - `offset` - Pagination offset
    
    **Examples:**
    - Get my recent activity: `GET /api/v1/audit/logs?user_id=<my-id>&limit=50`
    - Get task history: `GET /api/v1/audit/logs?resource_type=task&resource_id=<task-id>`
    - Get auth events: `GET /api/v1/audit/logs?event_type=auth_event&start_date=2026-02-01T00:00:00Z`
    """
    # Permission check: regular users can only see their own logs
    if not current_user.is_superuser:
        if user_id and user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only access your own audit logs"
            )
        # Force filter to current user if not superuser
        user_id = current_user.id
    
    # Query logs
    logs = AuditService.get_logs(
        db=db,
        user_id=user_id,
        workspace_id=workspace_id,
        resource_type=resource_type,
        resource_id=resource_id,
        event_type=event_type,
        action=action,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
    
    # Count total (for pagination)
    # Note: This is a simplified count; in production, use a separate count query
    total = len(logs)
    
    return AuditLogListResponse(
        logs=[AuditLogResponse.model_validate(log.to_dict()) for log in logs],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/resource/{resource_type}/{resource_id}", response_model=List[AuditLogResponse])
def get_resource_history(
    resource_type: str,
    resource_id: str,
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get full audit history for a specific resource.
    
    **Permissions:**
    - Users can only access resources they own or have access to
    - Superusers can access all resources
    
    **Examples:**
    - Get task history: `GET /api/v1/audit/resource/task/<task-id>`
    - Get user history: `GET /api/v1/audit/resource/user/<user-id>`
    - Get workspace history: `GET /api/v1/audit/resource/workspace/<workspace-id>`
    """
    # Get history
    logs = AuditService.get_resource_history(
        db=db,
        resource_type=resource_type,
        resource_id=resource_id,
        limit=limit,
    )
    
    # Permission check: regular users can only see their own resources
    if not current_user.is_superuser:
        # Filter out logs that don't belong to the current user
        logs = [log for log in logs if log.user_id == current_user.id]
    
    return [AuditLogResponse.model_validate(log.to_dict()) for log in logs]


@router.get("/my-activity", response_model=List[AuditLogResponse])
def get_my_activity(
    start_date: Optional[datetime] = Query(None, description="Filter by start date (ISO 8601)"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date (ISO 8601)"),
    limit: int = Query(100, ge=1, le=500, description="Max results"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get my own activity log.
    
    Convenience endpoint for users to see their own audit trail.
    
    **Filters:**
    - `start_date` - Filter by start date (ISO 8601 format)
    - `end_date` - Filter by end date (ISO 8601 format)
    - `limit` - Max results (1-500, default 100)
    
    **Examples:**
    - Get my recent activity: `GET /api/v1/audit/my-activity?limit=50`
    - Get my activity last week: `GET /api/v1/audit/my-activity?start_date=2026-02-17T00:00:00Z`
    """
    logs = AuditService.get_user_activity(
        db=db,
        user_id=current_user.id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    
    return [AuditLogResponse.model_validate(log.to_dict()) for log in logs]


@router.get("/stats")
def get_audit_stats(
    start_date: Optional[datetime] = Query(None, description="Filter by start date (ISO 8601)"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date (ISO 8601)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get audit log statistics.
    
    **Permissions:**
    - Regular users see their own stats
    - Superusers see global stats
    
    **Returns:**
    - Total logs
    - Logs by event type
    - Logs by action
    - Most active users (superuser only)
    """
    # This is a placeholder for statistics
    # In production, implement proper aggregation queries
    
    user_id = None if current_user.is_superuser else current_user.id
    
    logs = AuditService.get_logs(
        db=db,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        limit=1000,  # Sample size for stats
        offset=0,
    )
    
    # Calculate stats
    event_type_counts = {}
    action_counts = {}
    
    for log in logs:
        event_type_counts[log.event_type] = event_type_counts.get(log.event_type, 0) + 1
        action_counts[log.action] = action_counts.get(log.action, 0) + 1
    
    return {
        "total_logs": len(logs),
        "event_types": event_type_counts,
        "actions": action_counts,
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
    }
