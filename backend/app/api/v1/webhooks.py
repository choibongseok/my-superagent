"""Google Drive Webhook API — Automatic file change detection and processing.

This module implements Google Drive push notifications to automatically
trigger document processing when files are uploaded or modified.

Flow:
  1. User enables webhooks via POST /webhooks/drive/watch
  2. Backend registers with Google Drive API
  3. Google sends notifications to POST /webhooks/drive/notifications
  4. Backend queues appropriate task (summary, analysis, etc.)

References:
  - https://developers.google.com/drive/api/guides/push
  - Google Drive API v3 push notifications
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.models.task import TaskType
from app.schemas.task import TaskCreate

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class DriveWatchRequest(BaseModel):
    """Request to start watching a Google Drive folder for changes."""
    
    folder_id: str = Field(
        ...,
        description="Google Drive folder ID to watch (use 'root' for entire drive)",
    )
    auto_summarize: bool = Field(
        default=True,
        description="Automatically summarize new documents",
    )
    auto_analyze_sheets: bool = Field(
        default=True,
        description="Automatically analyze new spreadsheets",
    )
    watch_duration_hours: int = Field(
        default=168,  # 7 days
        ge=1,
        le=720,  # 30 days max
        description="How long to watch for changes (hours)",
    )


class DriveWatchResponse(BaseModel):
    """Response after setting up Drive watching."""
    
    watch_id: str
    folder_id: str
    expires_at: str
    resource_id: str
    webhook_url: str
    auto_summarize: bool
    auto_analyze_sheets: bool


class DriveNotificationPayload(BaseModel):
    """Google Drive push notification payload structure."""
    
    kind: str = Field(default="drive#channel")
    id: str  # Channel ID we provided
    resource_id: str  # Google's resource identifier
    resource_uri: str
    token: Optional[str] = None  # Verification token
    expiration: Optional[str] = None  # Unix timestamp (milliseconds)


# ---------------------------------------------------------------------------
# In-Memory Watch Registry (Production: use Redis or DB)
# ---------------------------------------------------------------------------

# TODO: Move to Redis/PostgreSQL for production
_active_watches: dict[str, dict] = {}


def _store_watch(watch_id: str, user_id: str, watch_config: dict):
    """Store active watch configuration (temp in-memory implementation)."""
    _active_watches[watch_id] = {
        "user_id": user_id,
        "config": watch_config,
        "created_at": datetime.now(tz=timezone.utc),
    }


def _get_watch(watch_id: str) -> dict | None:
    """Retrieve watch configuration by ID."""
    return _active_watches.get(watch_id)


def _remove_watch(watch_id: str):
    """Remove a watch when it expires or is cancelled."""
    _active_watches.pop(watch_id, None)


# ---------------------------------------------------------------------------
# Google Drive API Helpers
# ---------------------------------------------------------------------------

def _create_drive_watch_channel(
    credentials,
    folder_id: str,
    watch_id: str,
    expiration_ms: int,
) -> dict:
    """Register a push notification channel with Google Drive API.
    
    Args:
        credentials: Google OAuth2 credentials
        folder_id: Drive folder to watch
        watch_id: Unique channel ID
        expiration_ms: Expiration time in Unix milliseconds
        
    Returns:
        Google API response with resource_id and resource_uri
    """
    from googleapiclient.discovery import build
    
    service = build("drive", "v3", credentials=credentials)
    
    # Webhook endpoint (must be HTTPS in production)
    webhook_url = f"{settings.BACKEND_URL}/api/v1/webhooks/drive/notifications"
    
    channel_body = {
        "id": watch_id,
        "type": "web_hook",
        "address": webhook_url,
        "expiration": expiration_ms,
        "token": watch_id,  # Verification token
    }
    
    # Watch changes in the folder
    response = service.files().watch(
        fileId=folder_id,
        body=channel_body,
        supportsAllDrives=True,
    ).execute()
    
    logger.info(f"Drive watch channel created: {watch_id} → {folder_id}")
    return response


def _stop_drive_watch_channel(credentials, channel_id: str, resource_id: str):
    """Stop a Google Drive push notification channel.
    
    Args:
        credentials: Google OAuth2 credentials
        channel_id: Our channel ID
        resource_id: Google's resource ID
    """
    from googleapiclient.discovery import build
    
    service = build("drive", "v3", credentials=credentials)
    
    service.channels().stop(body={
        "id": channel_id,
        "resourceId": resource_id,
    }).execute()
    
    logger.info(f"Drive watch channel stopped: {channel_id}")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/drive/watch", response_model=DriveWatchResponse)
async def start_drive_watch(
    request: DriveWatchRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Start watching a Google Drive folder for changes.
    
    This endpoint registers a webhook with Google Drive API to receive
    push notifications when files are added or modified in the specified folder.
    
    Args:
        request: Watch configuration (folder_id, auto actions)
        current_user: Authenticated user
        db: Database session
        
    Returns:
        DriveWatchResponse with watch details
        
    Raises:
        HTTPException: If user doesn't have Google credentials
    """
    # Check for Google credentials
    if not current_user.google_access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google credentials required. Please authenticate via /auth/google",
        )
    
    from google.oauth2.credentials import Credentials
    
    credentials = Credentials(
        token=current_user.google_access_token,
        refresh_token=current_user.google_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
    )
    
    # Generate unique watch ID
    watch_id = f"watch_{uuid.uuid4().hex[:16]}"
    
    # Calculate expiration
    expiration_time = datetime.now(tz=timezone.utc) + timedelta(
        hours=request.watch_duration_hours
    )
    expiration_ms = int(expiration_time.timestamp() * 1000)
    
    # Register with Google Drive API
    try:
        drive_response = _create_drive_watch_channel(
            credentials=credentials,
            folder_id=request.folder_id,
            watch_id=watch_id,
            expiration_ms=expiration_ms,
        )
    except Exception as e:
        logger.error(f"Failed to create Drive watch: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register Drive webhook: {str(e)}",
        )
    
    # Store watch configuration
    watch_config = {
        "folder_id": request.folder_id,
        "auto_summarize": request.auto_summarize,
        "auto_analyze_sheets": request.auto_analyze_sheets,
        "resource_id": drive_response["resourceId"],
        "resource_uri": drive_response["resourceUri"],
        "expires_at": expiration_time,
    }
    
    _store_watch(watch_id, str(current_user.id), watch_config)
    
    webhook_url = f"{settings.BACKEND_URL}/api/v1/webhooks/drive/notifications"
    
    return DriveWatchResponse(
        watch_id=watch_id,
        folder_id=request.folder_id,
        expires_at=expiration_time.isoformat(),
        resource_id=drive_response["resourceId"],
        webhook_url=webhook_url,
        auto_summarize=request.auto_summarize,
        auto_analyze_sheets=request.auto_analyze_sheets,
    )


