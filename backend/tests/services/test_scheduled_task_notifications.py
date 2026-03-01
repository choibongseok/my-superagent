"""Tests for scheduled task notifications."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.scheduled_task_executor import ScheduledTaskExecutor
from app.models.scheduled_task import ScheduledTask, ScheduledTaskExecution
from app.models.user import User


@pytest.fixture
def mock_user():
    """Create a mock user."""
    user = MagicMock(spec=User)
    user.id = uuid4()
    user.email = "user@example.com"
    user.name = "Test User"
    return user


@pytest.fixture
def mock_scheduled_task(mock_user):
    """Create a mock scheduled task with notifications enabled."""
    task = MagicMock(spec=ScheduledTask)
    task.id = uuid4()
    task.user_id = mock_user.id
    task.user = mock_user
    task.name = "Daily Report"
    task.description = "Generate daily sales report"
    task.task_type = "sheets"
    task.prompt_template = "Generate sales report for {date}"
    task.schedule_type = "daily"
    task.schedule_config = {"hour": 9, "minute": 0}
    task.notify_on_completion = True
    task.notification_email = "custom@example.com"
    task.notification_channels = ["email"]
    task.is_active = True
    task.last_run_at = None
    task.next_run_at = datetime.utcnow()
    task.run_count = 0
    task.created_at = datetime.utcnow()
    return task


@pytest.fixture
def mock_execution_success():
    """Create a successful mock execution."""
    execution = MagicMock(spec=ScheduledTaskExecution)
    execution.id = uuid4()
    execution.started_at = datetime.utcnow() - timedelta(seconds=45)
    execution.completed_at = datetime.utcnow()
    execution.status = "completed"
    execution.success = True
    execution.error_message = None
    execution.output_data = {
        "spreadsheet_url": "https://docs.google.com/spreadsheets/d/abc123",
        "spreadsheet_title": "Daily Sales Report - 2026-03-01",
        "rows_created": 150,
    }
    return execution


@pytest.fixture
def mock_execution_failure():
    """Create a failed mock execution."""
    execution = MagicMock(spec=ScheduledTaskExecution)
    execution.id = uuid4()
    execution.started_at = datetime.utcnow() - timedelta(seconds=12)
    execution.completed_at = datetime.utcnow()
    execution.status = "failed"
    execution.success = False
    execution.error_message = "API rate limit exceeded"
    execution.output_data = None
    return execution


@pytest.mark.asyncio
async def test_send_notification_success(
    mock_scheduled_task,
    mock_execution_success,
):
    """Test sending notification for successful task execution."""
    mock_db = AsyncMock()
    
    with patch("app.services.email_service.email_service") as mock_email:
        mock_email.send_task_completion_notification.return_value = True
        
        await ScheduledTaskExecutor.send_completion_notification(
            mock_scheduled_task,
            mock_execution_success,
            mock_db
        )
        
        # Verify email was sent
        mock_email.send_task_completion_notification.assert_called_once()
        call_kwargs = mock_email.send_task_completion_notification.call_args.kwargs
        
        assert call_kwargs["to_email"] == "custom@example.com"
        assert call_kwargs["task_name"] == "Daily Report"
        assert call_kwargs["task_type"] == "sheets"
        assert call_kwargs["success"] is True
        assert call_kwargs["output_data"] == mock_execution_success.output_data
        assert call_kwargs["error_message"] is None
        assert call_kwargs["execution_time_seconds"] == pytest.approx(45, abs=1)


@pytest.mark.asyncio
async def test_send_notification_failure(
    mock_scheduled_task,
    mock_execution_failure,
):
    """Test sending notification for failed task execution."""
    mock_db = AsyncMock()
    
    with patch("app.services.email_service.email_service") as mock_email:
        mock_email.send_task_completion_notification.return_value = True
        
        await ScheduledTaskExecutor.send_completion_notification(
            mock_scheduled_task,
            mock_execution_failure,
            mock_db
        )
        
        # Verify email was sent with error info
        mock_email.send_task_completion_notification.assert_called_once()
        call_kwargs = mock_email.send_task_completion_notification.call_args.kwargs
        
        assert call_kwargs["to_email"] == "custom@example.com"
        assert call_kwargs["task_name"] == "Daily Report"
        assert call_kwargs["success"] is False
        assert call_kwargs["error_message"] == "API rate limit exceeded"
        assert call_kwargs["output_data"] is None


@pytest.mark.asyncio
async def test_send_notification_fallback_to_user_email(
    mock_scheduled_task,
    mock_execution_success,
):
    """Test notification falls back to user email if no custom email set."""
    mock_db = AsyncMock()
    mock_scheduled_task.notification_email = None  # No custom email
    
    with patch("app.services.email_service.email_service") as mock_email:
        mock_email.send_task_completion_notification.return_value = True
        
        await ScheduledTaskExecutor.send_completion_notification(
            mock_scheduled_task,
            mock_execution_success,
            mock_db
        )
        
        # Should use user's email
        call_kwargs = mock_email.send_task_completion_notification.call_args.kwargs
        assert call_kwargs["to_email"] == "user@example.com"


@pytest.mark.asyncio
async def test_send_notification_no_email_configured(
    mock_scheduled_task,
    mock_execution_success,
    caplog,
):
    """Test warning when no email is configured."""
    mock_db = AsyncMock()
    mock_scheduled_task.notification_email = None
    mock_scheduled_task.user.email = None  # No user email either
    
    with patch("app.services.email_service.email_service") as mock_email:
        await ScheduledTaskExecutor.send_completion_notification(
            mock_scheduled_task,
            mock_execution_success,
            mock_db
        )
        
        # Should log warning and not send email
        assert "No notification email configured" in caplog.text
        mock_email.send_task_completion_notification.assert_not_called()


@pytest.mark.asyncio
async def test_notification_in_execute_scheduled_task(
    mock_scheduled_task,
):
    """Test that execute_scheduled_task calls notification if enabled."""
    mock_db = AsyncMock()
    
    with (
        patch("app.services.scheduled_task_executor.MultiAgentOrchestrator") as mock_orch,
        patch.object(ScheduledTaskExecutor, "send_completion_notification") as mock_notify,
    ):
        # Mock orchestrator
        mock_instance = AsyncMock()
        mock_instance.run_task.return_value = {
            "success": True,
            "spreadsheet_url": "https://docs.google.com/spreadsheets/d/xyz",
        }
        mock_orch.return_value = mock_instance
        
        # Execute task
        execution = await ScheduledTaskExecutor.execute_scheduled_task(
            mock_scheduled_task,
            mock_db
        )
        
        # Verify notification was called
        mock_notify.assert_called_once()
        assert mock_notify.call_args.args[0] == mock_scheduled_task
        assert mock_notify.call_args.args[2] == mock_db


@pytest.mark.asyncio
async def test_notification_disabled(
    mock_scheduled_task,
):
    """Test that notification is not sent when disabled."""
    mock_db = AsyncMock()
    mock_scheduled_task.notify_on_completion = False  # Disabled
    
    with (
        patch("app.services.scheduled_task_executor.MultiAgentOrchestrator") as mock_orch,
        patch.object(ScheduledTaskExecutor, "send_completion_notification") as mock_notify,
    ):
        mock_instance = AsyncMock()
        mock_instance.run_task.return_value = {"success": True}
        mock_orch.return_value = mock_instance
        
        await ScheduledTaskExecutor.execute_scheduled_task(
            mock_scheduled_task,
            mock_db
        )
        
        # Notification should not be called
        mock_notify.assert_not_called()


@pytest.mark.asyncio
async def test_notification_error_does_not_fail_task(
    mock_scheduled_task,
):
    """Test that notification errors don't fail the task execution."""
    mock_db = AsyncMock()
    
    with (
        patch("app.services.scheduled_task_executor.MultiAgentOrchestrator") as mock_orch,
        patch.object(ScheduledTaskExecutor, "send_completion_notification") as mock_notify,
    ):
        mock_instance = AsyncMock()
        mock_instance.run_task.return_value = {"success": True}
        mock_orch.return_value = mock_instance
        
        # Make notification fail
        mock_notify.side_effect = Exception("SMTP server unavailable")
        
        # Task should still succeed
        execution = await ScheduledTaskExecutor.execute_scheduled_task(
            mock_scheduled_task,
            mock_db
        )
        
        # Verify task still marked as successful despite notification error
        assert execution.success is True


