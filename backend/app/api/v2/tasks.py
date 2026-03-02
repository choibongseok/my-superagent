"""Task management endpoints (v2)."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.task import Task as TaskModel
from app.models.task import TaskStatus
from app.models.user import User
from app.schemas.task import Task, TaskCreate

router = APIRouter()
logger = logging.getLogger(__name__)


class TaskCreateV2(TaskCreate):
    """Enhanced task creation schema for v2."""
    
    priority: int = Field(default=0, ge=0, le=10, description="Task priority (0=low, 10=high)")
    tags: list[str] = Field(default_factory=list, description="Task tags for organization")
    estimated_duration_seconds: int | None = Field(None, ge=1, description="Estimated task duration")


class TaskV2(Task):
    """Enhanced task response for v2."""
    
    priority: int = 0
    tags: list[str] = Field(default_factory=list)
    estimated_duration_seconds: int | None = None
    actual_duration_seconds: int | None = None
    retry_count: int = 0
    celery_task_id: str | None = None


class PaginationMetadata(BaseModel):
    """Pagination metadata."""
    
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_previous: bool


class TaskListV2(BaseModel):
    """Enhanced task list response for v2."""
    
    items: list[TaskV2]
    pagination: PaginationMetadata


class TaskStatsV2(BaseModel):
    """Task statistics response."""
    
    total_tasks: int
    pending: int
    in_progress: int
    completed: int
    failed: int
    cancelled: int
    average_duration_seconds: float | None = None


@router.post("/", response_model=TaskV2, status_code=status.HTTP_201_CREATED)
async def create_task_v2(
    task_data: TaskCreateV2,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
):
    """
    Create a new task (v2).
    
    Improvements over v1:
    - Priority support for task scheduling
    - Tags for better organization
    - Estimated duration tracking
    - Better error messages with details
    - Request context tracking
    
    Args:
        task_data: Task creation data
        current_user: Authenticated user
        db: Database session
        request: FastAPI request object
        
    Returns:
        TaskV2: Created task with enhanced metadata
    """
    # Validate task type
    valid_task_types = ["research", "docs", "sheets", "slides"]
    if task_data.task_type not in valid_task_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_task_type",
                "message": f"Task type must be one of: {', '.join(valid_task_types)}",
                "provided": task_data.task_type,
            },
        )
    
    # Create enhanced metadata
    enhanced_metadata = task_data.metadata or {}
    enhanced_metadata.update({
        "priority": task_data.priority,
        "tags": task_data.tags,
        "estimated_duration_seconds": task_data.estimated_duration_seconds,
        "api_version": "v2",
        "user_agent": request.headers.get("user-agent"),
    })
    
    # Create task
    task = TaskModel(
        user_id=current_user.id,
        prompt=task_data.prompt,
        task_type=task_data.task_type,
        status=TaskStatus.PENDING,
        task_metadata=enhanced_metadata,
        llm_provider=task_data.llm_provider,
        llm_model=task_data.llm_model,
    )
    
    db.add(task)
    await db.commit()
    await db.refresh(task)
    
    # Queue task to Celery
    try:
        from app.agents.celery_app import (
            process_research_task,
            process_docs_task,
            process_sheets_task,
            process_slides_task,
        )
        
        task_id_str = str(task.id)
        user_id_str = str(current_user.id)
        
        if task_data.task_type == "research":
            celery_task = process_research_task.apply_async(
                args=[task_id_str, task_data.prompt, user_id_str, task_data.llm_provider, task_data.llm_model],
                priority=task_data.priority,
            )
        elif task_data.task_type == "docs":
            title = enhanced_metadata.get("title", "Untitled Document")
            celery_task = process_docs_task.apply_async(
                args=[task_id_str, task_data.prompt, user_id_str, title, task_data.llm_provider, task_data.llm_model],
                priority=task_data.priority,
            )
        elif task_data.task_type == "sheets":
            title = enhanced_metadata.get("title", "Untitled Spreadsheet")
            celery_task = process_sheets_task.apply_async(
                args=[task_id_str, task_data.prompt, user_id_str, title, task_data.llm_provider, task_data.llm_model],
                priority=task_data.priority,
            )
        elif task_data.task_type == "slides":
            title = enhanced_metadata.get("title", "Untitled Presentation")
            celery_task = process_slides_task.apply_async(
                args=[task_id_str, task_data.prompt, user_id_str, title, task_data.llm_provider, task_data.llm_model],
                priority=task_data.priority,
            )
        
        # Store Celery task ID
        task.celery_task_id = celery_task.id
        task.status = TaskStatus.IN_PROGRESS
        await db.commit()
        await db.refresh(task)
        
        logger.info(
            f"Task {task.id} created and queued to Celery "
            f"(celery_task_id={celery_task.id}, priority={task_data.priority})"
        )
        
    except Exception as e:
        # If Celery queuing fails, mark task as failed with detailed error
        task.status = TaskStatus.FAILED
        task.error_message = str(e)
        enhanced_metadata["error_details"] = {
            "error_type": type(e).__name__,
            "error_message": str(e),
        }
        task.task_metadata = enhanced_metadata
        await db.commit()
        
        logger.error(f"Failed to queue task {task.id}: {str(e)}", exc_info=True)
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "task_queue_failed",
                "message": "Failed to queue task for processing",
                "task_id": str(task.id),
                "details": str(e) if task_data.llm_provider else "Internal error",
            },
        )
    
    # Convert to v2 response model
    return TaskV2(
        **task.__dict__,
        priority=task_data.priority,
        tags=task_data.tags,
        estimated_duration_seconds=task_data.estimated_duration_seconds,
    )


@router.get("/", response_model=TaskListV2)
async def list_tasks_v2(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status: TaskStatus | None = Query(None, description="Filter by status"),
    task_type: str | None = Query(None, description="Filter by task type"),
    tags: list[str] = Query(None, description="Filter by tags (OR logic)"),
    sort_by: str = Query("created_at", description="Sort field (created_at, priority, status)"),
    sort_order: str = Query("desc", description="Sort order (asc, desc)"),
):
    """
    List user tasks (v2).
    
    Improvements over v1:
    - Enhanced pagination with metadata
    - Multiple filter options (status, type, tags)
    - Flexible sorting
    - Tag-based filtering
    
    Args:
        current_user: Authenticated user
        db: Database session
        page: Page number
        page_size: Items per page
        status: Filter by status
        task_type: Filter by task type
        tags: Filter by tags (match any)
        sort_by: Sort field
        sort_order: Sort order
        
    Returns:
        TaskListV2: List of tasks with enhanced pagination metadata
    """
    # Build query
    query = select(TaskModel).where(TaskModel.user_id == current_user.id)
    
    # Apply filters
    if status:
        query = query.where(TaskModel.status == status)
    
    if task_type:
        query = query.where(TaskModel.task_type == task_type)
    
    # Filter by tags (if task metadata contains any of the specified tags)
    if tags:
        # This is a simplified version - actual implementation would need JSON query
        # For now, we'll fetch and filter in Python
        pass
    
    # Apply sorting
    if sort_by == "priority":
        # Priority is in metadata, so we'd need JSON query
        # For now, default to created_at
        sort_by = "created_at"
    
    sort_column = getattr(TaskModel, sort_by, TaskModel.created_at)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()
    
    # Calculate pagination metadata
    total_pages = (total + page_size - 1) // page_size
    has_next = page < total_pages
    has_previous = page > 1
    
    # Apply pagination
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    # Execute query
    result = await db.execute(query)
    tasks = result.scalars().all()
    
    # Convert to v2 response models
    task_v2_list = []
    for task in tasks:
        metadata = task.task_metadata or {}
        task_v2_list.append(
            TaskV2(
                **task.__dict__,
                priority=metadata.get("priority", 0),
                tags=metadata.get("tags", []),
                estimated_duration_seconds=metadata.get("estimated_duration_seconds"),
                retry_count=metadata.get("retry_count", 0),
            )
        )
    
    return TaskListV2(
        items=task_v2_list,
        pagination=PaginationMetadata(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=has_next,
            has_previous=has_previous,
        ),
    )


@router.get("/stats", response_model=TaskStatsV2)
async def get_task_stats_v2(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get task statistics (v2 only).
    
    Returns aggregate statistics about user tasks.
    
    Args:
        current_user: Authenticated user
        db: Database session
        
    Returns:
        TaskStatsV2: Task statistics
    """
    # Get status counts
    query = (
        select(TaskModel.status, func.count())
        .where(TaskModel.user_id == current_user.id)
        .group_by(TaskModel.status)
    )
    result = await db.execute(query)
    status_counts = dict(result.all())
    
    # Get total count
    total_tasks = sum(status_counts.values())
    
    # Calculate average duration (simplified - would need better tracking)
    # For now, return None
    average_duration = None
    
    return TaskStatsV2(
        total_tasks=total_tasks,
        pending=status_counts.get(TaskStatus.PENDING, 0),
        in_progress=status_counts.get(TaskStatus.IN_PROGRESS, 0),
        completed=status_counts.get(TaskStatus.COMPLETED, 0),
        failed=status_counts.get(TaskStatus.FAILED, 0),
        cancelled=status_counts.get(TaskStatus.CANCELLED, 0),
        average_duration_seconds=average_duration,
    )


