"""Task Chain model — Smart Task Chaining (#227).

A TaskChain groups ordered steps where each step's output feeds into the next.
Example: Research → Docs → Slides (research findings → document → presentation).
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.task import TaskType


class ChainStatus(str, Enum):
    """Overall chain execution status."""

    DRAFT = "draft"           # User building the chain, not yet started
    PENDING = "pending"       # Ready to run, first step not started
    RUNNING = "running"       # At least one step in progress
    PAUSED = "paused"         # Paused between steps (manual or error)
    COMPLETED = "completed"   # All steps finished successfully
    FAILED = "failed"         # A step failed and chain halted
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    """Individual chain step status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskChain(Base, TimestampMixin):
    """A chain of tasks executed in sequence, output → input."""

    __tablename__ = "task_chains"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[ChainStatus] = mapped_column(
        SQLEnum(ChainStatus, native_enum=False),
        default=ChainStatus.DRAFT,
        index=True,
    )

    # Index of the step currently executing (0-based)
    current_step_index: Mapped[int] = mapped_column(Integer, default=0)

    # Overall chain metadata (e.g. original user intent)
    chain_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    steps: Mapped[list["ChainStep"]] = relationship(
        "ChainStep",
        back_populates="chain",
        cascade="all, delete-orphan",
        order_by="ChainStep.step_order",
    )

    __table_args__ = (
        Index("ix_chains_user_status", "user_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<TaskChain(id={self.id}, name={self.name!r}, status={self.status})>"


class ChainStep(Base, TimestampMixin):
    """A single step in a task chain."""

    __tablename__ = "chain_steps"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    chain_id: Mapped[UUID] = mapped_column(
        ForeignKey("task_chains.id", ondelete="CASCADE"), index=True
    )

    step_order: Mapped[int] = mapped_column(Integer, nullable=False)

    # What this step does
    prompt_template: Mapped[str] = mapped_column(
        Text, nullable=False,
    )
    task_type: Mapped[TaskType] = mapped_column(
        SQLEnum(TaskType, native_enum=False), nullable=False,
    )

    # Status
    status: Mapped[StepStatus] = mapped_column(
        SQLEnum(StepStatus, native_enum=False),
        default=StepStatus.PENDING,
    )

    # The actual prompt sent (after template rendering with previous output)
    resolved_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Reference to the Task created when this step executes
    task_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True,
    )

    # Output summary extracted from the completed task (passed to next step)
    output_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Step-level metadata
    step_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    chain: Mapped["TaskChain"] = relationship("TaskChain", back_populates="steps")

    __table_args__ = (
        Index("ix_steps_chain_order", "chain_id", "step_order", unique=True),
    )

    def __repr__(self) -> str:
        return (
            f"<ChainStep(id={self.id}, order={self.step_order}, "
            f"type={self.task_type}, status={self.status})>"
        )
