"""Nudge email log model for tracking email sends."""

from datetime import datetime
from typing import Optional, TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class NudgeEmailLog(Base, TimestampMixin):
    """Log of nudge emails sent to users.
    
    Used to track:
    - Which users received nudge emails
    - When emails were sent
    - Whether email was delivered successfully
    - Weekly limit enforcement (max 2 per user per week)
    """

    __tablename__ = "nudge_email_logs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    email_type: Mapped[str] = mapped_column(String(50), nullable=False, default="usage_nudge", index=True)
    sent_at: Mapped[datetime] = mapped_column(nullable=False, index=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error_message: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="nudge_email_logs")

    def __repr__(self) -> str:
        return f"<NudgeEmailLog(id={self.id}, user_id={self.user_id}, type={self.email_type}, sent_at={self.sent_at})>"
