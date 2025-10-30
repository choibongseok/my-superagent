"""Example plugin: Slack notification integration."""

import logging
from typing import Any, Dict

from app.plugins.base import IntegrationPlugin, PluginManifest

logger = logging.getLogger(__name__)


class Plugin(IntegrationPlugin):
    """
    Slack notification plugin.

    Sends notifications to Slack channels via webhook.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Slack notifier plugin.

        Config:
            slack_webhook_url: Slack incoming webhook URL
        """
        super().__init__(config)
        self.webhook_url = config.get("slack_webhook_url")
        self.authenticated = False

    async def initialize(self) -> None:
        """Initialize Slack client."""
        if not self.webhook_url:
            raise ValueError("slack_webhook_url is required in config")

        logger.info("Slack notifier plugin initialized")

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send Slack notification.

        Args:
            inputs: {
                "channel": str (optional, webhook determines channel),
                "message": str (required),
                "username": str (optional, default: "AgentHQ Bot"),
                "icon_emoji": str (optional, default: ":robot_face:")
            }

        Returns:
            {
                "success": bool,
                "message": str
            }
        """
        import httpx

        message = inputs.get("message")
        if not message:
            raise ValueError("message is required")

        # Build Slack message payload
        payload = {
            "text": message,
            "username": inputs.get("username", "AgentHQ Bot"),
            "icon_emoji": inputs.get("icon_emoji", ":robot_face:"),
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url,
                    json=payload,
                    timeout=10.0,
                )

                if response.status_code == 200:
                    logger.info("Slack notification sent successfully")
                    return {
                        "success": True,
                        "message": "Notification sent successfully",
                    }
                else:
                    logger.error(
                        f"Slack notification failed: {response.status_code} {response.text}"
                    )
                    return {
                        "success": False,
                        "message": f"Failed with status {response.status_code}",
                    }

        except Exception as e:
            logger.error(f"Slack notification error: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"Error: {str(e)}",
            }

    def get_manifest(self) -> PluginManifest:
        """Get plugin manifest."""
        return PluginManifest(
            name="SlackNotifier",
            version="1.0.0",
            description="Send notifications to Slack channels",
            author="AgentHQ",
            permissions=["network.http"],
            inputs={
                "channel": "string (optional)",
                "message": "string (required)",
                "username": "string (optional)",
                "icon_emoji": "string (optional)",
            },
            outputs={
                "success": "boolean",
                "message": "string",
            },
        )

    async def authenticate(self, credentials: Dict[str, Any]) -> bool:
        """
        Authenticate with Slack (webhook doesn't require auth).

        Args:
            credentials: Not used for webhook

        Returns:
            True
        """
        self.authenticated = True
        return True

    async def sync_data(self, direction: str) -> Dict[str, Any]:
        """
        Sync data (not applicable for notification plugin).

        Args:
            direction: Not used

        Returns:
            Empty dict
        """
        return {}
