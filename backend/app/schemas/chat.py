"""Chat schemas."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field

from app.schemas.message import MessageResponse


class ChatBase(BaseModel):
    """Base chat schema."""

    title: str = Field(..., min_length=1, max_length=255)


class ChatCreate(ChatBase):
    """Chat creation schema."""

    pass


class ChatUpdate(BaseModel):
    """Chat update schema."""

    title: Optional[str] = Field(None, min_length=1, max_length=255)


class ChatResponse(ChatBase):
    """Chat response schema."""

    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChatWithMessages(ChatResponse):
    """Chat with messages schema."""

    messages: List[MessageResponse] = []

    class Config:
        from_attributes = True


class ChatListResponse(BaseModel):
    """Chat list response schema."""

    chats: List[ChatResponse]
    total: int
