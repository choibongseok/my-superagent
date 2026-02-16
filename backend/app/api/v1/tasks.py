"""Task management endpoints."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.task import Task as TaskModel
from app.models.task import TaskStatus, TaskType
from app.models.user import User
from app.schemas.task import Task, TaskCreate, TaskList

router = APIRouter()
logger = logging.getLogger(__name__)

TASK_TITLE_DEFAULTS = {
    "docs": "Untitled Document",
    "sheets": "Untitled Spreadsheet",
    "slides": "Untitled Presentation",
}

TASK_TITLE_METADATA_KEYS = {
    "docs": ("title", "document_title"),
    "sheets": ("title", "sheet_title", "spreadsheet_title"),
    "slides": ("title", "deck_title", "presentation_title"),
}


def _build_task_kwargs(
    *,
    user_id: UUID,
    prompt: str,
    task_type: TaskType | str,
    metadata: dict | None,
) -> dict:
    """Build Task model kwargs with explicit task metadata mapping."""
    return {
        "user_id": user_id,
        "prompt": prompt,
        "task_type": task_type,
        "status": TaskStatus.PENDING,
        "task_metadata": metadata,
    }


def _resolve_task_title(task_type: str, metadata: dict | None) -> str:
    """Resolve task title from metadata with sensible per-type fallbacks."""
    fallback = TASK_TITLE_DEFAULTS.get(task_type)
    if fallback is None:
        raise ValueError(f"No title default configured for task type: {task_type}")

    if not isinstance(metadata, dict):
        return fallback

    for key in TASK_TITLE_METADATA_KEYS.get(task_type, ("title",)):
        value = metadata.get(key)
        if isinstance(value, str):
            normalized_value = value.strip()
            if normalized_value:
                return normalized_value

    return fallback


@router.post("/", response_model=Task, status_code=status.HTTP_201_CREATED)
async def create_task(
    task_data: TaskCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Create a new task.
    
    Args:
        task_data: Task creation data
        current_user: Authenticated user
        db: Database session
        
    Returns:
        Task: Created task
    """
    # Create task
    task_kwargs = _build_task_kwargs(
        user_id=current_user.id,
        prompt=task_data.prompt,
        task_type=task_data.task_type,
        metadata=task_data.metadata,
    )
    task = TaskModel(**task_kwargs)
    
    db.add(task)
    await db.commit()
    await db.refresh(task)
    
    # Queue task to Celery based on task_type
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
                args=[task_id_str, task_data.prompt, user_id_str]
            )
        elif task_data.task_type == "docs":
            title = _resolve_task_title("docs", task_data.metadata)
            celery_task = process_docs_task.apply_async(
                args=[task_id_str, task_data.prompt, user_id_str, title]
            )
        elif task_data.task_type == "sheets":
            title = _resolve_task_title("sheets", task_data.metadata)
            celery_task = process_sheets_task.apply_async(
                args=[task_id_str, task_data.prompt, user_id_str, title]
            )
        elif task_data.task_type == "slides":
            title = _resolve_task_title("slides", task_data.metadata)
            celery_task = process_slides_task.apply_async(
                args=[task_id_str, task_data.prompt, user_id_str, title]
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown task type: {task_data.task_type}",
            )
        
        # Store Celery task ID
        task.celery_task_id = celery_task.id
        task.status = TaskStatus.IN_PROGRESS
        await db.commit()
        await db.refresh(task)
        
    except Exception as e:
        # If Celery queuing fails, mark task as failed
        task.status = TaskStatus.FAILED
        task.error_message = f"Failed to queue task: {str(e)}"
        await db.commit()
        logger.error(f"Failed to queue task {task.id}: {str(e)}")
    
    return task


@router.get("/", response_model=TaskList)
async def list_tasks(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: TaskStatus | None = None,
):
    """
    List user tasks.
    
    Args:
        current_user: Authenticated user
        db: Database session
        page: Page number
        page_size: Items per page
        status: Filter by status
        
    Returns:
        TaskList: List of tasks with pagination
    """
    # Build query
    query = select(TaskModel).where(TaskModel.user_id == current_user.id)
    
    if status:
        query = query.where(TaskModel.status == status)
    
    query = query.order_by(TaskModel.created_at.desc())
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()
    
    # Apply pagination
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    # Execute query
    result = await db.execute(query)
    tasks = result.scalars().all()
    
    return TaskList(
        tasks=tasks,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{task_id}", response_model=Task)
async def get_task(
    task_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get task by ID.
    
    Args:
        task_id: Task ID
        current_user: Authenticated user
        db: Database session
        
    Returns:
        Task: Task details
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
            detail="Task not found",
        )
    
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_task(
    task_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Cancel a task.
    
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
            detail="Task not found",
        )
    
    if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot cancel completed, failed, or already cancelled task",
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
