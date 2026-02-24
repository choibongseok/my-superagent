"""Productivity Streaks & Achievements service.

Tracks:
- Daily activity streaks (consecutive days with ≥1 completed task)
- Milestone badges (first task, 10 tasks, 50, 100, 500, 1000)
- Agent mastery badges (complete N tasks of each type)
- Quality streaks (consecutive tasks with QA score ≥ 80)
- Weekly productivity records
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.qa_result import QAResult
from app.models.task import Task, TaskStatus, TaskType

logger = logging.getLogger(__name__)


# ── Achievement definitions ───────────────────────────────────────────

@dataclass(frozen=True)
class AchievementDef:
    """Static definition of an achievement / badge."""

    id: str
    name: str
    description: str
    emoji: str
    category: str  # "milestone" | "streak" | "mastery" | "quality"


# Milestone badges
_MILESTONE_THRESHOLDS: list[tuple[int, str, str]] = [
    (1, "first_task", "First Steps"),
    (10, "task_10", "Getting Started"),
    (25, "task_25", "Quarter Century"),
    (50, "task_50", "Half Century"),
    (100, "task_100", "Centurion"),
    (250, "task_250", "Powerhouse"),
    (500, "task_500", "Task Machine"),
    (1000, "task_1000", "Legendary"),
]

MILESTONE_ACHIEVEMENTS: list[AchievementDef] = [
    AchievementDef(
        id=aid,
        name=name,
        description=f"Complete {n} task{'s' if n > 1 else ''}",
        emoji="🏆" if n >= 100 else "⭐" if n >= 25 else "🎯",
        category="milestone",
    )
    for n, aid, name in _MILESTONE_THRESHOLDS
]

# Streak badges
_STREAK_THRESHOLDS: list[tuple[int, str, str]] = [
    (3, "streak_3", "Hat Trick"),
    (7, "streak_7", "Week Warrior"),
    (14, "streak_14", "Fortnight Force"),
    (30, "streak_30", "Monthly Master"),
    (60, "streak_60", "Unstoppable"),
    (100, "streak_100", "Century Streak"),
]

STREAK_ACHIEVEMENTS: list[AchievementDef] = [
    AchievementDef(
        id=aid,
        name=name,
        description=f"Maintain a {n}-day activity streak",
        emoji="🔥",
        category="streak",
    )
    for n, aid, name in _STREAK_THRESHOLDS
]

# Agent mastery badges (complete N tasks of a specific type)
_MASTERY_THRESHOLDS: list[tuple[int, str]] = [
    (10, "Apprentice"),
    (50, "Expert"),
    (100, "Master"),
]

MASTERY_ACHIEVEMENTS: list[AchievementDef] = [
    AchievementDef(
        id=f"mastery_{agent_type.value}_{n}",
        name=f"{agent_type.value.title()} {title}",
        description=f"Complete {n} {agent_type.value} tasks",
        emoji={"docs": "📝", "sheets": "📊", "slides": "🎨", "research": "🔍"}[agent_type.value],
        category="mastery",
    )
    for agent_type in TaskType
    for n, title in _MASTERY_THRESHOLDS
]

# Quality streak badges
_QUALITY_THRESHOLDS: list[tuple[int, str, str]] = [
    (3, "quality_3", "Quality Trio"),
    (5, "quality_5", "Consistent"),
    (10, "quality_10", "Perfectionist"),
    (25, "quality_25", "Quality Legend"),
]

QUALITY_ACHIEVEMENTS: list[AchievementDef] = [
    AchievementDef(
        id=aid,
        name=name,
        description=f"{n} consecutive tasks with quality score ≥ 80",
        emoji="💎",
        category="quality",
    )
    for n, aid, name in _QUALITY_THRESHOLDS
]

ALL_ACHIEVEMENTS: dict[str, AchievementDef] = {
    a.id: a
    for a in (
        MILESTONE_ACHIEVEMENTS
        + STREAK_ACHIEVEMENTS
        + MASTERY_ACHIEVEMENTS
        + QUALITY_ACHIEVEMENTS
    )
}


# ── Streak calculation ────────────────────────────────────────────────

@dataclass
class StreakInfo:
    """Calculated streak data for a user."""

    current_streak: int = 0
    longest_streak: int = 0
    streak_start_date: Optional[str] = None  # ISO date
    last_active_date: Optional[str] = None  # ISO date
    is_active_today: bool = False


async def calculate_streak(db: AsyncSession, user_id: UUID) -> StreakInfo:
    """Calculate the current and longest daily activity streak.

    A streak day = at least one COMPLETED task on that calendar date (UTC).
    """
    # Get distinct dates with at least one completed task, ordered descending
    query = (
        select(func.date(Task.completed_at).label("d"))
        .where(
            and_(
                Task.user_id == user_id,
                Task.status == TaskStatus.COMPLETED,
                Task.completed_at.isnot(None),
            )
        )
        .group_by(func.date(Task.completed_at))
        .order_by(func.date(Task.completed_at).desc())
    )
    result = await db.execute(query)
    rows = result.all()

    if not rows:
        return StreakInfo()

    # Convert to list of date objects
    active_dates: list[datetime] = []
    for row in rows:
        val = row[0]
        if isinstance(val, str):
            val = datetime.strptime(val, "%Y-%m-%d").date()
        elif isinstance(val, datetime):
            val = val.date()
        active_dates.append(val)

    today = datetime.now(UTC).date()
    yesterday = today - timedelta(days=1)

    last_active = active_dates[0]
    is_active_today = last_active == today

    # Current streak: count consecutive days backwards from today (or yesterday)
    if last_active == today:
        anchor = today
    elif last_active == yesterday:
        anchor = yesterday
    else:
        # Streak is broken
        return StreakInfo(
            current_streak=0,
            longest_streak=_longest_streak(active_dates),
            last_active_date=str(last_active),
            is_active_today=False,
        )

    current_streak = 0
    expected = anchor
    for d in active_dates:
        if d == expected:
            current_streak += 1
            expected = d - timedelta(days=1)
        elif d < expected:
            break

    streak_start = anchor - timedelta(days=current_streak - 1)

    longest = _longest_streak(active_dates)
    if current_streak > longest:
        longest = current_streak

    return StreakInfo(
        current_streak=current_streak,
        longest_streak=longest,
        streak_start_date=str(streak_start),
        last_active_date=str(last_active),
        is_active_today=is_active_today,
    )


def _longest_streak(dates_desc: list) -> int:
    """Compute the longest consecutive-day run in a descending-sorted date list."""
    if not dates_desc:
        return 0
    best = 1
    run = 1
    for i in range(1, len(dates_desc)):
        if dates_desc[i - 1] - dates_desc[i] == timedelta(days=1):
            run += 1
            best = max(best, run)
        else:
            run = 1
    return best


# ── Quality streak ────────────────────────────────────────────────────

async def calculate_quality_streak(db: AsyncSession, user_id: UUID, threshold: float = 80.0) -> int:
    """Count consecutive recent tasks (by completed_at desc) with QA score ≥ threshold.

    Returns 0 if the most recent scored task is below threshold.
    """
    query = (
        select(QAResult.overall_score)
        .join(Task, QAResult.task_id == Task.id)
        .where(
            and_(
                Task.user_id == user_id,
                Task.status == TaskStatus.COMPLETED,
                Task.completed_at.isnot(None),
            )
        )
        .order_by(Task.completed_at.desc())
    )
    result = await db.execute(query)
    scores = [row[0] for row in result.all()]

    streak = 0
    for s in scores:
        if s >= threshold:
            streak += 1
        else:
            break
    return streak


# ── Earned achievements ───────────────────────────────────────────────

@dataclass
class EarnedAchievement:
    """An achievement the user has unlocked."""

    id: str
    name: str
    description: str
    emoji: str
    category: str
    earned: bool = True


async def compute_achievements(
    db: AsyncSession,
    user_id: UUID,
    streak: Optional[StreakInfo] = None,
    quality_streak: Optional[int] = None,
) -> list[EarnedAchievement]:
    """Compute all achievements earned by the user."""
    earned: list[EarnedAchievement] = []

    # ── Total completed tasks ──
    count_q = select(func.count(Task.id)).where(
        and_(Task.user_id == user_id, Task.status == TaskStatus.COMPLETED)
    )
    total_completed: int = (await db.execute(count_q)).scalar() or 0

    for n, aid, _name in _MILESTONE_THRESHOLDS:
        if total_completed >= n:
            defn = ALL_ACHIEVEMENTS[aid]
            earned.append(EarnedAchievement(
                id=defn.id, name=defn.name, description=defn.description,
                emoji=defn.emoji, category=defn.category,
            ))

    # ── Streak achievements ──
    if streak is None:
        streak = await calculate_streak(db, user_id)

    best_streak = max(streak.current_streak, streak.longest_streak)
    for n, aid, _name in _STREAK_THRESHOLDS:
        if best_streak >= n:
            defn = ALL_ACHIEVEMENTS[aid]
            earned.append(EarnedAchievement(
                id=defn.id, name=defn.name, description=defn.description,
                emoji=defn.emoji, category=defn.category,
            ))

    # ── Agent mastery ──
    type_counts_q = (
        select(Task.task_type, func.count(Task.id))
        .where(and_(Task.user_id == user_id, Task.status == TaskStatus.COMPLETED))
        .group_by(Task.task_type)
    )
    type_rows = (await db.execute(type_counts_q)).all()
    type_counts: dict[str, int] = {str(r[0].value if hasattr(r[0], "value") else r[0]): r[1] for r in type_rows}

    for agent_type in TaskType:
        count = type_counts.get(agent_type.value, 0)
        for n, _title in _MASTERY_THRESHOLDS:
            aid = f"mastery_{agent_type.value}_{n}"
            if count >= n and aid in ALL_ACHIEVEMENTS:
                defn = ALL_ACHIEVEMENTS[aid]
                earned.append(EarnedAchievement(
                    id=defn.id, name=defn.name, description=defn.description,
                    emoji=defn.emoji, category=defn.category,
                ))

    # ── Quality streak achievements ──
    if quality_streak is None:
        quality_streak = await calculate_quality_streak(db, user_id)

    for n, aid, _name in _QUALITY_THRESHOLDS:
        # Use the current quality streak (consecutive from most recent)
        if quality_streak >= n:
            defn = ALL_ACHIEVEMENTS[aid]
            earned.append(EarnedAchievement(
                id=defn.id, name=defn.name, description=defn.description,
                emoji=defn.emoji, category=defn.category,
            ))

    return earned


# ── Weekly productivity record ────────────────────────────────────────

@dataclass
class WeeklyRecord:
    """Whether this week broke a personal productivity record."""

    is_record: bool = False
    this_week_count: int = 0
    previous_best_count: int = 0
    record_margin: int = 0  # how much above previous best


async def check_weekly_record(db: AsyncSession, user_id: UUID) -> WeeklyRecord:
    """Check if the current week is a personal-best for completed tasks.

    Uses Python-side grouping (compatible with both PostgreSQL and SQLite).
    """
    now = datetime.now(UTC)
    # Monday of this week
    this_monday = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    # Fetch all completed tasks with their completed_at timestamps
    query = (
        select(Task.completed_at)
        .where(
            and_(
                Task.user_id == user_id,
                Task.status == TaskStatus.COMPLETED,
                Task.completed_at.isnot(None),
            )
        )
    )
    result = await db.execute(query)
    rows = result.all()

    if not rows:
        return WeeklyRecord()

    # Group by ISO week in Python
    from collections import Counter

    week_counts: Counter = Counter()
    for (completed_at,) in rows:
        if completed_at is None:
            continue
        if isinstance(completed_at, str):
            completed_at = datetime.fromisoformat(completed_at)
        # Get the Monday of that task's week
        task_monday = (completed_at - timedelta(days=completed_at.weekday())).date()
        week_counts[task_monday] += 1

    this_monday_date = this_monday.date()
    this_week_count = week_counts.pop(this_monday_date, 0)
    previous_best = max(week_counts.values()) if week_counts else 0

    is_record = this_week_count > previous_best > 0
    return WeeklyRecord(
        is_record=is_record,
        this_week_count=this_week_count,
        previous_best_count=previous_best,
        record_margin=max(0, this_week_count - previous_best),
    )


# ── Next achievement progress ────────────────────────────────────────

@dataclass
class NextAchievementProgress:
    """Progress toward the next unearned achievement in a category."""

    id: str
    name: str
    description: str
    emoji: str
    category: str
    current: int
    target: int
    progress_pct: float  # 0-100


async def next_achievements(
    db: AsyncSession,
    user_id: UUID,
    streak: Optional[StreakInfo] = None,
    quality_streak: Optional[int] = None,
) -> list[NextAchievementProgress]:
    """Return progress toward the next unearned achievement in each category."""
    upcoming: list[NextAchievementProgress] = []

    # ── Next milestone ──
    count_q = select(func.count(Task.id)).where(
        and_(Task.user_id == user_id, Task.status == TaskStatus.COMPLETED)
    )
    total_completed: int = (await db.execute(count_q)).scalar() or 0

    for n, aid, _name in _MILESTONE_THRESHOLDS:
        if total_completed < n:
            defn = ALL_ACHIEVEMENTS[aid]
            upcoming.append(NextAchievementProgress(
                id=defn.id, name=defn.name, description=defn.description,
                emoji=defn.emoji, category=defn.category,
                current=total_completed, target=n,
                progress_pct=round(total_completed / n * 100, 1),
            ))
            break

    # ── Next streak ──
    if streak is None:
        streak = await calculate_streak(db, user_id)

    best_streak = max(streak.current_streak, streak.longest_streak)
    for n, aid, _name in _STREAK_THRESHOLDS:
        if best_streak < n:
            defn = ALL_ACHIEVEMENTS[aid]
            upcoming.append(NextAchievementProgress(
                id=defn.id, name=defn.name, description=defn.description,
                emoji=defn.emoji, category=defn.category,
                current=streak.current_streak, target=n,
                progress_pct=round(streak.current_streak / n * 100, 1),
            ))
            break

    # ── Next quality ──
    if quality_streak is None:
        quality_streak = await calculate_quality_streak(db, user_id)

    for n, aid, _name in _QUALITY_THRESHOLDS:
        if quality_streak < n:
            defn = ALL_ACHIEVEMENTS[aid]
            upcoming.append(NextAchievementProgress(
                id=defn.id, name=defn.name, description=defn.description,
                emoji=defn.emoji, category=defn.category,
                current=quality_streak, target=n,
                progress_pct=round(quality_streak / n * 100, 1),
            ))
            break

    return upcoming
