"""Shared Prompt Library model."""

from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class SharedPrompt(Base, TimestampMixin):
    """User-created prompts that can be shared publicly."""

    __tablename__ = "shared_prompts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    use_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index("ix_shared_prompts_is_public_created", "is_public", "created_at"),
        Index("ix_shared_prompts_user_id_created", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<SharedPrompt(id={self.id}, title={self.title!r}, public={self.is_public})>"
