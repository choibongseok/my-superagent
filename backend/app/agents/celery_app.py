"""Celery application for AgentHQ task processing.

This module provides the Celery app instance and task definitions for
asynchronous processing of agent tasks (research, docs, sheets, slides).
"""

import logging
from datetime import datetime, timezone

from celery import Celery

from app.core.async_runner import run_async
from app.core.config import settings

logger = logging.getLogger(__name__)

# Create Celery app
celery_app = Celery(
    "agenthq",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,  # 10 minutes max
    task_soft_time_limit=540,  # 9 minutes soft limit
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)


@celery_app.task(name="agents.process_research_task", bind=True, max_retries=3)
def process_research_task(self, task_id: str, prompt: str, user_id: str):
    """Process research task asynchronously.

    Args:
        task_id: UUID of the task
        prompt: Research prompt
        user_id: User ID for context

    Returns:
        dict: Task result with research findings
    """
    try:
        from app.agents.research_agent import ResearchAgent

        logger.info(f"Starting research task {task_id}")

        # Create agent instance
        agent = ResearchAgent(
            user_id=user_id,
            session_id=task_id,
        )

        # Execute research (async method - must await)
        result = run_async(agent.research, prompt)

        logger.info(f"Completed research task {task_id}")

        # Update task status in database
        update_task_status(task_id, "completed", result=result)

        return {
            "status": "completed",
            "result": result,
        }

    except Exception as e:
        logger.error(f"Error in research task {task_id}: {str(e)}")
        # Update task status to failed
        update_task_status(task_id, "failed", error=str(e))
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2**self.request.retries))


@celery_app.task(name="agents.process_docs_task", bind=True, max_retries=3)
def process_docs_task(
    self,
    task_id: str,
    prompt: str,
    user_id: str,
    title: str = "Untitled Document",
):
    """Process Google Docs generation task asynchronously.

    Args:
        task_id: UUID of the task
        prompt: Document generation prompt
        user_id: User ID for context
        title: Document title

    Returns:
        dict: Task result with document URL
    """
    try:
        from app.agents.docs_agent import DocsAgent
        from app.services.google_auth import get_user_credentials

        logger.info(f"Starting docs task {task_id}")

        # Retrieve user credentials from database (async operation)
        credentials = run_async(get_user_credentials, user_id)

        if not credentials:
            raise ValueError(
                f"User {user_id} has no Google credentials. "
                "Please authenticate via Google OAuth first."
            )

        # Create agent instance with real credentials
        agent = DocsAgent(
            user_id=user_id,
            session_id=task_id,
            credentials=credentials,
        )

        # Generate document (async method - must await)
        result = run_async(
            agent.create_document,
            title=title,
            prompt=prompt,
        )

        logger.info(f"Completed docs task {task_id}")

        # Update task status in database
        update_task_status(task_id, "completed", result=result)

        return {
            "status": "completed",
            "result": result,
        }

    except Exception as e:
        logger.error(f"Error in docs task {task_id}: {str(e)}")
        update_task_status(task_id, "failed", error=str(e))
        raise self.retry(exc=e, countdown=60 * (2**self.request.retries))


@celery_app.task(name="agents.process_sheets_task", bind=True, max_retries=3)
def process_sheets_task(
    self,
    task_id: str,
    prompt: str,
    user_id: str,
    title: str = "Untitled Spreadsheet",
):
    """Process Google Sheets generation task asynchronously.

    Args:
        task_id: UUID of the task
        prompt: Spreadsheet generation prompt
        user_id: User ID for context
        title: Spreadsheet title

    Returns:
        dict: Task result with spreadsheet URL
    """
    try:
        from app.agents.sheets_agent import SheetsAgent
        from app.services.google_auth import get_user_credentials

        logger.info(f"Starting sheets task {task_id}")

        # Retrieve user credentials from database (async operation)
        credentials = run_async(get_user_credentials, user_id)

        if not credentials:
            raise ValueError(
                f"User {user_id} has no Google credentials. "
                "Please authenticate via Google OAuth first."
            )

        # Create agent instance with real credentials
        agent = SheetsAgent(
            user_id=user_id,
            session_id=task_id,
            credentials=credentials,
        )

        # Generate spreadsheet (async method - must await)
        result = run_async(agent.run, prompt)

        logger.info(f"Completed sheets task {task_id}")

        # Update task status in database
        update_task_status(task_id, "completed", result=result)

        return {
            "status": "completed",
            "result": result,
        }

    except Exception as e:
        logger.error(f"Error in sheets task {task_id}: {str(e)}")
        update_task_status(task_id, "failed", error=str(e))
        raise self.retry(exc=e, countdown=60 * (2**self.request.retries))


@celery_app.task(name="agents.process_slides_task", bind=True, max_retries=3)
def process_slides_task(
    self,
    task_id: str,
    prompt: str,
    user_id: str,
    title: str = "Untitled Presentation",
):
    """Process Google Slides generation task asynchronously.

    Args:
        task_id: UUID of the task
        prompt: Presentation generation prompt
        user_id: User ID for context
        title: Presentation title

    Returns:
        dict: Task result with presentation URL
    """
    try:
        from app.agents.slides_agent import SlidesAgent
        from app.services.google_auth import get_user_credentials

        logger.info(f"Starting slides task {task_id}")

        # Retrieve user credentials from database (async operation)
        credentials = run_async(get_user_credentials, user_id)

        if not credentials:
            raise ValueError(
                f"User {user_id} has no Google credentials. "
                "Please authenticate via Google OAuth first."
            )

        # Create agent instance with real credentials
        agent = SlidesAgent(
            user_id=user_id,
            session_id=task_id,
            credentials=credentials,
        )

        # Generate presentation (async method - must await)
        result = run_async(agent.run, prompt)

        logger.info(f"Completed slides task {task_id}")

        # Update task status in database
        update_task_status(task_id, "completed", result=result)

        return {
            "status": "completed",
            "result": result,
        }

    except Exception as e:
        logger.error(f"Error in slides task {task_id}: {str(e)}")
        update_task_status(task_id, "failed", error=str(e))
        raise self.retry(exc=e, countdown=60 * (2**self.request.retries))


