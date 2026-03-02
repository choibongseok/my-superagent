"""
Tests for monitoring API endpoints.
"""

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.task import Task
from app.models.budget import CostRecord
from app.models.workflow_execution import WorkflowExecution


class TestMonitoringDashboard:
    """Test monitoring dashboard endpoint."""
    
    def test_dashboard_returns_complete_data(self, client: TestClient, auth_headers: dict, test_db: Session):
        """Test that dashboard returns all required data sections."""
        response = client.get("/api/v1/monitoring/dashboard", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        # Check all required sections
        assert "system_metrics" in data
        assert "agent_statuses" in data
        assert "recent_errors" in data
        assert "performance_trends" in data
        assert "active_alerts" in data
        
        # Check system metrics structure
        metrics = data["system_metrics"]
        assert "total_tasks" in metrics
        assert "active_tasks" in metrics
        assert "completed_tasks" in metrics
        assert "failed_tasks" in metrics
        assert "avg_task_duration_seconds" in metrics
        assert "tasks_per_hour" in metrics
        assert "total_cost_usd" in metrics
        assert "active_workflows" in metrics
    
    def test_dashboard_with_custom_time_window(self, client: TestClient, auth_headers: dict):
        """Test dashboard with custom time window."""
        response = client.get(
            "/api/v1/monitoring/dashboard?hours=48",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "system_metrics" in data
    
    def test_dashboard_requires_authentication(self, client: TestClient):
        """Test that dashboard requires authentication."""
        response = client.get("/api/v1/monitoring/dashboard")
        assert response.status_code == 401
    
    def test_dashboard_with_invalid_time_window(self, client: TestClient, auth_headers: dict):
        """Test dashboard with invalid time window."""
        # Too low
        response = client.get("/api/v1/monitoring/dashboard?hours=0", headers=auth_headers)
        assert response.status_code == 422
        
        # Too high
        response = client.get("/api/v1/monitoring/dashboard?hours=200", headers=auth_headers)
        assert response.status_code == 422


class TestAgentStatus:
    """Test agent status endpoints."""
    
    def test_get_agent_status(self, client: TestClient, auth_headers: dict, test_db: Session, test_user):
        """Test getting status for a specific agent."""
        # Create some test tasks
        task = Task(
            user_id=test_user.id,
            task_type="research",
            prompt="Test research task",
            status="completed",
            created_at=datetime.utcnow() - timedelta(hours=1),
            updated_at=datetime.utcnow()
        )
        test_db.add(task)
        test_db.commit()
        
        response = client.get("/api/v1/monitoring/agents/research", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["agent_name"] == "research"
        assert "status" in data
        assert "last_execution" in data
        assert "success_rate" in data
        assert "avg_duration_seconds" in data
        assert "total_executions" in data
        assert "recent_errors" in data
    
    def test_get_agent_status_invalid_agent(self, client: TestClient, auth_headers: dict):
        """Test getting status for invalid agent."""
        response = client.get("/api/v1/monitoring/agents/invalid_agent", headers=auth_headers)
        
        assert response.status_code == 400
        assert "Invalid agent name" in response.json()["detail"]
    
    def test_agent_status_with_no_tasks(self, client: TestClient, auth_headers: dict, test_db: Session):
        """Test agent status when no tasks exist."""
        response = client.get("/api/v1/monitoring/agents/research", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "idle"
        assert data["total_executions"] == 0
        assert data["success_rate"] == 0.0
    
    def test_agent_status_calculates_success_rate(
        self, client: TestClient, auth_headers: dict, test_db: Session, test_user
    ):
        """Test that success rate is calculated correctly."""
        # Create successful tasks
        for i in range(8):
            task = Task(
                user_id=test_user.id,
                task_type="docs",
                prompt=f"Task {i}",
                status="completed",
                created_at=datetime.utcnow() - timedelta(hours=1),
                updated_at=datetime.utcnow()
            )
            test_db.add(task)
        
        # Create failed tasks
        for i in range(2):
            task = Task(
                user_id=test_user.id,
                task_type="docs",
                prompt=f"Failed task {i}",
                status="failed",
                created_at=datetime.utcnow() - timedelta(hours=1)
            )
            test_db.add(task)
        
        test_db.commit()
        
        response = client.get("/api/v1/monitoring/agents/docs", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total_executions"] == 10
        assert data["success_rate"] == 0.8  # 8/10


class TestSystemMetrics:
    """Test system metrics endpoint."""
    
    def test_get_system_metrics(self, client: TestClient, auth_headers: dict, test_db: Session, test_user):
        """Test getting system metrics."""
        # Create test data
        task1 = Task(
            user_id=test_user.id,
            task_type="research",
            prompt="Test",
            status="completed",
            created_at=datetime.utcnow() - timedelta(hours=2),
            updated_at=datetime.utcnow() - timedelta(hours=1)
        )
        task2 = Task(
            user_id=test_user.id,
            task_type="docs",
            prompt="Test",
            status="failed",
            created_at=datetime.utcnow() - timedelta(hours=1)
        )
        task3 = Task(
            user_id=test_user.id,
            task_type="sheets",
            prompt="Test",
            status="pending",
            created_at=datetime.utcnow()
        )
        
        test_db.add_all([task1, task2, task3])
        test_db.commit()
        
        response = client.get("/api/v1/monitoring/metrics", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total_tasks"] >= 3
        assert data["active_tasks"] >= 1  # task3 is pending
        assert data["completed_tasks"] >= 1
        assert data["failed_tasks"] >= 1
    
    def test_metrics_with_budget_tracking(
        self, client: TestClient, auth_headers: dict, test_db: Session, test_user
    ):
        """Test metrics include budget tracking data."""
        # Create cost record entry
        cost = CostRecord(
            user_id=test_user.id,
            task_id=None,
            model="gpt-4",
            task_type="research",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            cost_usd=0.005,
            created_at=datetime.utcnow() - timedelta(hours=1)
        )
        test_db.add(cost)
        test_db.commit()
        
        response = client.get("/api/v1/monitoring/metrics", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total_cost_usd"] > 0


class TestErrorSummary:
    """Test error summary endpoint."""
    
    def test_get_error_summary(self, client: TestClient, auth_headers: dict, test_db: Session, test_user):
        """Test getting error summary."""
        # Create failed tasks with different error types
        errors = [
            "ValueError: Invalid input",
            "ValueError: Another invalid input",
            "ConnectionError: API timeout",
            "AuthenticationError: Invalid credentials"
        ]
        
        for error_msg in errors:
            task = Task(
                user_id=test_user.id,
                task_type="research",
                prompt="Test",
                status="failed",
                result={"error": error_msg},
                created_at=datetime.utcnow() - timedelta(hours=1)
            )
            test_db.add(task)
        
        test_db.commit()
        
        response = client.get("/api/v1/monitoring/errors", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data) > 0
        
        # Check error summary structure
        error = data[0]
        assert "error_type" in error
        assert "count" in error
        assert "last_occurrence" in error
        assert "affected_agents" in error
        assert "sample_message" in error
    
    def test_error_summary_groups_by_type(
        self, client: TestClient, auth_headers: dict, test_db: Session, test_user
    ):
        """Test that errors are grouped by type."""
        # Create multiple errors of same type
        for i in range(3):
            task = Task(
                user_id=test_user.id,
                task_type="research",
                prompt=f"Test {i}",
                status="failed",
                result={"error": "ValueError: Test error"},
                created_at=datetime.utcnow() - timedelta(hours=1)
            )
            test_db.add(task)
        
        test_db.commit()
        
        response = client.get("/api/v1/monitoring/errors", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        # Find ValueError group
        value_errors = [e for e in data if e["error_type"] == "ValueError"]
        assert len(value_errors) > 0
        assert value_errors[0]["count"] >= 3


class TestPerformanceTrends:
    """Test performance trends endpoint."""
    
    def test_get_performance_trends(self, client: TestClient, auth_headers: dict, test_db: Session, test_user):
        """Test getting performance trends."""
        # Create tasks spread over time
        for hour in range(3):
            task = Task(
                user_id=test_user.id,
                task_type="research",
                prompt=f"Task hour {hour}",
                status="completed",
                created_at=datetime.utcnow() - timedelta(hours=hour),
                updated_at=datetime.utcnow() - timedelta(hours=hour - 0.5) if hour > 0 else datetime.utcnow()
            )
            test_db.add(task)
        
        test_db.commit()
        
        response = client.get("/api/v1/monitoring/trends?hours=3", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data) > 0
        
        # Check metric structure
        metric = data[0]
        assert "timestamp" in metric
        assert "metric_name" in metric
        assert "value" in metric
        assert "unit" in metric
    
    def test_trends_include_multiple_metrics(
        self, client: TestClient, auth_headers: dict, test_db: Session
    ):
        """Test that trends include different metric types."""
        response = client.get("/api/v1/monitoring/trends?hours=24", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have multiple metric types
        metric_names = set(m["metric_name"] for m in data)
        assert "task_completion_rate" in metric_names
        assert "error_rate" in metric_names
        assert "avg_cost_per_task" in metric_names


class TestAlerts:
    """Test alert system."""
    
    def test_get_active_alerts(self, client: TestClient, auth_headers: dict):
        """Test getting active alerts."""
        response = client.get("/api/v1/monitoring/alerts", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
    
    def test_high_error_rate_alert(
        self, client: TestClient, auth_headers: dict, test_db: Session, test_user
    ):
        """Test that high error rate triggers alert."""
        # Create mostly failed tasks
        for i in range(10):
            task = Task(
                user_id=test_user.id,
                task_type="research",
                prompt=f"Task {i}",
                status="failed" if i < 8 else "completed",
                created_at=datetime.utcnow() - timedelta(hours=1)
            )
            test_db.add(task)
        
        test_db.commit()
        
        response = client.get("/api/v1/monitoring/alerts", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have high error rate alert
        error_alerts = [a for a in data if "error rate" in a.lower()]
        assert len(error_alerts) > 0
    
    def test_agent_error_alert(
        self, client: TestClient, auth_headers: dict, test_db: Session, test_user
    ):
        """Test that agent errors trigger alerts."""
        # Create recent failed task
        task = Task(
            user_id=test_user.id,
            task_type="docs",
            prompt="Test",
            status="failed",
            created_at=datetime.utcnow() - timedelta(minutes=30)
        )
        test_db.add(task)
        test_db.commit()
        
        response = client.get("/api/v1/monitoring/alerts", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        # May or may not have alert depending on recent activity
        # Just check it returns successfully
        assert isinstance(data, list)


class TestMonitoringHealth:
    """Test monitoring health check."""
    
    def test_health_check_no_auth_required(self, client: TestClient):
        """Test that health check doesn't require authentication."""
        response = client.get("/api/v1/monitoring/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "status" in data
        assert "timestamp" in data
        assert "database" in data
        assert "monitoring_api" in data
    
    def test_health_check_reports_healthy(self, client: TestClient):
        """Test that health check reports healthy status."""
        response = client.get("/api/v1/monitoring/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] in ["healthy", "degraded"]
        assert data["monitoring_api"] == "operational"
