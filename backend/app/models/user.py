"""User model."""

from datetime import datetime
from typing import Optional, TYPE_CHECKING, List
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.api_key import ApiKey
    from app.models.chat import Chat
    from app.models.message import Message
    from app.models.webhook import Webhook
    from app.models.workspace import Workspace
    from app.models.workspace_member import WorkspaceMember
    from app.models.marketplace import MarketplaceTemplate, TemplateInstall, TemplateRating
    from app.models.token_usage import TokenUsage


class User(Base, TimestampMixin):
    """User model for authentication."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    google_id: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, nullable=True, index=True
    )
    google_access_token: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True
    )
    google_refresh_token: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(default=True, index=True)

    # Nudge email tracking
    last_task_created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    nudge_email_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    nudge_email_week_start: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # Relationships
    chats: Mapped[List["Chat"]] = relationship(
        "Chat", back_populates="user", cascade="all, delete-orphan"
    )
    messages: Mapped[List["Message"]] = relationship(
        "Message", back_populates="user", cascade="all, delete-orphan"
    )

    # Workspace relationships
    owned_workspaces: Mapped[List["Workspace"]] = relationship(
        "Workspace", back_populates="owner", cascade="all, delete-orphan"
    )
    workspace_memberships: Mapped[List["WorkspaceMember"]] = relationship(
        "WorkspaceMember", back_populates="user", cascade="all, delete-orphan"
    )

    # Developer API key relationships
    api_keys: Mapped[List["ApiKey"]] = relationship(
        "ApiKey", back_populates="user", cascade="all, delete-orphan"
    )

    # Webhook relationships
    webhooks: Mapped[List["Webhook"]] = relationship(
        "Webhook", back_populates="user", cascade="all, delete-orphan"
    )

    # Marketplace relationships
    marketplace_templates: Mapped[List["MarketplaceTemplate"]] = relationship(
        "MarketplaceTemplate", back_populates="creator", cascade="all, delete-orphan"
    )
    template_installs: Mapped[List["TemplateInstall"]] = relationship(
        "TemplateInstall", back_populates="user", cascade="all, delete-orphan"
    )
    template_ratings: Mapped[List["TemplateRating"]] = relationship(
        "TemplateRating", back_populates="user", cascade="all, delete-orphan"
    )

    # Token usage relationships
    token_usages: Mapped[List["TokenUsage"]] = relationship(
        "TokenUsage", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"
