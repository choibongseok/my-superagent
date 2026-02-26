"""Usage nudge email tasks for inactive users.

This module contains Celery tasks for sending nudge emails to users
who haven't created tasks in the last 7 days.

Features:
- Detect users inactive for 7+ days (based on last task created_at)
- Send personalized nudge emails
- Limit to max 2 emails per user per week
- Async database queries with SQLAlchemy
"""

import logging
from datetime import datetime, timedelta
from typing import List
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.agents.celery_app import celery_app
from app.core.async_runner import run_async
from app.core.database import AsyncSessionLocal
from app.models.task import Task
from app.models.user import User
from app.services.email_service import email_service

logger = logging.getLogger(__name__)


# In-memory tracking for weekly email limits
# TODO: Replace with database table (NudgeEmailLog) for persistence
# Format: {user_id: [timestamp1, timestamp2, ...]}
_weekly_nudge_tracker: dict[str, List[datetime]] = {}


def _can_send_nudge_email(user_id: str) -> bool:
    """Check if user can receive a nudge email (max 2 per week).
    
    Args:
        user_id: User UUID string
        
    Returns:
        True if user can receive email, False otherwise
    """
    # Get week start (Monday 00:00)
    now = datetime.utcnow()
    week_start = now - timedelta(days=now.weekday(), hours=now.hour, 
                                  minutes=now.minute, seconds=now.second,
                                  microseconds=now.microsecond)
    
    # Get user's nudge history
    if user_id not in _weekly_nudge_tracker:
        _weekly_nudge_tracker[user_id] = []
    
    # Clean old entries (older than current week)
    _weekly_nudge_tracker[user_id] = [
        ts for ts in _weekly_nudge_tracker[user_id]
        if ts >= week_start
    ]
    
    # Check if under limit (2 per week)
    return len(_weekly_nudge_tracker[user_id]) < 2


def _record_nudge_email(user_id: str) -> None:
    """Record that a nudge email was sent to user.
    
    Args:
        user_id: User UUID string
    """
    if user_id not in _weekly_nudge_tracker:
        _weekly_nudge_tracker[user_id] = []
    
    _weekly_nudge_tracker[user_id].append(datetime.utcnow())
    logger.info(f"Recorded nudge email for user {user_id}. "
                f"Count this week: {len(_weekly_nudge_tracker[user_id])}")


async def _get_inactive_users(days: int = 7) -> List[User]:
    """Get users who haven't created tasks in the last N days.
    
    Args:
        days: Number of days to consider inactive (default: 7)
        
    Returns:
        List of inactive User objects
    """
    async with AsyncSessionLocal() as session:
        # Cutoff date (7 days ago)
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Subquery: Get each user's most recent task creation date
        subquery = (
            select(
                Task.user_id,
                func.max(Task.created_at).label("last_task_at")
            )
            .group_by(Task.user_id)
            .subquery()
        )
        
        # Main query: Get active users with last task before cutoff
        # OR users with no tasks at all
        query = (
            select(User)
            .outerjoin(subquery, User.id == subquery.c.user_id)
            .where(
                User.is_active == True,
                # Either no tasks OR last task before cutoff
                (subquery.c.last_task_at == None) | 
                (subquery.c.last_task_at < cutoff_date)
            )
        )
        
        result = await session.execute(query)
        users = result.scalars().all()
        
        logger.info(f"Found {len(users)} inactive users (>{days} days)")
        return list(users)


