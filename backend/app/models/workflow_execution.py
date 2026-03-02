"""
Database models for workflow execution tracking.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4
import enum

from sqlalchemy import String, Text, Enum as SQLEnum, ForeignKey
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class WorkflowStatus(str, enum.Enum):
    """Workflow execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowExecution(Base, TimestampMixin):
    """
    Tracks workflow execution history and status.
    
    Each workflow execution represents a single run of a multi-agent workflow,
    storing inputs, outputs, status, and timing information.
    """
    __tablename__ = "workflow_executions"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    execution_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    workflow_id: Mapped[str] = mapped_column(String(100), index=True)
    workflow_name: Mapped[str] = mapped_column(String(255))
    
    # Ownership
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    user: Mapped["User"] = relationship("User", back_populates="workflow_executions")
    
    # Status
    status: Mapped[WorkflowStatus] = mapped_column(
        SQLEnum(WorkflowStatus, native_enum=False),
        default=WorkflowStatus.PENDING,
        index=True
    )
    current_step: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    
    # Data
    initial_inputs: Mapped[dict] = mapped_column(JSON, default=dict)
    step_results: Mapped[dict] = mapped_column(JSON, default=dict)
    final_output: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timing
    started_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    
    # Metadata - inherited from TimestampMixin (created_at, updated_at)
    metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    
    def __repr__(self):
        return f"<WorkflowExecution(id={self.id}, execution_id={self.execution_id}, status={self.status})>"
    
    @property
    def duration_seconds(self) -> float:
        """Calculate execution duration in seconds."""
        if not self.completed_at:
            return (datetime.utcnow() - self.started_at).total_seconds()
        return (self.completed_at - self.started_at).total_seconds()
    
    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "execution_id": self.execution_id,
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "user_id": str(self.user_id),
            "status": self.status.value,
            "current_step": self.current_step,
            "initial_inputs": self.initial_inputs,
            "step_results": self.step_results,
            "final_output": self.final_output,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
