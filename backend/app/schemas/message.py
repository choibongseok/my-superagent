"""Message schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field

from app.models.message import MessageRole


class MessageBase(BaseModel):
    """Base message schema."""

    content: str = Field(..., min_length=1)
    role: MessageRole = MessageRole.USER


class MessageCreate(MessageBase):
    """Message creation schema."""

    chat_id: UUID


class MessageUpdate(BaseModel):
    """Message update schema."""

    content: Optional[str] = Field(None, min_length=1)


class MessageResponse(MessageBase):
    """Message response schema."""

    id: UUID
    chat_id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MessageListResponse(BaseModel):
    """Message list response schema."""

    messages: list[MessageResponse]
    total: int
