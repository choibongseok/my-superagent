"""Productivity Streaks & Achievements API.

Endpoints:
- GET /analytics/streaks       — current streak + best streak
- GET /analytics/achievements  — all earned badges
- GET /analytics/progress      — progress toward next achievements
- GET /analytics/gamification  — combined dashboard (streak + achievements + progress + weekly record)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.streak_service import (
    EarnedAchievement,
    NextAchievementProgress,
    StreakInfo,
    WeeklyRecord,
    calculate_quality_streak,
    calculate_streak,
    check_weekly_record,
    compute_achievements,
    next_achievements,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics", "gamification"])


# ── Response schemas ──────────────────────────────────────────────────


class StreakResponse(BaseModel):
    """Activity streak information."""

    current_streak: int = Field(..., description="Current consecutive-day streak")
    longest_streak: int = Field(..., description="All-time longest streak")
    streak_start_date: Optional[str] = Field(None, description="Start date of current streak (ISO)")
    last_active_date: Optional[str] = Field(None, description="Most recent active date (ISO)")
    is_active_today: bool = Field(..., description="Did the user complete a task today?")
    quality_streak: int = Field(
        ..., description="Consecutive recent tasks with QA score ≥ 80"
    )


class AchievementResponse(BaseModel):
    """Single achievement badge."""

    id: str
    name: str
    description: str
    emoji: str
    category: str


class ProgressResponse(BaseModel):
    """Progress toward next achievement."""

    id: str
    name: str
    description: str
    emoji: str
    category: str
    current: int
    target: int
    progress_pct: float = Field(..., description="0–100")


class WeeklyRecordResponse(BaseModel):
    """Weekly productivity record info."""

    is_record: bool = Field(..., description="True if this week beat a previous best")
    this_week_count: int
    previous_best_count: int
    record_margin: int


class GamificationDashboard(BaseModel):
    """Combined gamification dashboard."""

    streak: StreakResponse
    achievements: List[AchievementResponse]
    achievements_count: int = Field(..., description="Total badges earned")
    total_possible: int = Field(..., description="Total possible badges")
    progress: List[ProgressResponse]
    weekly_record: WeeklyRecordResponse
    level: int = Field(..., description="User level based on achievements")
    level_title: str = Field(..., description="Title for current level")


# ── Level calculation ─────────────────────────────────────────────────

_LEVEL_TITLES = [
    (0, "Newcomer"),
    (3, "Apprentice"),
    (6, "Practitioner"),
    (10, "Expert"),
    (15, "Master"),
    (20, "Grandmaster"),
    (25, "Legend"),
]


def _level_from_achievements(count: int) -> tuple[int, str]:
    """Derive a level and title from number of achievements earned."""
    level = 1
    title = "Newcomer"
    for threshold, t in _LEVEL_TITLES:
        if count >= threshold:
            level = threshold + 1
            title = t
    return level, title


# ── Endpoints ─────────────────────────────────────────────────────────


@router.get("/streaks", response_model=StreakResponse)
async def get_streaks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current user's activity streak and quality streak."""
    streak = await calculate_streak(db, current_user.id)
    quality = await calculate_quality_streak(db, current_user.id)

    logger.info(
        "Streak for user %s: current=%d, longest=%d, quality=%d",
        current_user.id, streak.current_streak, streak.longest_streak, quality,
    )

    return StreakResponse(
        current_streak=streak.current_streak,
        longest_streak=streak.longest_streak,
        streak_start_date=streak.streak_start_date,
        last_active_date=streak.last_active_date,
        is_active_today=streak.is_active_today,
        quality_streak=quality,
    )


@router.get("/achievements", response_model=List[AchievementResponse])
async def get_achievements(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all achievements/badges earned by the user."""
    earned = await compute_achievements(db, current_user.id)

    logger.info("User %s has %d achievements", current_user.id, len(earned))

    return [
        AchievementResponse(
            id=a.id, name=a.name, description=a.description,
            emoji=a.emoji, category=a.category,
        )
        for a in earned
    ]


@router.get("/progress", response_model=List[ProgressResponse])
async def get_progress(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get progress toward the next unearned achievement in each category."""
    upcoming = await next_achievements(db, current_user.id)

    return [
        ProgressResponse(
            id=p.id, name=p.name, description=p.description,
            emoji=p.emoji, category=p.category,
            current=p.current, target=p.target,
            progress_pct=p.progress_pct,
        )
        for p in upcoming
    ]


@router.get("/gamification", response_model=GamificationDashboard)
async def get_gamification_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Combined gamification dashboard: streak + achievements + progress + weekly record.

    Single endpoint for the frontend to render the full gamification panel.
    """
    from app.services.streak_service import ALL_ACHIEVEMENTS

    # Calculate all data (share streak/quality_streak to avoid duplicate queries)
    streak = await calculate_streak(db, current_user.id)
    quality = await calculate_quality_streak(db, current_user.id)
    earned = await compute_achievements(db, current_user.id, streak=streak, quality_streak=quality)
    upcoming = await next_achievements(db, current_user.id, streak=streak, quality_streak=quality)
    weekly = await check_weekly_record(db, current_user.id)

    level, title = _level_from_achievements(len(earned))

    logger.info(
        "Gamification dashboard for user %s: level=%d (%s), %d/%d achievements, streak=%d",
        current_user.id, level, title, len(earned), len(ALL_ACHIEVEMENTS),
        streak.current_streak,
    )

    return GamificationDashboard(
        streak=StreakResponse(
            current_streak=streak.current_streak,
            longest_streak=streak.longest_streak,
            streak_start_date=streak.streak_start_date,
            last_active_date=streak.last_active_date,
            is_active_today=streak.is_active_today,
            quality_streak=quality,
        ),
        achievements=[
            AchievementResponse(
                id=a.id, name=a.name, description=a.description,
                emoji=a.emoji, category=a.category,
            )
            for a in earned
        ],
        achievements_count=len(earned),
        total_possible=len(ALL_ACHIEVEMENTS),
        progress=[
            ProgressResponse(
                id=p.id, name=p.name, description=p.description,
                emoji=p.emoji, category=p.category,
                current=p.current, target=p.target,
                progress_pct=p.progress_pct,
            )
            for p in upcoming
        ],
        weekly_record=WeeklyRecordResponse(
            is_record=weekly.is_record,
            this_week_count=weekly.this_week_count,
            previous_best_count=weekly.previous_best_count,
            record_margin=weekly.record_margin,
        ),
        level=level,
        level_title=title,
    )
