"""OAuth provider connection model."""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import String, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column
import enum

from app.models.base import Base, TimestampMixin


class OAuthProvider(str, enum.Enum):
    """Supported OAuth providers."""
    
    GOOGLE = "google"
    GITHUB = "github"
    MICROSOFT = "microsoft"


class OAuthConnection(Base, TimestampMixin):
    """OAuth provider connection for a user."""

    __tablename__ = "oauth_connections"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[OAuthProvider] = mapped_column(
        SQLEnum(OAuthProvider),
        nullable=False,
        index=True,
    )
    provider_user_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Encrypted tokens
    access_token_encrypted: Mapped[str] = mapped_column(String(1024), nullable=False)
    refresh_token_encrypted: Mapped[Optional[str]] = mapped_column(
        String(1024), nullable=True
    )
    
    # Token metadata
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    scopes: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    
    # Additional provider data (JSON serialized)
    provider_data: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    
    # Last used for cleanup/auditing
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )

    def __repr__(self) -> str:
        return f"<OAuthConnection(id={self.id}, user_id={self.user_id}, provider={self.provider})>"
    
    @property
    def is_token_expired(self) -> bool:
        """Check if access token is expired."""
        if not self.token_expires_at:
            return False
        return datetime.utcnow() > self.token_expires_at
