"""Task Health Monitor service (#223).

Provides real-time task health monitoring:
- Failure rate tracking (last N minutes)
- Stuck task detection (processing too long)
- Per-user failure alerts via WebSocket
- System-wide health summary for ops dashboard
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task, TaskStatus

logger = logging.getLogger(__name__)

# A task processing longer than this is considered "stuck"
STUCK_THRESHOLD_MINUTES = 30

# Failure rate above this triggers a warning in health checks
FAILURE_RATE_WARNING_THRESHOLD = 0.20  # 20%
FAILURE_RATE_CRITICAL_THRESHOLD = 0.50  # 50%


async def get_task_health_summary(
    db: AsyncSession,
    *,
    window_minutes: int = 60,
    user_id: Optional[UUID] = None,
) -> dict[str, Any]:
    """Return a task health summary over the given time window.

    Args:
        db: Async database session.
        window_minutes: Look-back window in minutes (default 60).
        user_id: Optional user scope; ``None`` = system-wide.

    Returns:
        Dict with keys: total, completed, failed, pending, processing,
        cancelled, failure_rate, stuck_tasks, health_status, window_minutes.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)

    conditions = [Task.created_at >= cutoff]
    if user_id is not None:
        conditions.append(Task.user_id == user_id)

    query = select(
        Task.status,
        func.count(Task.id).label("cnt"),
    ).where(and_(*conditions)).group_by(Task.status)

    result = await db.execute(query)
    rows = result.all()

    counts: dict[str, int] = {
        "pending": 0,
        "processing": 0,
        "completed": 0,
        "failed": 0,
        "cancelled": 0,
    }
    for row in rows:
        status_val = row.status.value if hasattr(row.status, "value") else str(row.status)
        counts[status_val] = counts.get(status_val, 0) + row.cnt

    total = sum(counts.values())
    failure_rate = counts["failed"] / total if total > 0 else 0.0

    # Stuck tasks: status=processing and created > threshold ago
    stuck_cutoff = datetime.now(timezone.utc) - timedelta(minutes=STUCK_THRESHOLD_MINUTES)
    stuck_conditions = [
        Task.status == TaskStatus.PROCESSING,
        Task.created_at < stuck_cutoff,
    ]
    if user_id is not None:
        stuck_conditions.append(Task.user_id == user_id)

    stuck_query = select(func.count(Task.id)).where(and_(*stuck_conditions))
    stuck_result = await db.execute(stuck_query)
    stuck_count = stuck_result.scalar() or 0

    # Derive health status
    if failure_rate >= FAILURE_RATE_CRITICAL_THRESHOLD or stuck_count >= 5:
        health_status = "critical"
    elif failure_rate >= FAILURE_RATE_WARNING_THRESHOLD or stuck_count >= 1:
        health_status = "warning"
    else:
        health_status = "healthy"

    return {
        "total": total,
        "completed": counts["completed"],
        "failed": counts["failed"],
        "pending": counts["pending"],
        "processing": counts["processing"],
        "cancelled": counts["cancelled"],
        "failure_rate": round(failure_rate, 4),
        "stuck_tasks": stuck_count,
        "health_status": health_status,
        "window_minutes": window_minutes,
    }


async def get_recent_failures(
    db: AsyncSession,
    *,
    limit: int = 10,
    user_id: Optional[UUID] = None,
) -> list[dict[str, Any]]:
    """Return the most recent failed tasks.

    Args:
        db: Async database session.
        limit: Maximum number of failures to return.
        user_id: Optional user scope.

    Returns:
        List of dicts with task id, prompt (truncated), error_message,
        task_type, and created_at.
    """
    conditions = [Task.status == TaskStatus.FAILED]
    if user_id is not None:
        conditions.append(Task.user_id == user_id)

    query = (
        select(Task)
        .where(and_(*conditions))
        .order_by(Task.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(query)
    tasks = result.scalars().all()

    return [
        {
            "id": str(t.id),
            "prompt": (t.prompt[:80] + "…") if len(t.prompt) > 80 else t.prompt,
            "error_message": t.error_message or "Unknown error",
            "task_type": t.task_type.value if hasattr(t.task_type, "value") else str(t.task_type),
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in tasks
    ]


async def get_stuck_tasks(
    db: AsyncSession,
    *,
    threshold_minutes: int = STUCK_THRESHOLD_MINUTES,
    user_id: Optional[UUID] = None,
) -> list[dict[str, Any]]:
    """Return tasks that have been processing longer than the threshold.

    Args:
        db: Async database session.
        threshold_minutes: Minutes after which a processing task is "stuck".
        user_id: Optional user scope.

    Returns:
        List of dicts with task id, prompt (truncated), task_type,
        created_at, and minutes_elapsed.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=threshold_minutes)

    conditions = [
        Task.status == TaskStatus.PROCESSING,
        Task.created_at < cutoff,
    ]
    if user_id is not None:
        conditions.append(Task.user_id == user_id)

    query = (
        select(Task)
        .where(and_(*conditions))
        .order_by(Task.created_at.asc())
    )
    result = await db.execute(query)
    tasks = result.scalars().all()

    now = datetime.now(timezone.utc)
    return [
        {
            "id": str(t.id),
            "prompt": (t.prompt[:80] + "…") if len(t.prompt) > 80 else t.prompt,
            "task_type": t.task_type.value if hasattr(t.task_type, "value") else str(t.task_type),
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "minutes_elapsed": round(
                (now - t.created_at.replace(tzinfo=timezone.utc)).total_seconds() / 60, 1
            )
            if t.created_at
            else None,
        }
        for t in tasks
    ]