def _send_nudge_email(user: User) -> bool:
    """Send a nudge email to an inactive user.
    
    Args:
        user: User object to send email to
        
    Returns:
        True if email sent successfully, False otherwise
    """
    subject = "We miss you at AgentHQ! 🚀"
    
    text_body = f"""
Hi {user.full_name or 'there'}!

We noticed you haven't used AgentHQ in a while. We've been busy adding new features and we'd love for you to check them out!

✨ What's new:
- Faster Google Docs generation
- New Sheets & Slides agents
- Improved research capabilities
- Better memory and context tracking

Ready to get back to work? Log in and create your next task:
https://app.agenthq.com

Have feedback or questions? Just reply to this email.

Best,
The AgentHQ Team

---
AgentHQ - AI-Powered Workspace Automation
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
            background: #f9fafb;
        }}
        .container {{
            background: white;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px 30px;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 28px;
            font-weight: 700;
        }}
        .content {{
            padding: 40px 30px;
        }}
        .greeting {{
            font-size: 18px;
            margin-bottom: 20px;
        }}
        .features {{
            background: #f9fafb;
            padding: 20px;
            border-radius: 8px;
            margin: 25px 0;
        }}
        .features h3 {{
            margin-top: 0;
            color: #667eea;
            font-size: 16px;
        }}
        .features ul {{
            margin: 10px 0 0 0;
            padding-left: 20px;
        }}
        .features li {{
            margin: 8px 0;
            color: #4b5563;
        }}
        .cta {{
            text-align: center;
            margin: 30px 0;
        }}
        .button {{
            display: inline-block;
            background: #667eea;
            color: white !important;
            padding: 14px 32px;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
            font-size: 16px;
            transition: background 0.2s;
        }}
        .button:hover {{
            background: #5568d3;
        }}
        .footer {{
            text-align: center;
            color: #6b7280;
            font-size: 14px;
            padding: 20px 30px;
            border-top: 1px solid #e5e7eb;
        }}
        .emoji {{
            font-size: 24px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="emoji">👋</div>
            <h1>We Miss You!</h1>
        </div>
        
        <div class="content">
            <p class="greeting">Hi {user.full_name or 'there'}!</p>
            
            <p>We noticed you haven't used <strong>AgentHQ</strong> in a while. We've been busy adding new features and improvements, and we'd love for you to check them out!</p>
            
            <div class="features">
                <h3>✨ What's New:</h3>
                <ul>
                    <li><strong>Faster Google Docs generation</strong> - Create documents in seconds</li>
                    <li><strong>New Sheets & Slides agents</strong> - Automate spreadsheets and presentations</li>
                    <li><strong>Improved research capabilities</strong> - Better sources and citations</li>
                    <li><strong>Enhanced memory</strong> - Agents remember your preferences</li>
                </ul>
            </div>
            
            <div class="cta">
                <a href="https://app.agenthq.com" class="button">Get Back to Work 🚀</a>
            </div>
            
            <p style="color: #6b7280; font-size: 14px; text-align: center;">
                Have feedback or questions? Just reply to this email.<br>
                We're here to help!
            </p>
        </div>
        
        <div class="footer">
            <p style="margin: 0;"><strong>AgentHQ</strong></p>
            <p style="margin: 5px 0 0 0;">AI-Powered Workspace Automation</p>
        </div>
    </div>
</body>
</html>
"""
    
    return email_service.send_email(
        to_email=user.email,
        subject=subject,
        html_body=html_body,
        text_body=text_body
    )


@celery_app.task(name="tasks.send_usage_nudge_emails", bind=True)
def send_usage_nudge_emails(self, days_inactive: int = 7) -> dict:
    """Send nudge emails to users inactive for N days.
    
    This task runs periodically (e.g., daily via cron) to:
    1. Find users who haven't created tasks in the last 7 days
    2. Check weekly email limit (max 2 per user per week)
    3. Send personalized nudge emails
    
    Args:
        days_inactive: Number of days of inactivity to trigger email (default: 7)
        
    Returns:
        dict: Summary of results
            - total_inactive: Number of inactive users found
            - emails_sent: Number of emails successfully sent
            - emails_skipped: Number of emails skipped (weekly limit)
            - errors: List of error messages
    """
    try:
        logger.info(f"Starting usage nudge email task (inactive >{days_inactive} days)")
        
        # Get inactive users (async operation)
        async def _get_users():
            return await _get_inactive_users(days=days_inactive)
        
        inactive_users = run_async(_get_users)
        
        total_inactive = len(inactive_users)
        emails_sent = 0
        emails_skipped = 0
        errors = []
        
        for user in inactive_users:
            user_id_str = str(user.id)
            
            # Check weekly limit
            if not _can_send_nudge_email(user_id_str):
                logger.info(f"Skipping user {user.email} - weekly limit reached (2/week)")
                emails_skipped += 1
                continue
            
            # Send email
            try:
                success = _send_nudge_email(user)
                if success:
                    _record_nudge_email(user_id_str)
                    emails_sent += 1
                    logger.info(f"✅ Sent nudge email to {user.email}")
                else:
                    errors.append(f"Failed to send email to {user.email}")
                    logger.error(f"❌ Failed to send email to {user.email}")
            except Exception as e:
                error_msg = f"Error sending to {user.email}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        result = {
            "status": "completed",
            "total_inactive": total_inactive,
            "emails_sent": emails_sent,
            "emails_skipped": emails_skipped,
            "errors": errors,
        }
        
        logger.info(
            f"Nudge email task completed: {emails_sent} sent, "
            f"{emails_skipped} skipped, {len(errors)} errors"
        )
        
        return result
        
    except Exception as e:
        error_msg = f"Critical error in nudge email task: {str(e)}"
        logger.error(error_msg)
        # Don't retry on critical errors
        return {
            "status": "failed",
            "error": error_msg,
            "total_inactive": 0,
            "emails_sent": 0,
            "emails_skipped": 0,
            "errors": [error_msg],
        }


@celery_app.task(name="tasks.test_nudge_email")
def test_nudge_email(user_email: str) -> dict:
    """Test task to send a single nudge email (for development/testing).
    
    Args:
        user_email: Email address to send test email to
        
    Returns:
        dict: Result status
    """
    try:
        async def _get_user():
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(User).where(User.email == user_email)
                )
                return result.scalar_one_or_none()
        
        user = run_async(_get_user)
        
        if not user:
            return {
                "status": "failed",
                "error": f"User not found: {user_email}"
            }
        
        success = _send_nudge_email(user)
        
        if success:
            return {
                "status": "success",
                "message": f"Test email sent to {user_email}"
            }
        else:
            return {
                "status": "failed",
                "error": f"Failed to send email to {user_email}"
            }
            
    except Exception as e:
        return {
            "status": "failed",
            "error": str(e)
        }
