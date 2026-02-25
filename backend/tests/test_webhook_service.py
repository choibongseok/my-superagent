"""Comprehensive tests for webhook_service.py.

Tests webhook delivery, retries, signature verification, and error handling.
"""

import hashlib
import hmac
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook import Webhook
from app.services.webhook_service import (
    DELIVERY_TIMEOUT,
    MAX_RETRIES,
    RETRY_DELAY,
    _sign_payload,
    webhook_service,
)


@pytest.fixture
def sample_webhook():
    """Create a sample webhook instance."""
    return Webhook(
        id=uuid4(),
        user_id=uuid4(),
        name="Test Webhook",
        url="https://example.com/webhook",
        secret="test_secret_key",
        events="task.completed,task.failed",  # Comma-separated string
        is_active=True,
        success_count=0,
        failure_count=0,
        last_triggered_at=None,
        last_error=None,
    )


@pytest.fixture
def mock_db():
    """Mock AsyncSession database."""
    db = AsyncMock(spec=AsyncSession)
    db.commit = AsyncMock()
    db.execute = AsyncMock()
    return db


# ============================================================================
# Test _sign_payload()
# ============================================================================


class TestSignPayload:
    """Test HMAC-SHA256 signature generation."""

    def test_sign_payload_basic(self):
        """Test basic signature generation."""
        payload = b"test payload"
        secret = "my_secret"
        signature = _sign_payload(payload, secret)

        # Verify signature is hex string
        assert isinstance(signature, str)
        assert len(signature) == 64  # SHA256 hex = 64 chars
        assert all(c in "0123456789abcdef" for c in signature)

    def test_sign_payload_matches_hmac(self):
        """Test signature matches manual HMAC calculation."""
        payload = b"hello world"
        secret = "secret123"
        signature = _sign_payload(payload, secret)

        # Manual calculation
        expected = hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

        assert signature == expected

    def test_sign_payload_different_secrets(self):
        """Test different secrets produce different signatures."""
        payload = b"same payload"
        sig1 = _sign_payload(payload, "secret1")
        sig2 = _sign_payload(payload, "secret2")

        assert sig1 != sig2

    def test_sign_payload_different_payloads(self):
        """Test different payloads produce different signatures."""
        secret = "same_secret"
        sig1 = _sign_payload(b"payload1", secret)
        sig2 = _sign_payload(b"payload2", secret)

        assert sig1 != sig2

    def test_sign_payload_empty_payload(self):
        """Test signing empty payload."""
        signature = _sign_payload(b"", "secret")
        assert isinstance(signature, str)
        assert len(signature) == 64


# ============================================================================
# Test dispatch()
# ============================================================================


