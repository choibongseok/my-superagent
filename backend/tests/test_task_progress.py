"""Tests for real-time task progress tracking (Phase 5).

Tests the POST /api/v1/tasks/{task_id}/progress endpoint and WebSocket integration.
"""

import pytest
from datetime import datetime, UTC
from uuid import uuid4

from app.models.task import Task, TaskStatus, TaskType


@pytest.mark.asyncio
async def test_update_task_progress(client, test_user, test_db):
    """Test updating task progress successfully."""
    # Create a test task
    task = Task(
        id=uuid4(),
        user_id=test_user.id,
        prompt="Test task",
        task_type=TaskType.DOCS,
        status=TaskStatus.PROCESSING,
    )
    test_db.add(task)
    await test_db.commit()
    
    # Update progress
    progress_data = {
        "progress_percentage": 50,
        "progress_message": "Halfway through processing",
        "progress_steps": {
            "current_step": 3,
            "total_steps": 6,
            "step_name": "Generating content"
        }
    }
    
    response = await client.post(
        f"/api/v1/tasks/{task.id}/progress",
        json=progress_data
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["task_id"] == str(task.id)
    assert data["progress_percentage"] == 50
    assert data["progress_message"] == "Halfway through processing"
    assert data["progress_steps"]["current_step"] == 3
    assert data["status"] == "processing"


@pytest.mark.asyncio
async def test_update_progress_sets_started_at(client, test_user, test_db):
    """Test that updating progress sets started_at timestamp."""
    task = Task(
        id=uuid4(),
        user_id=test_user.id,
        prompt="Test task",
        task_type=TaskType.DOCS,
        status=TaskStatus.PENDING,
    )
    test_db.add(task)
    await test_db.commit()
    
    assert task.started_at is None
    
    # Update progress to > 0
    progress_data = {"progress_percentage": 10, "progress_message": "Starting"}
    
    response = await client.post(
        f"/api/v1/tasks/{task.id}/progress",
        json=progress_data
    )
    
    assert response.status_code == 200
    
    # Refresh task from DB
    await test_db.refresh(task)
    assert task.started_at is not None


@pytest.mark.asyncio
async def test_cannot_update_completed_task_progress(client, test_user, test_db):
    """Test that progress updates fail on completed tasks."""
    task = Task(
        id=uuid4(),
        user_id=test_user.id,
        prompt="Test task",
        task_type=TaskType.DOCS,
        status=TaskStatus.COMPLETED,
        completed_at=datetime.now(UTC),
    )
    test_db.add(task)
    await test_db.commit()
    
    progress_data = {"progress_percentage": 100}
    
    response = await client.post(
        f"/api/v1/tasks/{task.id}/progress",
        json=progress_data
    )
    
    assert response.status_code == 400
    assert "completed" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_cannot_update_failed_task_progress(client, test_user, test_db):
    """Test that progress updates fail on failed tasks."""
    task = Task(
        id=uuid4(),
        user_id=test_user.id,
        prompt="Test task",
        task_type=TaskType.DOCS,
        status=TaskStatus.FAILED,
        error_message="Some error",
    )
    test_db.add(task)
    await test_db.commit()
    
    progress_data = {"progress_percentage": 50}
    
    response = await client.post(
        f"/api/v1/tasks/{task.id}/progress",
        json=progress_data
    )
    
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_progress_update_partial_fields(client, test_user, test_db):
    """Test that progress updates work with partial field updates."""
    task = Task(
        id=uuid4(),
        user_id=test_user.id,
        prompt="Test task",
        task_type=TaskType.DOCS,
        status=TaskStatus.PROCESSING,
        progress_percentage=25,
        progress_message="Initial message",
    )
    test_db.add(task)
    await test_db.commit()
    
    # Update only percentage
    response = await client.post(
        f"/api/v1/tasks/{task.id}/progress",
        json={"progress_percentage": 75}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["progress_percentage"] == 75
    assert data["progress_message"] == "Initial message"  # Unchanged


@pytest.mark.asyncio
async def test_progress_update_validates_percentage(client, test_user, test_db):
    """Test that progress percentage is validated (0-100)."""
    task = Task(
        id=uuid4(),
        user_id=test_user.id,
        prompt="Test task",
        task_type=TaskType.DOCS,
        status=TaskStatus.PROCESSING,
    )
    test_db.add(task)
    await test_db.commit()
    
    # Try invalid percentage > 100
    response = await client.post(
        f"/api/v1/tasks/{task.id}/progress",
        json={"progress_percentage": 150}
    )
    
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_progress_update_access_control(client, test_user, test_db):
    """Test that users can only update their own tasks."""
    other_user_id = uuid4()
    
    task = Task(
        id=uuid4(),
        user_id=other_user_id,  # Different user
        prompt="Test task",
        task_type=TaskType.DOCS,
        status=TaskStatus.PROCESSING,
    )
    test_db.add(task)
    await test_db.commit()
    
    response = await client.post(
        f"/api/v1/tasks/{task.id}/progress",
        json={"progress_percentage": 50}
    )
    
    assert response.status_code == 404  # Task not found (access denied)
