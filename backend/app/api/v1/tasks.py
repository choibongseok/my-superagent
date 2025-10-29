"""Task management endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.task import Task as TaskModel
from app.models.task import TaskStatus
from app.models.user import User
from app.schemas.task import Task, TaskCreate, TaskList

router = APIRouter()


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
    task = TaskModel(
        user_id=current_user.id,
        prompt=task_data.prompt,
        task_type=task_data.task_type,
        status=TaskStatus.PENDING,
        metadata=task_data.metadata,
    )
    
    db.add(task)
    await db.commit()
    await db.refresh(task)
    
    # TODO: Queue task to Celery
    # from app.agents.tasks import process_task
    # celery_task = process_task.apply_async(args=[str(task.id)])
    # task.celery_task_id = celery_task.id
    # await db.commit()
    
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
    
    # TODO: Cancel Celery task
    # if task.celery_task_id:
    #     from app.agents.celery_app import celery_app
    #     celery_app.control.revoke(task.celery_task_id, terminate=True)
