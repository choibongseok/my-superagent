"""
Audit Log Model - Track all API calls and data changes for compliance
"""
from datetime import datetime, UTC
from sqlalchemy import Column, String, Integer, Text, JSON, Index, DateTime
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base
import uuid


class AuditLog(Base):
    """
    Audit trail for all API operations and data changes.
    
    Tracks:
    - User actions (who did what, when)
    - API endpoint calls
    - Data modifications (before/after snapshots)
    - Authentication events
    - Security-relevant events
    
    For compliance: GDPR, SOC2, HIPAA
    """
    __tablename__ = "audit_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Event metadata
    event_type = Column(String(100), nullable=False, index=True)  # api_call, data_change, auth_event
    action = Column(String(100), nullable=False, index=True)  # create, read, update, delete, login, logout
    resource_type = Column(String(100), nullable=True, index=True)  # task, user, workspace, etc.
    resource_id = Column(String(255), nullable=True, index=True)  # UUID or identifier
    
    # Request context
    user_id = Column(UUID(as_uuid=True), nullable=True, index=True)  # Who did it
    workspace_id = Column(UUID(as_uuid=True), nullable=True, index=True)  # Which workspace
    ip_address = Column(String(45), nullable=True)  # IPv4/IPv6
    user_agent = Column(Text, nullable=True)
    
    # API details
    method = Column(String(10), nullable=True)  # GET, POST, PUT, DELETE
    endpoint = Column(String(500), nullable=True, index=True)
    status_code = Column(Integer, nullable=True)
    
    # Data changes (JSON snapshots)
    before_data = Column(JSON, nullable=True)  # State before change
    after_data = Column(JSON, nullable=True)   # State after change
    changes = Column(JSON, nullable=True)      # Specific fields changed
    
    # Additional context
    extra_metadata = Column(JSON, nullable=True)  # Extra info (error messages, session_id, etc.)
    
    # Timestamp
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True
    )
    
    # Indexes for fast queries
    __table_args__ = (
        Index('ix_audit_logs_user_created', 'user_id', 'created_at'),
        Index('ix_audit_logs_resource', 'resource_type', 'resource_id'),
        Index('ix_audit_logs_event_created', 'event_type', 'created_at'),
        Index('ix_audit_logs_workspace_created', 'workspace_id', 'created_at'),
    )
    
    def __repr__(self):
        return f"<AuditLog(id={self.id}, event_type={self.event_type}, action={self.action}, user_id={self.user_id})>"
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": str(self.id),
            "event_type": self.event_type,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "user_id": str(self.user_id) if self.user_id else None,
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "method": self.method,
            "endpoint": self.endpoint,
            "status_code": self.status_code,
            "before_data": self.before_data,
            "after_data": self.after_data,
            "changes": self.changes,
            "extra_metadata": self.extra_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
