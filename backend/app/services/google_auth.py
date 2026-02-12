"""Google Authentication and Credentials Management Service."""

import logging
from typing import Optional
from uuid import UUID

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)


async def get_user_credentials(
    user_id: str | UUID,
    db: Optional[AsyncSession] = None,
) -> Optional[Credentials]:
    """
    Retrieve and refresh Google OAuth credentials for a user.
    
    Args:
        user_id: User UUID
        db: Optional database session (will create one if not provided)
        
    Returns:
        Google Credentials object, or None if user has no stored credentials
        
    Raises:
        ValueError: If user not found or credentials invalid
    """
    # Ensure user_id is UUID
    if isinstance(user_id, str):
        user_id = UUID(user_id)
    
    # Get database session
    should_close_db = False
    if db is None:
        db = await anext(get_db())
        should_close_db = True
    
    try:
        # Fetch user from database
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        # Check if user has Google credentials
        if not user.google_access_token:
            logger.warning(f"User {user_id} has no Google access token")
            return None
        
        # Create Credentials object
        credentials = Credentials(
            token=user.google_access_token,
            refresh_token=user.google_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            scopes=settings.google_scopes_list,
        )
        
        # Check if token is expired and refresh if needed
        if credentials.expired and credentials.refresh_token:
            logger.info(f"Refreshing expired token for user {user_id}")
            try:
                credentials.refresh(Request())
                
                # Update user with new tokens
                user.google_access_token = credentials.token
                if credentials.refresh_token:
                    user.google_refresh_token = credentials.refresh_token
                
                await db.commit()
                logger.info(f"Successfully refreshed token for user {user_id}")
                
            except Exception as e:
                logger.error(f"Failed to refresh token for user {user_id}: {e}")
                # Don't raise - return stale credentials and let Google API fail
                # This allows better error handling downstream
        
        return credentials
        
    finally:
        if should_close_db:
            await db.close()


def credentials_to_dict(credentials: Credentials) -> dict:
    """
    Convert Credentials object to dictionary for JSON serialization.
    
    Args:
        credentials: Google Credentials object
        
    Returns:
        Dictionary representation of credentials
    """
    return {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
    }


def dict_to_credentials(creds_dict: dict) -> Credentials:
    """
    Create Credentials object from dictionary.
    
    Args:
        creds_dict: Dictionary with credential data
        
    Returns:
        Google Credentials object
    """
    return Credentials(
        token=creds_dict.get("token"),
        refresh_token=creds_dict.get("refresh_token"),
        token_uri=creds_dict.get("token_uri"),
        client_id=creds_dict.get("client_id"),
        client_secret=creds_dict.get("client_secret"),
        scopes=creds_dict.get("scopes"),
    )


async def validate_credentials(credentials: Credentials) -> bool:
    """
    Validate that credentials are working.
    
    Args:
        credentials: Google Credentials object
        
    Returns:
        True if credentials are valid and working, False otherwise
    """
    try:
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        
        # Test credentials by making a simple API call
        from googleapiclient.discovery import build
        
        service = build("drive", "v3", credentials=credentials)
        # Just list files to verify credentials work
        service.files().list(pageSize=1).execute()
        
        return True
        
    except Exception as e:
        logger.error(f"Credential validation failed: {e}")
        return False


__all__ = [
    "get_user_credentials",
    "credentials_to_dict",
    "dict_to_credentials",
    "validate_credentials",
]
