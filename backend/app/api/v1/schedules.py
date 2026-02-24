"""Recurring Task Scheduler API — Idea #221.

Endpoints:
  POST   /tasks/{task_id}/schedule   → create recurring schedule from completed task
  GET    /schedules                   → list user's scheduled tasks
  GET    /schedules/{id}              → get schedule details
  PATCH  /schedules/{id}              → update schedule (name, active, timing)
  DELETE /schedules/{id}              → remove schedule
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional
from uuid import UUID

from croniter import croniter
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.scheduled_task import ScheduleType, ScheduledTask
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.schemas.schedule import (
    ScheduleCreate,
    ScheduleListResponse,
    ScheduleResponse,
    ScheduleUpdate,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_next_run(
    schedule_type: ScheduleType,
    anchor: datetime,
    cron_expr: str | None,
    tz_name: str = "UTC",
) -> datetime:
    """Compute the next run time from an anchor datetime.

    For daily/weekly/monthly we project from the anchor; for cron we use
    croniter to find the next occurrence after *now*.
    """
    now = datetime.now(tz=timezone.utc)

    if schedule_type == ScheduleType.ONCE:
        return anchor

    if schedule_type == ScheduleType.CRON:
        if not cron_expr:
            raise ValueError("cron_expression required for CRON schedule")
        cron = croniter(cron_expr, now)
        return cron.get_next(datetime).replace(tzinfo=timezone.utc)

    # For daily/weekly/monthly: start from anchor, advance until > now
    candidate = anchor if anchor.tzinfo else anchor.replace(tzinfo=timezone.utc)

    delta_map = {
        ScheduleType.DAILY: timedelta(days=1),
        ScheduleType.WEEKLY: timedelta(weeks=1),
        ScheduleType.MONTHLY: timedelta(days=30),  # approximate; good enough
    }
    delta = delta_map[schedule_type]

    while candidate <= now:
        candidate += delta

    return candidate


async def _get_schedule_or_404(
    schedule_id: UUID,
    user: User,
    db: AsyncSession,
) -> ScheduledTask:
    result = await db.execute(
        select(ScheduledTask).where(
            ScheduledTask.id == schedule_id,
            ScheduledTask.user_id == user.id,
        )
    )
    sched = result.scalar_one_or_none()
    if not sched:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    return sched


# ---------------------------------------------------------------------------
# POST /tasks/{task_id}/schedule — create a schedule from an existing task
# ---------------------------------------------------------------------------

@router.post(
    "/tasks/{task_id}/schedule",
    response_model=ScheduleResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["schedules"],
    summary="Create recurring schedule from a task (#221)",
)
async def create_schedule(
    task_id: UUID,
    body: ScheduleCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Schedule a completed task to re-run on a recurring basis.

    The task's prompt and type are cloned into the schedule definition.
    """
    # Look up original task
    result = await db.execute(
        select(Task).where(Task.id == task_id, Task.user_id == current_user.id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    if task.status != TaskStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only completed tasks can be scheduled for recurring execution",
        )

    # Validate cron expression
    if body.schedule_type == ScheduleType.CRON:
        if not body.cron_expression:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="cron_expression is required for cron schedule type",
            )
        if not croniter.is_valid(body.cron_expression):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"cron_expression is invalid: {body.cron_expression}",
            )

    next_run = _compute_next_run(
        body.schedule_type, body.scheduled_at, body.cron_expression, body.timezone
    )

    sched = ScheduledTask(
        user_id=current_user.id,
        name=body.name,
        prompt=task.prompt,
        task_type=task.task_type,
        task_metadata={"source_task_id": str(task_id)},
        schedule_type=body.schedule_type,
        scheduled_at=body.scheduled_at if body.scheduled_at.tzinfo else body.scheduled_at.replace(tzinfo=timezone.utc),
        cron_expression=body.cron_expression,
        timezone=body.timezone,
        next_run_at=next_run,
        max_runs=body.max_runs,
    )

    db.add(sched)
    await db.commit()
    await db.refresh(sched)

    return ScheduleResponse.model_validate(sched)


# ---------------------------------------------------------------------------
# GET /schedules — list schedules
# ---------------------------------------------------------------------------

@router.get(
    "/schedules",
    response_model=ScheduleListResponse,
    tags=["schedules"],
    summary="List user's recurring schedules",
)
async def list_schedules(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    active_only: bool = Query(True, description="Show only active schedules"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Return paginated list of the user's scheduled tasks."""
    filters = [ScheduledTask.user_id == current_user.id]
    if active_only:
        filters.append(ScheduledTask.is_active == True)  # noqa: E712

    # Total count
    count_q = select(func.count()).select_from(ScheduledTask).where(*filters)
    total = (await db.execute(count_q)).scalar_one()

    # Fetch page
    offset = (page - 1) * page_size
    rows = (
        await db.execute(
            select(ScheduledTask)
            .where(*filters)
            .order_by(ScheduledTask.next_run_at.asc().nullslast())
            .offset(offset)
            .limit(page_size)
        )
    ).scalars().all()

    return ScheduleListResponse(
        schedules=[ScheduleResponse.model_validate(r) for r in rows],
        total=total,
    )


# ---------------------------------------------------------------------------
# GET /schedules/{id} — details
# ---------------------------------------------------------------------------

@router.get(
    "/schedules/{schedule_id}",
    response_model=ScheduleResponse,
    tags=["schedules"],
)
async def get_schedule(
    schedule_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    sched = await _get_schedule_or_404(schedule_id, current_user, db)
    return ScheduleResponse.model_validate(sched)


# ---------------------------------------------------------------------------
# PATCH /schedules/{id} — update
# ---------------------------------------------------------------------------

@router.patch(
    "/schedules/{schedule_id}",
    response_model=ScheduleResponse,
    tags=["schedules"],
)
async def update_schedule(
    schedule_id: UUID,
    body: ScheduleUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    sched = await _get_schedule_or_404(schedule_id, current_user, db)

    if body.name is not None:
        sched.name = body.name
    if body.is_active is not None:
        sched.is_active = body.is_active
    if body.schedule_type is not None:
        sched.schedule_type = body.schedule_type
    if body.scheduled_at is not None:
        sched.scheduled_at = body.scheduled_at if body.scheduled_at.tzinfo else body.scheduled_at.replace(tzinfo=timezone.utc)
    if body.cron_expression is not None:
        if not croniter.is_valid(body.cron_expression):
            raise HTTPException(status_code=400, detail=f"cron_expression is invalid: {body.cron_expression}")
        sched.cron_expression = body.cron_expression
    if body.timezone is not None:
        sched.timezone = body.timezone
    if body.max_runs is not None:
        sched.max_runs = body.max_runs

    # Recompute next_run
    sched.next_run_at = _compute_next_run(
        sched.schedule_type, sched.scheduled_at,
        sched.cron_expression, sched.timezone,
    )

    await db.commit()
    await db.refresh(sched)

    return ScheduleResponse.model_validate(sched)


# ---------------------------------------------------------------------------
# DELETE /schedules/{id}
# ---------------------------------------------------------------------------

@router.delete(
    "/schedules/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["schedules"],
)
async def delete_schedule(
    schedule_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    sched = await _get_schedule_or_404(schedule_id, current_user, db)
    await db.delete(sched)
    await db.commit()
