"""Example plugin: Weather information tool."""

import inspect
import logging
import re
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
            logger.warning(
                "Weather tool plugin initialized in mock mode (no API key provided)"
            )

    def _build_location_params(self, location: str) -> Dict[str, Any]:
        """Build OpenWeatherMap query params for city names or lat/lon coordinates."""
        normalized_location = location.strip()

        coordinate_match = re.fullmatch(
            r"([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)",
            normalized_location,
        )
        if not coordinate_match:
            return {"q": normalized_location}

        lat = float(coordinate_match.group(1))
        lon = float(coordinate_match.group(2))
        return self._build_coordinate_params(lat, lon)

    def _build_coordinate_params(self, lat: float, lon: float) -> Dict[str, Any]:
        """Validate and build OpenWeatherMap query params for coordinates."""
        if not -90 <= lat <= 90:
            raise ValueError("Invalid coordinates: latitude must be between -90 and 90")
        if not -180 <= lon <= 180:
            raise ValueError(
                "Invalid coordinates: longitude must be between -180 and 180"
            )

        return {
            "lat": lat,
            "lon": lon,
        }

    def _resolve_location_inputs(
        self, inputs: Dict[str, Any]
    ) -> tuple[str, Dict[str, Any]]:
        """Resolve weather query params from location string or structured coordinates."""
        latitude = inputs.get("latitude")
        longitude = inputs.get("longitude")

        if latitude is not None or longitude is not None:
            if latitude is None or longitude is None:
                raise ValueError("latitude and longitude must be provided together")

            try:
                lat = float(latitude)
                lon = float(longitude)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    "latitude and longitude must be numeric values"
                ) from error

            location_params = self._build_coordinate_params(lat, lon)
            normalized_location = f"{lat},{lon}"
            return normalized_location, location_params

        location = inputs.get("location")
        if location is None:
            raise ValueError("location is required")
        if not isinstance(location, str):
            raise ValueError("location must be a string")

        normalized_location = location.strip()
        if not normalized_location:
            raise ValueError("location cannot be empty")

        return normalized_location, self._build_location_params(normalized_location)

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get weather information.

        Args:
            inputs: {
                "location": str (optional, required unless latitude/longitude are provided),
                "latitude": float (optional, requires longitude),
                "longitude": float (optional, requires latitude)
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
        normalized_location, location_params = self._resolve_location_inputs(inputs)

        # If no API key, return mock data
        if not self.api_key:
            logger.info(f"Getting weather for: {normalized_location} (mock mode)")
            return {
                "location": normalized_location,
                "temperature": 22.5,
                "condition": "Partly Cloudy",
                "humidity": 65,
                "wind_speed": 12.3,
            }

        # Make real API call to OpenWeatherMap
        logger.info(f"Fetching real weather data for: {normalized_location}")

        try:
            async with httpx.AsyncClient() as client:
                params = {
                    "appid": self.api_key,
                    "units": self.units,
                    **location_params,
                }

                response = await client.get(
                    self.OPENWEATHER_BASE_URL,
                    params=params,
                    timeout=10.0,
                )

                # httpx response methods are synchronous, but tests and adapters
                # may provide awaitable mocks. Support both for robustness.
                status_result = response.raise_for_status()
                if inspect.isawaitable(status_result):
                    await status_result

                data = response.json()
                if inspect.isawaitable(data):
                    data = await data

                # Parse OpenWeatherMap response
                return {
                    "location": data.get("name") or normalized_location,
                    "temperature": round(data["main"]["temp"], 1),
                    "condition": data["weather"][0]["description"].title(),
                    "humidity": data["main"]["humidity"],
                    "wind_speed": round(
                        data["wind"]["speed"] * (3.6 if self.units == "metric" else 1),
                        1,
                    ),  # Convert m/s to km/h for metric
                }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ValueError(f"Location not found: {normalized_location}")
            if e.response.status_code == 401:
                raise ValueError("Invalid API key")
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

        temperature_unit = "°C" if self.units == "metric" else "°F"
        wind_unit = "km/h" if self.units == "metric" else "mph"

        return (
            f"Weather in {result['location']}:\n"
            f"Temperature: {result['temperature']}{temperature_unit}\n"
            f"Condition: {result['condition']}\n"
            f"Humidity: {result['humidity']}%\n"
            f"Wind Speed: {result['wind_speed']} {wind_unit}"
        )

    def get_tool_description(self) -> str:
        """Get tool description for agent."""
        return (
            "Get current weather information for a location using OpenWeatherMap API. "
            "Input can be a city name (e.g., 'London', 'New York', 'Tokyo') "
            "or coordinates (e.g., '37.5665,126.9780'). "
            "Returns temperature, weather condition, humidity, and wind speed. "
            "Requires OpenWeatherMap API key in plugin config."
        )

    def get_manifest(self) -> PluginManifest:
        """Get plugin manifest."""
        return PluginManifest(
            name="WeatherTool",
            version="1.3.0",
            description="Get real-time weather information using OpenWeatherMap API",
            author="AgentHQ",
            permissions=["network.http"],
            config_schema={
                "api_key": "string (optional, OpenWeatherMap API key - uses mock data if not provided)",
                "units": "string (optional, 'metric' or 'imperial', default: 'metric')",
            },
            inputs={
                "location": "string (optional, required when latitude/longitude are not provided)",
                "latitude": "number (optional, must be used with longitude)",
                "longitude": "number (optional, must be used with latitude)",
            },
            outputs={
                "location": "string",
                "temperature": "float",
                "condition": "string",
                "humidity": "integer",
                "wind_speed": "float",
            },
        )