@celery_app.task(name="agents.update_task_status")
def update_task_status(
    task_id: str, status: str, result: dict = None, error: str = None
):
    """Update task status in database after completion.

    Args:
        task_id: Task UUID
        status: New task status (completed, failed)
        result: Task result data (optional)
        error: Error message if failed (optional)
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.core.database import AsyncSessionLocal
    from app.models.task import Task as TaskModel, TaskStatus
    from app.models.task_chain import TaskChain
    from uuid import UUID

    async def _update():
        async with AsyncSessionLocal()() as session:
            # Get task
            result_query = await session.execute(
                select(TaskModel).where(TaskModel.id == UUID(task_id))
            )
            task = result_query.scalar_one_or_none()

            if not task:
                logger.error(f"Task {task_id} not found in database")
                return

            async def _maybe_advance_chain() -> None:
                if not task.task_metadata or not isinstance(task.task_metadata, dict):
                    return

                chain_id = task.task_metadata.get("chain_id")
                if not chain_id:
                    return

                try:
                    from app.services.chain_service import advance_chain

                    chain_query = await session.execute(
                        select(TaskChain)
                        .where(TaskChain.id == UUID(str(chain_id)))
                        .options(selectinload(TaskChain.steps))
                    )
                    chain = chain_query.scalar_one_or_none()
                    if chain is None or chain.user_id != task.user_id:
                        return

                    await advance_chain(session, chain, task)
                except Exception as chain_err:
                    logger.warning(
                        "Failed to advance chain for task %s: %s",
                        task_id,
                        chain_err,
                    )

            # Update status and finalize completion timestamp for all terminal states.
            now = datetime.now(timezone.utc)
            if status == "completed":
                task.status = TaskStatus.COMPLETED
                task.result = result
                task.error_message = None
                task.completed_at = now
            elif status == "failed":
                task.status = TaskStatus.FAILED
                task.error_message = error
                task.completed_at = now

            if status in {"completed", "failed"}:
                await _maybe_advance_chain()

            await session.commit()
            logger.info(f"Updated task {task_id} status to {status}")

            # Broadcast task lifecycle updates via WebSocket for live UI updates.
            try:
                from app.core.websocket import manager as ws_manager
                import re

                task_uuid = UUID(task_id)
                user_id = task.user_id

                if status == "completed":
                    normalized_result = result if isinstance(result, dict) else {"raw": result}

                    # Best-effort document URL extraction for downstream UI actions.
                    document_url = None
                    if isinstance(result, dict):
                        for key in ("document_url", "spreadsheet_url", "presentation_url", "url", "output_url"):
                            value = result.get(key)
                            if isinstance(value, str) and value.strip():
                                document_url = value.strip()
                                break

                        # Parse common markdown/plain-text payloads if needed.
                        if not document_url:
                            output = result.get("output")
                            if isinstance(output, str):
                                url_match = re.search(r"https://docs\.google\.com/[^\s`)]*", output)
                                if url_match:
                                    document_url = url_match.group(0)
                    elif isinstance(result, str):
                        url_match = re.search(r"https://docs\.google\.com/[^\s`)]*", result)
                        if url_match:
                            document_url = url_match.group(0)

                    if user_id:
                        await ws_manager.task_completed(
                            user_id,
                            task_uuid,
                            result=normalized_result,
                            document_url=document_url,
                        )
                elif status == "failed":
                    if user_id:
                        await ws_manager.task_failed(
                            user_id,
                            task_uuid,
                            error=error or "Task execution failed",
                        )
            except Exception as ws_err:
                logger.warning("Failed to emit task ws update for %s: %s", task_id, ws_err)

            # #228 Auto-QA: run quality validation on completed tasks
            if status == "completed":
                try:
                    from app.services.qa_auto import auto_qa_on_completion
                    await auto_qa_on_completion(session, UUID(task_id))
                except Exception as qa_err:
                    logger.warning(f"Auto-QA failed for task {task_id}: {qa_err}")

    try:
        run_async(_update)
    except Exception as e:
        logger.error(f"Failed to update task {task_id} status: {str(e)}")


# ── Celery Beat periodic schedule ────────────────────────────────────────────
from celery.schedules import crontab  # noqa: E402

celery_app.conf.beat_schedule = {
    # Send nudge re-engagement emails every day at 09:00 UTC
    "send-nudge-emails-daily": {
        "task": "tasks.send_nudge_emails",
        "schedule": crontab(hour=9, minute=0),
        "options": {"expires": 3600},  # discard if not picked up within 1 h
    },
}

# Register periodic tasks as part of celery bootstrap.
# This import is intentionally placed here so importing app.agents.celery_app
# automatically wires periodic executions at runtime.
from app.tasks import nudge_email as _nudge_email  # noqa: E402, F401
from app.tasks import scheduler as _scheduler  # noqa: E402, F401


# Add callback configuration for automatic status updates
# Health check task
@celery_app.task(name="agents.health_check")
def health_check():
    """Simple health check task for monitoring."""
    return {"status": "healthy", "message": "Celery worker is running"}
