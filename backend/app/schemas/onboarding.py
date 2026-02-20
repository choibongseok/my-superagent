"""Onboarding schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.onboarding import OnboardingStep, UseCase


class OnboardingStatus(BaseModel):
    """Current onboarding status for a user."""

    user_id: UUID
    current_step: OnboardingStep
    use_case: Optional[UseCase] = None
    sample_task_id: Optional[UUID] = None
    is_completed: bool = False
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class UseCaseOption(BaseModel):
    """A selectable use-case option shown during onboarding."""

    key: UseCase
    title: str
    description: str
    icon: str
    sample_prompt: str


class UseCaseSelectRequest(BaseModel):
    """Request body for selecting a use case."""

    use_case: UseCase


class SamplePrompt(BaseModel):
    """A sample prompt associated with a use case."""

    prompt: str
    task_type: str
    title: str
    description: str


class OnboardingNextAction(BaseModel):
    """Describes the recommended next action after a step."""

    next_step: OnboardingStep
    message: str
    suggestions: list[SamplePrompt] = Field(default_factory=list)
    use_case_options: list[UseCaseOption] = Field(default_factory=list)


class OnboardingCompleteResponse(BaseModel):
    """Response when onboarding is marked complete."""

    message: str
    tips: list[str]
