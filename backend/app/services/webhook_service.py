"""Webhook delivery service.

Dispatches HTTP POST callbacks to registered webhook URLs when events occur.
Payloads are signed with HMAC-SHA256 so receivers can verify authenticity.

Usage (from task completion flow)::

    from app.services.webhook_service import webhook_service
    await webhook_service.dispatch(
        db=db,
        user_id=task.user_id,
        event="task.completed",
        payload={...},
    )
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook import Webhook

logger = logging.getLogger(__name__)

# Delivery settings
DELIVERY_TIMEOUT = 10  # seconds per request
MAX_RETRIES = 2
RETRY_DELAY = 1  # seconds between retries


def _sign_payload(payload_bytes: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 signature for a payload."""
    return hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()


class WebhookService:
    """Stateless service for dispatching webhook events."""

    async def dispatch(
        self,
        db: AsyncSession,
        user_id: UUID,
        event: str,
        payload: Dict[str, Any],
    ) -> int:
        """Send *event* to all matching webhooks for *user_id*.

        Returns the number of webhooks that were successfully delivered to.
        """
        result = await db.execute(
            select(Webhook).where(
                Webhook.user_id == user_id,
                Webhook.is_active.is_(True),
            )
        )
        webhooks: list[Webhook] = list(result.scalars().all())

        if not webhooks:
            return 0

        matching = [wh for wh in webhooks if wh.matches_event(event)]
        if not matching:
            return 0

        # Fire all deliveries concurrently
        results = await asyncio.gather(
            *(self._deliver(db, wh, event, payload) for wh in matching),
            return_exceptions=True,
        )

        success_count = sum(1 for r in results if r is True)
        logger.info(
            "Webhook dispatch: event=%s user=%s matched=%d succeeded=%d",
            event,
            user_id,
            len(matching),
            success_count,
        )
        return success_count

    async def _deliver(
        self,
        db: AsyncSession,
        webhook: Webhook,
        event: str,
        payload: Dict[str, Any],
    ) -> bool:
        """Deliver a single webhook with retries."""
        body = {
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": payload,
        }
        body_bytes = json.dumps(body, default=str).encode("utf-8")
        signature = _sign_payload(body_bytes, webhook.secret)

        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Event": event,
            "X-Webhook-Signature": f"sha256={signature}",
            "User-Agent": "AgentHQ-Webhook/1.0",
        }

        last_error: Optional[str] = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=DELIVERY_TIMEOUT) as client:
                    resp = await client.post(
                        webhook.url,
                        content=body_bytes,
                        headers=headers,
                    )
                if resp.status_code < 400:
                    # Success
                    webhook.success_count += 1
                    webhook.last_triggered_at = datetime.now(timezone.utc)
                    webhook.last_error = None
                    await db.commit()
                    return True
                else:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    logger.warning(
                        "Webhook %s delivery attempt %d failed: %s",
                        webhook.id,
                        attempt,
                        last_error,
                    )
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "Webhook %s delivery attempt %d error: %s",
                    webhook.id,
                    attempt,
                    last_error,
                )

            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY)

        # All retries exhausted
        webhook.failure_count += 1
        webhook.last_triggered_at = datetime.now(timezone.utc)
        webhook.last_error = last_error
        await db.commit()
        return False

    async def test_webhook(
        self,
        webhook: Webhook,
    ) -> Dict[str, Any]:
        """Send a test event to a webhook and return the result."""
        body = {
            "event": "webhook.test",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {
                "message": "This is a test webhook delivery from AgentHQ.",
                "webhook_id": str(webhook.id),
                "webhook_name": webhook.name,
            },
        }
        body_bytes = json.dumps(body, default=str).encode("utf-8")
        signature = _sign_payload(body_bytes, webhook.secret)

        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Event": "webhook.test",
            "X-Webhook-Signature": f"sha256={signature}",
            "User-Agent": "AgentHQ-Webhook/1.0",
        }

        try:
            async with httpx.AsyncClient(timeout=DELIVERY_TIMEOUT) as client:
                resp = await client.post(
                    webhook.url,
                    content=body_bytes,
                    headers=headers,
                )
            return {
                "success": resp.status_code < 400,
                "status_code": resp.status_code,
                "response_body": resp.text[:500],
            }
        except Exception as exc:
            return {
                "success": False,
                "error": f"{type(exc).__name__}: {exc}",
            }


# Module-level singleton
webhook_service = WebhookService()
