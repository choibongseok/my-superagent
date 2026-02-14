"""Tests for Slack notifier plugin."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.plugins.slack_notifier import Plugin as SlackNotifierPlugin


class _MockResponse:
    def __init__(self, status_code: int, text: str = "ok"):
        self.status_code = status_code
        self.text = text


@pytest.mark.asyncio
async def test_initialize_requires_webhook_url() -> None:
    plugin = SlackNotifierPlugin(config={})

    with pytest.raises(ValueError, match="slack_webhook_url is required in config"):
        await plugin.initialize()


def test_invalid_webhook_url_is_rejected_during_configuration() -> None:
    with pytest.raises(ValueError, match="slack_webhook_url must be an http\(s\) URL"):
        SlackNotifierPlugin(config={"slack_webhook_url": "ftp://example.com"})


@pytest.mark.asyncio
async def test_execute_rejects_blank_message() -> None:
    plugin = SlackNotifierPlugin(config={"slack_webhook_url": "https://example.com"})

    with pytest.raises(ValueError, match="message is required"):
        await plugin.execute({"message": "   "})


@pytest.mark.asyncio
async def test_execute_builds_structured_payload_with_context_fields() -> None:
    plugin = SlackNotifierPlugin(config={"slack_webhook_url": "https://example.com"})

    with patch("httpx.AsyncClient") as mock_client_cls:
        post_mock = AsyncMock(return_value=_MockResponse(status_code=200))
        mock_client_cls.return_value.__aenter__.return_value.post = post_mock

        result = await plugin.execute(
            {
                "channel": "#alerts",
                "thread_ts": "1700000000.123456",
                "title": "Nightly Build",
                "severity": "warning",
                "message": "Build completed with warnings",
                "context": {
                    "workflow": "backend-ci",
                    "duration": "14m",
                },
            }
        )

    assert result == {
        "success": True,
        "message": "Notification sent successfully",
        "attempts": 1,
    }

    payload = post_mock.await_args.kwargs["json"]
    assert payload["channel"] == "#alerts"
    assert payload["thread_ts"] == "1700000000.123456"
    assert payload["text"] == "[WARNING] Build completed with warnings"
    assert payload["blocks"][0]["text"]["text"].startswith("*⚠️ WARNING*")
    assert payload["blocks"][1]["fields"] == [
        {"type": "mrkdwn", "text": "*duration:* 14m"},
        {"type": "mrkdwn", "text": "*workflow:* backend-ci"},
    ]


@pytest.mark.asyncio
async def test_execute_retries_retryable_status_codes() -> None:
    plugin = SlackNotifierPlugin(
        config={
            "slack_webhook_url": "https://example.com",
            "max_retries": 2,
            "retry_backoff_seconds": 0,
        }
    )

    with patch("httpx.AsyncClient") as mock_client_cls:
        post_mock = AsyncMock(
            side_effect=[
                _MockResponse(status_code=500, text="server error"),
                _MockResponse(status_code=200),
            ]
        )
        mock_client_cls.return_value.__aenter__.return_value.post = post_mock

        result = await plugin.execute({"message": "hello"})

    assert result["success"] is True
    assert result["attempts"] == 2
    assert post_mock.await_count == 2


@pytest.mark.asyncio
async def test_execute_does_not_retry_non_retryable_status_codes() -> None:
    plugin = SlackNotifierPlugin(
        config={
            "slack_webhook_url": "https://example.com",
            "max_retries": 3,
            "retry_backoff_seconds": 0,
        }
    )

    with patch("httpx.AsyncClient") as mock_client_cls:
        post_mock = AsyncMock(return_value=_MockResponse(status_code=400, text="bad"))
        mock_client_cls.return_value.__aenter__.return_value.post = post_mock

        result = await plugin.execute({"message": "hello"})

    assert result == {
        "success": False,
        "message": "Failed with status 400",
        "status_code": 400,
        "attempts": 1,
    }
    assert post_mock.await_count == 1


@pytest.mark.asyncio
async def test_execute_retries_transient_timeout_errors() -> None:
    plugin = SlackNotifierPlugin(
        config={
            "slack_webhook_url": "https://example.com",
            "max_retries": 1,
            "retry_backoff_seconds": 0,
        }
    )

    timeout_error = httpx.ReadTimeout("timed out")

    with patch("httpx.AsyncClient") as mock_client_cls:
        post_mock = AsyncMock(side_effect=[timeout_error, timeout_error])
        mock_client_cls.return_value.__aenter__.return_value.post = post_mock

        result = await plugin.execute({"message": "hello"})

    assert result["success"] is False
    assert result["attempts"] == 2
    assert result["message"] == "Error: timed out"
    assert post_mock.await_count == 2


@pytest.mark.asyncio
async def test_execute_rejects_invalid_severity_value() -> None:
    plugin = SlackNotifierPlugin(config={"slack_webhook_url": "https://example.com"})

    with pytest.raises(ValueError, match="severity must be one of"):
        await plugin.execute({"message": "hello", "severity": "critical"})
