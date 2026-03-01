"""Tests for usage nudge email tasks."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from app.tasks.nudge_email import (
    _can_send_nudge_email,
    _record_nudge_email,
    _get_inactive_users,
    _send_nudge_email,
    send_usage_nudge_emails,
    test_nudge_email,
)
from app.models.user import User
from app.models.task import Task
from app.models.nudge_email_log import NudgeEmailLog


@pytest.fixture
def mock_user():
    """Create a mock user."""
    return User(
        id=uuid4(),
        email="test@example.com",
        full_name="Test User",
        is_active=True,
        created_at=datetime.utcnow() - timedelta(days=30),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def mock_inactive_user():
    """Create a mock inactive user (no recent tasks)."""
    user = User(
        id=uuid4(),
        email="inactive@example.com",
        full_name="Inactive User",
        is_active=True,
        created_at=datetime.utcnow() - timedelta(days=30),
        updated_at=datetime.utcnow() - timedelta(days=10),
    )
    return user


@pytest.mark.asyncio
async def test_can_send_nudge_email_under_limit(mock_user):
    """Test that user can receive email when under weekly limit."""
    with patch("app.tasks.nudge_email.AsyncSessionLocal") as mock_session_local:
        # Mock database query result (0 emails sent this week)
        mock_session = AsyncMock()
        mock_result = AsyncMock()
        mock_result.scalar.return_value = 0
        mock_session.execute.return_value = mock_result
        mock_session_local.return_value.__aenter__.return_value = mock_session

        can_send = await _can_send_nudge_email(mock_user.id)

        assert can_send is True


@pytest.mark.asyncio
async def test_can_send_nudge_email_at_limit(mock_user):
    """Test that user cannot receive email when at weekly limit (2/week)."""
    with patch("app.tasks.nudge_email.AsyncSessionLocal") as mock_session_local:
        # Mock database query result (2 emails sent this week)
        mock_session = AsyncMock()
        mock_result = AsyncMock()
        mock_result.scalar.return_value = 2
        mock_session.execute.return_value = mock_result
        mock_session_local.return_value.__aenter__.return_value = mock_session

        can_send = await _can_send_nudge_email(mock_user.id)

        assert can_send is False


@pytest.mark.asyncio
async def test_record_nudge_email_success(mock_user):
    """Test recording successful email send."""
    with patch("app.tasks.nudge_email.AsyncSessionLocal") as mock_session_local:
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session

        await _record_nudge_email(mock_user.id, success=True)

        # Verify session.add was called
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

        # Check the NudgeEmailLog object
        call_args = mock_session.add.call_args[0][0]
        assert isinstance(call_args, NudgeEmailLog)
        assert call_args.user_id == mock_user.id
        assert call_args.success is True
        assert call_args.error_message is None


@pytest.mark.asyncio
async def test_record_nudge_email_failure(mock_user):
    """Test recording failed email send."""
    with patch("app.tasks.nudge_email.AsyncSessionLocal") as mock_session_local:
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session

        await _record_nudge_email(
            mock_user.id, success=False, error_message="SMTP error"
        )

        call_args = mock_session.add.call_args[0][0]
        assert call_args.success is False
        assert call_args.error_message == "SMTP error"


@pytest.mark.asyncio
async def test_get_inactive_users(mock_inactive_user):
    """Test finding inactive users."""
    with patch("app.tasks.nudge_email.AsyncSessionLocal") as mock_session_local:
        mock_session = AsyncMock()
        mock_result = AsyncMock()
        
        # Mock returning one inactive user
        mock_result.scalars.return_value.all.return_value = [mock_inactive_user]
        mock_session.execute.return_value = mock_result
        mock_session_local.return_value.__aenter__.return_value = mock_session

        users = await _get_inactive_users(days=7)

        assert len(users) == 1
        assert users[0].email == "inactive@example.com"


@pytest.mark.asyncio
async def test_get_inactive_users_empty():
    """Test when no inactive users found."""
    with patch("app.tasks.nudge_email.AsyncSessionLocal") as mock_session_local:
        mock_session = AsyncMock()
        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        mock_session_local.return_value.__aenter__.return_value = mock_session

        users = await _get_inactive_users(days=7)

        assert len(users) == 0


def test_send_nudge_email_success(mock_user):
    """Test sending nudge email successfully."""
    with patch("app.tasks.nudge_email.email_service") as mock_email_service:
        mock_email_service.send_email.return_value = True

        result = _send_nudge_email(mock_user)

        assert result is True
        mock_email_service.send_email.assert_called_once()

        # Verify email content
        call_args = mock_email_service.send_email.call_args
        assert call_args[1]["to_email"] == mock_user.email
        assert "We miss you" in call_args[1]["subject"]
        assert mock_user.full_name in call_args[1]["html_body"]


def test_send_nudge_email_no_full_name(mock_user):
    """Test sending email when user has no full_name."""
    mock_user.full_name = None

    with patch("app.tasks.nudge_email.email_service") as mock_email_service:
        mock_email_service.send_email.return_value = True

        result = _send_nudge_email(mock_user)

        assert result is True
        # Should use "there" as fallback
        call_args = mock_email_service.send_email.call_args
        assert "there" in call_args[1]["html_body"]


def test_send_nudge_email_failure(mock_user):
    """Test handling email send failure."""
    with patch("app.tasks.nudge_email.email_service") as mock_email_service:
        mock_email_service.send_email.return_value = False

        result = _send_nudge_email(mock_user)

        assert result is False


@patch("app.tasks.nudge_email.run_async")
@patch("app.tasks.nudge_email._send_nudge_email")
def test_send_usage_nudge_emails_success(mock_send_email, mock_run_async, mock_inactive_user):
    """Test full nudge email task execution."""
    # Mock async operations
    mock_run_async.side_effect = [
        [mock_inactive_user],  # _get_inactive_users result
        True,                   # _can_send_nudge_email result
        None,                   # _record_nudge_email result
    ]
    
    # Mock email send
    mock_send_email.return_value = True

    result = send_usage_nudge_emails(days_inactive=7)

    assert result["status"] == "completed"
    assert result["total_inactive"] == 1
    assert result["emails_sent"] == 1
    assert result["emails_skipped"] == 0
    assert len(result["errors"]) == 0


@patch("app.tasks.nudge_email.run_async")
@patch("app.tasks.nudge_email._send_nudge_email")
def test_send_usage_nudge_emails_weekly_limit(mock_send_email, mock_run_async, mock_inactive_user):
    """Test skipping user at weekly limit."""
    # Mock async operations
    mock_run_async.side_effect = [
        [mock_inactive_user],  # _get_inactive_users result
        False,                  # _can_send_nudge_email result (limit reached)
    ]

    result = send_usage_nudge_emails(days_inactive=7)

    assert result["status"] == "completed"
    assert result["total_inactive"] == 1
    assert result["emails_sent"] == 0
    assert result["emails_skipped"] == 1
    mock_send_email.assert_not_called()


@patch("app.tasks.nudge_email.run_async")
@patch("app.tasks.nudge_email._send_nudge_email")
def test_send_usage_nudge_emails_send_failure(mock_send_email, mock_run_async, mock_inactive_user):
    """Test handling email send failure."""
    # Mock async operations
    mock_run_async.side_effect = [
        [mock_inactive_user],  # _get_inactive_users result
        True,                   # _can_send_nudge_email result
        None,                   # _record_nudge_email result
    ]
    
    # Mock email send failure
    mock_send_email.return_value = False

    result = send_usage_nudge_emails(days_inactive=7)

    assert result["status"] == "completed"
    assert result["total_inactive"] == 1
    assert result["emails_sent"] == 0
    assert len(result["errors"]) == 1
    assert "Failed to send email" in result["errors"][0]


@patch("app.tasks.nudge_email.run_async")
def test_send_usage_nudge_emails_critical_error(mock_run_async):
    """Test handling critical error in task."""
    # Mock critical error
    mock_run_async.side_effect = Exception("Database connection failed")

    result = send_usage_nudge_emails(days_inactive=7)

    assert result["status"] == "failed"
    assert "Critical error" in result["error"]
    assert result["emails_sent"] == 0


@patch("app.tasks.nudge_email.run_async")
@patch("app.tasks.nudge_email._send_nudge_email")
def test_test_nudge_email_success(mock_send_email, mock_run_async, mock_user):
    """Test the test_nudge_email task."""
    # Mock async operations
    mock_run_async.side_effect = [
        mock_user,  # _get_user result
        None,       # _record_nudge_email result
    ]
    
    # Mock email send
    mock_send_email.return_value = True

    result = test_nudge_email(mock_user.email)

    assert result["status"] == "success"
    assert f"Test email sent to {mock_user.email}" in result["message"]
    mock_send_email.assert_called_once_with(mock_user)


@patch("app.tasks.nudge_email.run_async")
def test_test_nudge_email_user_not_found(mock_run_async):
    """Test test_nudge_email with non-existent user."""
    mock_run_async.return_value = None

    result = test_nudge_email("nonexistent@example.com")

    assert result["status"] == "failed"
    assert "User not found" in result["error"]


@patch("app.tasks.nudge_email.run_async")
@patch("app.tasks.nudge_email._send_nudge_email")
def test_test_nudge_email_send_failure(mock_send_email, mock_run_async, mock_user):
    """Test test_nudge_email when email send fails."""
    mock_run_async.side_effect = [mock_user, None]
    mock_send_email.return_value = False

    result = test_nudge_email(mock_user.email)

    assert result["status"] == "failed"
    assert "Failed to send email" in result["error"]
