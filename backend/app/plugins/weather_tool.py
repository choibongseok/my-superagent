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
        "standard": "standard",
        "kelvin": "standard",
        "k": "standard",
    }
    LANGUAGE_PATTERN = re.compile(r"^[a-z]{2}(?:[_-][a-z]{2})?$")

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize weather tool plugin.

        Config:
            api_key: OpenWeatherMap API key (optional, uses mock data if not provided)
            units: Temperature units ('metric'/'celsius', 'imperial'/'fahrenheit', or 'standard'/'kelvin'; default: 'metric')
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
                "Unsupported units. Use metric/celsius, imperial/fahrenheit, or standard/kelvin"
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
    def _convert_metric_to_standard_temperature(celsius: float) -> float:
        """Convert Celsius to Kelvin."""
        return round(celsius + 273.15, 1)

    @staticmethod
    def _convert_kmh_to_mph(kmh: float) -> float:
        """Convert km/h to mph."""
        return round(kmh / 1.60934, 1)

    @staticmethod
    def _convert_kmh_to_ms(kmh: float) -> float:
        """Convert km/h to m/s."""
        return round(kmh / 3.6, 1)

    @staticmethod
    def _normalize_wind_speed_for_units(api_wind_speed: float, units: str) -> float:
        """Normalize OpenWeatherMap wind speed to output units used by this plugin."""
        if units == "metric":
            # OpenWeatherMap returns m/s for metric; expose km/h for consistency.
            return round(api_wind_speed * 3.6, 1)

        # OpenWeatherMap already returns mph for imperial and m/s for standard.
        return round(api_wind_speed, 1)

    def _build_mock_weather_response(self, location: str, units: str) -> Dict[str, Any]:
        """Build deterministic mock weather data for offline/test mode."""
        temperature_celsius = 22.5
        feels_like_celsius = 21.3
        wind_kmh = 12.3

        if units == "imperial":
            temperature = self._convert_metric_to_imperial_temperature(
                temperature_celsius
            )
            feels_like = self._convert_metric_to_imperial_temperature(
                feels_like_celsius
            )
            wind_speed = self._convert_kmh_to_mph(wind_kmh)
        elif units == "standard":
            temperature = self._convert_metric_to_standard_temperature(
                temperature_celsius
            )
            feels_like = self._convert_metric_to_standard_temperature(
                feels_like_celsius
            )
            wind_speed = self._convert_kmh_to_ms(wind_kmh)
        else:
            temperature = temperature_celsius
            feels_like = feels_like_celsius
            wind_speed = wind_kmh

        return {
            "location": location,
            "temperature": temperature,
            "feels_like": feels_like,
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
                "units": str (optional, metric/celsius, imperial/fahrenheit, or standard/kelvin),
                "lang": str (optional, ISO 639-1 code with optional locale such as 'ko' or 'pt_br')
            }

        Returns:
            {
                "location": str,
                "temperature": float,
                "feels_like": float,
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
                main = data["main"]
                temperature = round(main["temp"], 1)
                feels_like = round(main.get("feels_like", main["temp"]), 1)

                return {
                    "location": data.get("name") or normalized_location,
                    "temperature": temperature,
                    "feels_like": feels_like,
                    "condition": data["weather"][0]["description"].title(),
                    "humidity": main["humidity"],
                    "wind_speed": self._normalize_wind_speed_for_units(
                        data["wind"]["speed"],
                        resolved_units,
                    ),
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
        if resolved_units == "imperial":
            temperature_unit = "°F"
            wind_unit = "mph"
        elif resolved_units == "standard":
            temperature_unit = "K"
            wind_unit = "m/s"
        else:
            temperature_unit = "°C"
            wind_unit = "km/h"

        feels_like = result.get("feels_like", result["temperature"])

        return (
            f"Weather in {result['location']}:\n"
            f"Temperature: {result['temperature']}{temperature_unit}\n"
            f"Feels Like: {feels_like}{temperature_unit}\n"
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
            "Per-request units override is supported via units='metric/celsius', "
            "units='imperial/fahrenheit', or units='standard/kelvin'. "
            "Responses include both actual temperature and feels-like temperature. "
            "Localized conditions are supported via optional lang='en', 'ko', 'pt_br', etc. "
            "Returns temperature, weather condition, humidity, and wind speed. "
            "Requires OpenWeatherMap API key in plugin config."
        )

    def get_manifest(self) -> PluginManifest:
        """Get plugin manifest."""
        return PluginManifest(
            name="WeatherTool",
            version="1.9.0",
            description="Get real-time weather information using OpenWeatherMap API",
            author="AgentHQ",
            permissions=["network.http"],
            config_schema={
                "api_key": "string (optional, OpenWeatherMap API key - uses mock data if not provided)",
                "units": "string (optional, metric/celsius, imperial/fahrenheit, or standard/kelvin; default: metric)",
                "lang": "string (optional, ISO 639-1 code with optional locale, e.g., en or pt_br)",
            },
            inputs={
                "location": "string (optional, required when zip_code and latitude/longitude are not provided)",
                "zip_code": "string (optional, postal code; can be combined with country_code)",
                "country_code": "string (optional, ISO alpha-2 country code used with location or zip_code)",
                "latitude": "number (optional, must be used with longitude)",
                "longitude": "number (optional, must be used with latitude)",
                "units": "string (optional, metric/celsius, imperial/fahrenheit, or standard/kelvin; overrides plugin default)",
                "lang": "string (optional, ISO 639-1 code with optional locale, overrides plugin default)",
            },
            outputs={
                "location": "string",
                "temperature": "float",
                "feels_like": "float",
                "condition": "string",
                "humidity": "integer",
                "wind_speed": "float",
                "units": "string (metric, imperial, or standard)",
            },
        )
