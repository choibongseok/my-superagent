"""Onboarding model for tracking user setup progress."""

from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class OnboardingStep(str, PyEnum):
    """Onboarding wizard steps."""

    WELCOME = "welcome"
    USE_CASE = "use_case"
    SAMPLE_TASK = "sample_task"
    COMPLETED = "completed"


class UseCase(str, PyEnum):
    """User-selected primary use case."""

    RESEARCH = "research"
    DOCUMENTS = "documents"
    DATA_ANALYSIS = "data_analysis"
    PRESENTATIONS = "presentations"


class OnboardingProgress(Base, TimestampMixin):
    """Track user onboarding wizard progress.

    Each user has at most one row.  The row is created when the user
    first hits the onboarding endpoint and updated as they advance
    through the wizard steps.
    """

    __tablename__ = "onboarding_progress"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    current_step: Mapped[str] = mapped_column(
        Enum(OnboardingStep, name="onboarding_step", create_constraint=False),
        default=OnboardingStep.WELCOME,
        nullable=False,
    )
    use_case: Mapped[Optional[str]] = mapped_column(
        Enum(UseCase, name="onboarding_use_case", create_constraint=False),
        nullable=True,
    )
    sample_task_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<OnboardingProgress(user_id={self.user_id}, "
            f"step={self.current_step})>"
        )
