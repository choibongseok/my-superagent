"""Google Authentication and Credentials Management Service."""

import logging
import re
from collections.abc import Iterable
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


_SCOPE_DELIMITER_PATTERN = re.compile(r"[\s,]+")


def _normalize_required_scopes(
    required_scopes: str | Iterable[str] | None,
) -> list[str]:
    """Normalize and validate required scope inputs.

    Args:
        required_scopes: Scope string, iterable of scope strings, or ``None``.
            String values can contain one scope or a comma/whitespace-delimited
            scope list.

    Returns:
        Normalized unique scope list in first-seen order.

    Raises:
        TypeError: If input shape is unsupported or includes non-string values.
        ValueError: If any scope value is blank.
    """
    if required_scopes is None:
        return []

    if isinstance(required_scopes, str):
        scope_values: list[str] = [required_scopes]
    elif isinstance(required_scopes, Iterable):
        scope_values = list(required_scopes)
    else:
        raise TypeError(
            "required_scopes must be a string, an iterable of strings, or None"
        )

    normalized_scopes: list[str] = []
    seen_scopes: set[str] = set()

    for scope in scope_values:
        if not isinstance(scope, str):
            raise TypeError("required_scopes must contain only strings")

        normalized_scope_value = scope.strip()
        if not normalized_scope_value:
            raise ValueError("required_scopes cannot contain empty values")

        extracted_scopes = [
            token
            for token in _SCOPE_DELIMITER_PATTERN.split(normalized_scope_value)
            if token
        ]
        if not extracted_scopes:
            raise ValueError("required_scopes cannot contain empty values")

        for normalized_scope in extracted_scopes:
            if normalized_scope in seen_scopes:
                continue

            seen_scopes.add(normalized_scope)
            normalized_scopes.append(normalized_scope)

    return normalized_scopes


def get_missing_scopes(
    credentials: Credentials,
    required_scopes: str | Iterable[str] | None,
) -> list[str]:
    """Return required scopes that are not present in credentials."""
    normalized_required_scopes = _normalize_required_scopes(required_scopes)
    if not normalized_required_scopes:
        return []

    available_scopes = {
        scope.strip()
        for scope in (credentials.scopes or [])
        if isinstance(scope, str) and scope.strip()
    }

    return [
        scope for scope in normalized_required_scopes if scope not in available_scopes
    ]


def credentials_have_scopes(
    credentials: Credentials,
    required_scopes: str | Iterable[str] | None,
) -> bool:
    """Return whether credentials include all required scopes."""
    return not get_missing_scopes(credentials, required_scopes)


async def get_user_credentials(
    user_id: str | UUID,
    db: Optional[AsyncSession] = None,
    required_scopes: str | Iterable[str] | None = None,
) -> Optional[Credentials]:
    """
    Retrieve and refresh Google OAuth credentials for a user.

    Args:
        user_id: User UUID
        db: Optional database session (will create one if not provided)
        required_scopes: Optional scope or scopes that must be present

    Returns:
        Google Credentials object, or None if user has no stored credentials

    Raises:
        ValueError: If user not found, user_id is invalid, credentials are invalid,
            or required scopes are missing.
        TypeError: If ``required_scopes`` is invalid.
    """
    # Ensure user_id is UUID
    if isinstance(user_id, str):
        try:
            user_id = UUID(user_id)
        except ValueError as error:
            raise ValueError("user_id must be a valid UUID") from error

    # Get database session
    should_close_db = False
    if db is None:
        db = await anext(get_db())
        should_close_db = True

    try:
        # Fetch user from database
        result = await db.execute(select(User).where(User.id == user_id))
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

        missing_scopes = get_missing_scopes(credentials, required_scopes)
        if missing_scopes:
            missing_scopes_text = ", ".join(missing_scopes)
            raise ValueError(
                f"User {user_id} credentials are missing required scopes: "
                f"{missing_scopes_text}"
            )

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
    "get_missing_scopes",
    "credentials_have_scopes",
]
