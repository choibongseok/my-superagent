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
    llm_provider: str = Field(default="openai", pattern="^(openai|anthropic)$")
    llm_model: str = Field(
        default="gpt-4-turbo-preview",
        description="Model name (e.g., gpt-4-turbo-preview, claude-3-opus-20240229)"
    )


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
    metadata: Optional[Dict[str, Any]] = None
    celery_task_id: Optional[str] = None
    llm_provider: str = "openai"
    llm_model: str = "gpt-4-turbo-preview"
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class Task(TaskInDB):
    """Public task schema."""

    pass


class TaskList(BaseModel):
    """Task list response schema."""

    tasks: list[Task]
    total: int
    page: int
    page_size: int
