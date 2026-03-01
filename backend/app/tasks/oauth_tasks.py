"""Celery task for OAuth token maintenance."""

from app.agents.celery_app import celery_app
from app.core.async_runner import run_async
from app.core.database import get_db_context
from app.services.oauth_service import OAuthService


@celery_app.task(name="oauth.cleanup_expired_tokens")
def cleanup_expired_tokens():
    """
    Clean up expired and old revoked refresh tokens.
    
    Scheduled to run daily via Celery Beat.
    
    Returns:
        dict: Result summary
    """
    async def _cleanup():
        async with get_db_context() as db:
            count = await OAuthService.cleanup_expired_tokens(db)
            return {
                "status": "success",
                "tokens_cleaned": count,
            }
    
    return run_async(_cleanup)