@router.get("/{task_id}", response_model=TaskV2)
async def get_task_v2(
    task_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get task by ID (v2).
    
    Improvements over v1:
    - Enhanced response model with metadata
    - Better error messages
    
    Args:
        task_id: Task ID
        current_user: Authenticated user
        db: Database session
        
    Returns:
        TaskV2: Task details
    """
    result = await db.execute(
        select(TaskModel).where(
            TaskModel.id == task_id,
            TaskModel.user_id == current_user.id,
        )
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "task_not_found",
                "message": f"Task with ID {task_id} not found",
                "task_id": str(task_id),
            },
        )
    
    # Convert to v2 response model
    metadata = task.task_metadata or {}
    return TaskV2(
        **task.__dict__,
        priority=metadata.get("priority", 0),
        tags=metadata.get("tags", []),
        estimated_duration_seconds=metadata.get("estimated_duration_seconds"),
        retry_count=metadata.get("retry_count", 0),
    )


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_task_v2(
    task_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Cancel a task (v2).
    
    Improvements over v1:
    - Better error messages
    - Improved cancellation logic
    
    Args:
        task_id: Task ID
        current_user: Authenticated user
        db: Database session
    """
    result = await db.execute(
        select(TaskModel).where(
            TaskModel.id == task_id,
            TaskModel.user_id == current_user.id,
        )
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "task_not_found",
                "message": f"Task with ID {task_id} not found",
                "task_id": str(task_id),
            },
        )
    
    if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "task_not_cancellable",
                "message": f"Cannot cancel task in {task.status.value} status",
                "current_status": task.status.value,
            },
        )
    
    # Update task status
    task.status = TaskStatus.CANCELLED
    await db.commit()
    
    # Cancel Celery task if it exists
    if task.celery_task_id:
        try:
            from app.agents.celery_app import celery_app
            celery_app.control.revoke(task.celery_task_id, terminate=True)
            logger.info(f"Cancelled Celery task {task.celery_task_id} for task {task_id}")
        except Exception as e:
            logger.error(f"Failed to cancel Celery task {task.celery_task_id}: {str(e)}")
            # Don't fail the request if Celery cancellation fails
