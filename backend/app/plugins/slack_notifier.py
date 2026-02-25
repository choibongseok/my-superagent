"""Slack notification integration plugin."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any, Dict, List, Optional

import httpx

from app.plugins.base import Plugin, PluginConfig, PluginType

logger = logging.getLogger(__name__)


class SlackNotifierPlugin(Plugin):
    """Slack notification plugin that posts messages through incoming webhooks."""

    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
    SEVERITY_LABELS = {
        "info": "ℹ️ INFO",
        "success": "✅ SUCCESS",
        "warning": "⚠️ WARNING",
        "error": "🚨 ERROR",
    }

    def __init__(self, webhook_url: str, **config_overrides):
        """Initialize Slack notifier plugin."""
        config = PluginConfig(
            name="slack_notifier",
            display_name="Slack Notifier",
            type=PluginType.COMMUNICATION,
            config={
                "webhook_url": webhook_url,
                "request_timeout_seconds": config_overrides.get("request_timeout_seconds", 10.0),
                "max_retries": config_overrides.get("max_retries", 2),
                "retry_backoff_seconds": config_overrides.get("retry_backoff_seconds", 0.5),
                **config_overrides
            }
        )
        super().__init__(config)
        self.webhook_url = self._normalize_webhook_url(webhook_url)
        self.request_timeout_seconds = self._normalize_positive_float(
            config.config.get("request_timeout_seconds", 10.0),
            field_name="request_timeout_seconds",
            allow_zero=False,
        )
        self.max_retries = self._normalize_non_negative_int(
            config.config.get("max_retries", 2),
            field_name="max_retries",
        )
        self.retry_backoff_seconds = self._normalize_positive_float(
            config.config.get("retry_backoff_seconds", 0.5),
            field_name="retry_backoff_seconds",
            allow_zero=True,
        )

    @staticmethod
    def _normalize_webhook_url(value: Any) -> str | None:
        """Normalize optional webhook URL values from plugin config."""
        if value is None:
            return None

        if not isinstance(value, str):
            raise ValueError("slack_webhook_url must be a string")

        normalized_value = value.strip()
        if not normalized_value:
            raise ValueError("slack_webhook_url cannot be empty")

        if not normalized_value.startswith(("https://", "http://")):
            raise ValueError("slack_webhook_url must be an http(s) URL")

        return normalized_value

    @staticmethod
    def _normalize_positive_float(
        value: Any,
        *,
        field_name: str,
        allow_zero: bool,
    ) -> float:
        """Normalize numeric float-like values for timeout/backoff configuration."""
        if isinstance(value, bool):
            raise ValueError(f"{field_name} must be a number")

        try:
            normalized_value = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{field_name} must be a number") from error

        if allow_zero:
            if normalized_value < 0:
                raise ValueError(f"{field_name} cannot be negative")
        elif normalized_value <= 0:
            raise ValueError(f"{field_name} must be greater than 0")

        return normalized_value

    @staticmethod
    def _normalize_non_negative_int(value: Any, *, field_name: str) -> int:
        """Normalize integer configuration values and reject invalid inputs."""
        if isinstance(value, bool):
            raise ValueError(f"{field_name} must be an integer")

        try:
            normalized_value = int(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{field_name} must be an integer") from error

        if normalized_value < 0:
            raise ValueError(f"{field_name} cannot be negative")

        return normalized_value

    @staticmethod
    def _normalize_message(value: Any) -> str:
        """Normalize and validate required message text."""
        if not isinstance(value, str):
            raise ValueError("message is required")

        normalized_message = value.strip()
        if not normalized_message:
            raise ValueError("message is required")

        return normalized_message

    @staticmethod
    def _normalize_optional_string(value: Any, *, field_name: str) -> str | None:
        """Normalize optional string values provided in execute inputs."""
        if value is None:
            return None

        if not isinstance(value, str):
            raise ValueError(f"{field_name} must be a string")

        normalized_value = value.strip()
        if not normalized_value:
            return None

        return normalized_value

    def _normalize_severity(self, value: Any) -> str:
        """Normalize optional severity labels used in rich Slack payloads."""
        severity = self._normalize_optional_string(value, field_name="severity")
        if severity is None:
            return "info"

        normalized_severity = severity.casefold()
        if normalized_severity not in self.SEVERITY_LABELS:
            allowed_values = ", ".join(sorted(self.SEVERITY_LABELS))
            raise ValueError(f"severity must be one of: {allowed_values}")

        return normalized_severity

    @staticmethod
    def _normalize_context(value: Any) -> dict[str, str]:
        """Normalize optional context key/value pairs for structured notifications."""
        if value is None:
            return {}

        if not isinstance(value, Mapping):
            raise ValueError("context must be a mapping of key/value pairs")

        normalized_context: dict[str, str] = {}
        for key, raw_value in value.items():
            if not isinstance(key, str):
                raise ValueError("context keys must be strings")

            normalized_key = key.strip()
            if not normalized_key:
                raise ValueError("context keys cannot be blank")

            normalized_context[normalized_key] = str(raw_value)

        return normalized_context

    def _build_payload(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Build Slack webhook payload including optional rich blocks."""
        message = self._normalize_message(inputs.get("message"))
        title = self._normalize_optional_string(inputs.get("title"), field_name="title")
        severity = self._normalize_severity(inputs.get("severity"))
        context = self._normalize_context(inputs.get("context"))

        header_text = self.SEVERITY_LABELS[severity]
        body_lines = [message]
        if title is not None:
            body_lines.insert(0, f"*{title}*")

        text_prefix = f"[{severity.upper()}]"
        payload: dict[str, Any] = {
            "text": f"{text_prefix} {message}",
            "username": self._normalize_optional_string(
                inputs.get("username"), field_name="username"
            )
            or "AgentHQ Bot",
            "icon_emoji": self._normalize_optional_string(
                inputs.get("icon_emoji"), field_name="icon_emoji"
            )
            or ":robot_face:",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{header_text}*\n" + "\n".join(body_lines),
                    },
                }
            ],
        }

        channel = self._normalize_optional_string(
            inputs.get("channel"), field_name="channel"
        )
        if channel is not None:
            payload["channel"] = channel

        thread_ts = self._normalize_optional_string(
            inputs.get("thread_ts"), field_name="thread_ts"
        )
        if thread_ts is not None:
            payload["thread_ts"] = thread_ts

        if context:
            context_lines = [
                {"type": "mrkdwn", "text": f"*{key}:* {value}"}
                for key, value in sorted(context.items())
            ]
            payload["blocks"].append(
                {
                    "type": "section",
                    "fields": context_lines[:10],
                }
            )

        return payload

    async def authenticate(self) -> bool:
        """Authenticate with Slack (webhook integrations don't require explicit auth)."""
        if not self.webhook_url:
            raise ValueError("slack_webhook_url is required in config")
        logger.info("Slack notifier plugin authenticated")
        return True

    async def test_connection(self) -> Dict[str, Any]:
        """Test the Slack webhook connection."""
        if not self.webhook_url:
            return {
                "connected": False,
                "message": "No webhook URL configured",
                "details": {}
            }
        
        try:
            # Send a simple test message
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url,
                    json={"text": "Connection test from AgentHQ"},
                    timeout=self.request_timeout_seconds,
                )
                
                if response.status_code == 200:
                    return {
                        "connected": True,
                        "message": "Connection successful",
                        "details": {"status_code": 200}
                    }
                else:
                    return {
                        "connected": False,
                        "message": f"Connection failed with status {response.status_code}",
                        "details": {"status_code": response.status_code}
                    }
        except Exception as e:
            return {
                "connected": False,
                "message": f"Connection error: {str(e)}",
                "details": {}
            }

    async def get_capabilities(self) -> List[str]:
        """Return list of supported operations."""
        return [
            "send_notification",
            "send_with_context",
            "send_threaded",
            "send_with_severity"
        ]

    async def _sleep_before_retry(self, attempt: int) -> None:
        """Sleep using exponential backoff before retrying transient failures."""
        if self.retry_backoff_seconds <= 0:
            return

        await asyncio.sleep(self.retry_backoff_seconds * (2**attempt))

    async def send_notification(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Send Slack notification with optional retries and rich context."""
        payload = self._build_payload(inputs)

        if not self.webhook_url:
            raise ValueError("slack_webhook_url is required in config")

        attempts = 0
        async with httpx.AsyncClient() as client:
            for attempt in range(self.max_retries + 1):
                attempts = attempt + 1
                try:
                    response = await client.post(
                        self.webhook_url,
                        json=payload,
                        timeout=self.request_timeout_seconds,
                    )

                    if response.status_code == 200:
                        logger.info("Slack notification sent successfully")
                        return {
                            "success": True,
                            "message": "Notification sent successfully",
                            "attempts": attempts,
                        }

                    if (
                        response.status_code in self.RETRYABLE_STATUS_CODES
                        and attempt < self.max_retries
                    ):
                        logger.warning(
                            "Slack notification failed with retryable status %s (attempt %s/%s)",
                            response.status_code,
                            attempts,
                            self.max_retries + 1,
                        )
                        await self._sleep_before_retry(attempt)
                        continue

                    logger.error(
                        "Slack notification failed: %s %s",
                        response.status_code,
                        response.text,
                    )
                    return {
                        "success": False,
                        "message": f"Failed with status {response.status_code}",
                        "status_code": response.status_code,
                        "attempts": attempts,
                    }

                except (httpx.TimeoutException, httpx.NetworkError) as error:
                    if attempt < self.max_retries:
                        logger.warning(
                            "Slack notification transient error (%s), retrying (%s/%s)",
                            error,
                            attempts,
                            self.max_retries + 1,
                        )
                        await self._sleep_before_retry(attempt)
                        continue

                    logger.error("Slack notification error: %s", error, exc_info=True)
                    return {
                        "success": False,
                        "message": f"Error: {str(error)}",
                        "attempts": attempts,
                    }

                except Exception as error:  # pragma: no cover - defensive guard
                    logger.error("Slack notification error: %s", error, exc_info=True)
                    return {
                        "success": False,
                        "message": f"Error: {str(error)}",
                        "attempts": attempts,
                    }

        return {
            "success": False,
            "message": "Notification failed",
            "attempts": attempts,
        }
