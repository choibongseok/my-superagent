"""
FactoryHub Integration Tests

FactoryHub Go 백엔드와의 통합 엔드포인트 테스트:
- POST /api/v1/factoryhub/callback (이벤트 수신)
- GET /api/v1/factoryhub/status (통합 상태 조회)
- POST /api/v1/factoryhub/webhook/task-complete (task 완료 웹훅)
"""

import pytest
from datetime import datetime, UTC
from unittest.mock import patch, MagicMock

from app.models.user import User
from app.models.task import Task


@pytest.fixture
def factoryhub_token():
    """Valid FactoryHub authentication token"""
    return "factoryhub-dev-token-12345"


@pytest.fixture
def invalid_token():
    """Invalid token for security testing"""
    return "invalid-token-xyz"


# ============================================================================
# Authentication Tests
# ============================================================================

def test_factoryhub_callback_missing_token(client, db_session):
    """Missing X-FactoryHub-Token header should return 401"""
    event_data = {
        "event_type": "task.create",
        "user_id": "user-123",
        "agent_type": "docs",
        "prompt": "Create a document"
    }
    
    response = client.post("/api/v1/factoryhub/callback", json=event_data)
    assert response.status_code == 401
    assert "Missing X-FactoryHub-Token" in response.json()["detail"]


def test_factoryhub_callback_invalid_token(client, db_session, invalid_token):
    """Invalid token should return 403"""
    event_data = {
        "event_type": "task.create",
        "user_id": "user-123",
        "agent_type": "docs",
        "prompt": "Create a document"
    }
    
    response = client.post(
        "/api/v1/factoryhub/callback",
        json=event_data,
        headers={"X-FactoryHub-Token": invalid_token}
    )
    assert response.status_code == 403
    assert "Invalid FactoryHub token" in response.json()["detail"]


# ============================================================================
# Task Creation via FactoryHub Event
# ============================================================================

def test_create_task_from_factoryhub_event(client, db_session, test_user, factoryhub_token):
    """FactoryHub task.create event should create AgentHQ task"""
    event_data = {
        "event_type": "task.create",
        "task_id": "factory-task-001",
        "user_id": str(test_user.id),
        "agent_type": "docs",
        "prompt": "Create a quarterly report",
        "metadata": {
            "project_id": "proj-123",
            "priority": "high"
        },
        "callback_url": "https://factoryhub.example.com/callback/task-001"
    }
    
    with patch("app.tasks.celery_app.send_task") as mock_celery:
        response = client.post(
            "/api/v1/factoryhub/callback",
            json=event_data,
            headers={"X-FactoryHub-Token": factoryhub_token}
        )
    
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert data["factory_task_id"] == "factory-task-001"
    assert "task_id" in data
    
    # Verify task was created in DB
    task = db_session.query(Task).filter(Task.id == data["task_id"]).first()
    assert task is not None
    assert task.user_id == test_user.id
    assert task.agent_type == "docs"
    assert task.prompt == "Create a quarterly report"
    assert task.status == "pending"
    assert task.metadata["source"] == "factoryhub"
    assert task.metadata["factory_task_id"] == "factory-task-001"
    assert task.metadata["callback_url"] == "https://factoryhub.example.com/callback/task-001"
    assert task.metadata["project_id"] == "proj-123"
    
    # Verify Celery task was queued
    mock_celery.assert_called_once_with(
        "app.tasks.run_agent_task",
        args=[str(task.id)],
        queue="agent_tasks"
    )


def test_create_task_user_not_found(client, db_session, factoryhub_token):
    """Event with non-existent user should return 404"""
    event_data = {
        "event_type": "task.create",
        "user_id": "00000000-0000-0000-0000-000000000000",  # Non-existent user
        "agent_type": "sheets",
        "prompt": "Analyze data"
    }
    
    response = client.post(
        "/api/v1/factoryhub/callback",
        json=event_data,
        headers={"X-FactoryHub-Token": factoryhub_token}
    )
    
    assert response.status_code == 404
    assert "User not found" in response.json()["detail"]


