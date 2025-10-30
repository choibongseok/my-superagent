"""Example plugin: Weather information tool."""

import logging
from typing import Any, Dict

from app.plugins.base import PluginManifest, ToolPlugin

logger = logging.getLogger(__name__)


class Plugin(ToolPlugin):
    """
    Weather information tool plugin.

    Fetches current weather information for a location.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize weather tool plugin.

        Config:
            api_key: Weather API key (optional, uses mock data if not provided)
        """
        super().__init__(config)
        self.api_key = config.get("api_key")

    async def initialize(self) -> None:
        """Initialize weather tool."""
        logger.info("Weather tool plugin initialized")

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get weather information.

        Args:
            inputs: {
                "location": str (required, city name or coordinates)
            }

        Returns:
            {
                "location": str,
                "temperature": float,
                "condition": str,
                "humidity": int,
                "wind_speed": float
            }
        """
        location = inputs.get("location")
        if not location:
            raise ValueError("location is required")

        # TODO: Integrate with real weather API (OpenWeatherMap, etc.)
        # For now, return mock data
        logger.info(f"Getting weather for: {location}")

        return {
            "location": location,
            "temperature": 22.5,
            "condition": "Partly Cloudy",
            "humidity": 65,
            "wind_speed": 12.3,
        }

    async def run_tool(self, tool_input: str) -> str:
        """
        Run tool with input string.

        Args:
            tool_input: Location name

        Returns:
            Weather information as formatted string
        """
        result = await self.execute({"location": tool_input})

        return (
            f"Weather in {result['location']}:\n"
            f"Temperature: {result['temperature']}°C\n"
            f"Condition: {result['condition']}\n"
            f"Humidity: {result['humidity']}%\n"
            f"Wind Speed: {result['wind_speed']} km/h"
        )

    def get_tool_description(self) -> str:
        """Get tool description for agent."""
        return (
            "Get current weather information for a location. "
            "Input should be a city name or coordinates. "
            "Returns temperature, condition, humidity, and wind speed."
        )

    def get_manifest(self) -> PluginManifest:
        """Get plugin manifest."""
        return PluginManifest(
            name="WeatherTool",
            version="1.0.0",
            description="Get current weather information for any location",
            author="AgentHQ",
            permissions=["network.http"],
            inputs={
                "location": "string (required)",
            },
            outputs={
                "location": "string",
                "temperature": "float",
                "condition": "string",
                "humidity": "integer",
                "wind_speed": "float",
            },
        )
