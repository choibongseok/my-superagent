"""
Tests for Audit Log functionality
"""
import pytest
from datetime import datetime, UTC, timedelta
from uuid import uuid4
from fastapi import status
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.services.audit_service import AuditService


class TestAuditLogModel:
    """Test AuditLog model"""
    
    def test_audit_log_creation(self, db: Session):
        """Test creating audit log entry"""
        log = AuditLog(
            event_type="api_call",
            action="read",
            resource_type="task",
            resource_id=str(uuid4()),
            user_id=uuid4(),
            ip_address="192.168.1.1",
            method="GET",
            endpoint="/api/v1/tasks/123",
            status_code=200,
            created_at=datetime.now(UTC),
        )
        
        db.add(log)
        db.commit()
        db.refresh(log)
        
        assert log.id is not None
        assert log.event_type == "api_call"
        assert log.action == "read"
    
    def test_audit_log_with_data_changes(self, db: Session):
        """Test audit log with before/after data"""
        log = AuditLog(
            event_type="data_change",
            action="update",
            resource_type="task",
            resource_id=str(uuid4()),
            user_id=uuid4(),
            before_data={"status": "pending"},
            after_data={"status": "completed"},
            changes={"status": {"from": "pending", "to": "completed"}},
            created_at=datetime.now(UTC),
        )
        
        db.add(log)
        db.commit()
        db.refresh(log)
        
        assert log.before_data == {"status": "pending"}
        assert log.after_data == {"status": "completed"}
        assert log.changes["status"]["from"] == "pending"
    
    def test_audit_log_to_dict(self, db: Session):
        """Test converting audit log to dictionary"""
        log = AuditLog(
            event_type="auth_event",
            action="login",
            resource_type="user",
            resource_id=str(uuid4()),
            user_id=uuid4(),
            created_at=datetime.now(UTC),
        )
        
        db.add(log)
        db.commit()
        db.refresh(log)
        
        log_dict = log.to_dict()
        
        assert log_dict["id"] == str(log.id)
        assert log_dict["event_type"] == "auth_event"
        assert log_dict["action"] == "login"
        assert "created_at" in log_dict


