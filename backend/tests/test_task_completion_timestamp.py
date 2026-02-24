"""Tests for Celery task status finalization timestamp updates."""

from uuid import uuid4

import pytest

from app.agents.celery_app import update_task_status
from app.models.task import Task as TaskModel, TaskStatus, TaskType
from app.models.user import User


@pytest.mark.asyncio
async def test_update_task_status_completed_sets_completed_at(db):
    user = User(
        id=uuid4(),
        email="timestamp-complete@example.com",
        is_active=True,
    )
    db.add(user)
    await db.commit()

    task = TaskModel(
        id=uuid4(),
        user_id=user.id,
        prompt="Summarize recent wins",
        task_type=TaskType.DOCS,
        status=TaskStatus.PENDING,
        task_metadata=None,
    )
    db.add(task)
    await db.commit()

    update_task_status(str(task.id), "completed", result={"content": "ok"})

    refreshed = await db.get(TaskModel, task.id)
    assert refreshed is not None
    await db.refresh(refreshed)

    assert refreshed.status == TaskStatus.COMPLETED
    assert refreshed.completed_at is not None
    assert refreshed.error_message is None
    assert refreshed.result == {"content": "ok"}


@pytest.mark.asyncio
async def test_update_task_status_failed_sets_completed_at(db):
    user = User(
        id=uuid4(),
        email="timestamp-failed@example.com",
        is_active=True,
    )
    db.add(user)
    await db.commit()

    task = TaskModel(
        id=uuid4(),
        user_id=user.id,
        prompt="Build slides",
        task_type=TaskType.SLIDES,
        status=TaskStatus.PENDING,
        task_metadata=None,
    )
    db.add(task)
    await db.commit()

    update_task_status(str(task.id), "failed", error="boom")

    refreshed = await db.get(TaskModel, task.id)
    assert refreshed is not None
    await db.refresh(refreshed)

    assert refreshed.status == TaskStatus.FAILED
    assert refreshed.completed_at is not None
    assert refreshed.error_message == "boom"