"""Chat model."""

from typing import TYPE_CHECKING, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.message import Message


class Chat(Base, TimestampMixin):
    """Chat conversation model."""

    __tablename__ = "chats"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    workspace_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="chats")
    messages: Mapped[List["Message"]] = relationship(
        "Message",
        back_populates="chat",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )

    # Composite indexes
    __table_args__ = (
        Index("ix_chats_workspace_id", "workspace_id"),
        Index("ix_chats_workspace_user", "workspace_id", "user_id"),
    )

    def __repr__(self) -> str:
        return f"<Chat(id={self.id}, title={self.title!r})>"
