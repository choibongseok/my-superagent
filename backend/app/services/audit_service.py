"""
Audit Service - Record all API calls and data changes
"""
from datetime import datetime, UTC
from typing import Optional, Dict, Any, List
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc
from fastapi import Request

from app.models.audit_log import AuditLog


class AuditService:
    """
    Service for recording audit trails.
    
    Features:
    - API call logging
    - Data change tracking (before/after snapshots)
    - Authentication event logging
    - Flexible filtering and search
    """
    
    @staticmethod
    def log_api_call(
        db: Session,
        request: Request,
        user_id: Optional[UUID],
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        action: str = "read",
        status_code: int = 200,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditLog:
        """
        Log an API endpoint call.
        
        Args:
            db: Database session
            request: FastAPI request object
            user_id: User who made the request
            resource_type: Type of resource accessed (task, user, workspace, etc.)
            resource_id: ID of the resource
            action: Action performed (read, create, update, delete)
            status_code: HTTP status code
            extra_metadata: Additional context
        
        Returns:
            Created AuditLog entry
        """
        log_entry = AuditLog(
            event_type="api_call",
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=user_id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            method=request.method,
            endpoint=str(request.url.path),
            status_code=status_code,
            extra_metadata=extra_metadata,
            created_at=datetime.now(UTC),
        )
        
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        
        return log_entry
    
    @staticmethod
    def log_data_change(
        db: Session,
        user_id: Optional[UUID],
        resource_type: str,
        resource_id: str,
        action: str,
        before_data: Optional[Dict[str, Any]] = None,
        after_data: Optional[Dict[str, Any]] = None,
        changes: Optional[Dict[str, Any]] = None,
        workspace_id: Optional[UUID] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditLog:
        """
        Log a data modification event.
        
        Args:
            db: Database session
            user_id: User who made the change
            resource_type: Type of resource (task, user, workspace, etc.)
            resource_id: ID of the resource
            action: Action performed (create, update, delete)
            before_data: State before change
            after_data: State after change
            changes: Specific fields changed
            workspace_id: Workspace context
            extra_metadata: Additional context
        
        Returns:
            Created AuditLog entry
        """
        log_entry = AuditLog(
            event_type="data_change",
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=user_id,
            workspace_id=workspace_id,
            before_data=before_data,
            after_data=after_data,
            changes=changes,
            extra_metadata=extra_metadata,
            created_at=datetime.now(UTC),
        )
        
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        
        return log_entry
    
    @staticmethod
    def log_auth_event(
        db: Session,
        user_id: Optional[UUID],
        action: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditLog:
        """
        Log an authentication event.
        
        Args:
            db: Database session
            user_id: User involved
            action: Action (login, logout, token_refresh, password_reset, etc.)
            ip_address: Client IP
            user_agent: Client user agent
            extra_metadata: Additional context
        
        Returns:
            Created AuditLog entry
        """
        log_entry = AuditLog(
            event_type="auth_event",
            action=action,
            resource_type="user",
            resource_id=str(user_id) if user_id else None,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            extra_metadata=extra_metadata,
            created_at=datetime.now(UTC),
        )
        
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        
        return log_entry
    
    @staticmethod
    def get_logs(
        db: Session,
        user_id: Optional[UUID] = None,
        workspace_id: Optional[UUID] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        event_type: Optional[str] = None,
        action: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditLog]:
        """
        Query audit logs with filters.
        
        Args:
            db: Database session
            user_id: Filter by user
            workspace_id: Filter by workspace
            resource_type: Filter by resource type
            resource_id: Filter by resource ID
            event_type: Filter by event type
            action: Filter by action
            start_date: Filter by start date
            end_date: Filter by end date
            limit: Max results
            offset: Pagination offset
        
        Returns:
            List of matching AuditLog entries
        """
        query = db.query(AuditLog)
        
        # Apply filters
        if user_id:
            query = query.filter(AuditLog.user_id == user_id)
        if workspace_id:
            query = query.filter(AuditLog.workspace_id == workspace_id)
        if resource_type:
            query = query.filter(AuditLog.resource_type == resource_type)
        if resource_id:
            query = query.filter(AuditLog.resource_id == resource_id)
        if event_type:
            query = query.filter(AuditLog.event_type == event_type)
        if action:
            query = query.filter(AuditLog.action == action)
        if start_date:
            query = query.filter(AuditLog.created_at >= start_date)
        if end_date:
            query = query.filter(AuditLog.created_at <= end_date)
        
        # Order by most recent first
        query = query.order_by(desc(AuditLog.created_at))
        
        # Pagination
        query = query.offset(offset).limit(limit)
        
        return query.all()
    
    @staticmethod
    def get_resource_history(
        db: Session,
        resource_type: str,
        resource_id: str,
        limit: int = 50,
    ) -> List[AuditLog]:
        """
        Get full history of a specific resource.
        
        Args:
            db: Database session
            resource_type: Type of resource
            resource_id: ID of the resource
            limit: Max results
        
        Returns:
            List of AuditLog entries for this resource
        """
        return (
            db.query(AuditLog)
            .filter(
                and_(
                    AuditLog.resource_type == resource_type,
                    AuditLog.resource_id == resource_id
                )
            )
            .order_by(desc(AuditLog.created_at))
            .limit(limit)
            .all()
        )
    
    @staticmethod
    def get_user_activity(
        db: Session,
        user_id: UUID,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[AuditLog]:
        """
        Get all activity for a specific user.
        
        Args:
            db: Database session
            user_id: User ID
            start_date: Filter by start date
            end_date: Filter by end date
            limit: Max results
        
        Returns:
            List of AuditLog entries for this user
        """
        query = db.query(AuditLog).filter(AuditLog.user_id == user_id)
        
        if start_date:
            query = query.filter(AuditLog.created_at >= start_date)
        if end_date:
            query = query.filter(AuditLog.created_at <= end_date)
        
        return (
            query
            .order_by(desc(AuditLog.created_at))
            .limit(limit)
            .all()
        )
