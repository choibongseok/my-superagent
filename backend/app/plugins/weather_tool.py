"""Example plugin: Weather information tool."""

import inspect
import logging
import re
from typing import Any, Dict

import httpx

from app.plugins.base import PluginManifest, ToolPlugin
from app.services.cache import LocalCacheService

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
            cache_ttl_seconds: Optional positive integer TTL for response caching (default: 0 disables caching)
            cache_max_entries: Optional maximum cache entries (default: 256)
        """
        super().__init__(config)
        self.api_key = config.get("api_key")
        self.units = self._normalize_units(config.get("units", "metric"))
        self.lang = self._normalize_language(config.get("lang"))
        self.cache_ttl_seconds = self._normalize_cache_ttl(
            config.get("cache_ttl_seconds", 0)
        )
        self.cache_max_entries = self._normalize_cache_max_entries(
            config.get("cache_max_entries", 256)
        )
        self._response_cache = (
            LocalCacheService(max_entries=self.cache_max_entries)
            if self.cache_ttl_seconds > 0
            else None
        )

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
    def _normalize_cache_ttl(value: Any) -> int:
        """Normalize optional cache TTL configuration."""
        if value is None:
            return 0
        if isinstance(value, bool):
            raise ValueError("cache_ttl_seconds must be an integer")

        try:
            normalized = int(value)
        except (TypeError, ValueError) as error:
            raise ValueError("cache_ttl_seconds must be an integer") from error

        if normalized < 0:
            raise ValueError("cache_ttl_seconds cannot be negative")

        return normalized

    @staticmethod
    def _normalize_cache_max_entries(value: Any) -> int:
        """Normalize cache size limits for response caching."""
        if value is None:
            return 256
        if isinstance(value, bool):
            raise ValueError("cache_max_entries must be an integer")

        try:
            normalized = int(value)
        except (TypeError, ValueError) as error:
            raise ValueError("cache_max_entries must be an integer") from error

        if normalized <= 0:
            raise ValueError("cache_max_entries must be greater than 0")

        return normalized

    @staticmethod
    def _normalize_refresh_cache(value: Any) -> bool:
        """Validate cache bypass flags used by execute inputs."""
        if value is None:
            return False
        if isinstance(value, bool):
            return value

        raise ValueError("refresh_cache must be a boolean")

    @staticmethod
    def _build_cache_key(
        *,
        location: str,
        units: str,
        language: str | None,
    ) -> str:
        """Build deterministic cache keys for weather responses."""
        language_key = language or "default"
        return f"weather:{location.lower()}|{units}|{language_key}"

    @staticmethod
    def _clone_weather_result(result: Dict[str, Any]) -> Dict[str, Any]:
        """Return a shallow copy to avoid external mutations of cached payloads."""
        return dict(result)

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

    def _normalize_state_code(self, state_code: Any) -> str | None:
        """Normalize optional region/state codes for city disambiguation queries."""
        if state_code is None:
            return None
        if not isinstance(state_code, str):
            raise ValueError("state_code must be a string")

        normalized_state_code = state_code.strip().upper()
        if not normalized_state_code:
            raise ValueError("state_code cannot be empty")
        if len(normalized_state_code) > 12:
            raise ValueError("state_code must be 12 characters or fewer")
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9-]*", normalized_state_code):
            raise ValueError(
                "state_code must contain only letters, numbers, or hyphens"
            )

        return normalized_state_code

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

    def _normalize_city_id(self, city_id: Any) -> int | None:
        """Normalize optional OpenWeatherMap city identifiers."""
        if city_id is None:
            return None
        if isinstance(city_id, bool):
            raise ValueError("city_id must be a positive integer")

        if isinstance(city_id, str):
            normalized_city_id = city_id.strip()
            if not normalized_city_id:
                raise ValueError("city_id cannot be empty")
            city_id = normalized_city_id

        try:
            parsed_city_id = int(city_id)
        except (TypeError, ValueError) as error:
            raise ValueError("city_id must be a positive integer") from error

        if parsed_city_id <= 0:
            raise ValueError("city_id must be a positive integer")

        return parsed_city_id

    async def initialize(self) -> None:
        """Initialize weather tool."""
        cache_state = (
            f"enabled (ttl={self.cache_ttl_seconds}s, max_entries={self.cache_max_entries})"
            if self._response_cache is not None
            else "disabled"
        )

        if self.api_key:
            logger.info(
                "Weather tool plugin initialized with OpenWeatherMap API; cache=%s",
                cache_state,
            )
        else:
            logger.warning(
                "Weather tool plugin initialized in mock mode (no API key provided); cache=%s",
                cache_state,
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
        """Resolve weather query params from location string, zip code, city ID, or coordinates."""
        latitude = inputs.get("latitude")
        longitude = inputs.get("longitude")
        city_id = self._normalize_city_id(inputs.get("city_id"))
        country_code = self._normalize_country_code(inputs.get("country_code"))
        state_code = self._normalize_state_code(inputs.get("state_code"))
        zip_code = self._normalize_zip_code(inputs.get("zip_code"))
        location = inputs.get("location")

        if city_id is not None:
            if (
                latitude is not None
                or longitude is not None
                or country_code is not None
                or state_code is not None
                or zip_code is not None
                or location is not None
            ):
                raise ValueError(
                    "city_id cannot be combined with location, zip_code, state_code, country_code, latitude, or longitude"
                )

            return str(city_id), {"id": city_id}

        if latitude is not None or longitude is not None:
            if latitude is None or longitude is None:
                raise ValueError("latitude and longitude must be provided together")
            if country_code is not None:
                raise ValueError(
                    "country_code cannot be used with latitude/longitude inputs"
                )
            if state_code is not None:
                raise ValueError(
                    "state_code cannot be used with latitude/longitude inputs"
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

        if zip_code is not None:
            if location is not None:
                raise ValueError("zip_code cannot be used with location input")
            if state_code is not None:
                raise ValueError("state_code cannot be used with zip_code input")

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

        location_parts = [normalized_location]
        if state_code is not None:
            location_parts.append(state_code)
        if country_code is not None:
            location_parts.append(country_code)

        resolved_location = ",".join(location_parts)
        return resolved_location, self._build_location_params(resolved_location)

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get weather information.

        Args:
            inputs: {
                "location": str (optional, required unless city_id, zip_code, or latitude/longitude are provided),
                "city_id": int (optional, OpenWeatherMap city ID; cannot be combined with other location fields),
                "zip_code": str (optional, postal code; can be combined with country_code),
                "country_code": str (optional, ISO alpha-2 country code used with location or zip_code),
                "state_code": str (optional, region/state code used with location, e.g., 'CA' for US city disambiguation),
                "latitude": float (optional, requires longitude),
                "longitude": float (optional, requires latitude),
                "units": str (optional, metric/celsius, imperial/fahrenheit, or standard/kelvin),
                "lang": str (optional, ISO 639-1 code with optional locale such as 'ko' or 'pt_br'),
                "refresh_cache": bool (optional, when true bypasses cache lookup and forces a fresh fetch)
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
        refresh_cache = self._normalize_refresh_cache(inputs.get("refresh_cache"))

        cache_key: str | None = None
        if self._response_cache is not None:
            cache_key = self._build_cache_key(
                location=normalized_location,
                units=resolved_units,
                language=resolved_language,
            )
            if not refresh_cache:
                cached_result = self._response_cache.get(cache_key)
                if cached_result is not None:
                    logger.debug("Weather cache hit for %s", cache_key)
                    return self._clone_weather_result(cached_result)
            else:
                logger.debug("Weather cache refresh requested for %s", cache_key)

        # If no API key, return mock data
        if not self.api_key:
            logger.info(
                "Getting weather for: %s (mock mode, units=%s, lang=%s)",
                normalized_location,
                resolved_units,
                resolved_language,
            )
            result = self._build_mock_weather_response(
                normalized_location, resolved_units
            )
            if cache_key is not None and self._response_cache is not None:
                self._response_cache.set(
                    cache_key,
                    self._clone_weather_result(result),
                    ttl_seconds=self.cache_ttl_seconds,
                )
            return result

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

                result = {
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

                if cache_key is not None and self._response_cache is not None:
                    self._response_cache.set(
                        cache_key,
                        self._clone_weather_result(result),
                        ttl_seconds=self.cache_ttl_seconds,
                    )

                return result

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
            "a city_id from OpenWeatherMap (e.g., city_id=2643743 for London), "
            "a city plus optional state/country codes (e.g., location='Springfield', state_code='IL', country_code='US'), "
            "a postal code via zip_code (e.g., zip_code='94040', country_code='US'), "
            "or coordinates (e.g., '37.5665,126.9780'). "
            "Per-request units override is supported via units='metric/celsius', "
            "units='imperial/fahrenheit', or units='standard/kelvin'. "
            "Responses include both actual temperature and feels-like temperature. "
            "Localized conditions are supported via optional lang='en', 'ko', 'pt_br', etc. "
            "Optional response caching can be enabled with cache_ttl_seconds to reduce repeated API calls. "
            "Set refresh_cache=true to bypass cached responses and force a fresh API fetch. "
            "Returns temperature, weather condition, humidity, and wind speed. "
            "Requires OpenWeatherMap API key in plugin config."
        )

    def get_manifest(self) -> PluginManifest:
        """Get plugin manifest."""
        return PluginManifest(
            name="WeatherTool",
            version="1.13.0",
            description="Get real-time weather information using OpenWeatherMap API with optional response caching and state-aware city lookup",
            author="AgentHQ",
            permissions=["network.http"],
            config_schema={
                "api_key": "string (optional, OpenWeatherMap API key - uses mock data if not provided)",
                "units": "string (optional, metric/celsius, imperial/fahrenheit, or standard/kelvin; default: metric)",
                "lang": "string (optional, ISO 639-1 code with optional locale, e.g., en or pt_br)",
                "cache_ttl_seconds": "integer (optional, >0 enables per-location response cache for this many seconds; default: 0)",
                "cache_max_entries": "integer (optional, maximum cached responses; default: 256)",
            },
            inputs={
                "location": "string (optional, required when city_id, zip_code, and latitude/longitude are not provided)",
                "city_id": "integer (optional, OpenWeatherMap city ID; cannot be combined with other location fields)",
                "zip_code": "string (optional, postal code; can be combined with country_code)",
                "country_code": "string (optional, ISO alpha-2 country code used with location or zip_code)",
                "state_code": "string (optional, region/state code used with location for city disambiguation)",
                "latitude": "number (optional, must be used with longitude)",
                "longitude": "number (optional, must be used with latitude)",
                "units": "string (optional, metric/celsius, imperial/fahrenheit, or standard/kelvin; overrides plugin default)",
                "lang": "string (optional, ISO 639-1 code with optional locale, overrides plugin default)",
                "refresh_cache": "boolean (optional, true bypasses cache lookup and forces a fresh fetch)",
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
