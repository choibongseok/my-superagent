"""Tests for email service."""

import pytest
from unittest.mock import MagicMock, patch

from app.services.email_service import EmailService


@pytest.fixture
def email_service():
    """Create email service with test configuration."""
    with patch("app.services.email_service.settings") as mock_settings:
        mock_settings.EMAIL_ENABLED = True
        mock_settings.SMTP_HOST = "smtp.test.com"
        mock_settings.SMTP_PORT = 587
        mock_settings.SMTP_USER = "test@test.com"
        mock_settings.SMTP_PASSWORD = "testpass"
        mock_settings.FROM_EMAIL = "noreply@test.com"
        mock_settings.FROM_NAME = "Test Service"
        
        service = EmailService()
        yield service


class TestEmailService:
    """Test EmailService class."""
    
    def test_create_message(self, email_service):
        """Test message creation."""
        msg = email_service._create_message(
            to_email="recipient@test.com",
            subject="Test Subject",
            html_body="<p>Test HTML</p>",
            text_body="Test text"
        )
        
        assert msg["To"] == "recipient@test.com"
        assert msg["Subject"] == "Test Subject"
        assert msg["From"] == "Test Service <noreply@test.com>"
        assert msg.is_multipart()
    
    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_success(self, mock_smtp, email_service):
        """Test successful email sending."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server
        
        result = email_service.send_email(
            to_email="recipient@test.com",
            subject="Test",
            html_body="<p>Test</p>"
        )
        
        assert result is True
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("test@test.com", "testpass")
        mock_server.send_message.assert_called_once()
    
    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_failure(self, mock_smtp, email_service):
        """Test email sending failure."""
        mock_smtp.side_effect = Exception("SMTP error")
        
        result = email_service.send_email(
            to_email="recipient@test.com",
            subject="Test",
            html_body="<p>Test</p>"
        )
        
        assert result is False
    
    def test_send_email_disabled(self, email_service):
        """Test email sending when disabled."""
        email_service.enabled = False
        
        result = email_service.send_email(
            to_email="recipient@test.com",
            subject="Test",
            html_body="<p>Test</p>"
        )
        
        assert result is False
    
    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_workspace_invitation(self, mock_smtp, email_service):
        """Test workspace invitation email."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server
        
        result = email_service.send_workspace_invitation(
            to_email="newuser@test.com",
            workspace_name="Test Workspace",
            inviter_name="John Doe",
            invitation_link="https://app.test.com/invite/abc123",
            role="EDITOR",
            expires_in_days=7
        )
        
        assert result is True
        
        # Verify send_message was called
        mock_server.send_message.assert_called_once()
        
        # Get the message that was sent
        sent_message = mock_server.send_message.call_args[0][0]
        
        # Verify message properties
        assert sent_message["To"] == "newuser@test.com"
        assert "Test Workspace" in sent_message["Subject"]
        
        # Verify message contains key elements
        message_str = sent_message.as_string()
        assert "Test Workspace" in message_str
        assert "John Doe" in message_str
        assert "https://app.test.com/invite/abc123" in message_str
        assert "EDITOR" in message_str
    
    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_invitation_with_html(self, mock_smtp, email_service):
        """Test that invitation email contains HTML formatting."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server
        
        result = email_service.send_workspace_invitation(
            to_email="newuser@test.com",
            workspace_name="My Team",
            inviter_name="Alice",
            invitation_link="https://example.com/accept",
            role="VIEWER"
        )
        
        assert result is True
        
        sent_message = mock_server.send_message.call_args[0][0]
        message_str = sent_message.as_string()
        
        # Verify HTML elements
        assert "<!DOCTYPE html>" in message_str
        assert 'class="button"' in message_str
        assert 'href="https://example.com/accept"' in message_str
