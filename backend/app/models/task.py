"""Task model for agent operations."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, Enum as SQLEnum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.qa_result import QAResult
    from app.models.token_usage import TokenUsage
    from app.models.recovery_suggestion import RecoverySuggestion


class TaskStatus(str, Enum):
    """Task status enum."""

    PENDING = "pending"
    PROCESSING = "processing"
    # Backward-compatible alias used by older API/tests.
    IN_PROGRESS = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(str, Enum):
    """Task type enum."""

    DOCS = "docs"
    SHEETS = "sheets"
    SLIDES = "slides"
    RESEARCH = "research"


class Task(Base, TimestampMixin):
    """Task model for tracking agent operations."""

    __tablename__ = "tasks"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("workspaces.id", ondelete="SET NULL"), 
        nullable=True
    )

    # Task details
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    task_type: Mapped[TaskType] = mapped_column(
        SQLEnum(TaskType, native_enum=False), nullable=False, index=True
    )
    status: Mapped[TaskStatus] = mapped_column(
        SQLEnum(TaskStatus, native_enum=False), default=TaskStatus.PENDING, index=True
    )

    # Results
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Google Drive links
    document_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    document_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Task metadata (renamed from 'metadata' to avoid SQLAlchemy conflict)
    task_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Celery task ID
    celery_task_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True
    )

    # Lifecycle timestamps (completed_at was in the original schema)
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    # Progress tracking for real-time updates
    progress_percentage: Mapped[Optional[int]] = mapped_column(nullable=True, default=None)
    progress_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    progress_steps: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Public share token (generated on demand via POST /tasks/{id}/share)
    share_token: Mapped[Optional[UUID]] = mapped_column(
        nullable=True, unique=True, index=True, default=None
    )

    # Share link expiry (null = never expires unless set by /share endpoint)
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    # Composite indexes for common queries
    __table_args__ = (
        Index("ix_tasks_user_status", "user_id", "status"),
        Index("ix_tasks_user_type", "user_id", "task_type"),
        Index("ix_tasks_status_created", "status", "created_at"),
        Index("ix_tasks_workspace_id", "workspace_id"),
        Index("ix_tasks_workspace_user", "workspace_id", "user_id"),
        Index("ix_tasks_workspace_status", "workspace_id", "status"),
    )

    # Relationships
    qa_results: Mapped[list["QAResult"]] = relationship(
        "QAResult", back_populates="task", cascade="all, delete-orphan"
    )
    
    token_usages: Mapped[list["TokenUsage"]] = relationship(
        "TokenUsage", back_populates="task", cascade="all, delete-orphan"
    )
    
    recovery_suggestions: Mapped[list["RecoverySuggestion"]] = relationship(
        "RecoverySuggestion", back_populates="task", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Task(id={self.id}, type={self.task_type}, status={self.status})>"