class TestAuditService:
    """Test AuditService"""
    
    def test_log_api_call(self, db: Session, mock_request):
        """Test logging an API call"""
        user_id = uuid4()
        
        log = AuditService.log_api_call(
            db=db,
            request=mock_request,
            user_id=user_id,
            resource_type="task",
            resource_id="test-task-123",
            action="read",
            status_code=200,
        )
        
        assert log.id is not None
        assert log.event_type == "api_call"
        assert log.user_id == user_id
        assert log.method == "GET"
    
    def test_log_data_change(self, db: Session):
        """Test logging a data modification"""
        user_id = uuid4()
        resource_id = str(uuid4())
        
        log = AuditService.log_data_change(
            db=db,
            user_id=user_id,
            resource_type="task",
            resource_id=resource_id,
            action="update",
            before_data={"title": "Old Title"},
            after_data={"title": "New Title"},
            changes={"title": {"from": "Old Title", "to": "New Title"}},
        )
        
        assert log.id is not None
        assert log.event_type == "data_change"
        assert log.action == "update"
        assert log.changes["title"]["from"] == "Old Title"
    
    def test_log_auth_event(self, db: Session):
        """Test logging an authentication event"""
        user_id = uuid4()
        
        log = AuditService.log_auth_event(
            db=db,
            user_id=user_id,
            action="login",
            ip_address="192.168.1.100",
            extra_metadata={"login_method": "google_oauth"},
        )
        
        assert log.id is not None
        assert log.event_type == "auth_event"
        assert log.action == "login"
        assert log.ip_address == "192.168.1.100"
    
    def test_get_logs_with_filters(self, db: Session):
        """Test querying logs with filters"""
        user_id = uuid4()
        
        # Create multiple log entries
        for i in range(5):
            AuditService.log_api_call(
                db=db,
                request=mock_request(),
                user_id=user_id,
                resource_type="task",
                resource_id=f"task-{i}",
                action="read",
                status_code=200,
            )
        
        # Query logs
        logs = AuditService.get_logs(
            db=db,
            user_id=user_id,
            event_type="api_call",
            limit=10,
        )
        
        assert len(logs) == 5
        assert all(log.user_id == user_id for log in logs)
    
    def test_get_resource_history(self, db: Session):
        """Test getting history for a specific resource"""
        resource_id = str(uuid4())
        user_id = uuid4()
        
        # Create log entries for the same resource
        for action in ["create", "update", "read"]:
            AuditService.log_data_change(
                db=db,
                user_id=user_id,
                resource_type="task",
                resource_id=resource_id,
                action=action,
            )
        
        # Get history
        history = AuditService.get_resource_history(
            db=db,
            resource_type="task",
            resource_id=resource_id,
        )
        
        assert len(history) == 3
        actions = [log.action for log in history]
        assert "create" in actions
        assert "update" in actions
        assert "read" in actions
    
    def test_get_user_activity(self, db: Session):
        """Test getting activity for a specific user"""
        user_id = uuid4()
        
        # Create various activities
        AuditService.log_auth_event(db=db, user_id=user_id, action="login")
        AuditService.log_api_call(
            db=db,
            request=mock_request(),
            user_id=user_id,
            action="read",
            status_code=200,
        )
        AuditService.log_data_change(
            db=db,
            user_id=user_id,
            resource_type="task",
            resource_id=str(uuid4()),
            action="create",
        )
        
        # Get activity
        activity = AuditService.get_user_activity(
            db=db,
            user_id=user_id,
        )
        
        assert len(activity) == 3
        event_types = [log.event_type for log in activity]
        assert "auth_event" in event_types
        assert "api_call" in event_types
        assert "data_change" in event_types


class TestAuditAPI:
    """Test Audit API endpoints"""
    
    def test_get_audit_logs_authenticated(self, client, auth_headers, db: Session):
        """Test getting audit logs with authentication"""
        response = client.get(
            "/api/v1/audit/logs",
            headers=auth_headers,
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "logs" in data
        assert "total" in data
        assert "offset" in data
        assert "limit" in data
    
    def test_get_audit_logs_unauthenticated(self, client):
        """Test that unauthenticated requests are rejected"""
        response = client.get("/api/v1/audit/logs")
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_get_resource_history(self, client, auth_headers, db: Session):
        """Test getting resource history"""
        resource_id = str(uuid4())
        
        response = client.get(
            f"/api/v1/audit/resource/task/{resource_id}",
            headers=auth_headers,
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.json(), list)
    
    def test_get_my_activity(self, client, auth_headers):
        """Test getting own activity"""
        response = client.get(
            "/api/v1/audit/my-activity",
            headers=auth_headers,
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.json(), list)
    
    def test_get_audit_stats(self, client, auth_headers):
        """Test getting audit statistics"""
        response = client.get(
            "/api/v1/audit/stats",
            headers=auth_headers,
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "total_logs" in data
        assert "event_types" in data
        assert "actions" in data
    
    def test_get_audit_logs_with_filters(self, client, auth_headers):
        """Test filtering audit logs"""
        response = client.get(
            "/api/v1/audit/logs",
            headers=auth_headers,
            params={
                "event_type": "api_call",
                "limit": 50,
            },
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["limit"] == 50


# Fixtures
@pytest.fixture
def mock_request():
    """Mock FastAPI request object"""
    class MockRequest:
        def __init__(self):
            self.method = "GET"
            self.url = type('obj', (object,), {'path': '/api/v1/test'})()
            self.client = type('obj', (object,), {'host': '127.0.0.1'})()
            self.headers = {"user-agent": "test-client/1.0"}
    
    return MockRequest()
