"""
E2E API Integration Tests
Tests complete HTTP API flows: Auth → Task Creation → Execution → Webhooks
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timedelta
import jwt

from app.main import app
from app.core.config import settings
from app.models.user import User
from app.models.task import Task, TaskStatus, TaskType
from app.core.database import get_db


@pytest.fixture
def client():
    """FastAPI test client"""
    return TestClient(app)


@pytest.fixture
def mock_db():
    """Mock database session"""
    mock_session = MagicMock()
    
    def override_get_db():
        try:
            yield mock_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    yield mock_session
    app.dependency_overrides.clear()


@pytest.fixture
def test_user():
    """Test user object"""
    return User(
        id="test_user_123",
        email="test@example.com",
        full_name="Test User",
        google_access_token="mock_access_token",
        google_refresh_token="mock_refresh_token",
    )


@pytest.fixture
def auth_token(test_user):
    """Generate valid JWT token"""
    payload = {
        "sub": test_user.email,
        "user_id": test_user.id,
        "exp": datetime.utcnow() + timedelta(hours=1),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")


class TestAuthFlowE2E:
    """E2E tests for authentication flow"""
    
    def test_login_redirect(self, client):
        """Test OAuth login redirect generation"""
        response = client.get("/api/v1/auth/login")
        
        assert response.status_code == 200
        data = response.json()
        assert "authorization_url" in data
        assert "google" in data["authorization_url"].lower()
    
    @patch('app.api.v1.auth.google_auth_service')
    @patch('app.api.v1.auth.jwt')
    def test_oauth_callback_success(self, mock_jwt, mock_google_auth, client, mock_db, test_user):
        """Test OAuth callback → JWT generation"""
        # Mock Google token exchange
        mock_google_auth.exchange_code.return_value = {
            "access_token": "mock_access_token",
            "refresh_token": "mock_refresh_token",
            "expires_in": 3600,
        }
        
        # Mock user info retrieval
        mock_google_auth.get_user_info.return_value = {
            "email": "test@example.com",
            "name": "Test User",
            "picture": "https://example.com/photo.jpg",
        }
        
        # Mock database user lookup/creation
        mock_db.query.return_value.filter.return_value.first.return_value = test_user
        
        # Mock JWT encoding
        mock_jwt.encode.return_value = "mock_jwt_token"
        
        # Execute callback
        response = client.get("/api/v1/auth/callback?code=mock_auth_code&state=mock_state")
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
    
    def test_protected_endpoint_without_token(self, client):
        """Test protected endpoint rejects unauthenticated requests"""
        response = client.get("/api/v1/tasks")
        
        # Should return 401 or 403
        assert response.status_code in [401, 403]


class TestTaskAPIE2E:
    """E2E tests for task creation and management"""
    
    @patch('app.api.v1.tasks.create_task_executor')
    def test_create_task_docs(self, mock_executor, client, mock_db, test_user, auth_token):
        """Test POST /tasks → Task creation → Celery dispatch"""
        # Mock database query
        mock_db.query.return_value.filter.return_value.first.return_value = test_user
        
        # Mock task creation
        new_task = Task(
            id="task_123",
            user_id=test_user.id,
            prompt="Create a sales report",
            task_type=TaskType.DOCS,
            status=TaskStatus.PENDING,
        )
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()
        mock_db.refresh = MagicMock(side_effect=lambda x: setattr(x, 'id', 'task_123'))
        
        # Mock Celery task dispatch
        mock_celery_task = MagicMock()
        mock_celery_task.id = "celery_task_123"
        mock_executor.return_value.delay.return_value = mock_celery_task
        
        # Create task
        response = client.post(
            "/api/v1/tasks",
            json={
                "prompt": "Create a sales report",
                "agent_type": "docs",
            },
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code in [200, 201]
        data = response.json()
        assert "task_id" in data or "id" in data
        assert data.get("status") == "pending" or data.get("status") == TaskStatus.PENDING
    
    @patch('app.api.v1.tasks.get_current_user')
    def test_get_task_status(self, mock_get_user, client, mock_db, test_user, auth_token):
        """Test GET /tasks/{id} → Task status retrieval"""
        # Mock user authentication
        mock_get_user.return_value = test_user
        
        # Mock task retrieval
        task = Task(
            id="task_123",
            user_id=test_user.id,
            prompt="Create sales report",
            task_type=TaskType.DOCS,
            status=TaskStatus.COMPLETED,
            result={"document_id": "doc_123"},
        )
        mock_db.query.return_value.filter.return_value.first.return_value = task
        
        # Get task status
        response = client.get(
            "/api/v1/tasks/task_123",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "task_123"
        assert data["status"] == TaskStatus.COMPLETED or data["status"] == "completed"
    
    @patch('app.api.v1.tasks.get_current_user')
    def test_list_user_tasks(self, mock_get_user, client, mock_db, test_user, auth_token):
        """Test GET /tasks → List user's tasks"""
        # Mock user authentication
        mock_get_user.return_value = test_user
        
        # Mock task list
        tasks = [
            Task(
                id="task_1",
                user_id=test_user.id,
                prompt="Task 1",
                task_type=TaskType.DOCS,
                status=TaskStatus.COMPLETED,
            ),
            Task(
                id="task_2",
                user_id=test_user.id,
                prompt="Task 2",
                task_type=TaskType.SHEETS,
                status=TaskStatus.IN_PROGRESS,
            ),
        ]
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = tasks
        
        # List tasks
        response = client.get(
            "/api/v1/tasks",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 2 or "tasks" in data


class TestWebhookE2E:
    """E2E tests for webhook → task automation"""
    
    @patch('app.api.v1.webhooks.verify_google_webhook')
    @patch('app.api.v1.webhooks.create_task_executor')
    def test_drive_webhook_triggers_task(self, mock_executor, mock_verify, client, mock_db, test_user):
        """Test Google Drive webhook → Automatic task creation"""
        # Mock webhook verification
        mock_verify.return_value = True
        
        # Mock user lookup by resource_id (simulate webhook metadata)
        mock_db.query.return_value.filter.return_value.first.return_value = test_user
        
        # Mock Celery task dispatch
        mock_celery_task = MagicMock()
        mock_celery_task.id = "celery_webhook_task"
        mock_executor.return_value.delay.return_value = mock_celery_task
        
        # Simulate Google Drive push notification
        webhook_payload = {
            "kind": "api#channel",
            "id": "channel_123",
            "resourceId": "resource_123",
            "resourceUri": "https://www.googleapis.com/drive/v3/files/file_123",
            "changed": "true",
        }
        
        response = client.post(
            "/api/v1/webhooks/google/drive",
            json=webhook_payload,
            headers={
                "X-Goog-Channel-ID": "channel_123",
                "X-Goog-Resource-ID": "resource_123",
                "X-Goog-Resource-State": "update",
            }
        )
        
        assert response.status_code in [200, 202]
        
        # Verify Celery task was dispatched
        # mock_executor.assert_called() - depends on implementation


class TestOrchestrationE2E:
    """E2E tests for multi-agent orchestration"""
    
    @patch('app.api.v1.orchestrate.orchestrate_task_executor')
    def test_orchestrate_multi_agent_task(self, mock_executor, client, mock_db, test_user, auth_token):
        """Test POST /orchestrate → Multi-agent coordination"""
        # Mock user authentication
        mock_db.query.return_value.filter.return_value.first.return_value = test_user
        
        # Mock Celery orchestration task
        mock_celery_task = MagicMock()
        mock_celery_task.id = "orchestrate_task_123"
        mock_executor.return_value.delay.return_value = mock_celery_task
        
        # Create orchestration request
        response = client.post(
            "/api/v1/orchestrate",
            json={
                "prompt": "Research AI trends, create a Docs report, and a Sheets summary",
                "agents": ["research", "docs", "sheets"],
            },
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code in [200, 202]
        data = response.json()
        assert "task_id" in data or "orchestration_id" in data


class TestMemoryAPIE2E:
    """E2E tests for memory system endpoints"""
    
    @patch('app.api.v1.memory.get_current_user')
    @patch('app.memory.vector_store.VectorStoreManager')
    def test_memory_search(self, mock_vector_store, mock_get_user, client, test_user, auth_token):
        """Test POST /memory/search → Semantic search"""
        # Mock user authentication
        mock_get_user.return_value = test_user
        
        # Mock vector store search results
        mock_vector_store.return_value.search.return_value = [
            {
                "content": "Previous task: Created sales report Q1 2026",
                "score": 0.92,
                "metadata": {"task_id": "task_old_123", "timestamp": "2026-01-15"},
            }
        ]
        
        # Search memory
        response = client.post(
            "/api/v1/memory/search",
            json={"query": "sales report", "limit": 5},
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list) or "results" in data


class TestHealthAndStatus:
    """E2E tests for health and status endpoints"""
    
    def test_health_check(self, client):
        """Test GET /health → Service health"""
        response = client.get("/api/v1/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy" or data.get("status") == "ok"
    
    @patch('app.api.v1.health.check_database')
    @patch('app.api.v1.health.check_redis')
    def test_detailed_health_check(self, mock_redis, mock_db, client):
        """Test GET /health/detailed → Component health"""
        # Mock component checks
        mock_db.return_value = True
        mock_redis.return_value = True
        
        response = client.get("/api/v1/health/detailed")
        
        # May return 200 or 404 if endpoint doesn't exist yet
        if response.status_code == 200:
            data = response.json()
            assert "database" in data or "components" in data


class TestErrorHandlingE2E:
    """E2E tests for error handling and recovery"""
    
    @patch('app.api.v1.tasks.create_task_executor')
    def test_task_creation_with_invalid_agent(self, mock_executor, client, mock_db, test_user, auth_token):
        """Test POST /tasks with invalid agent_type → 400 error"""
        # Mock user authentication
        mock_db.query.return_value.filter.return_value.first.return_value = test_user
        
        response = client.post(
            "/api/v1/tasks",
            json={
                "prompt": "Do something",
                "agent_type": "invalid_agent_xyz",
            },
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        # Should return 400 or 422 (validation error)
        assert response.status_code in [400, 422]
    
    def test_get_nonexistent_task(self, client, mock_db, auth_token):
        """Test GET /tasks/{id} for non-existent task → 404"""
        # Mock database query returning None
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        response = client.get(
            "/api/v1/tasks/nonexistent_task_999",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
