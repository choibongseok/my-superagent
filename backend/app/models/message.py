"""Message model."""

from typing import TYPE_CHECKING
from uuid import UUID, uuid4
import enum

from sqlalchemy import Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.chat import Chat
    from app.models.user import User


class MessageRole(str, enum.Enum):
    """Message role enum."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Message(Base, TimestampMixin):
    """Chat message model."""

    __tablename__ = "messages"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    chat_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("chats.id"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    role: Mapped[MessageRole] = mapped_column(
        SQLEnum(MessageRole, name="message_role"), nullable=False, default=MessageRole.USER
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    chat: Mapped["Chat"] = relationship("Chat", back_populates="messages")
    user: Mapped["User"] = relationship("User", back_populates="messages")

    def __repr__(self) -> str:
        return f"<Message(id={self.id}, role={self.role}, chat_id={self.chat_id})>"
