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
    UNIT_ALIASES = {
        "metric": "metric",
        "celsius": "metric",
        "c": "metric",
        "imperial": "imperial",
        "fahrenheit": "imperial",
        "f": "imperial",
    }
    LANGUAGE_PATTERN = re.compile(r"^[a-z]{2}(?:[_-][a-z]{2})?$")

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize weather tool plugin.

        Config:
            api_key: OpenWeatherMap API key (optional, uses mock data if not provided)
            units: Temperature units ('metric'/'celsius' or 'imperial'/'fahrenheit', default: 'metric')
            lang: Optional language code for localized weather descriptions (e.g., 'en', 'ko', 'pt_br')
        """
        super().__init__(config)
        self.api_key = config.get("api_key")
        self.units = self._normalize_units(config.get("units", "metric"))
        self.lang = self._normalize_language(config.get("lang"))

    def _normalize_units(self, units: Any) -> str:
        """Normalize units and support human-friendly aliases."""
        if units is None:
            return "metric"
        if not isinstance(units, str):
            raise ValueError("units must be a string")

        normalized_units = units.strip().lower()
        if not normalized_units:
            return "metric"

        canonical_units = self.UNIT_ALIASES.get(normalized_units)
        if canonical_units is None:
            raise ValueError(
                "Unsupported units. Use metric/celsius or imperial/fahrenheit"
            )

        return canonical_units

    def _resolve_units(self, requested_units: Any) -> str:
        """Resolve effective units for a request.

        Uses plugin-level defaults when no per-request override is provided.
        """
        if requested_units is None:
            return self.units

        return self._normalize_units(requested_units)

    def _normalize_language(self, language: Any) -> str | None:
        """Normalize optional language code for OpenWeatherMap localization."""
        if language is None:
            return None
        if not isinstance(language, str):
            raise ValueError("lang must be a string")

        normalized_language = language.strip().lower().replace("-", "_")
        if not normalized_language:
            raise ValueError("lang cannot be empty")
        if not self.LANGUAGE_PATTERN.fullmatch(normalized_language):
            raise ValueError(
                "lang must be an ISO 639-1 code (optionally with locale, e.g., 'en' or 'pt_br')"
            )

        return normalized_language

    def _resolve_language(self, requested_language: Any) -> str | None:
        """Resolve effective language for a request."""
        if requested_language is None:
            return self.lang

        return self._normalize_language(requested_language)

    @staticmethod
    def _convert_metric_to_imperial_temperature(celsius: float) -> float:
        """Convert Celsius to Fahrenheit."""
        return round((celsius * 9 / 5) + 32, 1)

    @staticmethod
    def _convert_kmh_to_mph(kmh: float) -> float:
        """Convert km/h to mph."""
        return round(kmh / 1.60934, 1)

    def _build_mock_weather_response(self, location: str, units: str) -> Dict[str, Any]:
        """Build deterministic mock weather data for offline/test mode."""
        temperature_celsius = 22.5
        wind_kmh = 12.3

        if units == "imperial":
            temperature = self._convert_metric_to_imperial_temperature(
                temperature_celsius
            )
            wind_speed = self._convert_kmh_to_mph(wind_kmh)
        else:
            temperature = temperature_celsius
            wind_speed = wind_kmh

        return {
            "location": location,
            "temperature": temperature,
            "condition": "Partly Cloudy",
            "humidity": 65,
            "wind_speed": wind_speed,
            "units": units,
        }

    def _normalize_country_code(self, country_code: Any) -> str | None:
        """Normalize optional ISO 3166-1 alpha-2 country codes."""
        if country_code is None:
            return None
        if not isinstance(country_code, str):
            raise ValueError("country_code must be a string")

        normalized_country_code = country_code.strip().upper()
        if not normalized_country_code:
            raise ValueError("country_code cannot be empty")
        if not re.fullmatch(r"[A-Z]{2}", normalized_country_code):
            raise ValueError("country_code must be a 2-letter ISO country code")

        return normalized_country_code

    def _normalize_zip_code(self, zip_code: Any) -> str | None:
        """Normalize optional postal code inputs used by OpenWeatherMap zip queries."""
        if zip_code is None:
            return None
        if not isinstance(zip_code, str):
            raise ValueError("zip_code must be a string")

        normalized_zip_code = re.sub(r"\s+", " ", zip_code.strip().upper())
        if not normalized_zip_code:
            raise ValueError("zip_code cannot be empty")
        if len(normalized_zip_code) > 20:
            raise ValueError("zip_code must be 20 characters or fewer")
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9 -]*", normalized_zip_code):
            raise ValueError(
                "zip_code must contain only letters, numbers, spaces, or hyphens"
            )

        return normalized_zip_code

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
        """Resolve weather query params from location string, zip code, or coordinates."""
        latitude = inputs.get("latitude")
        longitude = inputs.get("longitude")
        country_code = self._normalize_country_code(inputs.get("country_code"))
        zip_code = self._normalize_zip_code(inputs.get("zip_code"))

        if latitude is not None or longitude is not None:
            if latitude is None or longitude is None:
                raise ValueError("latitude and longitude must be provided together")
            if country_code is not None:
                raise ValueError(
                    "country_code cannot be used with latitude/longitude inputs"
                )
            if zip_code is not None:
                raise ValueError(
                    "zip_code cannot be used with latitude/longitude inputs"
                )

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

        if zip_code is not None:
            if location is not None:
                raise ValueError("zip_code cannot be used with location input")

            normalized_location = (
                f"{zip_code},{country_code}" if country_code is not None else zip_code
            )
            return normalized_location, {"zip": normalized_location}

        if location is None:
            raise ValueError("location is required")
        if not isinstance(location, str):
            raise ValueError("location must be a string")

        normalized_location = location.strip()
        if not normalized_location:
            raise ValueError("location cannot be empty")

        if country_code is not None:
            normalized_location = f"{normalized_location},{country_code}"

        return normalized_location, self._build_location_params(normalized_location)

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get weather information.

        Args:
            inputs: {
                "location": str (optional, required unless zip_code or latitude/longitude are provided),
                "zip_code": str (optional, postal code; can be combined with country_code),
                "country_code": str (optional, ISO alpha-2 country code used with location or zip_code),
                "latitude": float (optional, requires longitude),
                "longitude": float (optional, requires latitude),
                "units": str (optional, metric/celsius or imperial/fahrenheit),
                "lang": str (optional, ISO 639-1 code with optional locale such as 'ko' or 'pt_br')
            }

        Returns:
            {
                "location": str,
                "temperature": float,
                "condition": str,
                "humidity": int,
                "wind_speed": float,
                "units": str
            }
        """
        normalized_location, location_params = self._resolve_location_inputs(inputs)
        resolved_units = self._resolve_units(inputs.get("units"))
        resolved_language = self._resolve_language(inputs.get("lang"))

        # If no API key, return mock data
        if not self.api_key:
            logger.info(
                "Getting weather for: %s (mock mode, units=%s, lang=%s)",
                normalized_location,
                resolved_units,
                resolved_language,
            )
            return self._build_mock_weather_response(
                normalized_location, resolved_units
            )

        # Make real API call to OpenWeatherMap
        logger.info(f"Fetching real weather data for: {normalized_location}")

        try:
            async with httpx.AsyncClient() as client:
                params = {
                    "appid": self.api_key,
                    "units": resolved_units,
                    **location_params,
                }
                if resolved_language:
                    params["lang"] = resolved_language

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
                        data["wind"]["speed"]
                        * (3.6 if resolved_units == "metric" else 1),
                        1,
                    ),  # Convert m/s to km/h for metric
                    "units": resolved_units,
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

        resolved_units = result.get("units", self.units)
        temperature_unit = "°C" if resolved_units == "metric" else "°F"
        wind_unit = "km/h" if resolved_units == "metric" else "mph"

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
            "Input can be a city name (e.g., 'London', 'New York', 'Tokyo'), "
            "a city plus country code (e.g., 'Paris' + country_code='FR'), "
            "a postal code via zip_code (e.g., zip_code='94040', country_code='US'), "
            "or coordinates (e.g., '37.5665,126.9780'). "
            "Per-request units override is supported via units='metric/celsius' or "
            "units='imperial/fahrenheit'. "
            "Localized conditions are supported via optional lang='en', 'ko', 'pt_br', etc. "
            "Returns temperature, weather condition, humidity, and wind speed. "
            "Requires OpenWeatherMap API key in plugin config."
        )

    def get_manifest(self) -> PluginManifest:
        """Get plugin manifest."""
        return PluginManifest(
            name="WeatherTool",
            version="1.7.0",
            description="Get real-time weather information using OpenWeatherMap API",
            author="AgentHQ",
            permissions=["network.http"],
            config_schema={
                "api_key": "string (optional, OpenWeatherMap API key - uses mock data if not provided)",
                "units": "string (optional, metric/celsius or imperial/fahrenheit, default: metric)",
                "lang": "string (optional, ISO 639-1 code with optional locale, e.g., en or pt_br)",
            },
            inputs={
                "location": "string (optional, required when zip_code and latitude/longitude are not provided)",
                "zip_code": "string (optional, postal code; can be combined with country_code)",
                "country_code": "string (optional, ISO alpha-2 country code used with location or zip_code)",
                "latitude": "number (optional, must be used with longitude)",
                "longitude": "number (optional, must be used with latitude)",
                "units": "string (optional, metric/celsius or imperial/fahrenheit, overrides plugin default)",
                "lang": "string (optional, ISO 639-1 code with optional locale, overrides plugin default)",
            },
            outputs={
                "location": "string",
                "temperature": "float",
                "condition": "string",
                "humidity": "integer",
                "wind_speed": "float",
                "units": "string (metric or imperial)",
            },
        )
