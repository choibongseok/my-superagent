"""Example plugin: Weather information tool."""

import inspect
import json
import logging
import math
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
    PRESSURE_UNIT_ALIASES = {
        "hpa": "hpa",
        "hectopascal": "hpa",
        "hectopascals": "hpa",
        "kpa": "kpa",
        "kilopascal": "kpa",
        "kilopascals": "kpa",
        "inhg": "inhg",
        "inchesofmercury": "inhg",
        "mmhg": "mmhg",
        "millimetersofmercury": "mmhg",
    }
    LANGUAGE_PATTERN = re.compile(r"^[a-z]{2}(?:[_-][a-z]{2})?$")

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize weather tool plugin.

        Config:
            api_key: OpenWeatherMap API key (optional, uses mock data if not provided)
            units: Temperature units ('metric'/'celsius', 'imperial'/'fahrenheit', or 'standard'/'kelvin'; default: 'metric')
            pressure_unit: Pressure output units ('hpa', 'kpa', 'inhg', or 'mmhg'; default: 'hpa')
            lang: Optional language code for localized weather descriptions (e.g., 'en', 'ko', 'pt_br')
            cache_ttl_seconds: Optional positive integer TTL for response caching (default: 0 disables caching)
            cache_max_entries: Optional maximum cache entries (default: 256)
        """
        super().__init__(config)
        self.api_key = config.get("api_key")
        self.units = self._normalize_units(config.get("units", "metric"))
        self.pressure_unit = self._normalize_pressure_unit(
            config.get("pressure_unit", "hpa")
        )
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

    def _normalize_pressure_unit(self, pressure_unit: Any) -> str:
        """Normalize pressure unit aliases to canonical values."""
        if pressure_unit is None:
            return "hpa"
        if not isinstance(pressure_unit, str):
            raise ValueError("pressure_unit must be a string")

        normalized_pressure_unit = re.sub(r"[\s_-]+", "", pressure_unit.strip().lower())
        if not normalized_pressure_unit:
            return "hpa"

        canonical_pressure_unit = self.PRESSURE_UNIT_ALIASES.get(
            normalized_pressure_unit
        )
        if canonical_pressure_unit is None:
            raise ValueError("Unsupported pressure_unit. Use hpa, kpa, inhg, or mmhg")

        return canonical_pressure_unit

    def _resolve_pressure_unit(self, requested_pressure_unit: Any) -> str:
        """Resolve effective pressure unit for a request."""
        if requested_pressure_unit is None:
            return self.pressure_unit

        return self._normalize_pressure_unit(requested_pressure_unit)

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
        pressure_unit: str,
    ) -> str:
        """Build deterministic cache keys for weather responses."""
        language_key = language or "default"
        return f"weather:{location.lower()}|{units}|{language_key}|{pressure_unit}"

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
    def _convert_pressure_from_hpa(pressure_hpa: float, pressure_unit: str) -> float:
        """Convert pressure from hPa into the requested output pressure unit."""
        if pressure_unit == "hpa":
            return round(pressure_hpa, 1)
        if pressure_unit == "kpa":
            return round(pressure_hpa / 10, 1)
        if pressure_unit == "inhg":
            return round(pressure_hpa * 0.0295299830714, 2)
        if pressure_unit == "mmhg":
            return round(pressure_hpa * 0.750061683, 1)

        raise ValueError("Unsupported pressure_unit. Use hpa, kpa, inhg, or mmhg")

    @staticmethod
    def _pressure_unit_label(pressure_unit: str) -> str:
        """Return display labels for pressure units in formatted output."""
        labels = {
            "hpa": "hPa",
            "kpa": "kPa",
            "inhg": "inHg",
            "mmhg": "mmHg",
        }
        return labels.get(pressure_unit, pressure_unit)

    @staticmethod
    def _normalize_wind_speed_for_units(api_wind_speed: float, units: str) -> float:
        """Normalize OpenWeatherMap wind speed to output units used by this plugin."""
        if units == "metric":
            # OpenWeatherMap returns m/s for metric; expose km/h for consistency.
            return round(api_wind_speed * 3.6, 1)

        # OpenWeatherMap already returns mph for imperial and m/s for standard.
        return round(api_wind_speed, 1)

    @classmethod
    def _normalize_wind_gust_for_units(
        cls,
        api_wind_gust: Any,
        units: str,
    ) -> float | None:
        """Normalize optional OpenWeather wind-gust values to output units."""
        if api_wind_gust is None or isinstance(api_wind_gust, bool):
            return None

        try:
            parsed_wind_gust = float(api_wind_gust)
        except (TypeError, ValueError):
            return None

        return cls._normalize_wind_speed_for_units(parsed_wind_gust, units)

    @staticmethod
    def _normalize_wind_direction_degrees(direction_degrees: Any) -> float | None:
        """Normalize raw wind-direction degrees into a [0, 360) range."""
        if direction_degrees is None or isinstance(direction_degrees, bool):
            return None

        try:
            parsed_direction = float(direction_degrees)
        except (TypeError, ValueError):
            return None

        normalized_direction = parsed_direction % 360
        return round(normalized_direction, 1)

    @staticmethod
    def _wind_direction_cardinal(direction_degrees: float | None) -> str | None:
        """Map direction degrees to a 16-point cardinal compass label."""
        if direction_degrees is None:
            return None

        directions = [
            "N",
            "NNE",
            "NE",
            "ENE",
            "E",
            "ESE",
            "SE",
            "SSE",
            "S",
            "SSW",
            "SW",
            "WSW",
            "W",
            "WNW",
            "NW",
            "NNW",
        ]
        index = int((direction_degrees / 22.5) + 0.5) % len(directions)
        return directions[index]

    @staticmethod
    def _normalize_visibility_for_units(
        api_visibility_meters: float,
        units: str,
    ) -> tuple[float, str]:
        """Normalize OpenWeatherMap visibility distance to requested output units."""
        if units == "imperial":
            return round(api_visibility_meters / 1609.34, 1), "mi"
        if units == "metric":
            return round(api_visibility_meters / 1000, 1), "km"

        return round(api_visibility_meters, 1), "m"

    @staticmethod
    def _resolve_unit_labels(units: str) -> tuple[str, str]:
        """Resolve display labels for temperature and wind-speed units."""
        if units == "imperial":
            return "°F", "mph"
        if units == "standard":
            return "K", "m/s"

        return "°C", "km/h"

    @staticmethod
    def _convert_temperature_to_celsius(temperature: float, units: str) -> float:
        """Convert a unit-normalized temperature into Celsius."""
        if units == "imperial":
            return (temperature - 32) * 5 / 9
        if units == "standard":
            return temperature - 273.15

        return temperature

    @staticmethod
    def _convert_celsius_to_units(temperature_celsius: float, units: str) -> float:
        """Convert Celsius into temperature value for ``units``."""
        if units == "imperial":
            return (temperature_celsius * 9 / 5) + 32
        if units == "standard":
            return temperature_celsius + 273.15

        return temperature_celsius

    @staticmethod
    def _convert_wind_speed_to_kmh(wind_speed: float, units: str) -> float:
        """Convert unit-normalized wind speed values into km/h."""
        if units == "imperial":
            return wind_speed * 1.60934
        if units == "standard":
            return wind_speed * 3.6

        return wind_speed

    @classmethod
    def _convert_wind_speed_to_ms(cls, wind_speed: float, units: str) -> float:
        """Convert unit-normalized wind speed values into m/s."""
        return cls._convert_wind_speed_to_kmh(wind_speed, units) / 3.6

    @classmethod
    def _calculate_wind_beaufort(cls, *, wind_speed: Any, units: str) -> int | None:
        """Map normalized wind speed to the Beaufort scale (0-12)."""
        if isinstance(wind_speed, bool):
            return None

        try:
            wind_speed_value = float(wind_speed)
        except (TypeError, ValueError):
            return None

        if wind_speed_value < 0:
            return None

        wind_speed_ms = cls._convert_wind_speed_to_ms(wind_speed_value, units)
        thresholds_ms = [
            0.3,
            1.6,
            3.4,
            5.5,
            8.0,
            10.8,
            13.9,
            17.2,
            20.8,
            24.5,
            28.5,
            32.7,
        ]

        for force, threshold in enumerate(thresholds_ms):
            if wind_speed_ms < threshold:
                return force

        return 12

    @staticmethod
    def _wind_beaufort_label(force: int | None) -> str | None:
        """Return standard Beaufort scale labels for display."""
        if force is None:
            return None

        labels = {
            0: "Calm",
            1: "Light Air",
            2: "Light Breeze",
            3: "Gentle Breeze",
            4: "Moderate Breeze",
            5: "Fresh Breeze",
            6: "Strong Breeze",
            7: "Near Gale",
            8: "Gale",
            9: "Strong Gale",
            10: "Storm",
            11: "Violent Storm",
            12: "Hurricane",
        }
        return labels.get(force)

    @classmethod
    def _calculate_wind_chill(
        cls,
        *,
        temperature: Any,
        wind_speed: Any,
        units: str,
    ) -> float | None:
        """Estimate wind-chill temperature for cold and windy conditions."""
        if isinstance(temperature, bool) or isinstance(wind_speed, bool):
            return None

        try:
            temperature_value = float(temperature)
            wind_speed_value = float(wind_speed)
        except (TypeError, ValueError):
            return None

        temperature_celsius = cls._convert_temperature_to_celsius(
            temperature_value,
            units,
        )
        wind_speed_kmh = cls._convert_wind_speed_to_kmh(wind_speed_value, units)

        # Environment Canada / NOAA metric wind-chill formula guidance.
        # Valid for temperatures <= 10°C and wind speeds > 4.8 km/h.
        if temperature_celsius > 10 or wind_speed_kmh <= 4.8:
            return None

        wind_factor = wind_speed_kmh**0.16
        wind_chill_celsius = (
            13.12
            + (0.6215 * temperature_celsius)
            - (11.37 * wind_factor)
            + (0.3965 * temperature_celsius * wind_factor)
        )

        wind_chill = cls._convert_celsius_to_units(wind_chill_celsius, units)
        return round(wind_chill, 1)

    @classmethod
    def _calculate_dew_point(
        cls,
        *,
        temperature: Any,
        humidity: Any,
        units: str,
    ) -> float | None:
        """Estimate dew-point temperature from ambient temperature and humidity."""
        if isinstance(temperature, bool) or isinstance(humidity, bool):
            return None

        try:
            temperature_value = float(temperature)
            humidity_value = float(humidity)
        except (TypeError, ValueError):
            return None

        if not 0 < humidity_value <= 100:
            return None

        temperature_celsius = cls._convert_temperature_to_celsius(
            temperature_value,
            units,
        )

        # Magnus approximation constants for water vapor over liquid water.
        alpha = 17.625
        beta = 243.04

        gamma = (alpha * temperature_celsius / (beta + temperature_celsius)) + math.log(
            humidity_value / 100
        )
        dew_point_celsius = (beta * gamma) / (alpha - gamma)

        dew_point = cls._convert_celsius_to_units(dew_point_celsius, units)
        return round(dew_point, 1)

    @classmethod
    def _calculate_heat_index(
        cls,
        *,
        temperature: Any,
        humidity: Any,
        units: str,
    ) -> float | None:
        """Estimate heat-index temperature from ambient temperature and humidity.

        Uses the NOAA Rothfusz regression in Fahrenheit and converts back to
        requested output units.
        """
        if isinstance(temperature, bool) or isinstance(humidity, bool):
            return None

        try:
            temperature_value = float(temperature)
            humidity_value = float(humidity)
        except (TypeError, ValueError):
            return None

        if not 0 < humidity_value <= 100:
            return None

        temperature_celsius = cls._convert_temperature_to_celsius(
            temperature_value,
            units,
        )
        temperature_fahrenheit = (temperature_celsius * 9 / 5) + 32

        # NOAA guidance: Rothfusz regression is valid primarily for hot and
        # humid conditions.
        if temperature_fahrenheit < 80 or humidity_value < 40:
            return None

        heat_index_fahrenheit = (
            -42.379
            + (2.04901523 * temperature_fahrenheit)
            + (10.14333127 * humidity_value)
            - (0.22475541 * temperature_fahrenheit * humidity_value)
            - (6.83783e-3 * (temperature_fahrenheit**2))
            - (5.481717e-2 * (humidity_value**2))
            + (1.22874e-3 * (temperature_fahrenheit**2) * humidity_value)
            + (8.5282e-4 * temperature_fahrenheit * (humidity_value**2))
            - (1.99e-6 * (temperature_fahrenheit**2) * (humidity_value**2))
        )

        heat_index_celsius = (heat_index_fahrenheit - 32) * 5 / 9
        heat_index = cls._convert_celsius_to_units(heat_index_celsius, units)
        return round(heat_index, 1)

    @staticmethod
    def _extract_precipitation_amount(
        data: Dict[str, Any], period: str
    ) -> float | None:
        """Return combined rain/snow precipitation (mm) for the requested period."""
        total_precipitation = 0.0
        has_precipitation = False

        for precipitation_kind in ("rain", "snow"):
            precipitation_data = data.get(precipitation_kind)
            if not isinstance(precipitation_data, dict):
                continue

            precipitation_value = precipitation_data.get(period)
            if precipitation_value is None:
                continue

            try:
                total_precipitation += float(precipitation_value)
                has_precipitation = True
            except (TypeError, ValueError):
                continue

        if not has_precipitation:
            return None

        return round(total_precipitation, 1)

    @staticmethod
    def _determine_precipitation_type(data: Dict[str, Any]) -> str | None:
        """Determine whether precipitation is rain, snow, or mixed."""
        has_rain = isinstance(data.get("rain"), dict)
        has_snow = isinstance(data.get("snow"), dict)

        if has_rain and has_snow:
            return "mixed"
        if has_rain:
            return "rain"
        if has_snow:
            return "snow"

        return None

    @staticmethod
    def _format_precipitation_summary(
        *,
        precipitation_type: str | None,
        precipitation_1h: float | None,
        precipitation_3h: float | None,
    ) -> str | None:
        """Format precipitation values for user-facing output."""
        intervals: list[str] = []
        if precipitation_1h is not None:
            intervals.append(f"1h {precipitation_1h} mm")
        if precipitation_3h is not None:
            intervals.append(f"3h {precipitation_3h} mm")

        if not intervals:
            return None

        label = precipitation_type.title() if precipitation_type else "Precipitation"
        return f"{label} ({', '.join(intervals)})"

    @staticmethod
    def _normalize_cloudiness(cloudiness: Any) -> int | None:
        """Normalize cloud coverage percentages from API payloads."""
        if cloudiness is None:
            return None

        try:
            normalized_cloudiness = int(round(float(cloudiness)))
        except (TypeError, ValueError):
            return None

        if not 0 <= normalized_cloudiness <= 100:
            return None

        return normalized_cloudiness

    @staticmethod
    def _classify_humidity_level(humidity: Any) -> str | None:
        """Classify humidity into user-friendly comfort ranges."""
        if humidity is None or isinstance(humidity, bool):
            return None

        try:
            normalized_humidity = int(round(float(humidity)))
        except (TypeError, ValueError):
            return None

        if not 0 <= normalized_humidity <= 100:
            return None

        if normalized_humidity < 30:
            return "dry"
        if normalized_humidity <= 60:
            return "comfortable"
        if normalized_humidity <= 75:
            return "humid"

        return "very humid"

    @staticmethod
    def _normalize_unix_timestamp(value: Any) -> int | None:
        """Best-effort unix timestamp parsing for daylight detection fields."""
        if value is None or isinstance(value, bool):
            return None

        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _determine_daylight_status(
        cls,
        observed_at: Any,
        sunrise_at: Any,
        sunset_at: Any,
    ) -> str | None:
        """Return day/night status when observation and sunrise/sunset are available."""
        observed_timestamp = cls._normalize_unix_timestamp(observed_at)
        sunrise_timestamp = cls._normalize_unix_timestamp(sunrise_at)
        sunset_timestamp = cls._normalize_unix_timestamp(sunset_at)

        if (
            observed_timestamp is None
            or sunrise_timestamp is None
            or sunset_timestamp is None
            or sunrise_timestamp == sunset_timestamp
        ):
            return None

        if sunrise_timestamp < sunset_timestamp:
            return (
                "day"
                if sunrise_timestamp <= observed_timestamp < sunset_timestamp
                else "night"
            )

        # Handles polar/twilight edge cases where API sunset may roll to next UTC day.
        return (
            "day"
            if observed_timestamp >= sunrise_timestamp
            or observed_timestamp < sunset_timestamp
            else "night"
        )

    def _build_mock_weather_response(
        self,
        location: str,
        units: str,
        pressure_unit: str,
    ) -> Dict[str, Any]:
        """Build deterministic mock weather data for offline/test mode."""
        temperature_celsius = 22.5
        feels_like_celsius = 21.3
        wind_kmh = 12.3
        wind_gust_kmh = 18.6
        pressure_hpa = 1013.0
        visibility_meters = 10_000

        if units == "imperial":
            temperature = self._convert_metric_to_imperial_temperature(
                temperature_celsius
            )
            feels_like = self._convert_metric_to_imperial_temperature(
                feels_like_celsius
            )
            wind_speed = self._convert_kmh_to_mph(wind_kmh)
            wind_gust = self._convert_kmh_to_mph(wind_gust_kmh)
        elif units == "standard":
            temperature = self._convert_metric_to_standard_temperature(
                temperature_celsius
            )
            feels_like = self._convert_metric_to_standard_temperature(
                feels_like_celsius
            )
            wind_speed = self._convert_kmh_to_ms(wind_kmh)
            wind_gust = self._convert_kmh_to_ms(wind_gust_kmh)
        else:
            temperature = temperature_celsius
            feels_like = feels_like_celsius
            wind_speed = wind_kmh
            wind_gust = wind_gust_kmh

        visibility, visibility_unit = self._normalize_visibility_for_units(
            visibility_meters,
            units,
        )
        temperature_unit, wind_speed_unit = self._resolve_unit_labels(units)
        dew_point = self._calculate_dew_point(
            temperature=temperature,
            humidity=65,
            units=units,
        )
        heat_index = self._calculate_heat_index(
            temperature=temperature,
            humidity=65,
            units=units,
        )
        wind_chill = self._calculate_wind_chill(
            temperature=temperature,
            wind_speed=wind_speed,
            units=units,
        )
        wind_beaufort = self._calculate_wind_beaufort(
            wind_speed=wind_speed,
            units=units,
        )

        return {
            "location": location,
            "temperature": temperature,
            "temperature_unit": temperature_unit,
            "dew_point": dew_point,
            "dew_point_unit": temperature_unit if dew_point is not None else None,
            "heat_index": heat_index,
            "heat_index_unit": temperature_unit if heat_index is not None else None,
            "wind_chill": wind_chill,
            "wind_chill_unit": temperature_unit if wind_chill is not None else None,
            "feels_like": feels_like,
            "condition": "Partly Cloudy",
            "humidity": 65,
            "humidity_level": self._classify_humidity_level(65),
            "cloudiness": 40,
            "daylight_status": "day",
            "pressure": self._convert_pressure_from_hpa(pressure_hpa, pressure_unit),
            "pressure_unit": pressure_unit,
            "wind_speed": wind_speed,
            "wind_speed_unit": wind_speed_unit,
            "wind_gust": wind_gust,
            "wind_gust_unit": wind_speed_unit,
            "wind_beaufort": wind_beaufort,
            "wind_beaufort_label": self._wind_beaufort_label(wind_beaufort),
            "wind_direction_degrees": 225.0,
            "wind_direction_cardinal": "SW",
            "visibility": visibility,
            "visibility_unit": visibility_unit,
            "precipitation_1h": None,
            "precipitation_3h": None,
            "precipitation_type": None,
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
                "pressure_unit": str (optional, hpa/kpa/inhg/mmhg; overrides plugin default),
                "lang": str (optional, ISO 639-1 code with optional locale such as 'ko' or 'pt_br'),
                "refresh_cache": bool (optional, when true bypasses cache lookup and forces a fresh fetch)
            }

        Returns:
            {
                "location": str,
                "temperature": float,
                "temperature_unit": str,
                "dew_point": float | None,
                "dew_point_unit": str | None,
                "heat_index": float | None,
                "heat_index_unit": str | None,
                "wind_chill": float | None,
                "wind_chill_unit": str | None,
                "feels_like": float,
                "condition": str,
                "humidity": int,
                "humidity_level": str | None,
                "cloudiness": int | None,
                "daylight_status": str | None,
                "pressure": float | None,
                "pressure_unit": str | None,
                "wind_speed": float,
                "wind_speed_unit": str,
                "wind_gust": float | None,
                "wind_gust_unit": str | None,
                "wind_beaufort": int | None,
                "wind_beaufort_label": str | None,
                "wind_direction_degrees": float | None,
                "wind_direction_cardinal": str | None,
                "visibility": float | None,
                "visibility_unit": str | None,
                "precipitation_1h": float | None,
                "precipitation_3h": float | None,
                "precipitation_type": str | None,
                "units": str
            }
        """
        normalized_location, location_params = self._resolve_location_inputs(inputs)
        resolved_units = self._resolve_units(inputs.get("units"))
        resolved_pressure_unit = self._resolve_pressure_unit(
            inputs.get("pressure_unit")
        )
        resolved_language = self._resolve_language(inputs.get("lang"))
        refresh_cache = self._normalize_refresh_cache(inputs.get("refresh_cache"))

        cache_key: str | None = None
        if self._response_cache is not None:
            cache_key = self._build_cache_key(
                location=normalized_location,
                units=resolved_units,
                language=resolved_language,
                pressure_unit=resolved_pressure_unit,
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
                normalized_location,
                resolved_units,
                resolved_pressure_unit,
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
                humidity = main["humidity"]
                humidity_level = self._classify_humidity_level(humidity)
                dew_point = self._calculate_dew_point(
                    temperature=temperature,
                    humidity=humidity,
                    units=resolved_units,
                )
                heat_index = self._calculate_heat_index(
                    temperature=temperature,
                    humidity=humidity,
                    units=resolved_units,
                )

                visibility_value = data.get("visibility")
                visibility = None
                visibility_unit = None
                if visibility_value is not None:
                    visibility, visibility_unit = self._normalize_visibility_for_units(
                        float(visibility_value),
                        resolved_units,
                    )

                pressure = None
                pressure_hpa = main.get("pressure")
                if pressure_hpa is not None:
                    pressure = self._convert_pressure_from_hpa(
                        float(pressure_hpa),
                        resolved_pressure_unit,
                    )

                precipitation_1h = self._extract_precipitation_amount(data, "1h")
                precipitation_3h = self._extract_precipitation_amount(data, "3h")
                precipitation_type = self._determine_precipitation_type(data)
                cloudiness = self._normalize_cloudiness(
                    data.get("clouds", {}).get("all")
                    if isinstance(data.get("clouds"), dict)
                    else None
                )
                daylight_status = self._determine_daylight_status(
                    data.get("dt"),
                    data.get("sys", {}).get("sunrise")
                    if isinstance(data.get("sys"), dict)
                    else None,
                    data.get("sys", {}).get("sunset")
                    if isinstance(data.get("sys"), dict)
                    else None,
                )
                wind_payload = data.get("wind") if isinstance(data.get("wind"), dict) else {}
                wind_speed = self._normalize_wind_speed_for_units(
                    wind_payload["speed"],
                    resolved_units,
                )
                wind_gust = self._normalize_wind_gust_for_units(
                    wind_payload.get("gust"),
                    resolved_units,
                )
                wind_chill = self._calculate_wind_chill(
                    temperature=temperature,
                    wind_speed=wind_speed,
                    units=resolved_units,
                )
                wind_beaufort = self._calculate_wind_beaufort(
                    wind_speed=wind_speed,
                    units=resolved_units,
                )
                wind_direction_degrees = self._normalize_wind_direction_degrees(
                    wind_payload.get("deg")
                )
                wind_direction_cardinal = self._wind_direction_cardinal(
                    wind_direction_degrees
                )

                temperature_unit, wind_speed_unit = self._resolve_unit_labels(
                    resolved_units
                )

                result = {
                    "location": data.get("name") or normalized_location,
                    "temperature": temperature,
                    "temperature_unit": temperature_unit,
                    "dew_point": dew_point,
                    "dew_point_unit": temperature_unit if dew_point is not None else None,
                    "heat_index": heat_index,
                    "heat_index_unit": temperature_unit
                    if heat_index is not None
                    else None,
                    "wind_chill": wind_chill,
                    "wind_chill_unit": temperature_unit
                    if wind_chill is not None
                    else None,
                    "feels_like": feels_like,
                    "condition": data["weather"][0]["description"].title(),
                    "humidity": humidity,
                    "humidity_level": humidity_level,
                    "cloudiness": cloudiness,
                    "daylight_status": daylight_status,
                    "pressure": pressure,
                    "pressure_unit": resolved_pressure_unit
                    if pressure is not None
                    else None,
                    "wind_speed": wind_speed,
                    "wind_speed_unit": wind_speed_unit,
                    "wind_gust": wind_gust,
                    "wind_gust_unit": wind_speed_unit if wind_gust is not None else None,
                    "wind_beaufort": wind_beaufort,
                    "wind_beaufort_label": self._wind_beaufort_label(wind_beaufort),
                    "wind_direction_degrees": wind_direction_degrees,
                    "wind_direction_cardinal": wind_direction_cardinal,
                    "visibility": visibility,
                    "visibility_unit": visibility_unit,
                    "precipitation_1h": precipitation_1h,
                    "precipitation_3h": precipitation_3h,
                    "precipitation_type": precipitation_type,
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

    def _resolve_tool_inputs(self, tool_input: str) -> Dict[str, Any]:
        """Resolve ``run_tool`` input into execute payload.

        Supports plain-text location input (e.g. ``"Seoul"``) and JSON object
        payloads for advanced usage (e.g.
        ``{"location":"Seoul","units":"imperial"}``).
        """
        if not isinstance(tool_input, str):
            raise ValueError("tool_input must be a string")

        normalized_input = tool_input.strip()
        if normalized_input.startswith("{") or normalized_input.startswith("["):
            try:
                parsed_payload = json.loads(normalized_input)
            except json.JSONDecodeError as error:
                raise ValueError("tool_input JSON payload is invalid") from error

            if not isinstance(parsed_payload, dict):
                raise ValueError("tool_input JSON payload must be an object")
            if not parsed_payload:
                raise ValueError("tool_input JSON payload cannot be empty")

            return parsed_payload

        return {"location": tool_input}

    async def run_tool(self, tool_input: str) -> str:
        """
        Run tool with either a location string or JSON payload string.

        Args:
            tool_input: Plain location string or JSON object string accepted by
                :meth:`execute`.

        Returns:
            Weather information as formatted string
        """
        result = await self.execute(self._resolve_tool_inputs(tool_input))

        resolved_units = result.get("units", self.units)
        default_temperature_unit, default_wind_unit = self._resolve_unit_labels(
            resolved_units
        )
        temperature_unit = str(
            result.get("temperature_unit") or default_temperature_unit
        )
        wind_unit = str(result.get("wind_speed_unit") or default_wind_unit)
        wind_gust = result.get("wind_gust")
        wind_gust_unit = str(result.get("wind_gust_unit") or wind_unit)
        wind_beaufort = result.get("wind_beaufort")
        wind_beaufort_label = result.get("wind_beaufort_label") or self._wind_beaufort_label(
            wind_beaufort
        )

        dew_point = result.get("dew_point")
        dew_point_unit = str(result.get("dew_point_unit") or temperature_unit)
        heat_index = result.get("heat_index")
        heat_index_unit = str(result.get("heat_index_unit") or temperature_unit)
        wind_chill = result.get("wind_chill")
        wind_chill_unit = str(result.get("wind_chill_unit") or temperature_unit)
        feels_like = result.get("feels_like", result["temperature"])
        pressure = result.get("pressure")
        pressure_unit = result.get("pressure_unit")
        visibility = result.get("visibility")
        visibility_unit = result.get("visibility_unit")
        cloudiness = self._normalize_cloudiness(result.get("cloudiness"))
        daylight_status = result.get("daylight_status")
        wind_direction_degrees = self._normalize_wind_direction_degrees(
            result.get("wind_direction_degrees")
        )
        wind_direction_cardinal = result.get("wind_direction_cardinal")
        precipitation_summary = self._format_precipitation_summary(
            precipitation_type=result.get("precipitation_type"),
            precipitation_1h=result.get("precipitation_1h"),
            precipitation_3h=result.get("precipitation_3h"),
        )
        humidity_level = result.get("humidity_level")
        humidity_suffix = ""
        if isinstance(humidity_level, str) and humidity_level.strip():
            humidity_suffix = f" ({humidity_level.strip().title()})"

        lines = [
            f"Weather in {result['location']}:",
            f"Temperature: {result['temperature']}{temperature_unit}",
            f"Feels Like: {feels_like}{temperature_unit}",
            f"Condition: {result['condition']}",
            f"Humidity: {result['humidity']}%{humidity_suffix}",
            f"Wind Speed: {result['wind_speed']} {wind_unit}",
        ]

        if wind_gust is not None:
            lines.append(f"Wind Gust: {wind_gust} {wind_gust_unit}")
        if wind_beaufort is not None:
            beaufort_suffix = (
                f" ({wind_beaufort_label})"
                if isinstance(wind_beaufort_label, str) and wind_beaufort_label.strip()
                else ""
            )
            lines.append(f"Wind Force: Beaufort {wind_beaufort}{beaufort_suffix}")
        if dew_point is not None:
            lines.append(f"Dew Point: {dew_point}{dew_point_unit}")
        if heat_index is not None:
            lines.append(f"Heat Index: {heat_index}{heat_index_unit}")
        if wind_chill is not None:
            lines.append(f"Wind Chill: {wind_chill}{wind_chill_unit}")
        if cloudiness is not None:
            lines.append(f"Cloudiness: {cloudiness}%")
        if isinstance(daylight_status, str) and daylight_status.strip():
            lines.append(f"Daylight: {daylight_status.strip().title()}")
        if pressure is not None:
            resolved_pressure_unit = self._pressure_unit_label(
                str(pressure_unit or "hpa")
            )
            lines.append(f"Pressure: {pressure} {resolved_pressure_unit}")
        if wind_direction_degrees is not None:
            wind_direction_suffix = ""
            if isinstance(wind_direction_cardinal, str) and wind_direction_cardinal.strip():
                wind_direction_suffix = f" ({wind_direction_cardinal.strip().upper()})"

            lines.append(
                f"Wind Direction: {wind_direction_degrees:g}°{wind_direction_suffix}"
            )
        if visibility is not None:
            visibility_suffix = f" {visibility_unit}" if visibility_unit else ""
            lines.append(f"Visibility: {visibility}{visibility_suffix}")
        if precipitation_summary is not None:
            lines.append(f"Precipitation: {precipitation_summary}")

        return "\n".join(lines)

    def get_tool_description(self) -> str:
        """Get tool description for agent."""
        return (
            "Get current weather information for a location using OpenWeatherMap API. "
            "Input can be a city name (e.g., 'London', 'New York', 'Tokyo'), "
            "a city_id from OpenWeatherMap (e.g., city_id=2643743 for London), "
            "a city plus optional state/country codes (e.g., location='Springfield', state_code='IL', country_code='US'), "
            "a postal code via zip_code (e.g., zip_code='94040', country_code='US'), "
            "or coordinates (e.g., '37.5665,126.9780'). "
            "Tool-style string input can also be provided as a JSON object for advanced options, "
            "for example '{\"location\":\"Seoul\",\"units\":\"imperial\"}'. "
            "Per-request units override is supported via units='metric/celsius', "
            "units='imperial/fahrenheit', or units='standard/kelvin'. "
            "Pressure output units can be configured globally or overridden per request via pressure_unit='hpa'/'kpa'/'inhg'/'mmhg'. "
            "Responses include both actual temperature and feels-like temperature. "
            "Localized conditions are supported via optional lang='en', 'ko', 'pt_br', etc. "
            "Optional response caching can be enabled with cache_ttl_seconds to reduce repeated API calls. "
            "Set refresh_cache=true to bypass cached responses and force a fresh API fetch. "
            "Returns temperature, dew-point temperature, heat-index temperature, wind-chill temperature, feels-like temperature, weather condition, humidity with comfort-level classification, cloud coverage, daylight status, pressure, wind speed, optional wind gust, Beaufort wind-force details, wind direction, visibility, and precipitation summaries when available. "
            "Requires OpenWeatherMap API key in plugin config."
        )

    def get_manifest(self) -> PluginManifest:
        """Get plugin manifest."""
        return PluginManifest(
            name="WeatherTool",
            version="1.26.0",
            description="Get real-time weather information using OpenWeatherMap API with optional response caching, state-aware city lookup, explicit unit labels, configurable pressure units, dew-point/heat-index/wind-chill insights, humidity comfort-level insights, wind speed and gust details, Beaufort wind-force details, wind direction details, visibility details, cloud coverage, daylight status, precipitation insights, and JSON payload support for tool-style input",
            author="AgentHQ",
            permissions=["network.http"],
            config_schema={
                "api_key": "string (optional, OpenWeatherMap API key - uses mock data if not provided)",
                "units": "string (optional, metric/celsius, imperial/fahrenheit, or standard/kelvin; default: metric)",
                "pressure_unit": "string (optional, hpa/kpa/inhg/mmhg; default: hpa)",
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
                "pressure_unit": "string (optional, hpa/kpa/inhg/mmhg; overrides plugin default)",
                "lang": "string (optional, ISO 639-1 code with optional locale, overrides plugin default)",
                "refresh_cache": "boolean (optional, true bypasses cache lookup and forces a fresh fetch)",
            },
            outputs={
                "location": "string",
                "temperature": "float",
                "temperature_unit": "string (°C, °F, or K)",
                "dew_point": "float | null",
                "dew_point_unit": "string | null (°C, °F, or K)",
                "heat_index": "float | null",
                "heat_index_unit": "string | null (°C, °F, or K)",
                "wind_chill": "float | null",
                "wind_chill_unit": "string | null (°C, °F, or K)",
                "feels_like": "float",
                "condition": "string",
                "humidity": "integer",
                "humidity_level": "string | null (dry, comfortable, humid, or very humid)",
                "cloudiness": "integer | null (cloud coverage percentage)",
                "daylight_status": "string | null (day or night based on sunrise/sunset)",
                "pressure": "float | null",
                "pressure_unit": "string | null (hpa, kpa, inhg, or mmhg)",
                "wind_speed": "float",
                "wind_speed_unit": "string (km/h, mph, or m/s)",
                "wind_gust": "float | null",
                "wind_gust_unit": "string | null (km/h, mph, or m/s)",
                "wind_beaufort": "integer | null (0-12 Beaufort wind-force scale)",
                "wind_beaufort_label": "string | null (Calm through Hurricane)",
                "wind_direction_degrees": "float | null (0-360 degrees)",
                "wind_direction_cardinal": "string | null (16-point compass direction)",
                "visibility": "float | null",
                "visibility_unit": "string | null (km, mi, or m)",
                "precipitation_1h": "float | null (mm of rain/snow in the last 1 hour)",
                "precipitation_3h": "float | null (mm of rain/snow in the last 3 hours)",
                "precipitation_type": "string | null (rain, snow, mixed)",
                "units": "string (metric, imperial, or standard)",
            },
        )
