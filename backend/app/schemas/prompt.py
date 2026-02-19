"""Shared Prompt Library schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SharedPromptCreate(BaseModel):
    """Schema for creating a shared prompt."""

    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)
    is_public: bool = False


class SharedPromptResponse(BaseModel):
    """Public response schema for a shared prompt."""

    id: UUID
    user_id: UUID
    title: str
    content: str
    is_public: bool
    use_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SharedPromptList(BaseModel):
    """Paginated list of shared prompts."""

    prompts: list[SharedPromptResponse]
    total: int
    page: int
    page_size: int
