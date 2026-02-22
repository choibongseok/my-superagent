"""Tests for Productivity Streaks & Achievements.

Covers:
- GET /api/v1/analytics/streaks
- GET /api/v1/analytics/achievements
- GET /api/v1/analytics/progress
- GET /api/v1/analytics/gamification
- streak_service unit tests
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.qa_result import QAResult
from app.models.task import Task as TaskModel, TaskStatus, TaskType
from app.models.user import User


# ── Helpers ───────────────────────────────────────────────────────────


async def _user(db: AsyncSession, email: str | None = None) -> User:
    u = User(id=uuid4(), email=email or f"streak-{uuid4().hex[:6]}@test.com", is_active=True)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _task(
    db: AsyncSession,
    user: User,
    *,
    task_type: TaskType = TaskType.DOCS,
    status: TaskStatus = TaskStatus.COMPLETED,
    created_at: datetime | None = None,
    completed_at: datetime | None = None,
    prompt: str = "test",
) -> TaskModel:
    now = datetime.now(timezone.utc)
    ca = created_at or now - timedelta(hours=1)
    comp = completed_at or (ca + timedelta(minutes=5) if status == TaskStatus.COMPLETED else None)
    t = TaskModel(
        id=uuid4(),
        user_id=user.id,
        prompt=prompt,
        task_type=task_type,
        status=status,
        result={"ok": True} if status == TaskStatus.COMPLETED else None,
        created_at=ca,
        completed_at=comp,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


async def _qa(db: AsyncSession, task: TaskModel, score: float) -> QAResult:
    q = QAResult(id=uuid4(), task_id=task.id, overall_score=score)
    db.add(q)
    await db.commit()
    await db.refresh(q)
    return q


def _headers(user: User) -> dict:
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


# ── Service unit tests: streak calculation ────────────────────────────


@pytest.mark.asyncio
async def test_streak_no_tasks(db: AsyncSession):
    from app.services.streak_service import calculate_streak

    user = await _user(db)
    info = await calculate_streak(db, user.id)
    assert info.current_streak == 0
    assert info.longest_streak == 0
    assert info.is_active_today is False
    assert info.streak_start_date is None
    assert info.last_active_date is None


@pytest.mark.asyncio
async def test_streak_single_day_today(db: AsyncSession):
    from app.services.streak_service import calculate_streak

    user = await _user(db)
    now = datetime.now(timezone.utc)
    await _task(db, user, completed_at=now)

    info = await calculate_streak(db, user.id)
    assert info.current_streak == 1
    assert info.is_active_today is True


@pytest.mark.asyncio
async def test_streak_consecutive_days(db: AsyncSession):
    from app.services.streak_service import calculate_streak

    user = await _user(db)
    now = datetime.now(timezone.utc)

    # Create tasks for today, yesterday, and day before
    for days_ago in range(3):
        dt = now - timedelta(days=days_ago)
        await _task(db, user, created_at=dt - timedelta(minutes=10), completed_at=dt)

    info = await calculate_streak(db, user.id)
    assert info.current_streak == 3
    assert info.longest_streak == 3
    assert info.is_active_today is True


@pytest.mark.asyncio
async def test_streak_broken_gap(db: AsyncSession):
    from app.services.streak_service import calculate_streak

    user = await _user(db)
    now = datetime.now(timezone.utc)

    # Today and 3 days ago (gap of 1 day)
    await _task(db, user, created_at=now - timedelta(minutes=5), completed_at=now)
    dt_old = now - timedelta(days=3)
    await _task(db, user, created_at=dt_old - timedelta(minutes=5), completed_at=dt_old)

    info = await calculate_streak(db, user.id)
    assert info.current_streak == 1  # only today
    assert info.longest_streak == 1


@pytest.mark.asyncio
async def test_streak_yesterday_anchor(db: AsyncSession):
    """If no task today but yesterday had one, streak starts from yesterday."""
    from app.services.streak_service import calculate_streak

    user = await _user(db)
    now = datetime.now(timezone.utc)

    yesterday = now - timedelta(days=1)
    day_before = now - timedelta(days=2)

    await _task(db, user, created_at=yesterday - timedelta(minutes=5), completed_at=yesterday)
    await _task(db, user, created_at=day_before - timedelta(minutes=5), completed_at=day_before)

    info = await calculate_streak(db, user.id)
    assert info.current_streak == 2
    assert info.is_active_today is False


@pytest.mark.asyncio
async def test_streak_only_completed_tasks_count(db: AsyncSession):
    from app.services.streak_service import calculate_streak

    user = await _user(db)
    now = datetime.now(timezone.utc)

    # A failed task today shouldn't count
    await _task(db, user, status=TaskStatus.FAILED, created_at=now - timedelta(minutes=5))

    info = await calculate_streak(db, user.id)
    assert info.current_streak == 0


@pytest.mark.asyncio
async def test_longest_streak_calculation():
    from app.services.streak_service import _longest_streak
    from datetime import date

    # 5-day streak then gap then 2-day streak
    dates = [
        date(2026, 2, 20),
        date(2026, 2, 19),
        date(2026, 2, 18),
        date(2026, 2, 17),
        date(2026, 2, 16),
        # gap
        date(2026, 2, 13),
        date(2026, 2, 12),
    ]
    assert _longest_streak(dates) == 5


# ── Service unit tests: quality streak ────────────────────────────────


@pytest.mark.asyncio
async def test_quality_streak_empty(db: AsyncSession):
    from app.services.streak_service import calculate_quality_streak

    user = await _user(db)
    assert await calculate_quality_streak(db, user.id) == 0


@pytest.mark.asyncio
async def test_quality_streak_consecutive(db: AsyncSession):
    from app.services.streak_service import calculate_quality_streak

    user = await _user(db)
    now = datetime.now(timezone.utc)

    # 3 high-quality tasks
    for i in range(3):
        t = await _task(db, user, completed_at=now - timedelta(hours=i))
        await _qa(db, t, 85.0)

    assert await calculate_quality_streak(db, user.id) == 3


@pytest.mark.asyncio
async def test_quality_streak_broken_by_low_score(db: AsyncSession):
    from app.services.streak_service import calculate_quality_streak

    user = await _user(db)
    now = datetime.now(timezone.utc)

    # Most recent: high score
    t1 = await _task(db, user, completed_at=now)
    await _qa(db, t1, 90.0)

    # Second: low score (breaks streak)
    t2 = await _task(db, user, completed_at=now - timedelta(hours=1))
    await _qa(db, t2, 50.0)

    # Third: high score (doesn't count since streak is broken)
    t3 = await _task(db, user, completed_at=now - timedelta(hours=2))
    await _qa(db, t3, 95.0)

    assert await calculate_quality_streak(db, user.id) == 1


# ── Service unit tests: achievements ──────────────────────────────────


@pytest.mark.asyncio
async def test_no_achievements_without_tasks(db: AsyncSession):
    from app.services.streak_service import compute_achievements

    user = await _user(db)
    earned = await compute_achievements(db, user.id)
    assert len(earned) == 0


@pytest.mark.asyncio
async def test_first_task_achievement(db: AsyncSession):
    from app.services.streak_service import compute_achievements

    user = await _user(db)
    await _task(db, user)

    earned = await compute_achievements(db, user.id)
    ids = [a.id for a in earned]
    assert "first_task" in ids


@pytest.mark.asyncio
async def test_milestone_achievements(db: AsyncSession):
    from app.services.streak_service import compute_achievements

    user = await _user(db)
    now = datetime.now(timezone.utc)

    # Create 10 completed tasks
    for i in range(10):
        await _task(db, user, completed_at=now - timedelta(minutes=i))

    earned = await compute_achievements(db, user.id)
    ids = [a.id for a in earned]
    assert "first_task" in ids
    assert "task_10" in ids
    assert "task_25" not in ids


@pytest.mark.asyncio
async def test_mastery_achievements(db: AsyncSession):
    from app.services.streak_service import compute_achievements

    user = await _user(db)
    now = datetime.now(timezone.utc)

    # 10 docs tasks → should earn "mastery_docs_10"
    for i in range(10):
        await _task(db, user, task_type=TaskType.DOCS, completed_at=now - timedelta(minutes=i))

    earned = await compute_achievements(db, user.id)
    ids = [a.id for a in earned]
    assert "mastery_docs_10" in ids
    assert "mastery_sheets_10" not in ids


@pytest.mark.asyncio
async def test_quality_achievements(db: AsyncSession):
    from app.services.streak_service import compute_achievements, StreakInfo

    user = await _user(db)
    now = datetime.now(timezone.utc)

    # 5 consecutive high-quality tasks
    for i in range(5):
        t = await _task(db, user, completed_at=now - timedelta(hours=i))
        await _qa(db, t, 88.0)

    earned = await compute_achievements(db, user.id, quality_streak=5)
    ids = [a.id for a in earned]
    assert "quality_3" in ids
    assert "quality_5" in ids
    assert "quality_10" not in ids


# ── Service unit tests: next achievements ─────────────────────────────


@pytest.mark.asyncio
async def test_next_achievements_for_new_user(db: AsyncSession):
    from app.services.streak_service import next_achievements, StreakInfo

    user = await _user(db)
    upcoming = await next_achievements(db, user.id)

    # Should have at least milestone and quality progress entries
    categories = [p.category for p in upcoming]
    assert "milestone" in categories


@pytest.mark.asyncio
async def test_next_milestone_progress(db: AsyncSession):
    from app.services.streak_service import next_achievements

    user = await _user(db)
    now = datetime.now(timezone.utc)

    # 3 tasks done → next milestone is task_10
    for i in range(3):
        await _task(db, user, completed_at=now - timedelta(minutes=i))

    upcoming = await next_achievements(db, user.id)
    milestone = next(p for p in upcoming if p.category == "milestone")
    assert milestone.id == "task_10"
    assert milestone.current == 3
    assert milestone.target == 10
    assert milestone.progress_pct == 30.0


# ── Service unit tests: weekly record ─────────────────────────────────


@pytest.mark.asyncio
async def test_weekly_record_no_data(db: AsyncSession):
    from app.services.streak_service import check_weekly_record

    user = await _user(db)
    rec = await check_weekly_record(db, user.id)
    assert rec.is_record is False
    assert rec.this_week_count == 0


@pytest.mark.asyncio
async def test_weekly_record_first_week(db: AsyncSession):
    from app.services.streak_service import check_weekly_record

    user = await _user(db)
    now = datetime.now(timezone.utc)

    await _task(db, user, completed_at=now)

    rec = await check_weekly_record(db, user.id)
    # First week can't be a "record" (no previous week to compare)
    assert rec.this_week_count == 1
    assert rec.previous_best_count == 0
    assert rec.is_record is False


# ── Service unit tests: level ─────────────────────────────────────────


def test_level_from_achievements():
    from app.api.v1.streaks import _level_from_achievements

    level, title = _level_from_achievements(0)
    assert title == "Newcomer"

    level, title = _level_from_achievements(5)
    assert title == "Apprentice"

    level, title = _level_from_achievements(10)
    assert title == "Expert"

    level, title = _level_from_achievements(25)
    assert title == "Legend"


# ── Service unit tests: achievement definitions ───────────────────────


def test_all_achievements_registered():
    from app.services.streak_service import ALL_ACHIEVEMENTS

    # Should have milestone + streak + mastery + quality badges
    assert len(ALL_ACHIEVEMENTS) > 20
    categories = set(a.category for a in ALL_ACHIEVEMENTS.values())
    assert categories == {"milestone", "streak", "mastery", "quality"}


def test_achievement_ids_unique():
    from app.services.streak_service import (
        MILESTONE_ACHIEVEMENTS,
        STREAK_ACHIEVEMENTS,
        MASTERY_ACHIEVEMENTS,
        QUALITY_ACHIEVEMENTS,
    )

    all_ids = [a.id for a in (
        MILESTONE_ACHIEVEMENTS + STREAK_ACHIEVEMENTS +
        MASTERY_ACHIEVEMENTS + QUALITY_ACHIEVEMENTS
    )]
    assert len(all_ids) == len(set(all_ids)), "Duplicate achievement IDs found"


def test_achievement_categories():
    from app.services.streak_service import MILESTONE_ACHIEVEMENTS, STREAK_ACHIEVEMENTS

    for a in MILESTONE_ACHIEVEMENTS:
        assert a.category == "milestone"
    for a in STREAK_ACHIEVEMENTS:
        assert a.category == "streak"
        assert a.emoji == "🔥"


# ── API tests: GET /api/v1/analytics/streaks ──────────────────────────


@pytest.mark.asyncio
async def test_streaks_requires_auth(async_client: AsyncClient, db: AsyncSession):
    resp = await async_client.get("/api/v1/analytics/streaks")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_streaks_empty_user(async_client: AsyncClient, db: AsyncSession):
    user = await _user(db)
    resp = await async_client.get("/api/v1/analytics/streaks", headers=_headers(user))
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_streak"] == 0
    assert data["longest_streak"] == 0
    assert data["is_active_today"] is False
    assert data["quality_streak"] == 0


@pytest.mark.asyncio
async def test_streaks_with_activity(async_client: AsyncClient, db: AsyncSession):
    user = await _user(db)
    now = datetime.now(timezone.utc)

    # Tasks today and yesterday
    await _task(db, user, completed_at=now)
    await _task(db, user, completed_at=now - timedelta(days=1))

    resp = await async_client.get("/api/v1/analytics/streaks", headers=_headers(user))
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_streak"] == 2
    assert data["is_active_today"] is True


# ── API tests: GET /api/v1/analytics/achievements ─────────────────────


@pytest.mark.asyncio
async def test_achievements_requires_auth(async_client: AsyncClient, db: AsyncSession):
    resp = await async_client.get("/api/v1/analytics/achievements")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_achievements_empty(async_client: AsyncClient, db: AsyncSession):
    user = await _user(db)
    resp = await async_client.get("/api/v1/analytics/achievements", headers=_headers(user))
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_achievements_with_tasks(async_client: AsyncClient, db: AsyncSession):
    user = await _user(db)
    now = datetime.now(timezone.utc)

    await _task(db, user, completed_at=now)

    resp = await async_client.get("/api/v1/analytics/achievements", headers=_headers(user))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert any(a["id"] == "first_task" for a in data)
    # Verify response shape
    first = data[0]
    assert "id" in first
    assert "name" in first
    assert "description" in first
    assert "emoji" in first
    assert "category" in first


# ── API tests: GET /api/v1/analytics/progress ─────────────────────────


@pytest.mark.asyncio
async def test_progress_requires_auth(async_client: AsyncClient, db: AsyncSession):
    resp = await async_client.get("/api/v1/analytics/progress")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_progress_shows_next_targets(async_client: AsyncClient, db: AsyncSession):
    user = await _user(db)
    now = datetime.now(timezone.utc)

    # 3 tasks → next milestone is task_10
    for i in range(3):
        await _task(db, user, completed_at=now - timedelta(minutes=i))

    resp = await async_client.get("/api/v1/analytics/progress", headers=_headers(user))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1

    milestone = next((p for p in data if p["category"] == "milestone"), None)
    assert milestone is not None
    assert milestone["id"] == "task_10"
    assert milestone["current"] == 3
    assert milestone["target"] == 10
    assert milestone["progress_pct"] == 30.0


# ── API tests: GET /api/v1/analytics/gamification ─────────────────────


@pytest.mark.asyncio
async def test_gamification_requires_auth(async_client: AsyncClient, db: AsyncSession):
    resp = await async_client.get("/api/v1/analytics/gamification")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_gamification_empty_user(async_client: AsyncClient, db: AsyncSession):
    user = await _user(db)
    resp = await async_client.get("/api/v1/analytics/gamification", headers=_headers(user))
    assert resp.status_code == 200
    data = resp.json()

    assert data["streak"]["current_streak"] == 0
    assert data["achievements"] == []
    assert data["achievements_count"] == 0
    assert data["total_possible"] > 20
    assert data["level"] >= 1
    assert data["level_title"] == "Newcomer"
    assert data["weekly_record"]["is_record"] is False


@pytest.mark.asyncio
async def test_gamification_full_dashboard(async_client: AsyncClient, db: AsyncSession):
    user = await _user(db)
    now = datetime.now(timezone.utc)

    # Create 3 tasks today with high QA scores
    for i in range(3):
        t = await _task(db, user, completed_at=now - timedelta(minutes=i * 10))
        await _qa(db, t, 90.0)

    resp = await async_client.get("/api/v1/analytics/gamification", headers=_headers(user))
    assert resp.status_code == 200
    data = resp.json()

    # Streak
    assert data["streak"]["current_streak"] == 1
    assert data["streak"]["is_active_today"] is True
    assert data["streak"]["quality_streak"] == 3

    # Achievements (should have first_task at minimum)
    assert data["achievements_count"] >= 1
    earned_ids = [a["id"] for a in data["achievements"]]
    assert "first_task" in earned_ids
    assert "quality_3" in earned_ids  # 3 consecutive high quality

    # Progress
    assert len(data["progress"]) >= 1

    # Weekly record
    assert isinstance(data["weekly_record"]["this_week_count"], int)

    # Level
    assert data["level"] >= 1
    assert isinstance(data["level_title"], str)


@pytest.mark.asyncio
async def test_gamification_response_shape(async_client: AsyncClient, db: AsyncSession):
    """Verify the full response schema matches expected fields."""
    user = await _user(db)
    resp = await async_client.get("/api/v1/analytics/gamification", headers=_headers(user))
    assert resp.status_code == 200
    data = resp.json()

    # Top-level keys
    expected_keys = {
        "streak", "achievements", "achievements_count",
        "total_possible", "progress", "weekly_record",
        "level", "level_title",
    }
    assert expected_keys.issubset(set(data.keys()))

    # Streak shape
    streak_keys = {
        "current_streak", "longest_streak", "streak_start_date",
        "last_active_date", "is_active_today", "quality_streak",
    }
    assert streak_keys.issubset(set(data["streak"].keys()))

    # Weekly record shape
    wr_keys = {"is_record", "this_week_count", "previous_best_count", "record_margin"}
    assert wr_keys.issubset(set(data["weekly_record"].keys()))


@pytest.mark.asyncio
async def test_gamification_different_users_independent(async_client: AsyncClient, db: AsyncSession):
    """Each user's gamification data should be independent."""
    user_a = await _user(db, email="a@test.com")
    user_b = await _user(db, email="b@test.com")
    now = datetime.now(timezone.utc)

    # User A has 5 tasks
    for i in range(5):
        await _task(db, user_a, completed_at=now - timedelta(minutes=i))

    # User B has 0 tasks
    resp_a = await async_client.get("/api/v1/analytics/gamification", headers=_headers(user_a))
    resp_b = await async_client.get("/api/v1/analytics/gamification", headers=_headers(user_b))

    assert resp_a.json()["achievements_count"] >= 1
    assert resp_b.json()["achievements_count"] == 0


@pytest.mark.asyncio
async def test_gamification_mastery_shows_agent_specific(async_client: AsyncClient, db: AsyncSession):
    """Verify mastery badges are agent-type specific."""
    user = await _user(db)
    now = datetime.now(timezone.utc)

    # 10 research tasks
    for i in range(10):
        await _task(
            db, user,
            task_type=TaskType.RESEARCH,
            completed_at=now - timedelta(minutes=i),
        )

    resp = await async_client.get("/api/v1/analytics/gamification", headers=_headers(user))
    data = resp.json()

    earned_ids = [a["id"] for a in data["achievements"]]
    assert "mastery_research_10" in earned_ids
    assert "mastery_docs_10" not in earned_ids
