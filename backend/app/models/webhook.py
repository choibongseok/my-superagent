"""Webhook configuration model for external notifications.

Users register webhook URLs to receive POST callbacks when events occur
(task completion, task failure, etc.). Supports optional HMAC-SHA256
signature verification via a per-webhook secret.
"""

import secrets
from datetime import datetime
from enum import Enum
from typing import Optional, TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


def generate_webhook_secret() -> str:
    """Generate a secure random webhook signing secret."""
    return f"whsec_{secrets.token_urlsafe(32)}"


class WebhookEvent(str, Enum):
    """Events that can trigger a webhook."""

    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_CREATED = "task.created"
    TASK_ALL = "task.*"


class Webhook(Base, TimestampMixin):
    """Webhook configuration.

    Each webhook targets a single URL and listens for one or more event types.
    The ``secret`` is used to compute an ``X-Webhook-Signature`` HMAC header
    so the receiver can verify the payload authenticity.
    """

    __tablename__ = "webhooks"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Target URL (must be HTTPS in production)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)

    # Friendly label
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Comma-separated event types (e.g. "task.completed,task.failed")
    events: Mapped[str] = mapped_column(
        String(512), nullable=False, default="task.*"
    )

    # HMAC signing secret
    secret: Mapped[str] = mapped_column(
        String(255), nullable=False, default=generate_webhook_secret
    )

    # Whether this webhook is active
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Delivery stats
    success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_triggered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="webhooks")

    @property
    def event_list(self) -> list[str]:
        """Return the events as a list."""
        return [e.strip() for e in self.events.split(",") if e.strip()]

    def matches_event(self, event: str) -> bool:
        """Check whether this webhook should fire for the given event."""
        for pattern in self.event_list:
            if pattern == event:
                return True
            # Wildcard: "task.*" matches any "task.xxx"
            if pattern.endswith(".*"):
                prefix = pattern[:-2]
                if event.startswith(prefix + "."):
                    return True
        return False

    def __repr__(self) -> str:
        return f"<Webhook(id={self.id}, name={self.name!r}, url={self.url!r})>"