@router.post("/drive/notifications", status_code=status.HTTP_200_OK)
async def receive_drive_notification(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_goog_channel_id: Annotated[str, Header()],
    x_goog_resource_id: Annotated[str, Header()],
    x_goog_resource_state: Annotated[str, Header()],
    x_goog_channel_token: Annotated[str | None, Header()] = None,
):
    """Receive Google Drive push notifications.
    
    Google Drive sends POST requests to this endpoint when files change.
    
    Headers from Google:
      - X-Goog-Channel-ID: Our channel ID
      - X-Goog-Resource-ID: Google's resource ID
      - X-Goog-Resource-State: change | sync
      - X-Goog-Channel-Token: Our verification token
      
    Args:
        request: FastAPI request object
        db: Database session
        x_goog_channel_id: Channel ID (our watch_id)
        x_goog_resource_id: Google resource ID
        x_goog_resource_state: Notification type
        x_goog_channel_token: Verification token
        
    Returns:
        Success message
    """
    logger.info(
        f"Drive notification received: channel={x_goog_channel_id}, "
        f"state={x_goog_resource_state}, resource={x_goog_resource_id}"
    )
    
    # Verify this is a legitimate watch
    watch_data = _get_watch(x_goog_channel_id)
    if not watch_data:
        logger.warning(f"Unknown watch channel: {x_goog_channel_id}")
        return {"status": "ignored", "reason": "unknown_channel"}
    
    # Ignore initial sync notifications
    if x_goog_resource_state == "sync":
        logger.debug(f"Sync notification ignored for {x_goog_channel_id}")
        return {"status": "sync_acknowledged"}
    
    # Only process "change" notifications
    if x_goog_resource_state != "change":
        return {"status": "ignored", "reason": f"state={x_goog_resource_state}"}
    
    # Verify token matches
    if x_goog_channel_token != x_goog_channel_id:
        logger.warning(
            f"Token mismatch for {x_goog_channel_id}: "
            f"expected={x_goog_channel_id}, got={x_goog_channel_token}"
        )
        return {"status": "ignored", "reason": "token_mismatch"}
    
    # Get user
    user_id = watch_data["user_id"]
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        logger.error(f"User not found for watch: {user_id}")
        _remove_watch(x_goog_channel_id)
        return {"status": "error", "reason": "user_not_found"}
    
    # Fetch changed file details
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        
        credentials = Credentials(
            token=user.google_access_token,
            refresh_token=user.google_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
        )
        
        service = build("drive", "v3", credentials=credentials)
        
        # Get recent changes
        # Note: This is simplified - production should use change tokens
        folder_id = watch_data["config"]["folder_id"]
        query = f"'{folder_id}' in parents and trashed=false"
        
        files = service.files().list(
            q=query,
            pageSize=10,
            orderBy="modifiedTime desc",
            fields="files(id, name, mimeType, modifiedTime)",
        ).execute().get("files", [])
        
        if not files:
            logger.debug("No recent files found in watched folder")
            return {"status": "no_changes"}
        
        # Process most recent file
        file = files[0]
        file_id = file["id"]
        file_name = file["name"]
        mime_type = file.get("mimeType", "")
        
        logger.info(f"Processing changed file: {file_name} ({file_id})")
        
        # Determine task type based on mime type
        config = watch_data["config"]
        task_type = None
        prompt_template = None
        
        if "document" in mime_type and config.get("auto_summarize"):
            task_type = TaskType.DOCS
            prompt_template = f"Summarize the document: {file_name}"
        elif "spreadsheet" in mime_type and config.get("auto_analyze_sheets"):
            task_type = TaskType.SHEETS
            prompt_template = f"Analyze the spreadsheet: {file_name}"
        elif "presentation" in mime_type:
            task_type = TaskType.SLIDES
            prompt_template = f"Review the presentation: {file_name}"
        
        if not task_type:
            logger.debug(f"No auto-action configured for {mime_type}")
            return {"status": "ignored", "reason": "no_auto_action"}
        
        # Queue task
        from app.agents.celery_app import (
            process_docs_task,
            process_sheets_task,
            process_slides_task,
        )
        
        # Create task in DB
        from app.models.task import Task as TaskModel, TaskStatus
        
        task = TaskModel(
            user_id=user.id,
            prompt=prompt_template,
            task_type=task_type,
            status=TaskStatus.PENDING,
            task_metadata={
                "file_id": file_id,
                "file_name": file_name,
                "trigger": "drive_webhook",
                "watch_id": x_goog_channel_id,
            },
        )
        
        db.add(task)
        await db.commit()
        await db.refresh(task)
        
        # Queue to Celery
        task_id_str = str(task.id)
        user_id_str = str(user.id)
        
        if task_type == TaskType.DOCS:
            celery_task = process_docs_task.apply_async(
                args=[task_id_str, prompt_template, user_id_str, file_name]
            )
        elif task_type == TaskType.SHEETS:
            celery_task = process_sheets_task.apply_async(
                args=[task_id_str, prompt_template, user_id_str, file_name]
            )
        elif task_type == TaskType.SLIDES:
            celery_task = process_slides_task.apply_async(
                args=[task_id_str, prompt_template, user_id_str, file_name]
            )
        else:
            logger.warning(f"Unsupported task type: {task_type}")
            return {"status": "error", "reason": "unsupported_task_type"}
        
        task.celery_task_id = celery_task.id
        task.status = TaskStatus.IN_PROGRESS
        await db.commit()
        
        logger.info(
            f"Auto-task queued: {task.id} for file {file_name} (type={task_type})"
        )
        
        return {
            "status": "processed",
            "task_id": str(task.id),
            "file_name": file_name,
            "action": str(task_type.value),
        }
        
    except Exception as e:
        logger.error(f"Failed to process Drive notification: {e}", exc_info=True)
        return {"status": "error", "reason": str(e)}


