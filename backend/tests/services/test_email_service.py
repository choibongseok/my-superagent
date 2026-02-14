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
            to_emails=["recipient@test.com"],
            subject="Test Subject",
            html_body="<p>Test HTML</p>",
            text_body="Test text",
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
            to_email="recipient@test.com", subject="Test", html_body="<p>Test</p>"
        )

        assert result is True
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("test@test.com", "testpass")
        mock_server.send_message.assert_called_once()
        assert mock_server.send_message.call_args.kwargs["to_addrs"] == [
            "recipient@test.com"
        ]

    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_failure(self, mock_smtp, email_service):
        """Test email sending failure."""
        mock_smtp.side_effect = Exception("SMTP error")

        result = email_service.send_email(
            to_email="recipient@test.com", subject="Test", html_body="<p>Test</p>"
        )

        assert result is False

    def test_send_email_disabled(self, email_service):
        """Test email sending when disabled."""
        email_service.enabled = False

        result = email_service.send_email(
            to_email="recipient@test.com", subject="Test", html_body="<p>Test</p>"
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
            expires_in_days=7,
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
            role="VIEWER",
        )

        assert result is True

        sent_message = mock_server.send_message.call_args[0][0]
        html_part = sent_message.get_payload()[-1]
        html_content = html_part.get_payload(decode=True).decode()

        # Verify HTML elements
        assert "<!DOCTYPE html>" in html_content
        assert 'class="button"' in html_content
        assert 'href="https://example.com/accept"' in html_content

    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_supports_multiple_to_cc_and_bcc_recipients(
        self,
        mock_smtp,
        email_service,
    ):
        """Test sending one message to multiple recipients with CC/BCC."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        result = email_service.send_email(
            to_email=["primary@test.com", "secondary@test.com", "primary@test.com"],
            cc_emails=["cc@test.com"],
            bcc_emails=["bcc@test.com", "cc@test.com"],
            subject="Status Update",
            html_body="<p>All systems operational.</p>",
        )

        assert result is True

        sent_message = mock_server.send_message.call_args[0][0]
        delivery_recipients = mock_server.send_message.call_args.kwargs["to_addrs"]

        assert sent_message["To"] == "primary@test.com, secondary@test.com"
        assert sent_message["Cc"] == "cc@test.com"
        assert "Bcc" not in sent_message
        assert delivery_recipients == [
            "primary@test.com",
            "secondary@test.com",
            "cc@test.com",
            "bcc@test.com",
        ]

    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_sets_reply_to_header_when_requested(
        self,
        mock_smtp,
        email_service,
    ):
        """Test optional Reply-To header support."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        result = email_service.send_email(
            to_email="recipient@test.com",
            subject="Support",
            html_body="<p>Reply to support team</p>",
            reply_to_email="support@test.com",
        )

        assert result is True

        sent_message = mock_server.send_message.call_args[0][0]
        assert sent_message["Reply-To"] == "support@test.com"

    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_supports_comma_or_semicolon_delimited_recipient_strings(
        self,
        mock_smtp,
        email_service,
    ):
        """Recipient strings can include comma/semicolon delimiters."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        result = email_service.send_email(
            to_email="primary@test.com; secondary@test.com, primary@test.com",
            cc_emails="cc@test.com; secondary@test.com",
            bcc_emails="bcc@test.com, cc@test.com",
            subject="Delimited",
            html_body="<p>Delimited recipients</p>",
        )

        assert result is True

        sent_message = mock_server.send_message.call_args[0][0]
        delivery_recipients = mock_server.send_message.call_args.kwargs["to_addrs"]

        assert sent_message["To"] == "primary@test.com, secondary@test.com"
        assert sent_message["Cc"] == "cc@test.com, secondary@test.com"
        assert delivery_recipients == [
            "primary@test.com",
            "secondary@test.com",
            "cc@test.com",
            "bcc@test.com",
        ]

    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_rejects_newline_header_injection_in_recipients(
        self,
        mock_smtp,
        email_service,
    ):
        """Newline characters in recipient fields should be rejected."""
        result = email_service.send_email(
            to_email="victim@test.com\nBCC:attacker@test.com",
            subject="Unsafe",
            html_body="<p>should fail</p>",
        )

        assert result is False
        mock_smtp.assert_not_called()

    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_rejects_multiple_reply_to_addresses(
        self,
        mock_smtp,
        email_service,
    ):
        """Reply-To should remain a single address field."""
        result = email_service.send_email(
            to_email="recipient@test.com",
            subject="Reply-to",
            html_body="<p>should fail</p>",
            reply_to_email="support@test.com,helpdesk@test.com",
        )

        assert result is False
        mock_smtp.assert_not_called()

    def test_send_email_returns_false_for_empty_recipient_values(self, email_service):
        """Test invalid recipients are handled as send failures."""
        result = email_service.send_email(
            to_email=["   "],
            subject="Invalid",
            html_body="<p>should fail</p>",
        )

        assert result is False
