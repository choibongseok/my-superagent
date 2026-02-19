"""API Key model for Developer API Mode."""

import hashlib
import secrets
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


def generate_api_key() -> str:
    """Generate a secure random API key with 'sk-' prefix."""
    token = secrets.token_urlsafe(32)
    return f"sk-{token}"


def hash_api_key(key: str) -> str:
    """SHA-256 hash of the plaintext API key. Plaintext is never stored."""
    return hashlib.sha256(key.encode()).hexdigest()


class ApiKey(Base, TimestampMixin):
    """API Key model. Stores only the SHA-256 hash of the plaintext key."""

    __tablename__ = "api_keys"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="api_keys")

    def __repr__(self) -> str:
        return f"<ApiKey(id={self.id}, name={self.name!r}, user_id={self.user_id})>"
