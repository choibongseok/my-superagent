"""Background tasks for AgentHQ."""

# Import all tasks to register with Celery
from app.tasks.nudge_email import send_usage_nudge_emails, test_nudge_email
from app.tasks.scheduled_tasks import *

__all__ = [
    "send_usage_nudge_emails",
    "test_nudge_email",
]
