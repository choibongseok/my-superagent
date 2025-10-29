"""Celery application for AgentHQ task processing.

This module provides the Celery app instance and task definitions for
asynchronous processing of agent tasks (research, docs, sheets, slides).
"""

from celery import Celery
from app.core.config import settings
import logging

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
        from uuid import UUID

        logger.info(f"Starting research task {task_id}")

        # Create agent instance
        agent = ResearchAgent(
            user_id=user_id,
            session_id=task_id,
        )

        # Execute research
        result = agent.research(prompt)

        logger.info(f"Completed research task {task_id}")
        return {
            "status": "completed",
            "result": result,
        }

    except Exception as e:
        logger.error(f"Error in research task {task_id}: {str(e)}")
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


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

        logger.info(f"Starting docs task {task_id}")

        # Create agent instance
        agent = DocsAgent(
            user_id=user_id,
            session_id=task_id,
            credentials=None,  # TODO: Get user credentials
        )

        # Generate document
        result = agent.create_document(
            title=title,
            content_request=prompt,
        )

        logger.info(f"Completed docs task {task_id}")
        return {
            "status": "completed",
            "result": result,
        }

    except Exception as e:
        logger.error(f"Error in docs task {task_id}: {str(e)}")
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


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

        logger.info(f"Starting sheets task {task_id}")

        # Create agent instance
        agent = SheetsAgent(
            user_id=user_id,
            session_id=task_id,
            credentials=None,  # TODO: Get user credentials
        )

        # Generate spreadsheet
        result = agent.create_spreadsheet(
            title=title,
            data_request=prompt,
        )

        logger.info(f"Completed sheets task {task_id}")
        return {
            "status": "completed",
            "result": result,
        }

    except Exception as e:
        logger.error(f"Error in sheets task {task_id}: {str(e)}")
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


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

        logger.info(f"Starting slides task {task_id}")

        # Create agent instance
        agent = SlidesAgent(
            user_id=user_id,
            session_id=task_id,
            credentials=None,  # TODO: Get user credentials
        )

        # Generate presentation
        result = agent.create_presentation(
            title=title,
            content_request=prompt,
        )

        logger.info(f"Completed slides task {task_id}")
        return {
            "status": "completed",
            "result": result,
        }

    except Exception as e:
        logger.error(f"Error in slides task {task_id}: {str(e)}")
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


# Health check task
@celery_app.task(name="agents.health_check")
def health_check():
    """Simple health check task for monitoring."""
    return {"status": "healthy", "message": "Celery worker is running"}
