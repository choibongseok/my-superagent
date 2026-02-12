"""Example plugin: Weather information tool."""

import logging
from typing import Any, Dict

import httpx

from app.plugins.base import PluginManifest, ToolPlugin

logger = logging.getLogger(__name__)


class Plugin(ToolPlugin):
    """
    Weather information tool plugin.

    Fetches current weather information for a location using OpenWeatherMap API.
    Falls back to mock data if no API key is provided.
    """

    OPENWEATHER_BASE_URL = "https://api.openweathermap.org/data/2.5/weather"

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize weather tool plugin.

        Config:
            api_key: OpenWeatherMap API key (optional, uses mock data if not provided)
            units: Temperature units ('metric' for Celsius, 'imperial' for Fahrenheit, default: 'metric')
        """
        super().__init__(config)
        self.api_key = config.get("api_key")
        self.units = config.get("units", "metric")

    async def initialize(self) -> None:
        """Initialize weather tool."""
        if self.api_key:
            logger.info("Weather tool plugin initialized with OpenWeatherMap API")
        else:
            logger.warning("Weather tool plugin initialized in mock mode (no API key provided)")

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

        # If no API key, return mock data
        if not self.api_key:
            logger.info(f"Getting weather for: {location} (mock mode)")
            return {
                "location": location,
                "temperature": 22.5,
                "condition": "Partly Cloudy",
                "humidity": 65,
                "wind_speed": 12.3,
            }

        # Make real API call to OpenWeatherMap
        logger.info(f"Fetching real weather data for: {location}")
        
        try:
            async with httpx.AsyncClient() as client:
                params = {
                    "q": location,
                    "appid": self.api_key,
                    "units": self.units,
                }
                
                response = await client.get(
                    self.OPENWEATHER_BASE_URL,
                    params=params,
                    timeout=10.0,
                )
                response.raise_for_status()
                
                data = response.json()
                
                # Parse OpenWeatherMap response
                return {
                    "location": data["name"],
                    "temperature": round(data["main"]["temp"], 1),
                    "condition": data["weather"][0]["description"].title(),
                    "humidity": data["main"]["humidity"],
                    "wind_speed": round(data["wind"]["speed"] * (3.6 if self.units == "metric" else 1), 1),  # Convert m/s to km/h for metric
                }
        
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ValueError(f"Location not found: {location}")
            elif e.response.status_code == 401:
                raise ValueError("Invalid API key")
            else:
                raise ValueError(f"Weather API error: {e.response.status_code}")
        
        except httpx.TimeoutException:
            raise ValueError("Weather API request timed out")
        
        except Exception as e:
            logger.error(f"Error fetching weather data: {e}")
            raise ValueError(f"Failed to fetch weather data: {str(e)}")

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
            "Get current weather information for a location using OpenWeatherMap API. "
            "Input should be a city name (e.g., 'London', 'New York', 'Tokyo'). "
            "Returns temperature, weather condition, humidity, and wind speed. "
            "Requires OpenWeatherMap API key in plugin config."
        )

    def get_manifest(self) -> PluginManifest:
        """Get plugin manifest."""
        return PluginManifest(
            name="WeatherTool",
            version="1.1.0",
            description="Get real-time weather information using OpenWeatherMap API",
            author="AgentHQ",
            permissions=["network.http"],
            config_schema={
                "api_key": "string (optional, OpenWeatherMap API key - uses mock data if not provided)",
                "units": "string (optional, 'metric' or 'imperial', default: 'metric')",
            },
            inputs={
                "location": "string (required, city name)",
            },
            outputs={
                "location": "string",
                "temperature": "float",
                "condition": "string",
                "humidity": "integer",
                "wind_speed": "float",
            },
        )
