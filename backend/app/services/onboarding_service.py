"""Onboarding wizard business logic.

Provides the step-by-step onboarding flow:
1. WELCOME  → show use-case picker
2. USE_CASE → user picks a use-case, get sample prompts
3. SAMPLE_TASK → user runs a sample task, celebrate on completion
4. COMPLETED → tips for next steps
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.onboarding import OnboardingProgress, OnboardingStep, UseCase
from app.schemas.onboarding import (
    OnboardingCompleteResponse,
    OnboardingNextAction,
    OnboardingStatus,
    SamplePrompt,
    UseCaseOption,
)

logger = logging.getLogger(__name__)

# ── Use-case catalogue ──────────────────────────────────────────────

USE_CASE_OPTIONS: list[UseCaseOption] = [
    UseCaseOption(
        key=UseCase.RESEARCH,
        title="Research & Reports",
        description="Gather information from the web and compile comprehensive reports with citations.",
        icon="🔍",
        sample_prompt="Research the latest trends in artificial intelligence for 2026 and summarize the top 5 findings.",
    ),
    UseCaseOption(
        key=UseCase.DOCUMENTS,
        title="Document Creation",
        description="Generate professional Google Docs — proposals, memos, blog posts, and more.",
        icon="📝",
        sample_prompt="Write a one-page project proposal for an internal AI assistant tool.",
    ),
    UseCaseOption(
        key=UseCase.DATA_ANALYSIS,
        title="Data & Spreadsheets",
        description="Create and analyze Google Sheets with formulas, charts, and insights.",
        icon="📊",
        sample_prompt="Create a monthly budget tracker spreadsheet with categories for housing, food, transport, and entertainment.",
    ),
    UseCaseOption(
        key=UseCase.PRESENTATIONS,
        title="Presentations",
        description="Build Google Slides decks with structured content and speaker notes.",
        icon="🎨",
        sample_prompt="Create a 5-slide pitch deck for a SaaS product that helps small businesses automate invoicing.",
    ),
]

_USE_CASE_MAP = {opt.key: opt for opt in USE_CASE_OPTIONS}

# ── Sample prompts per use-case ─────────────────────────────────────

SAMPLE_PROMPTS: dict[UseCase, list[SamplePrompt]] = {
    UseCase.RESEARCH: [
        SamplePrompt(
            prompt="Research the latest trends in artificial intelligence for 2026 and summarize the top 5 findings.",
            task_type="research",
            title="AI Trends 2026",
            description="Quick web research with citations",
        ),
        SamplePrompt(
            prompt="Compare the pros and cons of remote work vs. hybrid work based on recent studies.",
            task_type="research",
            title="Remote vs Hybrid",
            description="Comparative analysis report",
        ),
    ],
    UseCase.DOCUMENTS: [
        SamplePrompt(
            prompt="Write a one-page project proposal for an internal AI assistant tool.",
            task_type="docs",
            title="Project Proposal",
            description="Professional proposal document",
        ),
        SamplePrompt(
            prompt="Draft a company-wide memo announcing a new flexible work policy.",
            task_type="docs",
            title="Company Memo",
            description="Internal communication draft",
        ),
    ],
    UseCase.DATA_ANALYSIS: [
        SamplePrompt(
            prompt="Create a monthly budget tracker spreadsheet with categories for housing, food, transport, and entertainment.",
            task_type="sheets",
            title="Budget Tracker",
            description="Pre-filled spreadsheet with formulas",
        ),
        SamplePrompt(
            prompt="Build a sales pipeline tracker with stages: Lead, Qualified, Proposal, Closed Won, Closed Lost.",
            task_type="sheets",
            title="Sales Pipeline",
            description="CRM-style tracking sheet",
        ),
    ],
    UseCase.PRESENTATIONS: [
        SamplePrompt(
            prompt="Create a 5-slide pitch deck for a SaaS product that helps small businesses automate invoicing.",
            task_type="slides",
            title="SaaS Pitch Deck",
            description="Investor-ready presentation",
        ),
        SamplePrompt(
            prompt="Build a team retrospective presentation covering: what went well, what to improve, and action items.",
            task_type="slides",
            title="Sprint Retro",
            description="Team retrospective deck",
        ),
    ],
}

# ── Tips shown after completion ─────────────────────────────────────

COMPLETION_TIPS = [
    "Try different task types — research, docs, sheets, and slides are all available.",
    "Use the Shared Prompt Library to discover popular prompts from other users.",
    "Share your results with teammates using the share link on any task.",
    "Failed tasks can be retried with one click from the task detail view.",
    "Check the analytics dashboard to track your productivity over time.",
]


# ── Service functions ───────────────────────────────────────────────


async def get_onboarding_status(
    db: AsyncSession, user_id: UUID
) -> OnboardingStatus:
    """Return the current onboarding status, creating a row if none exists."""
    progress = await _get_or_create(db, user_id)
    return _to_status(progress)


async def get_use_case_options() -> list[UseCaseOption]:
    """Return the static list of use-case options (no DB needed)."""
    return list(USE_CASE_OPTIONS)


async def select_use_case(
    db: AsyncSession, user_id: UUID, use_case: UseCase
) -> OnboardingNextAction:
    """Record the user's chosen use case and advance to SAMPLE_TASK step."""
    progress = await _get_or_create(db, user_id)
    progress.use_case = use_case
    progress.current_step = OnboardingStep.SAMPLE_TASK
    await db.commit()
    await db.refresh(progress)

    suggestions = SAMPLE_PROMPTS.get(use_case, [])
    option = _USE_CASE_MAP.get(use_case)
    message = (
        f"Great choice! Here are some sample {option.title.lower() if option else ''} "
        "prompts to get you started.  Pick one — or write your own!"
    )
    return OnboardingNextAction(
        next_step=OnboardingStep.SAMPLE_TASK,
        message=message,
        suggestions=suggestions,
    )


