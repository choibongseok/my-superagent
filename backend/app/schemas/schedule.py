"""Schemas for Recurring Task Scheduler (#221)."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.scheduled_task import ScheduleType
from app.models.task import TaskType


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class ScheduleCreate(BaseModel):
    """Create a recurring schedule for an existing task's prompt."""

    name: str = Field(
        ..., min_length=1, max_length=255,
        description="Human-readable name (e.g. 'Weekly standup report')"
    )
    schedule_type: ScheduleType = Field(
        ..., description="Recurrence type: once, daily, weekly, monthly, cron"
    )
    scheduled_at: datetime = Field(
        ..., description="Anchor time: hour/minute used for recurring schedules"
    )
    cron_expression: Optional[str] = Field(
        None, max_length=100,
        description="Cron expression (required when schedule_type='cron')"
    )
    timezone: str = Field("UTC", max_length=50)
    max_runs: Optional[int] = Field(
        None, ge=1, description="Stop after N runs (null = unlimited)"
    )

    @field_validator("cron_expression")
    @classmethod
    def cron_required_for_cron_type(cls, v, info):
        if info.data.get("schedule_type") == ScheduleType.CRON and not v:
            raise ValueError("cron_expression is required when schedule_type is 'cron'")
        return v


class ScheduleUpdate(BaseModel):
    """Partial update for a scheduled task."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    is_active: Optional[bool] = None
    scheduled_at: Optional[datetime] = None
    schedule_type: Optional[ScheduleType] = None
    cron_expression: Optional[str] = Field(None, max_length=100)
    timezone: Optional[str] = Field(None, max_length=50)
    max_runs: Optional[int] = Field(None, ge=1)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class ScheduleResponse(BaseModel):
    """Scheduled task response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    name: str
    prompt: str
    task_type: TaskType
    schedule_type: ScheduleType
    scheduled_at: datetime
    cron_expression: Optional[str] = None
    timezone: str
    is_active: bool
    next_run_at: Optional[datetime] = None
    last_run_at: Optional[datetime] = None
    last_task_id: Optional[UUID] = None
    run_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    last_error: Optional[str] = None
    max_runs: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class ScheduleListResponse(BaseModel):
    """Paginated list of scheduled tasks."""

    schedules: list[ScheduleResponse]
    total: int