class TestDispatch:
    """Test event dispatching to multiple webhooks."""

    @pytest.mark.asyncio
    async def test_dispatch_no_webhooks(self, mock_db):
        """Test dispatch with no registered webhooks."""
        # Mock empty result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        count = await webhook_service.dispatch(
            db=mock_db,
            user_id=uuid4(),
            event="task.completed",
            payload={"task_id": "123"},
        )

        assert count == 0

    @pytest.mark.asyncio
    async def test_dispatch_no_matching_events(self, mock_db, sample_webhook):
        """Test dispatch with webhooks that don't match event."""
        # Mock webhook that only listens to "task.started"
        sample_webhook.events = "task.started"  # String, not list
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_webhook]
        mock_db.execute.return_value = mock_result

        # Mock matches_event to return False
        with patch.object(sample_webhook, "matches_event", return_value=False):
            count = await webhook_service.dispatch(
                db=mock_db,
                user_id=sample_webhook.user_id,
                event="task.completed",
                payload={"task_id": "123"},
            )

        assert count == 0

    @pytest.mark.asyncio
    async def test_dispatch_inactive_webhooks_ignored(self, mock_db):
        """Test inactive webhooks are not triggered."""
        inactive_webhook = Webhook(
            id=uuid4(),
            user_id=uuid4(),
            name="Inactive",
            url="https://example.com/webhook",
            secret="secret",
            events="task.completed",  # String, not list
            is_active=False,  # Inactive!
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [inactive_webhook]
        mock_db.execute.return_value = mock_result

        count = await webhook_service.dispatch(
            db=mock_db,
            user_id=inactive_webhook.user_id,
            event="task.completed",
            payload={},
        )

        # Should return 0 because webhook is inactive
        assert count == 0

    @pytest.mark.asyncio
    async def test_dispatch_success_single_webhook(self, mock_db, sample_webhook):
        """Test successful dispatch to single webhook."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_webhook]
        mock_db.execute.return_value = mock_result

        # Mock matches_event
        with patch.object(sample_webhook, "matches_event", return_value=True):
            # Mock _deliver to succeed
            with patch.object(
                webhook_service, "_deliver", return_value=True
            ) as mock_deliver:
                count = await webhook_service.dispatch(
                    db=mock_db,
                    user_id=sample_webhook.user_id,
                    event="task.completed",
                    payload={"task_id": "123"},
                )

        assert count == 1
        mock_deliver.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_multiple_webhooks(self, mock_db):
        """Test dispatch to multiple matching webhooks."""
        webhooks = [
            Webhook(
                id=uuid4(),
                user_id=uuid4(),
                name=f"Webhook {i}",
                url=f"https://example.com/webhook{i}",
                secret=f"secret{i}",
                events="task.completed",  # String, not list
                is_active=True,
            )
            for i in range(3)
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = webhooks
        mock_db.execute.return_value = mock_result

        # Mock matches_event for all
        for wh in webhooks:
            wh.matches_event = MagicMock(return_value=True)

        # Mock _deliver: 2 succeed, 1 fails
        with patch.object(
            webhook_service, "_deliver", side_effect=[True, True, False]
        ) as mock_deliver:
            count = await webhook_service.dispatch(
                db=mock_db,
                user_id=webhooks[0].user_id,
                event="task.completed",
                payload={"task_id": "123"},
            )

        assert count == 2
        assert mock_deliver.call_count == 3


# ============================================================================
# Test _deliver()
# ============================================================================


class TestDeliver:
    """Test single webhook delivery with retries."""

    @pytest.mark.asyncio
    async def test_deliver_success_first_attempt(self, mock_db, sample_webhook):
        """Test successful delivery on first attempt."""
        # Mock HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await webhook_service._deliver(
                db=mock_db,
                webhook=sample_webhook,
                event="task.completed",
                payload={"task_id": "123"},
            )

        assert result is True
        assert sample_webhook.success_count == 1
        assert sample_webhook.failure_count == 0
        assert sample_webhook.last_error is None
        assert sample_webhook.last_triggered_at is not None
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_deliver_success_with_3xx_status(self, mock_db, sample_webhook):
        """Test successful delivery with 3xx redirect status."""
        mock_response = MagicMock()
        mock_response.status_code = 302
        mock_response.text = "Redirect"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await webhook_service._deliver(
                db=mock_db,
                webhook=sample_webhook,
                event="task.completed",
                payload={},
            )

        assert result is True
        assert sample_webhook.success_count == 1

    @pytest.mark.asyncio
    async def test_deliver_failure_4xx_exhausts_retries(self, mock_db, sample_webhook):
        """Test delivery failure with 4xx status exhausts all retries."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Mock asyncio.sleep to avoid delays
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await webhook_service._deliver(
                    db=mock_db,
                    webhook=sample_webhook,
                    event="task.completed",
                    payload={},
                )

        assert result is False
        assert sample_webhook.failure_count == 1
        assert sample_webhook.success_count == 0
        assert "HTTP 404" in sample_webhook.last_error
        assert mock_client.post.call_count == MAX_RETRIES  # 2 attempts

    @pytest.mark.asyncio
    async def test_deliver_failure_5xx_exhausts_retries(self, mock_db, sample_webhook):
        """Test delivery failure with 5xx server error."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await webhook_service._deliver(
                    db=mock_db,
                    webhook=sample_webhook,
                    event="task.completed",
                    payload={},
                )

        assert result is False
        assert sample_webhook.failure_count == 1
        assert "HTTP 500" in sample_webhook.last_error

    @pytest.mark.asyncio
    async def test_deliver_network_error_retries(self, mock_db, sample_webhook):
        """Test network error triggers retries."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.ConnectError("Connection refused")
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await webhook_service._deliver(
                    db=mock_db,
                    webhook=sample_webhook,
                    event="task.completed",
                    payload={},
                )

        assert result is False
        assert sample_webhook.failure_count == 1
        assert "ConnectError" in sample_webhook.last_error
        assert mock_client.post.call_count == MAX_RETRIES

    @pytest.mark.asyncio
    async def test_deliver_timeout_error(self, mock_db, sample_webhook):
        """Test timeout error handling."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.TimeoutException("Request timeout")
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await webhook_service._deliver(
                    db=mock_db,
                    webhook=sample_webhook,
                    event="task.completed",
                    payload={},
                )

        assert result is False
        assert "TimeoutException" in sample_webhook.last_error

    @pytest.mark.asyncio
    async def test_deliver_retry_eventually_succeeds(self, mock_db, sample_webhook):
        """Test delivery succeeds after retry."""
        mock_response_fail = MagicMock()
        mock_response_fail.status_code = 500
        mock_response_fail.text = "Server Error"

        mock_response_success = MagicMock()
        mock_response_success.status_code = 200
        mock_response_success.text = "OK"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            # First attempt fails, second succeeds
            mock_client.post.side_effect = [mock_response_fail, mock_response_success]
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await webhook_service._deliver(
                    db=mock_db,
                    webhook=sample_webhook,
                    event="task.completed",
                    payload={},
                )

        assert result is True
        assert sample_webhook.success_count == 1
        assert sample_webhook.failure_count == 0
        assert sample_webhook.last_error is None

    @pytest.mark.asyncio
    async def test_deliver_payload_signature(self, mock_db, sample_webhook):
        """Test webhook payload is correctly signed."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        captured_headers = None

        async def capture_post(*args, **kwargs):
            nonlocal captured_headers
            captured_headers = kwargs.get("headers", {})
            return mock_response

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = capture_post
            mock_client_class.return_value.__aenter__.return_value = mock_client

            await webhook_service._deliver(
                db=mock_db,
                webhook=sample_webhook,
                event="task.completed",
                payload={"task_id": "123"},
            )

        # Verify signature header exists
        assert "X-Webhook-Signature" in captured_headers
        assert captured_headers["X-Webhook-Signature"].startswith("sha256=")

        # Verify signature is correct
        signature = captured_headers["X-Webhook-Signature"].replace("sha256=", "")
        assert len(signature) == 64  # SHA256 hex

    @pytest.mark.asyncio
    async def test_deliver_correct_headers(self, mock_db, sample_webhook):
        """Test webhook headers are correct."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        captured_headers = None

        async def capture_post(*args, **kwargs):
            nonlocal captured_headers
            captured_headers = kwargs.get("headers", {})
            return mock_response

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = capture_post
            mock_client_class.return_value.__aenter__.return_value = mock_client

            await webhook_service._deliver(
                db=mock_db,
                webhook=sample_webhook,
                event="task.completed",
                payload={},
            )

        assert captured_headers["Content-Type"] == "application/json"
        assert captured_headers["X-Webhook-Event"] == "task.completed"
        assert captured_headers["User-Agent"] == "AgentHQ-Webhook/1.0"


# ============================================================================
# Test test_webhook()
# ============================================================================


class TestTestWebhook:
    """Test webhook testing functionality."""

    @pytest.mark.asyncio
    async def test_test_webhook_success(self, sample_webhook):
        """Test successful webhook test."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Test received"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await webhook_service.test_webhook(sample_webhook)

        assert result["success"] is True
        assert result["status_code"] == 200
        assert "Test received" in result["response_body"]

    @pytest.mark.asyncio
    async def test_test_webhook_failure(self, sample_webhook):
        """Test failed webhook test with 4xx status."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await webhook_service.test_webhook(sample_webhook)

        assert result["success"] is False
        assert result["status_code"] == 404

    @pytest.mark.asyncio
    async def test_test_webhook_network_error(self, sample_webhook):
        """Test webhook test with network error."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.ConnectError("Connection refused")
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await webhook_service.test_webhook(sample_webhook)

        assert result["success"] is False
        assert "error" in result
        assert "ConnectError" in result["error"]

    @pytest.mark.asyncio
    async def test_test_webhook_payload_structure(self, sample_webhook):
        """Test webhook test sends correct payload structure."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        captured_body = None

        async def capture_post(*args, **kwargs):
            nonlocal captured_body
            captured_body = kwargs.get("content", b"")
            return mock_response

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = capture_post
            mock_client_class.return_value.__aenter__.return_value = mock_client

            await webhook_service.test_webhook(sample_webhook)

        # Parse captured body
        body = json.loads(captured_body)
        assert body["event"] == "webhook.test"
        assert "timestamp" in body
        assert "data" in body
        assert body["data"]["message"] == "This is a test webhook delivery from AgentHQ."
        assert body["data"]["webhook_id"] == str(sample_webhook.id)


# ============================================================================
# Integration Tests
# ============================================================================


class TestWebhookServiceIntegration:
    """Integration tests for webhook service."""

    @pytest.mark.asyncio
    async def test_full_delivery_flow(self, mock_db):
        """Test complete delivery flow from dispatch to delivery."""
        webhook = Webhook(
            id=uuid4(),
            user_id=uuid4(),
            name="Integration Test",
            url="https://example.com/webhook",
            secret="integration_secret",
            events="task.completed",  # String, not list
            is_active=True,
            success_count=0,
            failure_count=0,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [webhook]
        mock_db.execute.return_value = mock_result

        # Mock matches_event
        webhook.matches_event = MagicMock(return_value=True)

        # Mock HTTP success
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Success"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            count = await webhook_service.dispatch(
                db=mock_db,
                user_id=webhook.user_id,
                event="task.completed",
                payload={"task_id": "integration_123"},
            )

        assert count == 1
        assert webhook.success_count == 1
        assert webhook.failure_count == 0

    @pytest.mark.asyncio
    async def test_signature_verification_flow(self, mock_db, sample_webhook):
        """Test that signature can be verified by receiver."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        captured_signature = None
        captured_body = None

        async def capture_post(*args, **kwargs):
            nonlocal captured_signature, captured_body
            captured_body = kwargs.get("content", b"")
            headers = kwargs.get("headers", {})
            captured_signature = headers.get("X-Webhook-Signature", "")
            return mock_response

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = capture_post
            mock_client_class.return_value.__aenter__.return_value = mock_client

            await webhook_service._deliver(
                db=mock_db,
                webhook=sample_webhook,
                event="task.completed",
                payload={"task_id": "signature_test"},
            )

        # Verify receiver can validate signature
        expected_signature = _sign_payload(captured_body, sample_webhook.secret)
        actual_signature = captured_signature.replace("sha256=", "")

        assert actual_signature == expected_signature
