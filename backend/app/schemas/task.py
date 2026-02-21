"""Task schemas."""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.task import TaskStatus, TaskType


class TaskCreate(BaseModel):
    """Task creation schema."""

    prompt: str = Field(..., min_length=1, max_length=5000)
    task_type: TaskType
    metadata: Optional[Dict[str, Any]] = None


class TaskUpdate(BaseModel):
    """Task update schema."""

    status: Optional[TaskStatus] = None
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    document_url: Optional[str] = None
    document_id: Optional[str] = None


class TaskInDB(BaseModel):
    """Task schema with database fields."""

    id: UUID
    user_id: UUID
    prompt: str
    task_type: TaskType
    status: TaskStatus
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    document_url: Optional[str] = None
    document_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        validation_alias="task_metadata",
    )
    celery_task_id: Optional[str] = None
    share_token: Optional[UUID] = None
    expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ShareLinkResponse(BaseModel):
    """Response for POST /tasks/{id}/share."""

    task_id: UUID
    share_token: UUID
    share_url: str
    expires_at: datetime


class Task(TaskInDB):
    """Public task schema."""

    pass


class TaskList(BaseModel):
    """Task list response schema."""

    tasks: list[Task]
    total: int
    page: int
    page_size: int


# ── Interactive Task Preview (#234) ──────────────────────────────────


class TaskPreviewRequest(BaseModel):
    """Request schema for generating a task preview."""

    prompt: str = Field(..., min_length=1, max_length=5000)
    task_type: TaskType
    metadata: Optional[Dict[str, Any]] = None
    smart: bool = Field(
        default=False,
        description="Use LLM to generate contextual step descriptions instead of heuristic templates.",
    )


class TaskPreviewStep(BaseModel):
    """A single step in the execution preview."""

    order: int
    description: str
    agent_type: str
    detail: str = ""


class TaskPreviewModifyRequest(BaseModel):
    """Request to modify the prompt of an existing preview and regenerate."""

    prompt: str = Field(..., min_length=1, max_length=5000)
    smart: bool = Field(default=False)


class TaskPreviewResponse(BaseModel):
    """Response schema for task preview."""

    preview_id: str
    prompt: str
    task_type: str
    steps: list[TaskPreviewStep]
    output_format: str
    estimated_time_seconds: int
    estimated_cost_usd: float
    estimated_tokens: int
    notes: list[str] = Field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = None
    smart: bool = Field(default=False, description="Whether LLM was used for this preview.")
    original_prompt: Optional[str] = Field(
        default=None,
        description="If this preview was modified, the original prompt before modification.",
    )
