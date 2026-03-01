"""Celery tasks for scheduled task execution."""

import asyncio
import logging
from celery import Task

from app.agents.celery_app import celery as celery_app
from app.services.scheduled_task_executor import ScheduledTaskExecutor

logger = logging.getLogger(__name__)


class AsyncTask(Task):
    """Custom Celery task class that supports async functions."""

    def __call__(self, *args, **kwargs):
        """Execute async function in event loop."""
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self.run(*args, **kwargs))


@celery_app.task(name="tasks.run_scheduled_tasks", base=AsyncTask)
async def run_scheduled_tasks():
    """
    Execute all scheduled tasks that are due.
    
    This task is triggered by Celery Beat every minute.
    It checks for scheduled tasks whose next_run_at has passed
    and executes them.
    
    Returns:
        Execution summary
    """
    logger.info("Celery: Running scheduled task executor...")
    
    try:
        result = await ScheduledTaskExecutor.run_scheduler()
        logger.info(f"Scheduled tasks executed: {result}")
        return result
    except Exception as e:
        logger.error(f"Scheduled task execution failed: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "tasks_executed": 0
        }


@celery_app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    """
    Configure Celery Beat periodic tasks.
    
    This runs once when Celery worker starts and sets up the schedule.
    """
    logger.info("Setting up Celery Beat periodic tasks...")
    
    # Run scheduled task checker every 1 minute
    sender.add_periodic_task(
        60.0,  # Every 60 seconds
        run_scheduled_tasks.s(),
        name="Check and execute scheduled tasks"
    )
    
    logger.info("✅ Celery Beat: Scheduled task checker configured (every 1 minute)")


__all__ = ["run_scheduled_tasks", "setup_periodic_tasks"]
