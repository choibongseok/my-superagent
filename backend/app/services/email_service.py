"""Email service for sending notifications and invitations."""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails via SMTP."""
    
    def __init__(self):
        """Initialize email service with settings."""
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.from_email = settings.FROM_EMAIL
        self.from_name = settings.FROM_NAME
        self.enabled = settings.EMAIL_ENABLED
    
    def _create_message(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
    ) -> MIMEMultipart:
        """Create email message."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{self.from_name} <{self.from_email}>"
        msg["To"] = to_email
        
        # Add plain text version if provided
        if text_body:
            msg.attach(MIMEText(text_body, "plain"))
        
        # Add HTML version
        msg.attach(MIMEText(html_body, "html"))
        
        return msg
    
    def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
    ) -> bool:
        """
        Send an email.
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_body: HTML content
            text_body: Plain text content (optional)
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            logger.warning(
                f"Email disabled. Would send to {to_email}: {subject}"
            )
            return False
        
        try:
            msg = self._create_message(to_email, subject, html_body, text_body)
            
            # Connect to SMTP server
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            logger.info(f"Email sent to {to_email}: {subject}")
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
