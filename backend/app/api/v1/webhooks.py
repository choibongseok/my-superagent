"""Webhook management API endpoints.

CRUD for webhook configurations + test endpoint. Webhooks fire HTTP POST
callbacks when events like task completion/failure occur.

Endpoints:
- POST   /webhooks           — Register a new webhook
- GET    /webhooks           — List all webhooks for the current user
- GET    /webhooks/{id}      — Get a specific webhook
- PATCH  /webhooks/{id}      — Update a webhook
- DELETE /webhooks/{id}      — Delete a webhook
- POST   /webhooks/{id}/test — Send a test delivery
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.models.webhook import Webhook, WebhookEvent, generate_webhook_secret
from app.services.webhook_service import webhook_service

router = APIRouter()
logger = logging.getLogger(__name__)

# Maximum webhooks per user
MAX_WEBHOOKS_PER_USER = 10


# ── Schemas ───────────────────────────────────────────────────────────────────

class WebhookCreate(BaseModel):
    """Request body for creating a webhook."""

    name: str = Field(
        ..., min_length=1, max_length=255, description="Human-readable label"
    )
    url: str = Field(
        ..., max_length=2048, description="HTTPS URL to receive POST callbacks"
    )
    events: List[str] = Field(
        default=["task.*"],
        description="Event types to subscribe to",
        examples=[["task.completed", "task.failed"]],
    )


class WebhookUpdate(BaseModel):
    """Request body for updating a webhook."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    url: Optional[str] = Field(None, max_length=2048)
    events: Optional[List[str]] = None
    is_active: Optional[bool] = None


class WebhookResponse(BaseModel):
    """Webhook details returned to the client."""

    id: UUID
    name: str
    url: str
    events: List[str]
    is_active: bool
    secret: str = Field(
        ..., description="HMAC signing secret — use to verify X-Webhook-Signature"
    )
    success_count: int
    failure_count: int
    last_triggered_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, wh: Webhook) -> "WebhookResponse":
        return cls(
            id=wh.id,
            name=wh.name,
            url=wh.url,
            events=wh.event_list,
            is_active=wh.is_active,
            secret=wh.secret,
            success_count=wh.success_count,
            failure_count=wh.failure_count,
            last_triggered_at=wh.last_triggered_at,
            last_error=wh.last_error,
            created_at=wh.created_at,
            updated_at=wh.updated_at,
        )


class WebhookListResponse(BaseModel):
    """Paginated list of webhooks."""

    webhooks: List[WebhookResponse]
    total: int


class WebhookTestResponse(BaseModel):
    """Result of a test delivery."""

    success: bool
    status_code: Optional[int] = None
    response_body: Optional[str] = None
    error: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

_VALID_EVENTS = {e.value for e in WebhookEvent}


def _validate_events(events: List[str]) -> str:
    """Validate event names and return comma-separated string."""
    for event in events:
        if event not in _VALID_EVENTS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid event type: '{event}'. "
                       f"Valid types: {sorted(_VALID_EVENTS)}",
            )
    return ",".join(events)


async def _get_webhook_or_404(
    webhook_id: UUID,
    user: User,
    db: AsyncSession,
) -> Webhook:
    """Get a webhook owned by the user or raise 404."""
    result = await db.execute(
        select(Webhook).where(
            Webhook.id == webhook_id,
            Webhook.user_id == user.id,
        )
    )
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )
    return webhook


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "/webhooks",
    response_model=WebhookResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new webhook",
)
async def create_webhook(
    body: WebhookCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a webhook URL to receive event notifications.

    The response includes a ``secret`` for HMAC signature verification.
    Store it securely — it is only returned at creation time and on GET.
    """
    # Enforce per-user limit
    result = await db.execute(
        select(Webhook).where(Webhook.user_id == current_user.id)
    )
    existing = list(result.scalars().all())
    if len(existing) >= MAX_WEBHOOKS_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Maximum {MAX_WEBHOOKS_PER_USER} webhooks per user reached",
        )

    events_str = _validate_events(body.events)

    webhook = Webhook(
        user_id=current_user.id,
        name=body.name,
        url=body.url,
        events=events_str,
        secret=generate_webhook_secret(),
    )
    db.add(webhook)
    await db.commit()
    await db.refresh(webhook)

    logger.info("Webhook created: id=%s user=%s url=%s", webhook.id, current_user.id, body.url)
    return WebhookResponse.from_model(webhook)


@router.get(
    "/webhooks",
    response_model=WebhookListResponse,
    summary="List all webhooks",
)
async def list_webhooks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all webhooks registered by the current user."""
    result = await db.execute(
        select(Webhook)
        .where(Webhook.user_id == current_user.id)
        .order_by(Webhook.created_at.desc())
    )
    webhooks = list(result.scalars().all())
    return WebhookListResponse(
        webhooks=[WebhookResponse.from_model(wh) for wh in webhooks],
        total=len(webhooks),
    )


@router.get(
    "/webhooks/{webhook_id}",
    response_model=WebhookResponse,
    summary="Get a specific webhook",
)
async def get_webhook(
    webhook_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get details of a specific webhook."""
    webhook = await _get_webhook_or_404(webhook_id, current_user, db)
    return WebhookResponse.from_model(webhook)


@router.patch(
    "/webhooks/{webhook_id}",
    response_model=WebhookResponse,
    summary="Update a webhook",
)
async def update_webhook(
    webhook_id: UUID,
    body: WebhookUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update webhook configuration."""
    webhook = await _get_webhook_or_404(webhook_id, current_user, db)

    if body.name is not None:
        webhook.name = body.name
    if body.url is not None:
        webhook.url = body.url
    if body.events is not None:
        webhook.events = _validate_events(body.events)
    if body.is_active is not None:
        webhook.is_active = body.is_active

    await db.commit()
    await db.refresh(webhook)

    logger.info("Webhook updated: id=%s", webhook.id)
    return WebhookResponse.from_model(webhook)


@router.delete(
    "/webhooks/{webhook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a webhook",
)
async def delete_webhook(
    webhook_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a webhook permanently."""
    webhook = await _get_webhook_or_404(webhook_id, current_user, db)
    await db.delete(webhook)
    await db.commit()
    logger.info("Webhook deleted: id=%s", webhook.id)


@router.post(
    "/webhooks/{webhook_id}/test",
    response_model=WebhookTestResponse,
    summary="Send a test event",
)
async def test_webhook(
    webhook_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a test event to the webhook URL to verify connectivity."""
    webhook = await _get_webhook_or_404(webhook_id, current_user, db)
    result = await webhook_service.test_webhook(webhook)
    return WebhookTestResponse(**result)


@router.post(
    "/webhooks/{webhook_id}/rotate-secret",
    response_model=WebhookResponse,
    summary="Rotate the webhook signing secret",
)
async def rotate_webhook_secret(
    webhook_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a new signing secret for the webhook.

    The old secret is immediately invalidated. Update your receiver
    to use the new secret returned in the response.
    """
    webhook = await _get_webhook_or_404(webhook_id, current_user, db)
    webhook.secret = generate_webhook_secret()
    await db.commit()
    await db.refresh(webhook)
    logger.info("Webhook secret rotated: id=%s", webhook.id)
    return WebhookResponse.from_model(webhook)
