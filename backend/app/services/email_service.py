"""Email service for sending notifications and invitations."""

from __future__ import annotations

import logging
import re
import smtplib
from collections.abc import Sequence
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import getaddresses
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails via SMTP."""

    _RECIPIENT_SEPARATOR_PATTERN = re.compile(r";")
    _EMAIL_ADDRESS_PATTERN = re.compile(
        r"^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@"
        r"(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)"
        r"(?:\.(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?))*$",
        flags=re.IGNORECASE,
    )

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

    def _create_message(
        self,
        to_emails: Sequence[str],
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
        cc_emails: Optional[Sequence[str]] = None,
        reply_to_email: str | None = None,
    ) -> MIMEMultipart:
        """Create an email message with optional CC and Reply-To headers."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{self.from_name} <{self.from_email}>"
        msg["To"] = ", ".join(to_emails)

        if cc_emails:
            msg["Cc"] = ", ".join(cc_emails)

        if reply_to_email:
            msg["Reply-To"] = reply_to_email

        # Add plain text version if provided
        if text_body:
            msg.attach(MIMEText(text_body, "plain"))

        # Add HTML version
        msg.attach(MIMEText(html_body, "html"))

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

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            logger.warning(f"Email disabled. Would send to {to_email}: {subject}")
            return False

        try:
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

            delivery_recipients = self._merge_unique_recipients(
                to_recipients,
                cc_recipients,
                bcc_recipients,
            )

            msg = self._create_message(
                to_recipients,
                subject,
                html_body,
                text_body,
                cc_emails=cc_recipients,
                reply_to_email=reply_to_recipient,
            )

            # Connect to SMTP server
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg, to_addrs=delivery_recipients)

            logger.info(f"Email sent to {delivery_recipients}: {subject}")
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
