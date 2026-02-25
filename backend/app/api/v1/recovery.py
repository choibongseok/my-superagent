"""
Recovery API - Reliability Landing Page endpoints
"""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.api.dependencies import get_current_user
from app.models.user import User
from app.models.task import Task, TaskStatus
from app.models.recovery_suggestion import RecoverySuggestion
from app.services.recovery_suggestion_service import RecoverySuggestionService

router = APIRouter(prefix="/recovery", tags=["recovery"])


@router.get("/tasks/{task_id}/suggestions")
async def get_recovery_suggestions(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get recovery suggestions for a failed task.
    
    Returns 1-3 actionable suggestions to help the user recover from failure.
    """
    # Verify task exists and belongs to user
    result = await db.execute(
        select(Task).where(
            Task.id == task_id,
            Task.user_id == current_user.id
        )
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    
    # Get or generate suggestions
    service = RecoverySuggestionService(db)
    suggestions = await service.get_suggestions_for_task(task_id)
    
    # If no suggestions exist yet and task failed, generate them
    if not suggestions and task.status == TaskStatus.FAILED:
        suggestions = await service.generate_suggestions(task, current_user)
    
    return {
        "task_id": str(task_id),
        "task_status": task.status.value,
        "error_message": task.error_message,
        "suggestions": [s.to_dict() for s in suggestions]
    }


@router.post("/suggestions/{suggestion_id}/select")
async def select_recovery_suggestion(
    suggestion_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Mark a recovery suggestion as selected by the user.
    
    This helps track which recovery strategies are most effective.
    """
    # Verify suggestion exists and belongs to user's task
    result = await db.execute(
        select(RecoverySuggestion).where(RecoverySuggestion.id == suggestion_id)
    )
    suggestion = result.scalar_one_or_none()
    
    if not suggestion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Suggestion not found"
        )
    
    # Verify task belongs to user
    result = await db.execute(
        select(Task).where(
            Task.id == suggestion.task_id,
            Task.user_id == current_user.id
        )
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this suggestion"
        )
    
    # Mark as selected
    service = RecoverySuggestionService(db)
    updated_suggestion = await service.mark_suggestion_selected(suggestion_id)
    
    return {
        "success": True,
        "suggestion": updated_suggestion.to_dict(),
        "action_payload": updated_suggestion.action_payload
    }


@router.get("/tasks/{task_id}/recovery-status")
async def get_recovery_status(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get recovery status for a task including:
    - Current task status
    - Available suggestions
    - Steps remaining in chain (if part of a chain)
    - Historical retry success rate
    """
    # Verify task exists and belongs to user
    result = await db.execute(
        select(Task).where(
            Task.id == task_id,
            Task.user_id == current_user.id
        )
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    
    # Get suggestions
    service = RecoverySuggestionService(db)
    suggestions = await service.get_suggestions_for_task(task_id)
    
    # Calculate steps remaining (placeholder - would need chain integration)
    steps_remaining = None
    if task.metadata and "chain_id" in task.metadata:
        # TODO: Integrate with chain system to calculate remaining steps
        steps_remaining = {"current_step": 1, "total_steps": 3, "remaining": 2}
    
    # Calculate historical success rate for similar tasks
    # TODO: Query historical tasks with similar characteristics
    historical_success_rate = 75  # Placeholder
    
    return {
        "task": {
            "id": str(task.id),
            "status": task.status.value,
            "error_message": task.error_message,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "task_type": task.task_type.value if task.task_type else None
        },
        "recovery": {
            "suggestions": [s.to_dict() for s in suggestions],
            "suggestions_count": len(suggestions),
            "has_recovery_options": len(suggestions) > 0
        },
        "chain": steps_remaining,
        "analytics": {
            "historical_success_rate": historical_success_rate,
            "similar_tasks_count": 10  # Placeholder
        }
    }