@router.delete("/drive/watch/{watch_id}", status_code=status.HTTP_204_NO_CONTENT)
async def stop_drive_watch(
    watch_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Stop watching a Google Drive folder.
    
    Args:
        watch_id: Watch ID to cancel
        current_user: Authenticated user
        
    Raises:
        HTTPException: If watch not found or doesn't belong to user
    """
    watch_data = _get_watch(watch_id)
    
    if not watch_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watch not found or already expired",
        )
    
    # Verify ownership
    if watch_data["user_id"] != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to stop this watch",
        )
    
    # Stop the watch with Google
    try:
        from google.oauth2.credentials import Credentials
        
        credentials = Credentials(
            token=current_user.google_access_token,
            refresh_token=current_user.google_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
        )
        
        config = watch_data["config"]
        _stop_drive_watch_channel(
            credentials=credentials,
            channel_id=watch_id,
            resource_id=config["resource_id"],
        )
    except Exception as e:
        logger.warning(f"Failed to stop Drive watch with Google: {e}")
        # Continue anyway - remove from our registry
    
    _remove_watch(watch_id)
    
    logger.info(f"Watch stopped: {watch_id}")


@router.get("/drive/watches")
async def list_drive_watches(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """List all active Drive watches for the current user.
    
    Args:
        current_user: Authenticated user
        
    Returns:
        List of active watches with configuration
    """
    user_id = str(current_user.id)
    
    user_watches = [
        {
            "watch_id": watch_id,
            **watch_data["config"],
            "created_at": watch_data["created_at"].isoformat(),
        }
        for watch_id, watch_data in _active_watches.items()
        if watch_data["user_id"] == user_id
    ]
    
    return {
        "watches": user_watches,
        "total": len(user_watches),
    }


__all__ = ["router"]