def test_email_service_task_completion():
    """Test EmailService.send_task_completion_notification."""
    from app.services.email_service import EmailService
    
    service = EmailService()
    service.enabled = False  # Disable actual sending
    
    # Test successful task
    result = service.send_task_completion_notification(
        to_email="user@example.com",
        task_name="Daily Report",
        task_type="sheets",
        success=True,
        output_data={
            "spreadsheet_url": "https://docs.google.com/spreadsheets/d/abc",
            "spreadsheet_title": "Report",
        },
        execution_time_seconds=42.5,
    )
    
    # Should return False because email is disabled, but no exceptions
    assert result is False
    
    # Test failed task
    result = service.send_task_completion_notification(
        to_email="user@example.com",
        task_name="Daily Report",
        task_type="sheets",
        success=False,
        error_message="Connection timeout",
        execution_time_seconds=5.2,
    )
    
    assert result is False


@pytest.mark.parametrize("task_type,output_key,output_value", [
    ("docs", "document_url", "https://docs.google.com/document/d/abc"),
    ("sheets", "spreadsheet_url", "https://docs.google.com/spreadsheets/d/xyz"),
    ("slides", "presentation_url", "https://docs.google.com/presentation/d/123"),
])
def test_email_output_formatting(task_type, output_key, output_value):
    """Test that different task types format output correctly."""
    from app.services.email_service import EmailService
    
    service = EmailService()
    service.enabled = False
    
    output_data = {output_key: output_value}
    
    # Should not raise exceptions for different output types
    service.send_task_completion_notification(
        to_email="user@example.com",
        task_name=f"Test {task_type.title()} Task",
        task_type=task_type,
        success=True,
        output_data=output_data,
    )
