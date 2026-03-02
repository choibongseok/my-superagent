"""Workspace Insight models."""
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import relationship

from backend.app.core.database import Base


class WorkspaceInsight(Base):
    """Workspace analytics and insights."""
    
    __tablename__ = "workspace_insights"
    __table_args__ = {"extend_existing": True}
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Analysis metadata
    analyzed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    total_files = Column(Integer, default=0)
    total_size_bytes = Column(Integer, default=0)
    
    # Insights data (JSON)
    duplicate_files = Column(JSON, nullable=True)  # List of duplicate file groups
    stale_files = Column(JSON, nullable=True)  # List of files not accessed in 90+ days
    storage_breakdown = Column(JSON, nullable=True)  # Storage by file type
    organization_suggestions = Column(JSON, nullable=True)  # Auto-org recommendations
    
    # Relationships
    user = relationship("User", back_populates="workspace_insights")
    
    def __repr__(self):
        return f"<WorkspaceInsight(user_id={self.user_id}, files={self.total_files})>"


class WorkspaceCleanupLog(Base):
    """Log of workspace cleanup operations."""
    
    __tablename__ = "workspace_cleanup_logs"
    __table_args__ = {"extend_existing": True}
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    insight_id = Column(Integer, ForeignKey("workspace_insights.id"), nullable=True)
    
    # Operation details
    operation_type = Column(String(50), nullable=False)  # organize, cleanup, archive
    performed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    files_affected = Column(Integer, default=0)
    bytes_freed = Column(Integer, default=0)
    
    # Operation details (JSON)
    details = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="workspace_cleanup_logs")
    
    def __repr__(self):
        return f"<WorkspaceCleanupLog(user_id={self.user_id}, type={self.operation_type})>"