def test_cancel_task_not_implemented(client, db_session, factoryhub_token):
    """Task cancellation event should return not_implemented (Phase 5 feature)"""
    event_data = {
        "event_type": "task.cancel",
        "task_id": "factory-task-002",
        "user_id": "user-123",
        "agent_type": "docs",
        "prompt": ""
    }
    
    response = client.post(
        "/api/v1/factoryhub/callback",
        json=event_data,
        headers={"X-FactoryHub-Token": factoryhub_token}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "not_implemented"


def test_unknown_event_type(client, db_session, test_user, factoryhub_token):
    """Unknown event type should return 400"""
    event_data = {
        "event_type": "task.unknown",
        "user_id": str(test_user.id),
        "agent_type": "docs",
        "prompt": "Test"
    }
    
    response = client.post(
        "/api/v1/factoryhub/callback",
        json=event_data,
        headers={"X-FactoryHub-Token": factoryhub_token}
    )
    
    assert response.status_code == 400
    assert "Unknown event type" in response.json()["detail"]


# ============================================================================
# Integration Status
# ============================================================================

def test_get_integration_status_no_tasks(client, db_session, test_user, auth_headers):
    """Integration status with no FactoryHub tasks"""
    response = client.get("/api/v1/factoryhub/status", headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "AgentHQ"
    assert data["version"] == "1.0.0"
    assert data["status"] == "healthy"
    assert data["last_event_received"] is None
    assert data["total_events_processed"] == 0
    assert data["active_tasks"] == 0


def test_get_integration_status_with_tasks(client, db_session, test_user, auth_headers):
    """Integration status with existing FactoryHub tasks"""
    # Create 3 tasks from FactoryHub
    task1 = Task(
        user_id=test_user.id,
        agent_type="docs",
        prompt="Task 1",
        status="done",
        metadata={"source": "factoryhub", "factory_task_id": "ft-001"}
    )
    task2 = Task(
        user_id=test_user.id,
        agent_type="sheets",
        prompt="Task 2",
        status="running",
        metadata={"source": "factoryhub", "factory_task_id": "ft-002"}
    )
    task3 = Task(
        user_id=test_user.id,
        agent_type="slides",
        prompt="Task 3",
        status="pending",
        metadata={"source": "factoryhub", "factory_task_id": "ft-003"}
    )
    db_session.add_all([task1, task2, task3])
    db_session.commit()
    
    response = client.get("/api/v1/factoryhub/status", headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["total_events_processed"] == 3
    assert data["active_tasks"] == 2  # running + pending
    assert data["last_event_received"] is not None


# ============================================================================
# Task Complete Webhook (for FactoryHub to poll)
# ============================================================================

def test_task_complete_webhook_success(client, db_session, test_user, factoryhub_token):
    """Retrieve completed task status via webhook"""
    task = Task(
        user_id=test_user.id,
        agent_type="docs",
        prompt="Generate report",
        status="done",
        result={"document_id": "doc-123", "url": "https://docs.google.com/document/d/123"},
        metadata={"source": "factoryhub", "factory_task_id": "ft-100"}
    )
    db_session.add(task)
    db_session.commit()
    
    response = client.post(
        f"/api/v1/factoryhub/webhook/task-complete?task_id={task.id}",
        headers={"X-FactoryHub-Token": factoryhub_token}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["task_id"] == str(task.id)
    assert data["factory_task_id"] == "ft-100"
    assert data["status"] == "done"
    assert data["result"]["document_id"] == "doc-123"
    assert data["error"] is None


def test_task_complete_webhook_failed_task(client, db_session, test_user, factoryhub_token):
    """Retrieve failed task status"""
    task = Task(
        user_id=test_user.id,
        agent_type="sheets",
        prompt="Analyze data",
        status="failed",
        error="Google API rate limit exceeded",
        metadata={"source": "factoryhub", "factory_task_id": "ft-200"}
    )
    db_session.add(task)
    db_session.commit()
    
    response = client.post(
        f"/api/v1/factoryhub/webhook/task-complete?task_id={task.id}",
        headers={"X-FactoryHub-Token": factoryhub_token}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
    assert data["error"] == "Google API rate limit exceeded"
    assert data["result"] is None


def test_task_complete_webhook_not_factoryhub_task(client, db_session, test_user, factoryhub_token):
    """Non-FactoryHub task should return 403"""
    task = Task(
        user_id=test_user.id,
        agent_type="docs",
        prompt="Regular task",
        status="done",
        metadata={"source": "web_ui"}  # Not from FactoryHub
    )
    db_session.add(task)
    db_session.commit()
    
    response = client.post(
        f"/api/v1/factoryhub/webhook/task-complete?task_id={task.id}",
        headers={"X-FactoryHub-Token": factoryhub_token}
    )
    
    assert response.status_code == 403
    assert "Not a FactoryHub task" in response.json()["detail"]


def test_task_complete_webhook_task_not_found(client, db_session, factoryhub_token):
    """Non-existent task should return 404"""
    fake_task_id = "00000000-0000-0000-0000-000000000000"
    
    response = client.post(
        f"/api/v1/factoryhub/webhook/task-complete?task_id={fake_task_id}",
        headers={"X-FactoryHub-Token": factoryhub_token}
    )
    
    assert response.status_code == 404
    assert "Task not found" in response.json()["detail"]


# ============================================================================
# Edge Cases
# ============================================================================

def test_create_task_without_callback_url(client, db_session, test_user, factoryhub_token):
    """Task creation without callback_url should still succeed"""
    event_data = {
        "event_type": "task.create",
        "user_id": str(test_user.id),
        "agent_type": "slides",
        "prompt": "Create presentation"
        # No callback_url
    }
    
    with patch("app.tasks.celery_app.send_task"):
        response = client.post(
            "/api/v1/factoryhub/callback",
            json=event_data,
            headers={"X-FactoryHub-Token": factoryhub_token}
        )
    
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"


def test_create_task_minimal_metadata(client, db_session, test_user, factoryhub_token):
    """Task creation with minimal required fields"""
    event_data = {
        "event_type": "task.create",
        "user_id": str(test_user.id),
        "agent_type": "orchestrator",
        "prompt": "Complex workflow"
    }
    
    with patch("app.tasks.celery_app.send_task"):
        response = client.post(
            "/api/v1/factoryhub/callback",
            json=event_data,
            headers={"X-FactoryHub-Token": factoryhub_token}
        )
    
    assert response.status_code == 202
    task_id = response.json()["task_id"]
    
    task = db_session.query(Task).filter(Task.id == task_id).first()
    assert task.metadata["source"] == "factoryhub"
    assert task.metadata.get("factory_task_id") is None  # Not provided


# ============================================================================
# Security Tests
# ============================================================================

def test_status_requires_authentication(client, db_session):
    """Status endpoint requires JWT authentication (not FactoryHub token)"""
    response = client.get("/api/v1/factoryhub/status")
    assert response.status_code == 401


def test_webhook_requires_factoryhub_token(client, db_session, test_user):
    """Task complete webhook requires FactoryHub token, not JWT"""
    task = Task(
        user_id=test_user.id,
        agent_type="docs",
        prompt="Test",
        status="done",
        metadata={"source": "factoryhub"}
    )
    db_session.add(task)
    db_session.commit()
    
    # Try with JWT token (should fail)
    response = client.post(
        f"/api/v1/factoryhub/webhook/task-complete?task_id={task.id}"
        # No X-FactoryHub-Token header
    )
    assert response.status_code == 401
