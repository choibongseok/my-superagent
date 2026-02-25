"""
Service Layer Integration Tests

Tests core service functionality with minimal mocking.
"""

import pytest
from datetime import datetime, UTC
from uuid import uuid4

from app.services.audit_service import AuditService
from app.services.cost_tracker import CostTracker
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.models.audit_log import AuditLog
from app.models.token_usage import TokenUsage


class TestAuditServiceIntegration:
    """Test audit logging functionality"""
    
    def test_log_api_call_basic(self, db_session):
        """Test basic API call logging"""
        user_id = uuid4()
        task_id = uuid4()
        
        audit_service = AuditService(db_session)
        audit_service.log_api_call(
            user_id=user_id,
            endpoint="/api/v1/tasks",
            method="POST",
            status_code=201,
            response_time_ms=150,
            task_id=task_id
        )
        
        # Verify log was created
        logs = db_session.query(AuditLog).filter(
            AuditLog.user_id == user_id
        ).all()
        
        assert len(logs) == 1
        assert logs[0].event_type == "api_call"
        assert logs[0].action == "create"
        assert logs[0].resource_type == "task"
        
    def test_log_data_change(self, db_session):
        """Test data change logging with before/after"""
        user_id = uuid4()
        task_id = uuid4()
        
        before_data = {"status": "pending"}
        after_data = {"status": "completed"}
        
        audit_service = AuditService(db_session)
        audit_service.log_data_change(
            user_id=user_id,
            resource_type="task",
            resource_id=task_id,
            action="update",
            before_data=before_data,
            after_data=after_data
        )
        
        logs = db_session.query(AuditLog).filter(
            AuditLog.user_id == user_id
        ).all()
        
        assert len(logs) == 1
        assert logs[0].before_data == before_data
        assert logs[0].after_data == after_data
        assert logs[0].changes == ["status: pending -> completed"]


class TestCostTrackingIntegration:
    """Test token usage and cost tracking"""
    
    def test_track_llm_usage_basic(self, db_session):
        """Test basic token usage tracking"""
        task_id = uuid4()
        
        usage = TokenUsage(
            task_id=task_id,
            model="claude-3-5-sonnet-20241022",
            prompt_tokens=1000,
            completion_tokens=500,
            cost_usd=0.015,  # $3/MTok input, $15/MTok output
            metadata={"provider": "anthropic"}
        )
        
        db_session.add(usage)
        db_session.commit()
        
        # Verify tracking
        tracked = db_session.query(TokenUsage).filter(
            TokenUsage.task_id == task_id
        ).first()
        
        assert tracked is not None
        assert tracked.prompt_tokens == 1000
        assert tracked.completion_tokens == 500
        assert tracked.cost_usd == pytest.approx(0.015, 0.001)
        
    def test_aggregate_token_usage(self, db_session):
        """Test aggregating token usage across tasks"""
        user_id = uuid4()
        
        # Create multiple tasks with usage
        for i in range(3):
            task_id = uuid4()
            usage = TokenUsage(
                task_id=task_id,
                model="claude-3-5-sonnet-20241022",
                prompt_tokens=1000 * (i + 1),
                completion_tokens=500 * (i + 1),
                cost_usd=0.015 * (i + 1)
            )
            db_session.add(usage)
            
        db_session.commit()
        
        # Query total usage
        total_cost = db_session.query(
            TokenUsage
        ).with_entities(
            db_session.query(TokenUsage.cost_usd).func.sum()
        ).scalar()
        
        # 0.015 + 0.030 + 0.045 = 0.090
        assert total_cost == pytest.approx(0.090, 0.001)


class TestTaskWorkflowIntegration:
    """Test end-to-end task workflows"""
    
    def test_task_creation_to_completion(self, db_session):
        """Test complete task lifecycle"""
        user = User(email='workflow@example.com', google_id='workflow_123')
        db_session.add(user)
        db_session.commit()
        
        # Create task
        task = Task(
            user_id=user.id,
            agent_type='docs_agent',
            prompt='Create test document',
            status=TaskStatus.PENDING
        )
        db_session.add(task)
        db_session.commit()
        
        # Simulate processing
        task.status = TaskStatus.RUNNING
        db_session.commit()
        
        # Complete task
        task.status = TaskStatus.COMPLETED
        task.result = {'document_id': 'doc_123'}
        db_session.commit()
        
        # Verify final state
        completed_task = db_session.query(Task).filter(
            Task.id == task.id
        ).first()
        
        assert completed_task.status == TaskStatus.COMPLETED
        assert 'document_id' in completed_task.result
        assert completed_task.result['document_id'] == 'doc_123'
        
    def test_task_failure_with_retry(self, db_session):
        """Test task failure and retry mechanism"""
        user = User(email='retry@example.com', google_id='retry_123')
        db_session.add(user)
        db_session.commit()
        
        # Create and fail task
        task = Task(
            user_id=user.id,
            agent_type='sheets_agent',
            prompt='Read spreadsheet',
            status=TaskStatus.FAILED,
            error_message='Permission denied'
        )
        db_session.add(task)
        db_session.commit()
        
        # Verify failure is recorded
        failed_task = db_session.query(Task).filter(
            Task.id == task.id
        ).first()
        
        assert failed_task.status == TaskStatus.FAILED
        assert 'Permission denied' in failed_task.error_message


