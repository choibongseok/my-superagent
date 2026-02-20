"""Onboarding wizard endpoints.

Guides new users through a 3-step setup:
  1. GET  /status          — current onboarding state
  2. GET  /use-cases       — available use-case options
  3. POST /use-case        — pick a use case → get sample prompts
  4. POST /sample-task     — record that a sample task was created
  5. POST /complete        — mark onboarding done, get tips
  6. POST /skip            — skip wizard entirely
  7. POST /reset           — restart wizard (dev/testing)
"""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.onboarding import (
    OnboardingCompleteResponse,
    OnboardingNextAction,
    OnboardingStatus,
    UseCaseOption,
    UseCaseSelectRequest,
)
from app.services import onboarding_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/status", response_model=OnboardingStatus)
async def get_status(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Return the user's current onboarding progress."""
    return await onboarding_service.get_onboarding_status(db, current_user.id)


@router.get("/use-cases", response_model=list[UseCaseOption])
async def list_use_cases(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Return available use-case options for step 2."""
    return await onboarding_service.get_use_case_options()


@router.post("/use-case", response_model=OnboardingNextAction)
async def select_use_case(
    body: UseCaseSelectRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Record the user's chosen use case and return sample prompts."""
    return await onboarding_service.select_use_case(
        db, current_user.id, body.use_case
    )


class _SampleTaskBody(UseCaseSelectRequest):
    """Thin wrapper — just needs a task_id."""

    pass


from pydantic import BaseModel


class SampleTaskRequest(BaseModel):
    """Request body for recording a sample task."""

    task_id: UUID


@router.post("/sample-task", response_model=OnboardingStatus)
async def record_sample_task(
    body: SampleTaskRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Record that the user created a sample task and advance to completed."""
    return await onboarding_service.record_sample_task(
        db, current_user.id, body.task_id
    )


@router.post("/complete", response_model=OnboardingCompleteResponse)
async def complete_onboarding(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Mark onboarding as complete and return next-step tips."""
    return await onboarding_service.complete_onboarding(db, current_user.id)


@router.post("/skip", response_model=OnboardingStatus)
async def skip_onboarding(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Skip the onboarding wizard entirely."""
    return await onboarding_service.skip_onboarding(db, current_user.id)


@router.post("/reset", response_model=OnboardingStatus)
async def reset_onboarding(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Reset the onboarding wizard to the beginning (useful for testing)."""
    return await onboarding_service.reset_onboarding(db, current_user.id)
