"""Tests for email service."""

import base64

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
    def test_send_email_auto_generates_plain_text_fallback_from_html(
        self,
        mock_smtp,
        email_service,
    ):
        """HTML-only emails should include an auto-generated plain-text fallback."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        result = email_service.send_email(
            to_email="recipient@test.com",
            subject="Fallback",
            html_body="<h1>Hello</h1><p>Line&nbsp;two<br>Again</p>",
        )

        assert result is True

        sent_message = mock_server.send_message.call_args[0][0]
        payload_parts = [
            part
            for part in sent_message.walk()
            if part.get_content_maintype() == "text"
        ]

        plain_parts = [
            part for part in payload_parts if part.get_content_subtype() == "plain"
        ]
        html_parts = [
            part for part in payload_parts if part.get_content_subtype() == "html"
        ]

        assert len(plain_parts) == 1
        assert len(html_parts) == 1

        plain_body = plain_parts[0].get_payload(decode=True).decode()
        assert "Hello" in plain_body
        assert "Line two" in plain_body
        assert "Again" in plain_body
        assert "<h1>" not in plain_body

    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_can_disable_auto_text_body_fallback(
        self,
        mock_smtp,
        email_service,
    ):
        """Fallback plain-text generation can be disabled when not needed."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        result = email_service.send_email(
            to_email="recipient@test.com",
            subject="No fallback",
            html_body="<p>Only HTML</p>",
            auto_text_body=False,
        )

        assert result is True

        sent_message = mock_server.send_message.call_args[0][0]
        payload_parts = [
            part
            for part in sent_message.walk()
            if part.get_content_maintype() == "text"
        ]

        plain_parts = [
            part for part in payload_parts if part.get_content_subtype() == "plain"
        ]
        html_parts = [
            part for part in payload_parts if part.get_content_subtype() == "html"
        ]

        assert plain_parts == []
        assert len(html_parts) == 1

    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_supports_text_only_messages(self, mock_smtp, email_service):
        """Text-only emails should send without requiring an HTML payload."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        result = email_service.send_email(
            to_email="recipient@test.com",
            subject="Text only",
            text_body="Plain content only",
        )

        assert result is True

        sent_message = mock_server.send_message.call_args[0][0]
        payload_parts = [
            part
            for part in sent_message.walk()
            if part.get_content_maintype() == "text"
        ]

        plain_parts = [
            part for part in payload_parts if part.get_content_subtype() == "plain"
        ]
        html_parts = [
            part for part in payload_parts if part.get_content_subtype() == "html"
        ]

        assert len(plain_parts) == 1
        assert html_parts == []
        assert "Plain content only" in plain_parts[0].get_payload(decode=True).decode()

    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_rejects_missing_html_and_text_bodies(
        self,
        mock_smtp,
        email_service,
    ):
        """send_email should fail when both html_body and text_body are missing."""
        result = email_service.send_email(
            to_email="recipient@test.com",
            subject="Missing body",
            html_body=None,
            text_body=None,
        )

        assert result is False
        mock_smtp.assert_not_called()

    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_validates_auto_text_body_flag(self, mock_smtp, email_service):
        """auto_text_body must be a boolean flag."""
        result = email_service.send_email(
            to_email="recipient@test.com",
            subject="Invalid",
            html_body="<p>invalid</p>",
            auto_text_body="yes",  # type: ignore[arg-type]
        )

        assert result is False
        mock_smtp.assert_not_called()

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

    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_supports_display_name_recipients_and_case_insensitive_dedupe(
        self,
        mock_smtp,
        email_service,
    ):
        """Display-name addresses should parse correctly and dedupe case-insensitively."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        result = email_service.send_email(
            to_email=['"Doe, Jane" <Jane@Test.com>', "jane@test.com"],
            cc_emails=["Ops Team <ops@test.com>"],
            bcc_emails=["OPS@test.com", "Audit Team <audit@test.com>"],
            subject="Display Names",
            html_body="<p>hello</p>",
        )

        assert result is True

        sent_message = mock_server.send_message.call_args[0][0]
        delivery_recipients = mock_server.send_message.call_args.kwargs["to_addrs"]

        assert sent_message["To"] == "Jane@Test.com"
        assert sent_message["Cc"] == "ops@test.com"
        assert delivery_recipients == [
            "Jane@Test.com",
            "ops@test.com",
            "audit@test.com",
        ]

    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_allows_display_name_reply_to(self, mock_smtp, email_service):
        """Reply-To should accept display-name syntax and store normalized address."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        result = email_service.send_email(
            to_email="recipient@test.com",
            subject="Support",
            html_body="<p>reply here</p>",
            reply_to_email="Support Team <support@test.com>",
        )

        assert result is True

        sent_message = mock_server.send_message.call_args[0][0]
        assert sent_message["Reply-To"] == "support@test.com"

    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_supports_binary_and_text_attachments(
        self,
        mock_smtp,
        email_service,
    ):
        """Attachments should produce a multipart/mixed message with payload files."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        result = email_service.send_email(
            to_email="recipient@test.com",
            subject="With attachments",
            html_body="<p>See attached.</p>",
            text_body="See attached.",
            attachments=[
                {
                    "filename": "report.txt",
                    "content": "daily summary",
                    "mime_type": "text/plain",
                },
                {
                    "filename": "metrics.bin",
                    "content": b"\x00\x01\x02",
                    "mime_type": "application/octet-stream",
                },
            ],
        )

        assert result is True

        sent_message = mock_server.send_message.call_args[0][0]
        assert sent_message.get_content_type() == "multipart/mixed"

        attachments = [
            part
            for part in sent_message.walk()
            if part.get_content_disposition() == "attachment"
        ]
        assert [part.get_filename() for part in attachments] == [
            "report.txt",
            "metrics.bin",
        ]

    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_supports_inline_attachments_with_content_id(
        self,
        mock_smtp,
        email_service,
    ):
        """Inline attachments should expose Content-ID headers for cid: references."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        result = email_service.send_email(
            to_email="recipient@test.com",
            subject="Inline attachment",
            html_body='<p><img src="cid:logo-image"></p>',
            attachments=[
                {
                    "filename": "logo.png",
                    "content": b"\x89PNG\r\n\x1a\n",
                    "mime_type": "image/png",
                    "disposition": "inline",
                    "content_id": "logo-image",
                }
            ],
        )

        assert result is True

        sent_message = mock_server.send_message.call_args[0][0]
        attachments = [
            part
            for part in sent_message.walk()
            if part.get_content_disposition() in {"attachment", "inline"}
        ]

        assert len(attachments) == 1
        assert attachments[0].get_content_disposition() == "inline"
        assert attachments[0]["Content-ID"] == "<logo-image>"

    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_rejects_inline_attachments_without_content_id(
        self,
        mock_smtp,
        email_service,
    ):
        """Inline attachments require explicit content IDs for safe referencing."""
        result = email_service.send_email(
            to_email="recipient@test.com",
            subject="Inline attachment",
            html_body="<p>inline</p>",
            attachments=[
                {
                    "filename": "logo.png",
                    "content": b"\x89PNG\r\n\x1a\n",
                    "mime_type": "image/png",
                    "disposition": "inline",
                }
            ],
        )

        assert result is False
        mock_smtp.assert_not_called()

    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_rejects_invalid_attachment_disposition(
        self,
        mock_smtp,
        email_service,
    ):
        """Attachment disposition values should be limited to attachment/inline."""
        result = email_service.send_email(
            to_email="recipient@test.com",
            subject="Invalid attachment",
            html_body="<p>fail</p>",
            attachments=[
                {
                    "filename": "payload.txt",
                    "content": "hello",
                    "mime_type": "text/plain",
                    "disposition": "embed",
                }
            ],
        )

        assert result is False
        mock_smtp.assert_not_called()

    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_supports_base64_and_data_url_attachments(
        self,
        mock_smtp,
        email_service,
    ):
        """Base64 attachment payloads should decode before MIME packaging."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        binary_payload = b"\x00\x01\x02"
        data_url_payload = "data:text/plain;base64," + base64.b64encode(
            b"hello world"
        ).decode("ascii")

        result = email_service.send_email(
            to_email="recipient@test.com",
            subject="Base64 attachment",
            html_body="<p>See attached.</p>",
            attachments=[
                {
                    "filename": "payload.bin",
                    "content_base64": base64.b64encode(binary_payload).decode("ascii"),
                    "mime_type": "application/octet-stream",
                },
                {
                    "filename": "note.txt",
                    "content_b64": data_url_payload,
                    "mime_type": "text/plain",
                },
            ],
        )

        assert result is True

        sent_message = mock_server.send_message.call_args[0][0]
        attachments = [
            part
            for part in sent_message.walk()
            if part.get_content_disposition() == "attachment"
        ]

        assert [part.get_filename() for part in attachments] == [
            "payload.bin",
            "note.txt",
        ]
        assert attachments[0].get_payload(decode=True) == binary_payload
        assert attachments[1].get_payload(decode=True) == b"hello world"

    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_infers_attachment_mime_type_from_data_url_when_omitted(
        self,
        mock_smtp,
        email_service,
    ):
        """Data-URL attachments should infer MIME type when mime_type is omitted."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        data_url_payload = "data:text/markdown;base64," + base64.b64encode(
            b"# Daily Notes"
        ).decode("ascii")

        result = email_service.send_email(
            to_email="recipient@test.com",
            subject="Data URL mime",
            html_body="<p>See attached.</p>",
            attachments=[
                {
                    "filename": "notes.md",
                    "content_base64": data_url_payload,
                }
            ],
        )

        assert result is True

        sent_message = mock_server.send_message.call_args[0][0]
        attachments = [
            part
            for part in sent_message.walk()
            if part.get_content_disposition() == "attachment"
        ]

        assert len(attachments) == 1
        assert attachments[0].get_filename() == "notes.md"
        assert attachments[0].get_content_type() == "text/markdown"

    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_prefers_explicit_attachment_mime_type_over_data_url(
        self,
        mock_smtp,
        email_service,
    ):
        """Explicit attachment mime_type should override data-URL metadata."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        data_url_payload = "data:text/plain;base64," + base64.b64encode(
            b"custom payload"
        ).decode("ascii")

        result = email_service.send_email(
            to_email="recipient@test.com",
            subject="Explicit mime",
            html_body="<p>See attached.</p>",
            attachments=[
                {
                    "filename": "payload.bin",
                    "content_base64": data_url_payload,
                    "mime_type": "application/octet-stream",
                }
            ],
        )

        assert result is True

        sent_message = mock_server.send_message.call_args[0][0]
        attachments = [
            part
            for part in sent_message.walk()
            if part.get_content_disposition() == "attachment"
        ]

        assert len(attachments) == 1
        assert attachments[0].get_filename() == "payload.bin"
        assert attachments[0].get_content_type() == "application/octet-stream"

    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_supports_path_based_attachments(
        self,
        mock_smtp,
        email_service,
        tmp_path,
    ):
        """Attachments can be loaded from local file paths with inferred metadata."""
        report_path = tmp_path / "report.txt"
        report_path.write_text("daily summary", encoding="utf-8")

        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        result = email_service.send_email(
            to_email="recipient@test.com",
            subject="Path attachment",
            html_body="<p>See file.</p>",
            attachments=[
                {
                    "path": str(report_path),
                }
            ],
        )

        assert result is True

        sent_message = mock_server.send_message.call_args[0][0]
        attachments = [
            part
            for part in sent_message.walk()
            if part.get_content_disposition() == "attachment"
        ]

        assert len(attachments) == 1
        assert attachments[0].get_filename() == "report.txt"
        assert attachments[0].get_content_type() == "text/plain"

    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_rejects_attachments_with_conflicting_content_and_path(
        self,
        mock_smtp,
        email_service,
        tmp_path,
    ):
        """Attachment entries must provide either content or path, not both."""
        report_path = tmp_path / "report.txt"
        report_path.write_text("daily summary", encoding="utf-8")

        result = email_service.send_email(
            to_email="recipient@test.com",
            subject="Invalid attachment",
            html_body="<p>fail</p>",
            attachments=[
                {
                    "filename": "report.txt",
                    "content": "inline",
                    "path": str(report_path),
                }
            ],
        )

        assert result is False
        mock_smtp.assert_not_called()

    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_rejects_invalid_base64_attachment_payloads(
        self,
        mock_smtp,
        email_service,
    ):
        """Invalid base64 attachment definitions should fail before SMTP calls."""
        result = email_service.send_email(
            to_email="recipient@test.com",
            subject="Invalid attachment",
            html_body="<p>fail</p>",
            attachments=[
                {
                    "filename": "bad.txt",
                    "content_base64": "not-valid-base64@@@",
                    "mime_type": "text/plain",
                }
            ],
        )

        assert result is False
        mock_smtp.assert_not_called()

    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_rejects_attachments_with_multiple_payload_sources(
        self,
        mock_smtp,
        email_service,
    ):
        """Attachment entries must provide exactly one payload source."""
        result = email_service.send_email(
            to_email="recipient@test.com",
            subject="Invalid attachment",
            html_body="<p>fail</p>",
            attachments=[
                {
                    "filename": "bad.txt",
                    "content": "inline",
                    "content_base64": base64.b64encode(b"inline").decode("ascii"),
                    "mime_type": "text/plain",
                }
            ],
        )

        assert result is False
        mock_smtp.assert_not_called()

    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_rejects_invalid_attachment_payloads(
        self,
        mock_smtp,
        email_service,
    ):
        """Invalid attachment definitions should fail before SMTP is contacted."""
        result = email_service.send_email(
            to_email="recipient@test.com",
            subject="Invalid attachment",
            html_body="<p>fail</p>",
            attachments=[
                {
                    "filename": "bad.txt",
                    "content": b"payload",
                    "mime_type": "not-a-mime-type",
                }
            ],
        )

        assert result is False
        mock_smtp.assert_not_called()

    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_rejects_invalid_email_format(
        self,
        mock_smtp,
        email_service,
    ):
        """Malformed email addresses should fail before SMTP is contacted."""
        result = email_service.send_email(
            to_email="not-an-email",
            subject="Invalid",
            html_body="<p>should fail</p>",
        )

        assert result is False
        mock_smtp.assert_not_called()

    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_sets_priority_headers_for_high_priority(
        self,
        mock_smtp,
        email_service,
    ):
        """High-priority emails should include consistent triage headers."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        result = email_service.send_email(
            to_email="recipient@test.com",
            subject="Priority",
            html_body="<p>urgent</p>",
            priority="high",
        )

        assert result is True

        sent_message = mock_server.send_message.call_args[0][0]
        assert sent_message["Importance"] == "high"
        assert sent_message["Priority"] == "urgent"
        assert sent_message["X-Priority"] == "1"

    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_supports_priority_aliases(self, mock_smtp, email_service):
        """Priority aliases should normalize to canonical header values."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        result = email_service.send_email(
            to_email="recipient@test.com",
            subject="Priority alias",
            html_body="<p>normal</p>",
            priority="medium",
        )

        assert result is True

        sent_message = mock_server.send_message.call_args[0][0]
        assert sent_message["Importance"] == "normal"
        assert sent_message["Priority"] == "normal"
        assert sent_message["X-Priority"] == "3"

    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_rejects_invalid_priority(self, mock_smtp, email_service):
        """Unsupported priority values should fail before SMTP calls."""
        result = email_service.send_email(
            to_email="recipient@test.com",
            subject="Priority",
            html_body="<p>invalid</p>",
            priority="critical",
        )

        assert result is False
        mock_smtp.assert_not_called()

    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_supports_custom_headers(self, mock_smtp, email_service):
        """Custom headers should be attached without affecting recipient delivery."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        result = email_service.send_email(
            to_email="recipient@test.com",
            subject="With headers",
            html_body="<p>custom headers</p>",
            headers={
                "X-Correlation-ID": "run-123",
                "List-Unsubscribe": "<mailto:unsubscribe@test.com>",
            },
        )

        assert result is True

        sent_message = mock_server.send_message.call_args[0][0]
        assert sent_message["X-Correlation-ID"] == "run-123"
        assert sent_message["List-Unsubscribe"] == "<mailto:unsubscribe@test.com>"

    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_rejects_protected_custom_headers(
        self,
        mock_smtp,
        email_service,
    ):
        """Custom headers cannot override core routing headers like Subject."""
        result = email_service.send_email(
            to_email="recipient@test.com",
            subject="Safe subject",
            html_body="<p>should fail</p>",
            headers={"Subject": "override"},
        )

        assert result is False
        mock_smtp.assert_not_called()

    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_email_rejects_subject_newline_injection(
        self,
        mock_smtp,
        email_service,
    ):
        """Subject should reject newline injection attempts before SMTP use."""
        result = email_service.send_email(
            to_email="recipient@test.com",
            subject="Legit\nBCC:attacker@test.com",
            html_body="<p>should fail</p>",
        )

        assert result is False
        mock_smtp.assert_not_called()
