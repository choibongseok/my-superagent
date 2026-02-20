"""Celery beat task: execute due recurring schedules (#221).

Runs periodically (every 60s via Celery beat) and dispatches any
ScheduledTask whose ``next_run_at <= now`` and ``is_active == True``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from croniter import croniter

from app.agents.celery_app import celery_app
from app.core.async_runner import run_async
from app.models.scheduled_task import ScheduleType, ScheduledTask
from app.models.task import Task, TaskStatus

logger = logging.getLogger(__name__)


def _next_run_after(
    schedule_type: ScheduleType,
    anchor: datetime,
    cron_expr: str | None,
    last_run: datetime,
) -> datetime | None:
    """Compute the next occurrence after *last_run*.

    Returns ``None`` for ONCE schedules (they don't repeat).
    """
    if schedule_type == ScheduleType.ONCE:
        return None

    if schedule_type == ScheduleType.CRON:
        if not cron_expr:
            return None
        cron = croniter(cron_expr, last_run)
        return cron.get_next(datetime).replace(tzinfo=timezone.utc)

    delta_map = {
        ScheduleType.DAILY: timedelta(days=1),
        ScheduleType.WEEKLY: timedelta(weeks=1),
        ScheduleType.MONTHLY: timedelta(days=30),
    }
    delta = delta_map.get(schedule_type)
    if delta is None:
        return None

    candidate = last_run + delta
    return candidate


async def _execute_due_schedules() -> int:
    """Find and dispatch all due scheduled tasks. Returns count dispatched."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.database import AsyncSessionLocal

    now = datetime.now(tz=timezone.utc)
    dispatched = 0

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ScheduledTask).where(
                ScheduledTask.is_active == True,  # noqa: E712
                ScheduledTask.next_run_at <= now,
            )
        )
        schedules = result.scalars().all()

        for sched in schedules:
            try:
                dispatched += await _dispatch_one(sched, db, now)
            except Exception as exc:
                logger.error(f"Failed to dispatch schedule {sched.id}: {exc}")
                sched.last_error = str(exc)[:500]
                sched.failure_count += 1

        await db.commit()

    return dispatched


async def _dispatch_one(sched: ScheduledTask, db, now: datetime) -> int:
    """Dispatch a single scheduled task. Returns 1 on success, 0 on skip."""
    from app.agents.celery_app import (
        process_docs_task,
        process_research_task,
        process_sheets_task,
        process_slides_task,
    )

    # Check max_runs limit
    if sched.max_runs is not None and sched.run_count >= sched.max_runs:
        sched.is_active = False
        logger.info(f"Schedule {sched.id} reached max_runs={sched.max_runs}, deactivating.")
        return 0

    # Create a new Task record
    new_task_id = uuid4()
    task = Task(
        id=new_task_id,
        user_id=sched.user_id,
        prompt=sched.prompt,
        task_type=sched.task_type,
        status=TaskStatus.PENDING,
        task_metadata={
            "source": "recurring_schedule",
            "schedule_id": str(sched.id),
            "run_number": sched.run_count + 1,
        },
    )
    db.add(task)
    await db.flush()

    # Dispatch to Celery
    task_id_str = str(new_task_id)
    user_id_str = str(sched.user_id)
    task_type = str(sched.task_type.value if hasattr(sched.task_type, "value") else sched.task_type)

    dispatch_map = {
        "research": lambda: process_research_task.apply_async(
            args=[task_id_str, sched.prompt, user_id_str]
        ),
        "docs": lambda: process_docs_task.apply_async(
            args=[task_id_str, sched.prompt, user_id_str, sched.name]
        ),
        "sheets": lambda: process_sheets_task.apply_async(
            args=[task_id_str, sched.prompt, user_id_str, sched.name]
        ),
        "slides": lambda: process_slides_task.apply_async(
            args=[task_id_str, sched.prompt, user_id_str, sched.name]
        ),
    }

    dispatcher = dispatch_map.get(task_type)
    if not dispatcher:
        sched.last_error = f"Unknown task type: {task_type}"
        sched.failure_count += 1
        return 0

    celery_result = dispatcher()
    task.celery_task_id = celery_result.id
    task.status = TaskStatus.PROCESSING

    # Update schedule state
    sched.last_run_at = now
    sched.last_task_id = new_task_id
    sched.run_count += 1
    sched.success_count += 1
    sched.last_error = None

    # Compute next_run
    next_run = _next_run_after(
        sched.schedule_type, sched.scheduled_at, sched.cron_expression, now
    )
    sched.next_run_at = next_run

    # Deactivate ONCE schedules
    if sched.schedule_type == ScheduleType.ONCE:
        sched.is_active = False

    logger.info(
        f"Dispatched schedule {sched.id} ({sched.name}) → task {new_task_id}, "
        f"next_run={next_run}"
    )
    return 1


# ---------------------------------------------------------------------------
# Celery beat task (registered on the celery_app)
# ---------------------------------------------------------------------------

@celery_app.task(name="scheduler.execute_due_schedules")
def execute_due_schedules():
    """Celery task: find and dispatch all due scheduled tasks."""
    count = run_async(_execute_due_schedules())
    logger.info(f"Scheduler tick: dispatched {count} task(s)")
    return {"dispatched": count}


# Register the beat schedule (every 60 seconds)
celery_app.conf.beat_schedule = {
    **getattr(celery_app.conf, "beat_schedule", {}),
    "execute-due-schedules-every-60s": {
        "task": "scheduler.execute_due_schedules",
        "schedule": 60.0,  # seconds
    },
}
