"""API endpoints for scheduled tasks."""

import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.scheduled_task import ScheduledTask, ScheduledTaskExecution
from app.models.user import User
from app.schemas.scheduled_task import (
    ScheduledTaskCreate,
    ScheduledTaskResponse,
    ScheduledTaskUpdate,
    ScheduledTaskExecutionResponse,
)
from app.services.scheduled_task_executor import ScheduledTaskExecutor

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/", response_model=ScheduledTaskResponse, status_code=status.HTTP_201_CREATED)
async def create_scheduled_task(
    task_data: ScheduledTaskCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new scheduled task.
    
    Schedule types:
    - daily: Run at specific time every day
      ```json
      {"hour": 9, "minute": 0}
      ```
    - weekly: Run at specific time on specific day of week (0=Monday, 6=Sunday)
      ```json
      {"day_of_week": 1, "hour": 10, "minute": 0}
      ```
    - monthly: Run on specific day of month at specific time
      ```json
      {"day_of_month": 1, "hour": 9, "minute": 0}
      ```
    - cron: Custom cron expression
      ```json
      {"cron_expression": "0 9 * * 1-5"}  // Weekdays at 9 AM
      ```
    """
    logger.info(f"Creating scheduled task: {task_data.name} for user {current_user.id}")
    
    # Calculate first run time
    next_run_at = ScheduledTaskExecutor.calculate_next_run(
        schedule_type=task_data.schedule_type,
        schedule_config=task_data.schedule_config,
        cron_expression=task_data.cron_expression,
    )
    
    # Create scheduled task
    scheduled_task = ScheduledTask(
        user_id=current_user.id,
        name=task_data.name,
        description=task_data.description,
        task_type=task_data.task_type,
        prompt_template=task_data.prompt_template,
        schedule_type=task_data.schedule_type,
        schedule_config=task_data.schedule_config,
        cron_expression=task_data.cron_expression,
        is_active=task_data.is_active,
        next_run_at=next_run_at,
        notify_on_completion=task_data.notify_on_completion,
        notification_email=task_data.notification_email,
        notification_channels=task_data.notification_channels,
        output_config=task_data.output_config,
    )
    
    db.add(scheduled_task)
    await db.commit()
    await db.refresh(scheduled_task)
    
    logger.info(
        f"Scheduled task created: {scheduled_task.id} "
        f"(next run: {next_run_at.isoformat()})"
    )
    
    return scheduled_task


@router.get("/", response_model=List[ScheduledTaskResponse])
async def list_scheduled_tasks(
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List scheduled tasks for current user.
    
    Args:
        is_active: Filter by active status (optional)
        limit: Maximum number of results
        offset: Number of results to skip
    """
    query = select(ScheduledTask).where(
        ScheduledTask.user_id == current_user.id
    ).order_by(desc(ScheduledTask.created_at))
    
    if is_active is not None:
        query = query.where(ScheduledTask.is_active == is_active)
    
    query = query.offset(offset).limit(limit)
    
    result = await db.execute(query)
    tasks = list(result.scalars().all())
    
    return tasks


@router.get("/{task_id}", response_model=ScheduledTaskResponse)
async def get_scheduled_task(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific scheduled task by ID."""
    query = select(ScheduledTask).where(
        ScheduledTask.id == task_id,
        ScheduledTask.user_id == current_user.id
    )
    
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scheduled task not found"
        )
    
    return task


@router.patch("/{task_id}", response_model=ScheduledTaskResponse)
async def update_scheduled_task(
    task_id: UUID,
    task_update: ScheduledTaskUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update a scheduled task.
    
    If schedule configuration changes, next_run_at will be recalculated.
    """
    query = select(ScheduledTask).where(
        ScheduledTask.id == task_id,
        ScheduledTask.user_id == current_user.id
    )
    
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scheduled task not found"
        )
    
    # Track if schedule changed
    schedule_changed = False
    
    # Update fields
    update_data = task_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field in ["schedule_type", "schedule_config", "cron_expression"]:
            schedule_changed = True
        setattr(task, field, value)
    
    # Recalculate next run if schedule changed
    if schedule_changed:
        task.next_run_at = ScheduledTaskExecutor.calculate_next_run(
            schedule_type=task.schedule_type,
            schedule_config=task.schedule_config,
            cron_expression=task.cron_expression,
            from_time=datetime.utcnow()
        )
        logger.info(f"Schedule changed, next run: {task.next_run_at.isoformat()}")
    
    task.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(task)
    
    logger.info(f"Scheduled task updated: {task.id}")
    
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scheduled_task(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a scheduled task and all its execution history."""
    query = select(ScheduledTask).where(
        ScheduledTask.id == task_id,
        ScheduledTask.user_id == current_user.id
    )
    
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scheduled task not found"
        )
    
    await db.delete(task)
    await db.commit()
    
    logger.info(f"Scheduled task deleted: {task_id}")


@router.post("/{task_id}/pause", response_model=ScheduledTaskResponse)
async def pause_scheduled_task(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Pause a scheduled task (set is_active=False)."""
    query = select(ScheduledTask).where(
        ScheduledTask.id == task_id,
        ScheduledTask.user_id == current_user.id
    )
    
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scheduled task not found"
        )
    
    task.is_active = False
    task.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(task)
    
    logger.info(f"Scheduled task paused: {task_id}")
    
    return task


@router.post("/{task_id}/resume", response_model=ScheduledTaskResponse)
async def resume_scheduled_task(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Resume a paused scheduled task (set is_active=True)."""
    query = select(ScheduledTask).where(
        ScheduledTask.id == task_id,
        ScheduledTask.user_id == current_user.id
    )
    
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scheduled task not found"
        )
    
    task.is_active = True
    task.updated_at = datetime.utcnow()
    
    # Recalculate next run (in case it was in the past)
    task.next_run_at = ScheduledTaskExecutor.calculate_next_run(
        schedule_type=task.schedule_type,
        schedule_config=task.schedule_config,
        cron_expression=task.cron_expression,
        from_time=datetime.utcnow()
    )
    
    await db.commit()
    await db.refresh(task)
    
    logger.info(f"Scheduled task resumed: {task_id} (next run: {task.next_run_at.isoformat()})")
    
    return task


@router.get("/{task_id}/executions", response_model=List[ScheduledTaskExecutionResponse])
async def list_task_executions(
    task_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List execution history for a scheduled task."""
    # Verify task ownership
    task_query = select(ScheduledTask).where(
        ScheduledTask.id == task_id,
        ScheduledTask.user_id == current_user.id
    )
    result = await db.execute(task_query)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scheduled task not found"
        )
    
    # Get executions
    exec_query = select(ScheduledTaskExecution).where(
        ScheduledTaskExecution.scheduled_task_id == task_id
    ).order_by(desc(ScheduledTaskExecution.started_at)).offset(offset).limit(limit)
    
    result = await db.execute(exec_query)
    executions = list(result.scalars().all())
    
    return executions


__all__ = ["router"]
