"""Celery task: Usage nudge emails for inactive users.

Detects users who have not created a task in the past 7 days and sends
re-engagement emails. Weekly quota is enforced via ``nudge_email_count``
(with reset at the start of each UTC week).

Schedule: daily at 09:00 UTC (registered in celery_app.conf.beat_schedule).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select

from app.agents.celery_app import celery_app
from app.core.async_runner import run_async
from app.core.config import settings

logger = logging.getLogger(__name__)

# Maximum number of nudge emails sent per user per week
MAX_NUDGE_EMAILS_PER_WEEK = 2

# Days of inactivity before sending a nudge
INACTIVITY_DAYS = 7

_APP_FRONTEND_URL = settings.FRONTEND_URL.rstrip("/")


def _build_nudge_html(user_full_name: str | None) -> str:
    """Return the HTML body for the nudge re-engagement email."""
    name = user_full_name or "there"
    return f"""<!DOCTYPE html>
<html>
<head>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
                   'Helvetica Neue', Arial, sans-serif;
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
    <h1>🚀 We miss you, {name}!</h1>
  </div>
  <div class="content">
    <p>Hi {name},</p>
    <p>
      It's been a while since you last used <strong>AgentHQ</strong>.
      Your AI agents are ready and waiting to help you with research,
      documents, spreadsheets, and presentations.
    </p>
    <p style="text-align: center;">
      <a href="{_APP_FRONTEND_URL}" class="button">Jump back in →</a>
    </p>
    <p style="color: #6b7280; font-size: 14px;">
      If you no longer wish to receive these reminders, just ignore this
      email — we won't bother you more than twice each week.
    </p>
  </div>
  <div class="footer">
    <p>AgentHQ – AI-Powered Workspace Automation</p>
  </div>
</body>
</html>"""


def _build_nudge_text(user_full_name: str | None) -> str:
    """Return the plain-text body for the nudge re-engagement email."""
    name = user_full_name or "there"
    return (
        f"Hi {name},\n\n"
        "It's been a while since you last used AgentHQ. "
        "Your AI agents are ready and waiting!\n\n"
        f"Jump back in: {_APP_FRONTEND_URL}\n\n"
        "-- AgentHQ Team"
    )


def _utc_week_start(value: datetime) -> datetime:
    """Return the Monday 00:00 UTC boundary containing *value*."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value - timedelta(
        days=value.weekday(),
        hours=value.hour,
        minutes=value.minute,
        seconds=value.second,
        microseconds=value.microsecond,
    )


def _normalize_for_weekly_quota(
    user,
    now_week_start: datetime,
) -> bool:
    """Reset ``nudge_email_count`` when the user is in a new UTC week.

    Returns ``True`` when the counter was reset.
    """
    last_week_start = getattr(user, "nudge_email_week_start", None)

    if last_week_start is not None and last_week_start.tzinfo is None:
        last_week_start = last_week_start.replace(tzinfo=timezone.utc)

    if last_week_start is None or last_week_start < now_week_start:
        user.nudge_email_week_start = now_week_start
        user.nudge_email_count = 0
        return True

    return False


@celery_app.task(name="tasks.send_nudge_emails", bind=True, max_retries=3)
def send_nudge_emails(self):
    """Detect inactive users and send re-engagement emails.

    A user is considered inactive when their ``last_task_created_at`` is
    more than ``INACTIVITY_DAYS`` days ago (or ``NULL``, meaning they never
    created a task). Weekly quota is capped by ``MAX_NUDGE_EMAILS_PER_WEEK``.
    """

    async def _run() -> dict:
        from app.core.database import AsyncSessionLocal
        from app.models.user import User
        from app.services.email_service import email_service

        now = datetime.now(tz=timezone.utc)
        cutoff = now - timedelta(days=INACTIVITY_DAYS)
        week_start = _utc_week_start(now)

        async with AsyncSessionLocal() as session:
            # Query inactive, active users. ``nudge_email_count`` resets below if
            # the UTC week boundary changed.
            result = await session.execute(
                select(User).where(
                    and_(
                        User.is_active.is_(True),
                        or_(
                            User.last_task_created_at.is_(None),
                            User.last_task_created_at < cutoff,
                        ),
                    )
                )
            )
            inactive_users = result.scalars().all()

            sent_count = 0
            failed_count = 0

            for user in inactive_users:
                _normalize_for_weekly_quota(user, week_start)

                if user.nudge_email_count >= MAX_NUDGE_EMAILS_PER_WEEK:
                    logger.info(
                        "Nudge skip for %s: weekly quota already reached (%d/%d)",
                        user.email,
                        user.nudge_email_count,
                        MAX_NUDGE_EMAILS_PER_WEEK,
                    )
                    continue

                try:
                    success = email_service.send_email(
                        to_email=user.email,
                        subject="We miss you on AgentHQ 👋",
                        html_body=_build_nudge_html(user.full_name),
                        text_body=_build_nudge_text(user.full_name),
                    )
                    if success:
                        user.nudge_email_count += 1
                        sent_count += 1
                        logger.info(
                            "Nudge email sent to %s (count=%d)",
                            user.email,
                            user.nudge_email_count,
                        )
                    else:
                        failed_count += 1
                        logger.warning(
                            "Nudge email skipped/failed for %s (email disabled?)",
                            user.email,
                        )
                except Exception as exc:  # noqa: BLE001
                    failed_count += 1
                    logger.error(
                        "Error sending nudge to %s: %s",
                        user.email,
                        exc,
                    )

            await session.commit()

        return {
            "total_inactive": len(inactive_users),
            "sent": sent_count,
            "failed": failed_count,
        }

    try:
        result = run_async(_run)
        logger.info("send_nudge_emails completed: %s", result)
        return result
    except Exception as exc:
        logger.error("send_nudge_emails task error: %s", exc)
        raise self.retry(exc=exc, countdown=300)
