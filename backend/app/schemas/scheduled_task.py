"""Pydantic schemas for scheduled tasks."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ScheduledTaskCreate(BaseModel):
    """Schema for creating a scheduled task."""
    
    name: str = Field(..., min_length=1, max_length=255, description="Task name")
    description: Optional[str] = Field(None, description="Task description")
    task_type: str = Field(
        ...,
        description="Type of task (research, docs, sheets, slides)"
    )
    prompt_template: str = Field(
        ...,
        min_length=1,
        description="Prompt template with variables like {date}, {weekday}, etc."
    )
    
    schedule_type: str = Field(
        ...,
        description="Schedule type (daily, weekly, monthly, cron)"
    )
    schedule_config: Dict[str, Any] = Field(
        ...,
        description="Schedule configuration (hour, minute, day_of_week, etc.)"
    )
    cron_expression: Optional[str] = Field(
        None,
        description="Cron expression for custom schedules"
    )
    
    is_active: bool = Field(True, description="Whether task is active")
    notify_on_completion: bool = Field(True, description="Send notification on completion")
    notification_email: Optional[str] = Field(None, description="Email for notifications")
    notification_channels: Optional[List[str]] = Field(
        None,
        description="Notification channels (email, slack, webhook)"
    )
    output_config: Optional[Dict[str, Any]] = Field(
        None,
        description="Output configuration (Drive folder, naming pattern, etc.)"
    )
    
    @field_validator("task_type")
    @classmethod
    def validate_task_type(cls, v: str) -> str:
        """Validate task type."""
        allowed_types = ["research", "docs", "sheets", "slides"]
        if v not in allowed_types:
            raise ValueError(f"task_type must be one of: {', '.join(allowed_types)}")
        return v
    
    @field_validator("schedule_type")
    @classmethod
    def validate_schedule_type(cls, v: str) -> str:
        """Validate schedule type."""
        allowed_types = ["daily", "weekly", "monthly", "cron"]
        if v not in allowed_types:
            raise ValueError(f"schedule_type must be one of: {', '.join(allowed_types)}")
        return v


class ScheduledTaskUpdate(BaseModel):
    """Schema for updating a scheduled task."""
    
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    task_type: Optional[str] = None
    prompt_template: Optional[str] = Field(None, min_length=1)
    
    schedule_type: Optional[str] = None
    schedule_config: Optional[Dict[str, Any]] = None
    cron_expression: Optional[str] = None
    
    is_active: Optional[bool] = None
    notify_on_completion: Optional[bool] = None
    notification_email: Optional[str] = None
    notification_channels: Optional[List[str]] = None
    output_config: Optional[Dict[str, Any]] = None


class ScheduledTaskResponse(BaseModel):
    """Schema for scheduled task response."""
    
    id: UUID
    user_id: UUID
    
    name: str
    description: Optional[str]
    task_type: str
    prompt_template: str
    
    schedule_type: str
    schedule_config: Dict[str, Any]
    cron_expression: Optional[str]
    
    is_active: bool
    last_run_at: Optional[datetime]
    next_run_at: Optional[datetime]
    run_count: int
    
    notify_on_completion: bool
    notification_email: Optional[str]
    notification_channels: Optional[List[str]]
    
    output_config: Optional[Dict[str, Any]]
    
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}


class ScheduledTaskExecutionResponse(BaseModel):
    """Schema for scheduled task execution response."""
    
    id: UUID
    scheduled_task_id: UUID
    task_id: Optional[UUID]
    
    started_at: datetime
    completed_at: Optional[datetime]
    status: str
    
    success: bool
    error_message: Optional[str]
    output_data: Optional[Dict[str, Any]]
    
    model_config = {"from_attributes": True}


__all__ = [
    "ScheduledTaskCreate",
    "ScheduledTaskUpdate",
    "ScheduledTaskResponse",
    "ScheduledTaskExecutionResponse",
]