async def record_sample_task(
    db: AsyncSession, user_id: UUID, task_id: UUID
) -> OnboardingStatus:
    """Link a sample task to the onboarding and advance to COMPLETED."""
    progress = await _get_or_create(db, user_id)
    progress.sample_task_id = task_id
    progress.current_step = OnboardingStep.COMPLETED

    from datetime import datetime, timezone

    progress.completed_at = datetime.now(tz=timezone.utc)
    await db.commit()
    await db.refresh(progress)
    return _to_status(progress)


async def complete_onboarding(
    db: AsyncSession, user_id: UUID
) -> OnboardingCompleteResponse:
    """Mark onboarding as done (idempotent) and return tips."""
    progress = await _get_or_create(db, user_id)
    if progress.current_step != OnboardingStep.COMPLETED:
        progress.current_step = OnboardingStep.COMPLETED
        from datetime import datetime, timezone

        progress.completed_at = progress.completed_at or datetime.now(tz=timezone.utc)
        await db.commit()
    return OnboardingCompleteResponse(
        message="You're all set! 🎉 Here are some tips to make the most of AgentHQ.",
        tips=COMPLETION_TIPS,
    )


async def skip_onboarding(
    db: AsyncSession, user_id: UUID
) -> OnboardingStatus:
    """Allow a user to skip the wizard entirely."""
    progress = await _get_or_create(db, user_id)
    progress.current_step = OnboardingStep.COMPLETED
    from datetime import datetime, timezone

    progress.completed_at = progress.completed_at or datetime.now(tz=timezone.utc)
    await db.commit()
    await db.refresh(progress)
    return _to_status(progress)


async def reset_onboarding(
    db: AsyncSession, user_id: UUID
) -> OnboardingStatus:
    """Reset onboarding to WELCOME (useful for testing / re-onboarding)."""
    progress = await _get_or_create(db, user_id)
    progress.current_step = OnboardingStep.WELCOME
    progress.use_case = None
    progress.sample_task_id = None
    progress.completed_at = None
    await db.commit()
    await db.refresh(progress)
    return _to_status(progress)


# ── Helpers ─────────────────────────────────────────────────────────


async def _get_or_create(
    db: AsyncSession, user_id: UUID
) -> OnboardingProgress:
    """Fetch or lazily create an OnboardingProgress row."""
    result = await db.execute(
        select(OnboardingProgress).where(OnboardingProgress.user_id == user_id)
    )
    progress = result.scalar_one_or_none()
    if progress is None:
        progress = OnboardingProgress(user_id=user_id)
        db.add(progress)
        await db.commit()
        await db.refresh(progress)
    return progress


def _to_status(progress: OnboardingProgress) -> OnboardingStatus:
    return OnboardingStatus(
        user_id=progress.user_id,
        current_step=progress.current_step,
        use_case=progress.use_case,
        sample_task_id=progress.sample_task_id,
        is_completed=progress.current_step == OnboardingStep.COMPLETED,
        completed_at=progress.completed_at,
    )
