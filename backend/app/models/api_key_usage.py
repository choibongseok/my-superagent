"""API Key usage tracking model."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

from sqlalchemy import String, DateTime, ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.api_key import ApiKey


class ApiKeyUsage(Base):
    """Track API key usage for analytics."""

    __tablename__ = "api_key_usage"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    api_key_id: Mapped[UUID] = mapped_column(
        ForeignKey("api_keys.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    endpoint: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="API endpoint called"
    )
    method: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="HTTP method (GET, POST, etc.)"
    )
    status_code: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
        comment="HTTP status code"
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
        comment="Client IP address"
    )
    user_agent: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
        comment="User-Agent header"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
        index=True
    )

    # Relationships
    api_key: Mapped["ApiKey"] = relationship("ApiKey", back_populates="usage_logs")

    # Composite indexes for analytics queries
    __table_args__ = (
        Index("idx_usage_key_time", "api_key_id", "created_at"),
        Index("idx_usage_endpoint_time", "endpoint", "created_at"),
        Index("idx_usage_status_time", "status_code", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<ApiKeyUsage(id={self.id}, endpoint={self.endpoint}, status={self.status_code})>"
