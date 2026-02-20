"""Scheduled/Recurring task model.

Allows users to schedule tasks to run at specific times or on a
recurring schedule (daily, weekly, monthly, or cron expressions).
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.task import TaskType


class ScheduleType(str, Enum):
    """Schedule type for recurring tasks."""

    ONCE = "once"           # Run once at scheduled_at
    DAILY = "daily"         # Run every day at scheduled_at time
    WEEKLY = "weekly"       # Run every week on the same day/time
    MONTHLY = "monthly"     # Run every month on the same day/time
    CRON = "cron"           # Custom cron expression


class ScheduledTask(Base, TimestampMixin):
    """Scheduled task model for recurring agent operations."""

    __tablename__ = "scheduled_tasks"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)

    # Human-readable name
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Task definition (what to run)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    task_type: Mapped[TaskType] = mapped_column(
        SQLEnum(TaskType, native_enum=False), nullable=False
    )
    task_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Schedule definition
    schedule_type: Mapped[ScheduleType] = mapped_column(
        SQLEnum(ScheduleType, native_enum=False), nullable=False
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        comment="For ONCE: exact run time. For recurring: anchor time (hour/minute used)."
    )
    cron_expression: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
        comment="Cron expression for CRON schedule type (e.g. '0 9 * * 1')"
    )
    timezone: Mapped[str] = mapped_column(
        String(50), nullable=False, default="UTC"
    )

    # State
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_run_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_task_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )

    # Stats
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Limits
    max_runs: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        comment="Stop after this many runs (null = unlimited)"
    )

    __table_args__ = (
        Index("ix_sched_user_active", "user_id", "is_active"),
        Index("ix_sched_next_run", "is_active", "next_run_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<ScheduledTask(id={self.id}, name={self.name!r}, "
            f"type={self.schedule_type}, active={self.is_active})>"
        )