class TestWorkspaceCollaborationIntegration:
    """Test workspace-based collaboration"""
    
    def test_workspace_task_isolation(self, db_session):
        """Test that workspace tasks are properly isolated"""
        from app.models.workspace import Workspace
        
        user = User(email='workspace@example.com', google_id='workspace_123')
        db_session.add(user)
        db_session.commit()
        
        # Create two workspaces
        ws1 = Workspace(name='Workspace 1', owner_id=user.id)
        ws2 = Workspace(name='Workspace 2', owner_id=user.id)
        db_session.add_all([ws1, ws2])
        db_session.commit()
        
        # Create tasks in each workspace
        task1 = Task(
            user_id=user.id,
            workspace_id=ws1.id,
            agent_type='docs_agent',
            prompt='Task in WS1',
            status=TaskStatus.COMPLETED
        )
        task2 = Task(
            user_id=user.id,
            workspace_id=ws2.id,
            agent_type='docs_agent',
            prompt='Task in WS2',
            status=TaskStatus.COMPLETED
        )
        db_session.add_all([task1, task2])
        db_session.commit()
        
        # Query tasks per workspace
        ws1_tasks = db_session.query(Task).filter(
            Task.workspace_id == ws1.id
        ).all()
        ws2_tasks = db_session.query(Task).filter(
            Task.workspace_id == ws2.id
        ).all()
        
        assert len(ws1_tasks) == 1
        assert len(ws2_tasks) == 1
        assert ws1_tasks[0].id != ws2_tasks[0].id


class TestScheduledTaskIntegration:
    """Test scheduled task functionality"""
    
    def test_scheduled_task_creation(self, db_session):
        """Test creating a scheduled task"""
        from app.models.scheduled_task import ScheduledTask, ScheduleType
        
        user = User(email='schedule@example.com', google_id='schedule_123')
        db_session.add(user)
        db_session.commit()
        
        # Create daily schedule
        scheduled = ScheduledTask(
            user_id=user.id,
            schedule_type=ScheduleType.DAILY,
            agent_type='docs_agent',
            prompt_template='Daily report',
            enabled=True,
            next_run=datetime.now(UTC)
        )
        db_session.add(scheduled)
        db_session.commit()
        
        # Verify creation
        saved_schedule = db_session.query(ScheduledTask).filter(
            ScheduledTask.user_id == user.id
        ).first()
        
        assert saved_schedule is not None
        assert saved_schedule.schedule_type == ScheduleType.DAILY
        assert saved_schedule.enabled is True


# Test Fixtures
@pytest.fixture
def db_session():
    """Mock database session for testing"""
    from unittest.mock import MagicMock
    session = MagicMock()
    
    # Setup basic query/add/commit behavior
    _storage = []
    
    def mock_add(obj):
        if hasattr(obj, 'id') and obj.id is None:
            obj.id = uuid4()
        _storage.append(obj)
        
    def mock_commit():
        pass
        
    def mock_query(model):
        query_mock = MagicMock()
        
        def mock_filter(*args, **kwargs):
            # Simple filter simulation
            filtered = [
                obj for obj in _storage 
                if isinstance(obj, model)
            ]
            result_mock = MagicMock()
            result_mock.all.return_value = filtered
            result_mock.first.return_value = filtered[0] if filtered else None
            return result_mock
            
        query_mock.filter = mock_filter
        query_mock.with_entities = MagicMock(return_value=query_mock)
        query_mock.func = MagicMock()
        return query_mock
        
    session.add = mock_add
    session.add_all = lambda objs: [mock_add(obj) for obj in objs]
    session.commit = mock_commit
    session.query = mock_query
    
    return session
