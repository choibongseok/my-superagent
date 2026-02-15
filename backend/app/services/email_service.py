"""Email service for sending notifications and invitations."""

from __future__ import annotations

import html
import logging
import mimetypes
import os
import re
import smtplib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import getaddresses
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailAttachment:
    """Normalized email attachment payload."""

    filename: str
    content: bytes
    mime_type: str = "application/octet-stream"


class EmailService:
    """Service for sending emails via SMTP."""

    _RECIPIENT_SEPARATOR_PATTERN = re.compile(r";")
    _EMAIL_ADDRESS_PATTERN = re.compile(
        r"^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@"
        r"(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)"
        r"(?:\.(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?))*$",
        flags=re.IGNORECASE,
    )
    _HEADER_NAME_PATTERN = re.compile(r"^[!-9;-~]+$")
    _PROTECTED_HEADERS = {
        "bcc",
        "cc",
        "content-transfer-encoding",
        "content-type",
        "from",
        "importance",
        "mime-version",
        "priority",
        "reply-to",
        "subject",
        "to",
        "x-priority",
    }
    _PRIORITY_ALIASES = {
        "high": "high",
        "urgent": "high",
        "normal": "normal",
        "medium": "normal",
        "low": "low",
    }

    def __init__(self):
        """Initialize email service with settings."""
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.from_email = settings.FROM_EMAIL
        self.from_name = settings.FROM_NAME
        self.enabled = settings.EMAIL_ENABLED

    @staticmethod
    def _sanitize_header_value(value: str, *, field_name: str) -> str:
        """Sanitize header-like values and block CR/LF injection vectors."""
        if "\r" in value or "\n" in value:
            raise ValueError(f"{field_name} entries cannot contain newline characters")

        return value.strip()

    @classmethod
    def _build_fallback_text_body(cls, html_body: str) -> str:
        """Build a readable plain-text fallback from HTML content."""
        if not isinstance(html_body, str):
            raise TypeError("html_body must be a string")

        without_scripts = re.sub(
            r"(?is)<(script|style)\b[^>]*>.*?</\1>",
            " ",
            html_body,
        )
        with_breaks = re.sub(r"(?i)<\s*br\s*/?>", "\n", without_scripts)
        with_block_newlines = re.sub(
            r"(?i)</\s*(p|div|li|tr|h[1-6])\s*>",
            "\n",
            with_breaks,
        )
        without_tags = re.sub(r"(?s)<[^>]+>", " ", with_block_newlines)

        normalized_lines = [
            " ".join(line.split()) for line in html.unescape(without_tags).splitlines()
        ]

        return "\n".join(line for line in normalized_lines if line).strip()

    @classmethod
    def _parse_recipient_addresses(
        cls,
        value: str,
        *,
        field_name: str,
    ) -> list[str]:
        """Parse one recipient entry into normalized addresses.

        Supports comma/semicolon-separated addresses and RFC display-name forms
        like ``Jane Doe <jane@example.com>``.
        """
        sanitized_value = cls._sanitize_header_value(value, field_name=field_name)
        if not sanitized_value:
            return []

        normalized_value = cls._RECIPIENT_SEPARATOR_PATTERN.sub(",", sanitized_value)
        parsed_addresses = getaddresses([normalized_value])

        normalized_addresses: list[str] = []
        for _, raw_address in parsed_addresses:
            address = cls._sanitize_header_value(raw_address, field_name=field_name)
            if not address:
                continue
            if not cls._EMAIL_ADDRESS_PATTERN.fullmatch(address):
                raise ValueError(
                    f"{field_name} contains an invalid email address: {address}"
                )

            normalized_addresses.append(address)

        return normalized_addresses

    @classmethod
    def _normalize_recipients(
        cls,
        recipients: str | Sequence[str],
        *,
        field_name: str,
    ) -> list[str]:
        """Normalize recipient input into a unique, ordered email list."""
        if isinstance(recipients, str):
            candidate_recipients = [recipients]
        elif isinstance(recipients, Sequence):
            candidate_recipients = list(recipients)
        else:
            raise TypeError(f"{field_name} must be a string or sequence of strings")

        normalized: list[str] = []
        seen_addresses: set[str] = set()
        for recipient in candidate_recipients:
            if not isinstance(recipient, str):
                raise TypeError(f"{field_name} entries must be strings")

            for address in cls._parse_recipient_addresses(
                recipient,
                field_name=field_name,
            ):
                dedupe_key = address.casefold()
                if dedupe_key in seen_addresses:
                    continue

                seen_addresses.add(dedupe_key)
                normalized.append(address)

        if not normalized:
            raise ValueError(f"{field_name} must include at least one email address")

        return normalized

    @classmethod
    def _normalize_optional_email(
        cls,
        email: str | None,
        *,
        field_name: str,
    ) -> str | None:
        """Normalize an optional single-email field such as Reply-To."""
        if email is None:
            return None
        if not isinstance(email, str):
            raise TypeError(f"{field_name} must be a string")

        parsed_addresses = cls._parse_recipient_addresses(email, field_name=field_name)
        if not parsed_addresses:
            return None

        unique_addresses = {address.casefold() for address in parsed_addresses}
        if len(unique_addresses) > 1:
            raise ValueError(f"{field_name} must include a single email address")

        return parsed_addresses[0]

    @classmethod
    def _normalize_priority(cls, priority: str | None) -> str | None:
        """Normalize optional priority values for outbound message headers."""
        if priority is None:
            return None
        if not isinstance(priority, str):
            raise TypeError("priority must be a string")

        normalized_priority = priority.strip().lower()
        if not normalized_priority:
            raise ValueError("priority must not be empty")

        canonical_priority = cls._PRIORITY_ALIASES.get(normalized_priority)
        if canonical_priority is None:
            raise ValueError("priority must be one of: high, normal, low")

        return canonical_priority

    @staticmethod
    def _apply_priority_headers(msg: MIMEMultipart, priority: str | None) -> None:
        """Apply RFC-friendly priority headers for client inbox triage."""
        if priority is None:
            return

        if priority == "high":
            msg["Importance"] = "high"
            msg["Priority"] = "urgent"
            msg["X-Priority"] = "1"
            return

        if priority == "normal":
            msg["Importance"] = "normal"
            msg["Priority"] = "normal"
            msg["X-Priority"] = "3"
            return

        msg["Importance"] = "low"
        msg["Priority"] = "non-urgent"
        msg["X-Priority"] = "5"

    @staticmethod
    def _merge_unique_recipients(*recipient_groups: Sequence[str]) -> list[str]:
        """Merge recipient groups while preserving first-seen order (case-insensitive)."""
        merged: list[str] = []
        seen: set[str] = set()

        for group in recipient_groups:
            for address in group:
                dedupe_key = address.casefold()
                if dedupe_key in seen:
                    continue

                seen.add(dedupe_key)
                merged.append(address)

        return merged

    @classmethod
    def _normalize_headers(
        cls,
        headers: Mapping[str, str] | None,
    ) -> dict[str, str]:
        """Normalize optional custom headers for outbound messages."""
        if headers is None:
            return {}
        if not isinstance(headers, Mapping):
            raise TypeError("headers must be a mapping of header names to values")

        normalized_headers: dict[str, str] = {}
        seen_header_names: set[str] = set()

        for raw_name, raw_value in headers.items():
            if not isinstance(raw_name, str):
                raise TypeError("headers keys must be strings")
            if not isinstance(raw_value, str):
                raise TypeError("headers values must be strings")

            header_name = cls._sanitize_header_value(
                raw_name,
                field_name="headers name",
            )
            if not header_name:
                raise ValueError("headers names must not be empty")
            if not cls._HEADER_NAME_PATTERN.fullmatch(header_name):
                raise ValueError(
                    "headers names must contain only visible ASCII header token characters"
                )

            normalized_name = header_name.casefold()
            if normalized_name in cls._PROTECTED_HEADERS:
                raise ValueError(
                    f"headers cannot override protected header: {header_name}"
                )
            if normalized_name in seen_header_names:
                raise ValueError(
                    f"headers cannot contain duplicate names: {header_name}"
                )

            header_value = cls._sanitize_header_value(
                raw_value,
                field_name=f"headers[{header_name}]",
            )

            seen_header_names.add(normalized_name)
            normalized_headers[header_name] = header_value

        return normalized_headers

    @classmethod
    def _normalize_attachments(
        cls,
        attachments: Sequence[Mapping[str, object]] | None,
    ) -> list[EmailAttachment]:
        """Normalize attachment payloads for MIME encoding.

        Each attachment entry can provide either:
        - ``content`` (bytes-like or string payload), or
        - ``path`` / ``file_path`` to load content from disk.

        ``filename`` is required for ``content`` attachments and optional for
        path-based attachments (defaults to the path basename).
        """
        if attachments is None:
            return []

        normalized_attachments: list[EmailAttachment] = []
        for index, attachment in enumerate(attachments):
            if not isinstance(attachment, Mapping):
                raise TypeError("attachments entries must be mappings")

            raw_path = attachment.get("path", attachment.get("file_path"))
            has_content = "content" in attachment
            has_path = raw_path is not None

            if has_content and has_path:
                raise ValueError(
                    "attachments must provide either content or path, not both"
                )
            if not has_content and not has_path:
                raise ValueError("attachments must provide content or path")

            resolved_path: str | None = None
            payload: bytes

            if has_path:
                if not isinstance(raw_path, str):
                    raise TypeError("attachments path must be a string")

                resolved_path = cls._sanitize_header_value(
                    raw_path,
                    field_name="attachments path",
                )
                if not resolved_path:
                    raise ValueError("attachments path must not be empty")

                try:
                    with open(resolved_path, "rb") as file_handle:
                        payload = file_handle.read()
                except OSError as exc:
                    raise ValueError(
                        f"attachments[{index}] path could not be read: {resolved_path}"
                    ) from exc
            else:
                content = attachment.get("content")
                if isinstance(content, str):
                    payload = content.encode("utf-8")
                elif isinstance(content, (bytes, bytearray, memoryview)):
                    payload = bytes(content)
                else:
                    raise TypeError(
                        "attachments content must be bytes, bytearray, memoryview, or str"
                    )

            if not payload:
                raise ValueError("attachments content must not be empty")

            raw_filename = attachment.get("filename")
            if raw_filename is None and resolved_path is not None:
                raw_filename = os.path.basename(resolved_path)

            if not isinstance(raw_filename, str):
                raise TypeError("attachments filename must be a string")

            filename = cls._sanitize_header_value(
                raw_filename,
                field_name="attachments filename",
            )
            if not filename:
                raise ValueError("attachments filename must not be empty")

            raw_mime_type = attachment.get("mime_type")
            if raw_mime_type is None:
                guessed_mime_type = (
                    mimetypes.guess_type(resolved_path)[0] if resolved_path else None
                )
                raw_mime_type = guessed_mime_type or "application/octet-stream"

            if not isinstance(raw_mime_type, str):
                raise TypeError("attachments mime_type must be a string")

            mime_type = cls._sanitize_header_value(
                raw_mime_type,
                field_name="attachments mime_type",
            )
            if "/" not in mime_type:
                raise ValueError(
                    f"attachments[{index}] mime_type must be in 'type/subtype' format"
                )

            normalized_attachments.append(
                EmailAttachment(
                    filename=filename,
                    content=payload,
                    mime_type=mime_type,
                )
            )

        return normalized_attachments

    @staticmethod
    def _build_attachment_part(attachment: EmailAttachment) -> MIMEBase:
        """Build a MIME attachment part for the provided payload."""
        main_type, sub_type = attachment.mime_type.split("/", maxsplit=1)
        part = MIMEBase(main_type, sub_type)
        part.set_payload(attachment.content)
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition", "attachment", filename=attachment.filename
        )
        return part

    def _create_message(
        self,
        to_emails: Sequence[str],
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
        cc_emails: Optional[Sequence[str]] = None,
        reply_to_email: str | None = None,
        attachments: Sequence[EmailAttachment] | None = None,
        headers: Mapping[str, str] | None = None,
        priority: str | None = None,
        auto_text_body: bool = True,
    ) -> MIMEMultipart:
        """Create an email message with optional CC, Reply-To, attachments, headers, and priority."""
        normalized_attachments = list(attachments or [])
        msg = MIMEMultipart("mixed" if normalized_attachments else "alternative")
        msg["Subject"] = subject
        msg["From"] = f"{self.from_name} <{self.from_email}>"
        msg["To"] = ", ".join(to_emails)

        if cc_emails:
            msg["Cc"] = ", ".join(cc_emails)

        if reply_to_email:
            msg["Reply-To"] = reply_to_email

        self._apply_priority_headers(msg, priority)

        for header_name, header_value in (headers or {}).items():
            msg[header_name] = header_value

        content_container: MIMEMultipart | None = None
        if normalized_attachments:
            content_container = MIMEMultipart("alternative")
            msg.attach(content_container)

        target_container = content_container or msg

        effective_text_body = text_body
        if effective_text_body is None and auto_text_body:
            effective_text_body = self._build_fallback_text_body(html_body)

        # Add plain text version if provided or auto-generated
        if effective_text_body:
            target_container.attach(MIMEText(effective_text_body, "plain"))

        # Add HTML version
        target_container.attach(MIMEText(html_body, "html"))

        for attachment in normalized_attachments:
            msg.attach(self._build_attachment_part(attachment))

        return msg

    def send_email(
        self,
        to_email: str | Sequence[str],
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
        cc_emails: Optional[Sequence[str]] = None,
        bcc_emails: Optional[Sequence[str]] = None,
        reply_to_email: str | None = None,
        attachments: Sequence[Mapping[str, object]] | None = None,
        headers: Mapping[str, str] | None = None,
        priority: str | None = None,
        auto_text_body: bool = True,
    ) -> bool:
        """
        Send an email.

        Args:
            to_email: Recipient email address (single) or list of addresses
            subject: Email subject
            html_body: HTML content
            text_body: Plain text content (optional)
            cc_emails: Carbon-copy recipients shown in email headers
            bcc_emails: Blind carbon-copy recipients hidden from headers
            reply_to_email: Optional Reply-To email address for recipient responses
            attachments: Optional email attachments with keys:
                - filename (str, optional): Attachment display name. Required
                  when using ``content`` and optional when using ``path``.
                - content (bytes | bytearray | memoryview | str): Payload data
                - path / file_path (str): Filesystem path to load attachment
                  content from disk
                - mime_type (str, optional): MIME type. Defaults to detected
                  file type for path-based attachments, otherwise
                  "application/octet-stream"
            headers: Optional custom message headers. Header names are
                validated and cannot override core delivery headers such as
                Subject, From, To, Cc, Bcc, Reply-To, Content-Type,
                MIME-Version, and priority headers.
            priority: Optional delivery priority level (``"high"``,
                ``"normal"``, or ``"low"``). Aliases ``"urgent"`` and
                ``"medium"`` are also supported.
            auto_text_body: When ``True`` and ``text_body`` is omitted,
                generate a plain-text fallback from ``html_body`` for improved
                client compatibility.

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            logger.warning(f"Email disabled. Would send to {to_email}: {subject}")
            return False

        try:
            if not isinstance(auto_text_body, bool):
                raise TypeError("auto_text_body must be a boolean")

            normalized_subject = self._sanitize_header_value(
                subject,
                field_name="subject",
            )
            if not normalized_subject:
                raise ValueError("subject must not be empty")

            to_recipients = self._normalize_recipients(
                to_email,
                field_name="to_email",
            )
            cc_recipients = (
                self._normalize_recipients(cc_emails, field_name="cc_emails")
                if cc_emails
                else []
            )
            bcc_recipients = (
                self._normalize_recipients(bcc_emails, field_name="bcc_emails")
                if bcc_emails
                else []
            )
            reply_to_recipient = self._normalize_optional_email(
                reply_to_email,
                field_name="reply_to_email",
            )
            normalized_priority = self._normalize_priority(priority)
            normalized_attachments = self._normalize_attachments(attachments)
            normalized_headers = self._normalize_headers(headers)

            delivery_recipients = self._merge_unique_recipients(
                to_recipients,
                cc_recipients,
                bcc_recipients,
            )

            msg = self._create_message(
                to_recipients,
                normalized_subject,
                html_body,
                text_body,
                cc_emails=cc_recipients,
                reply_to_email=reply_to_recipient,
                attachments=normalized_attachments,
                headers=normalized_headers,
                priority=normalized_priority,
                auto_text_body=auto_text_body,
            )

            # Connect to SMTP server
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg, to_addrs=delivery_recipients)

            logger.info(f"Email sent to {delivery_recipients}: {normalized_subject}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False

    def send_workspace_invitation(
        self,
        to_email: str,
        workspace_name: str,
        inviter_name: str,
        invitation_link: str,
        role: str,
        expires_in_days: int = 7,
    ) -> bool:
        """
        Send workspace invitation email.

        Args:
            to_email: Invitee email
            workspace_name: Name of workspace
            inviter_name: Name of person who sent invitation
            invitation_link: Link to accept invitation
            role: Role being invited to
            expires_in_days: Days until invitation expires

        Returns:
            True if sent successfully
        """
        subject = f"You've been invited to join {workspace_name}"

        text_body = f"""
