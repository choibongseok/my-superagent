"""Chat model."""

from typing import TYPE_CHECKING, List
from uuid import UUID, uuid4
from sqlalchemy import String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.message import Message


class Chat(Base, TimestampMixin):
    """Chat conversation model."""

    __tablename__ = "chats"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="chats")
    messages: Mapped[List["Message"]] = relationship(
        "Message", back_populates="chat", cascade="all, delete-orphan", order_by="Message.created_at"
    )

    def __repr__(self) -> str:
        return f"<Chat(id={self.id}, title={self.title!r})>"
