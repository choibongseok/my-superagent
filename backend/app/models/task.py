"""Task model for agent operations."""

from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import JSON, Enum as SQLEnum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class TaskStatus(str, Enum):
    """Task status enum."""

    PENDING = "pending"
    PROCESSING = "processing"
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
    
    # Task details
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    task_type: Mapped[TaskType] = mapped_column(
        SQLEnum(TaskType, native_enum=False), nullable=False
    )
    status: Mapped[TaskStatus] = mapped_column(
        SQLEnum(TaskStatus, native_enum=False), default=TaskStatus.PENDING
    )
    
    # Results
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Google Drive links
    document_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    document_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Metadata
    metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    # Celery task ID
    celery_task_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True
    )

    def __repr__(self) -> str:
        return f"<Task(id={self.id}, type={self.task_type}, status={self.status})>"
