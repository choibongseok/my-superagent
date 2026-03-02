"""Tests for Tasks API v2 endpoints."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task as TaskModel, TaskStatus
from app.models.user import User


@pytest.mark.asyncio
class TestTasksV2:
    """Test Tasks API v2 endpoints."""
    
    @pytest.fixture
    def mock_user(self):
        """Create mock user."""
        return User(
            id=uuid4(),
            email="test@example.com",
            name="Test User",
            is_admin=False,
        )
    
    @pytest.fixture
    def mock_task(self, mock_user):
        """Create mock task."""
        task_id = uuid4()
        return TaskModel(
            id=task_id,
            user_id=mock_user.id,
            prompt="Test task",
            task_type="research",
            status=TaskStatus.COMPLETED,
            task_metadata={
                "priority": 5,
                "tags": ["test", "research"],
                "estimated_duration_seconds": 120,
                "api_version": "v2",
            },
            llm_provider="openai",
            llm_model="gpt-4",
            result={"data": "test result"},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    
    async def test_create_task_v2_basic(self, client, mock_user):
        """Test creating a basic task in v2."""
        with patch("app.api.dependencies.get_current_user", return_value=mock_user):
            with patch("app.agents.celery_app.process_research_task") as mock_celery:
                mock_celery.apply_async.return_value = MagicMock(id="celery-123")
                
                response = client.post(
                    "/api/v2/tasks/",
                    json={
                        "prompt": "Research AI trends",
                        "task_type": "research",
                        "llm_provider": "openai",
                        "llm_model": "gpt-4",
                    },
                    headers={"X-API-Version": "v2"}
                )
                
                assert response.status_code == status.HTTP_201_CREATED
                data = response.json()
                assert data["prompt"] == "Research AI trends"
                assert data["task_type"] == "research"
                assert data["priority"] == 0  # Default priority
                assert data["tags"] == []  # Default tags
    
    async def test_create_task_v2_with_priority(self, client, mock_user):
        """Test creating a task with priority in v2."""
        with patch("app.api.dependencies.get_current_user", return_value=mock_user):
            with patch("app.agents.celery_app.process_research_task") as mock_celery:
                mock_celery.apply_async.return_value = MagicMock(id="celery-123")
                
                response = client.post(
                    "/api/v2/tasks/",
                    json={
                        "prompt": "Urgent research",
                        "task_type": "research",
                        "llm_provider": "openai",
                        "llm_model": "gpt-4",
                        "priority": 10,
                        "tags": ["urgent", "research"],
                        "estimated_duration_seconds": 180,
                    },
                    headers={"X-API-Version": "v2"}
                )
                
                assert response.status_code == status.HTTP_201_CREATED
                data = response.json()
                assert data["priority"] == 10
                assert "urgent" in data["tags"]
                assert data["estimated_duration_seconds"] == 180
                
                # Verify Celery task was called with priority
                mock_celery.apply_async.assert_called_once()
                call_kwargs = mock_celery.apply_async.call_args[1]
                assert call_kwargs["priority"] == 10
    
    async def test_create_task_v2_invalid_type(self, client, mock_user):
        """Test creating task with invalid type returns structured error."""
        with patch("app.api.dependencies.get_current_user", return_value=mock_user):
            response = client.post(
                "/api/v2/tasks/",
                json={
                    "prompt": "Test",
                    "task_type": "invalid_type",
                    "llm_provider": "openai",
                    "llm_model": "gpt-4",
                },
                headers={"X-API-Version": "v2"}
            )
            
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            error = response.json()["detail"]
            assert error["error"] == "invalid_task_type"
            assert "message" in error
            assert error["provided"] == "invalid_type"
    
    async def test_list_tasks_v2_with_pagination(self, client, mock_user):
        """Test listing tasks with enhanced pagination in v2."""
        with patch("app.api.dependencies.get_current_user", return_value=mock_user):
            with patch("app.core.database.get_db") as mock_db:
                # Mock database session
                mock_session = AsyncMock(spec=AsyncSession)
                mock_db.return_value = mock_session
                
                # Mock query results
                mock_session.execute.return_value.scalars.return_value.all.return_value = []
                mock_session.execute.return_value.scalar_one.return_value = 0
                
                response = client.get(
                    "/api/v2/tasks/?page=1&page_size=20",
                    headers={"X-API-Version": "v2"}
                )
                
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                
                # Check v2 structure
                assert "items" in data
                assert "pagination" in data
                
                # Check pagination metadata
                pagination = data["pagination"]
                assert "total" in pagination
                assert "page" in pagination
                assert "page_size" in pagination
                assert "total_pages" in pagination
                assert "has_next" in pagination
                assert "has_previous" in pagination
    
    async def test_list_tasks_v2_with_filters(self, client, mock_user):
        """Test listing tasks with multiple filters in v2."""
        with patch("app.api.dependencies.get_current_user", return_value=mock_user):
            response = client.get(
                "/api/v2/tasks/?status=completed&task_type=research&sort_by=created_at&sort_order=desc",
                headers={"X-API-Version": "v2"}
            )
            
            # Should not error even if no results
            assert response.status_code == status.HTTP_200_OK
    
    async def test_get_task_stats_v2(self, client, mock_user):
        """Test getting task statistics (v2 only feature)."""
        with patch("app.api.dependencies.get_current_user", return_value=mock_user):
            with patch("app.core.database.get_db") as mock_db:
                mock_session = AsyncMock(spec=AsyncSession)
                mock_db.return_value = mock_session
                
                # Mock status counts
                mock_session.execute.return_value.all.return_value = [
                    (TaskStatus.COMPLETED, 10),
                    (TaskStatus.FAILED, 2),
                    (TaskStatus.IN_PROGRESS, 3),
                ]
                
                response = client.get(
                    "/api/v2/tasks/stats",
                    headers={"X-API-Version": "v2"}
                )
                
                assert response.status_code == status.HTTP_200_OK
                stats = response.json()
                
                assert "total_tasks" in stats
                assert "pending" in stats
                assert "in_progress" in stats
                assert "completed" in stats
                assert "failed" in stats
                assert "cancelled" in stats
                assert "average_duration_seconds" in stats
    
    async def test_get_task_v2_not_found_structured_error(self, client, mock_user):
        """Test getting non-existent task returns structured error in v2."""
        task_id = uuid4()
        with patch("app.api.dependencies.get_current_user", return_value=mock_user):
            with patch("app.core.database.get_db") as mock_db:
                mock_session = AsyncMock(spec=AsyncSession)
                mock_db.return_value = mock_session
                mock_session.execute.return_value.scalar_one_or_none.return_value = None
                
                response = client.get(
                    f"/api/v2/tasks/{task_id}",
                    headers={"X-API-Version": "v2"}
                )
                
                assert response.status_code == status.HTTP_404_NOT_FOUND
                error = response.json()["detail"]
                assert error["error"] == "task_not_found"
                assert str(task_id) in error["message"]
                assert error["task_id"] == str(task_id)
    
    async def test_cancel_task_v2_not_cancellable(self, client, mock_user, mock_task):
        """Test cancelling completed task returns structured error in v2."""
        mock_task.status = TaskStatus.COMPLETED
        
        with patch("app.api.dependencies.get_current_user", return_value=mock_user):
            with patch("app.core.database.get_db") as mock_db:
                mock_session = AsyncMock(spec=AsyncSession)
                mock_db.return_value = mock_session
                mock_session.execute.return_value.scalar_one_or_none.return_value = mock_task
                
                response = client.delete(
                    f"/api/v2/tasks/{mock_task.id}",
                    headers={"X-API-Version": "v2"}
                )
                
                assert response.status_code == status.HTTP_400_BAD_REQUEST
                error = response.json()["detail"]
                assert error["error"] == "task_not_cancellable"
                assert error["current_status"] == "completed"
    
    async def test_v2_response_includes_enhanced_fields(self, client, mock_user, mock_task):
        """Test v2 responses include all enhanced fields."""
        with patch("app.api.dependencies.get_current_user", return_value=mock_user):
            with patch("app.core.database.get_db") as mock_db:
                mock_session = AsyncMock(spec=AsyncSession)
                mock_db.return_value = mock_session
                mock_session.execute.return_value.scalar_one_or_none.return_value = mock_task
                
                response = client.get(
                    f"/api/v2/tasks/{mock_task.id}",
                    headers={"X-API-Version": "v2"}
                )
                
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                
                # Check v2-specific fields
                assert "priority" in data
                assert "tags" in data
                assert "estimated_duration_seconds" in data
                assert "actual_duration_seconds" in data
                assert "retry_count" in data
                assert "celery_task_id" in data
                
                # Verify values from metadata
                assert data["priority"] == 5
                assert "test" in data["tags"]
                assert data["estimated_duration_seconds"] == 120


@pytest.mark.asyncio
class TestTasksV1V2Comparison:
    """Test differences between v1 and v2 responses."""
    
    @pytest.fixture
    def mock_user(self):
        """Create mock user."""
        return User(
            id=uuid4(),
            email="test@example.com",
            name="Test User",
        )
    
    async def test_pagination_structure_difference(self, client, mock_user):
        """Test pagination structure differs between v1 and v2."""
        with patch("app.api.dependencies.get_current_user", return_value=mock_user):
            with patch("app.core.database.get_db") as mock_db:
                mock_session = AsyncMock(spec=AsyncSession)
                mock_db.return_value = mock_session
                mock_session.execute.return_value.scalars.return_value.all.return_value = []
                mock_session.execute.return_value.scalar_one.return_value = 0
                
                # v1 response
                v1_response = client.get("/api/v1/tasks/")
                v1_data = v1_response.json()
                
                # v1 has flat structure
                assert "tasks" in v1_data
                assert "total" in v1_data
                assert "page" in v1_data
                
                # v2 response
                v2_response = client.get(
                    "/api/v2/tasks/",
                    headers={"X-API-Version": "v2"}
                )
                v2_data = v2_response.json()
                
                # v2 has nested structure
                assert "items" in v2_data
                assert "pagination" in v2_data
                assert "total_pages" in v2_data["pagination"]
                assert "has_next" in v2_data["pagination"]
    
    async def test_error_structure_difference(self, client, mock_user):
        """Test error structure differs between v1 and v2."""
        task_id = uuid4()
        with patch("app.api.dependencies.get_current_user", return_value=mock_user):
            with patch("app.core.database.get_db") as mock_db:
                mock_session = AsyncMock(spec=AsyncSession)
                mock_db.return_value = mock_session
                mock_session.execute.return_value.scalar_one_or_none.return_value = None
                
                # v1 error (simple string)
                v1_response = client.get(f"/api/v1/tasks/{task_id}")
                assert v1_response.status_code == status.HTTP_404_NOT_FOUND
                v1_error = v1_response.json()
                assert isinstance(v1_error["detail"], str)
                
                # v2 error (structured object)
                v2_response = client.get(
                    f"/api/v2/tasks/{task_id}",
                    headers={"X-API-Version": "v2"}
                )
                assert v2_response.status_code == status.HTTP_404_NOT_FOUND
                v2_error = v2_response.json()["detail"]
                assert isinstance(v2_error, dict)
                assert "error" in v2_error
                assert "message" in v2_error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