Hi!

{inviter_name} has invited you to join the workspace "{workspace_name}" as a {role}.

Click the link below to accept the invitation:
{invitation_link}

This invitation will expire in {expires_in_days} days.

---
My SuperAgent
"""

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 8px 8px 0 0;
            text-align: center;
        }}
        .content {{
            background: #f9fafb;
            padding: 30px;
            border-radius: 0 0 8px 8px;
        }}
        .button {{
            display: inline-block;
            background: #667eea;
            color: white;
            padding: 12px 30px;
            text-decoration: none;
            border-radius: 6px;
            margin: 20px 0;
            font-weight: 600;
        }}
        .button:hover {{
            background: #5568d3;
        }}
        .details {{
            background: white;
            padding: 20px;
            border-radius: 6px;
            margin: 20px 0;
            border-left: 4px solid #667eea;
        }}
        .footer {{
            text-align: center;
            color: #6b7280;
            font-size: 14px;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #e5e7eb;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🎉 Workspace Invitation</h1>
    </div>
    <div class="content">
        <p>Hi!</p>
        
        <p><strong>{inviter_name}</strong> has invited you to join their workspace.</p>
        
        <div class="details">
            <p style="margin: 0;"><strong>Workspace:</strong> {workspace_name}</p>
            <p style="margin: 10px 0 0 0;"><strong>Role:</strong> {role}</p>
        </div>
        
        <p style="text-align: center;">
            <a href="{invitation_link}" class="button">Accept Invitation</a>
        </p>
        
        <p style="color: #6b7280; font-size: 14px;">
            This invitation will expire in {expires_in_days} days.
        </p>
        
        <p style="color: #6b7280; font-size: 14px;">
            If you didn't expect this invitation, you can safely ignore this email.
        </p>
    </div>
    <div class="footer">
        <p>My SuperAgent - AI-Powered Workspace Automation</p>
    </div>
</body>
</html>
"""

        return self.send_email(to_email, subject, html_body, text_body)


# Global email service instance
email_service = EmailService()
