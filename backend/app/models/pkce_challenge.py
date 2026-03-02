"""PKCE challenge model for storing code challenges during OAuth flow."""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PKCEChallenge(Base):
    """PKCE challenge storage for OAuth 2.0 with PKCE."""
    
    __tablename__ = "pkce_challenges"
    
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    state: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    code_challenge: Mapped[str] = mapped_column(String, nullable=False)
    code_challenge_method: Mapped[str] = mapped_column(String, default="S256", nullable=False)
    redirect_uri: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="pkce_challenges")
    
    def __repr__(self) -> str:
        return f"<PKCEChallenge(id={self.id}, state={self.state[:8]}..., used={self.used})>"
