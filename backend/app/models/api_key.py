"""API Key model for programmatic access."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional, List
from uuid import UUID, uuid4
import secrets
import hashlib

from sqlalchemy import String, Text, DateTime, ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.api_key_usage import ApiKeyUsage


class ApiKey(Base, TimestampMixin):
    """API key model for authentication."""

    __tablename__ = "api_keys"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    name: Mapped[str] = mapped_column(
        String(255), 
        nullable=False,
        comment="User-friendly name for the key"
    )
    key_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="SHA-256 hash of the API key"
    )
    key_prefix: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        index=True,
        comment="First 8 chars of key for identification"
    )
    scopes: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="read",
        comment="Comma-separated list of scopes (read,write,admin)"
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Optional expiration time"
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last time this key was used"
    )
    is_active: Mapped[bool] = mapped_column(
        default=True,
        index=True,
        comment="Whether the key is active"
    )
    usage_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Total number of requests made with this key"
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="api_keys")
    usage_logs: Mapped[List["ApiKeyUsage"]] = relationship(
        "ApiKeyUsage", 
        back_populates="api_key", 
        cascade="all, delete-orphan"
    )

    # Composite indexes
    __table_args__ = (
        Index("idx_api_keys_user_active", "user_id", "is_active"),
        Index("idx_api_keys_expires", "expires_at", "is_active"),
    )

    @staticmethod
    def generate_key() -> tuple[str, str]:
        """Generate a new API key and its hash.
        
        Returns:
            tuple[str, str]: (api_key, key_hash)
            - api_key: The actual key to return to user (only shown once)
            - key_hash: SHA-256 hash to store in database
        """
        # Generate a secure random key
        key = f"ahq_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        return key, key_hash

    @staticmethod
    def hash_key(api_key: str) -> str:
        """Hash an API key for storage/lookup."""
        return hashlib.sha256(api_key.encode()).hexdigest()

    @property
    def scope_list(self) -> List[str]:
        """Return scopes as a list."""
        return [s.strip() for s in self.scopes.split(",") if s.strip()]

    def has_scope(self, scope: str) -> bool:
        """Check if key has a specific scope."""
        return scope in self.scope_list or "admin" in self.scope_list

    def is_expired(self) -> bool:
        """Check if the key has expired."""
        if not self.expires_at:
            return False
        return datetime.utcnow() >= self.expires_at

    def is_valid(self) -> bool:
        """Check if the key is valid (active and not expired)."""
        return self.is_active and not self.is_expired()

    def __repr__(self) -> str:
        return f"<ApiKey(id={self.id}, name={self.name}, user_id={self.user_id}, prefix={self.key_prefix})>"
