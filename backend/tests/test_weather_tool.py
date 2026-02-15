"""Tests for Weather Tool plugin."""

import pytest
from unittest.mock import AsyncMock, patch

from app.plugins.weather_tool import Plugin as WeatherPlugin


class TestWeatherTool:
    """Test Weather Tool plugin functionality."""

    @pytest.fixture
    def mock_plugin(self):
        """Create weather plugin in mock mode (no API key)."""
        return WeatherPlugin(config={})

    @pytest.fixture
    def api_plugin(self):
        """Create weather plugin with API key."""
        return WeatherPlugin(config={"api_key": "test_key_12345"})

    @pytest.mark.asyncio
    async def test_mock_mode_returns_sample_data(self, mock_plugin):
        """Test that mock mode returns consistent sample data."""
        result = await mock_plugin.execute({"location": "Seoul"})

        assert result["location"] == "Seoul"
        assert result["temperature"] == 22.5
        assert result["temperature_unit"] == "°C"
        assert result["dew_point"] == 15.6
        assert result["dew_point_unit"] == "°C"
        assert result["heat_index"] is None
        assert result["heat_index_unit"] is None
        assert result["wind_chill"] is None
        assert result["wind_chill_unit"] is None
        assert result["feels_like"] == 21.3
        assert result["condition"] == "Partly Cloudy"
        assert result["humidity"] == 65
        assert result["cloudiness"] == 40
        assert result["daylight_status"] == "day"
        assert result["pressure"] == 1013
        assert result["wind_speed"] == 12.3
        assert result["wind_speed_unit"] == "km/h"
        assert result["wind_gust"] == 18.6
        assert result["wind_gust_unit"] == "km/h"
        assert result["wind_beaufort"] == 3
        assert result["wind_beaufort_label"] == "Gentle Breeze"
        assert result["wind_direction_degrees"] == 225.0
        assert result["wind_direction_cardinal"] == "SW"
        assert result["visibility"] == 10.0
        assert result["visibility_unit"] == "km"
        assert result["precipitation_1h"] is None
        assert result["precipitation_3h"] is None
        assert result["precipitation_type"] is None

    def test_units_aliases_are_normalized(self):
        """Test celsius/fahrenheit/kelvin aliases normalize to OpenWeather units."""
        celsius_plugin = WeatherPlugin(config={"units": "celsius"})
        fahrenheit_plugin = WeatherPlugin(config={"units": "F"})
        kelvin_plugin = WeatherPlugin(config={"units": "kelvin"})

        assert celsius_plugin.units == "metric"
        assert fahrenheit_plugin.units == "imperial"
        assert kelvin_plugin.units == "standard"

    def test_invalid_units_are_rejected(self):
        """Test unsupported units fail fast with a helpful message."""
        with pytest.raises(
            ValueError,
            match="Unsupported units. Use metric/celsius, imperial/fahrenheit, or standard/kelvin",
        ):
            WeatherPlugin(config={"units": "rankine"})

    def test_pressure_unit_aliases_are_normalized(self):
        """pressure_unit aliases should normalize to canonical internal units."""
        plugin = WeatherPlugin(config={"pressure_unit": " in-hg "})

        assert plugin.pressure_unit == "inhg"

    def test_invalid_pressure_units_are_rejected(self):
        """Unsupported pressure_unit values should fail fast."""
        with pytest.raises(
            ValueError,
            match="Unsupported pressure_unit. Use hpa, kpa, inhg, or mmhg",
        ):
            WeatherPlugin(config={"pressure_unit": "psi"})

    def test_language_codes_are_normalized(self):
        """Test language config values are normalized for API compatibility."""
        plugin = WeatherPlugin(config={"lang": "PT-BR"})

        assert plugin.lang == "pt_br"

    def test_invalid_language_codes_are_rejected(self):
        """Test invalid language configuration fails fast."""
        with pytest.raises(
            ValueError,
            match="lang must be an ISO 639-1 code",
        ):
            WeatherPlugin(config={"lang": "english"})

    def test_cache_config_validation(self):
        """Cache settings should validate numeric and range constraints."""
        with pytest.raises(ValueError, match="cache_ttl_seconds cannot be negative"):
            WeatherPlugin(config={"cache_ttl_seconds": -1})

        with pytest.raises(ValueError, match="cache_ttl_seconds must be an integer"):
            WeatherPlugin(config={"cache_ttl_seconds": "abc"})

        with pytest.raises(ValueError, match="cache_ttl_seconds must be an integer"):
            WeatherPlugin(config={"cache_ttl_seconds": True})

        with pytest.raises(
            ValueError, match="cache_max_entries must be greater than 0"
        ):
            WeatherPlugin(config={"cache_ttl_seconds": 60, "cache_max_entries": 0})

        with pytest.raises(ValueError, match="cache_max_entries must be an integer"):
            WeatherPlugin(config={"cache_ttl_seconds": 60, "cache_max_entries": False})

    @pytest.mark.asyncio
    async def test_response_cache_reuses_api_response(self):
        """Repeated calls with same query should reuse cached API responses."""
        plugin = WeatherPlugin(config={"api_key": "test_key", "cache_ttl_seconds": 30})

        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "name": "Seoul",
            "main": {"temp": 14.5, "humidity": 40},
            "weather": [{"description": "clear sky"}],
            "wind": {"speed": 2.0},
        }
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.get = mock_get

            first = await plugin.execute({"location": "Seoul"})
            second = await plugin.execute({"location": "Seoul"})

            assert first == second
            assert mock_get.await_count == 1

    @pytest.mark.asyncio
    async def test_response_cache_key_includes_units_and_language(self):
        """Different units/lang combinations should produce independent cache entries."""
        plugin = WeatherPlugin(config={"api_key": "test_key", "cache_ttl_seconds": 30})

        first_response = AsyncMock()
        first_response.json.return_value = {
            "name": "Seoul",
            "main": {"temp": 20.0, "humidity": 40},
            "weather": [{"description": "clear sky"}],
            "wind": {"speed": 3.0},
        }
        first_response.raise_for_status = AsyncMock()

        second_response = AsyncMock()
        second_response.json.return_value = {
            "name": "Seoul",
            "main": {"temp": 68.0, "humidity": 41},
            "weather": [{"description": "clear sky"}],
            "wind": {"speed": 8.0},
        }
        second_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(side_effect=[first_response, second_response])
            mock_client.return_value.__aenter__.return_value.get = mock_get

            metric_result = await plugin.execute(
                {"location": "Seoul", "units": "metric", "lang": "en"}
            )
            imperial_result = await plugin.execute(
                {"location": "Seoul", "units": "imperial", "lang": "ko"}
            )

            assert metric_result["units"] == "metric"
            assert imperial_result["units"] == "imperial"
            assert mock_get.await_count == 2

    @pytest.mark.asyncio
    async def test_response_cache_key_includes_pressure_unit(self):
        """Different pressure_unit overrides should generate separate cache entries."""
        plugin = WeatherPlugin(config={"api_key": "test_key", "cache_ttl_seconds": 30})

        first_response = AsyncMock()
        first_response.json.return_value = {
            "name": "Seoul",
            "main": {"temp": 20.0, "humidity": 40, "pressure": 1013},
            "weather": [{"description": "clear sky"}],
            "wind": {"speed": 3.0},
        }
        first_response.raise_for_status = AsyncMock()

        second_response = AsyncMock()
        second_response.json.return_value = {
            "name": "Seoul",
            "main": {"temp": 20.0, "humidity": 40, "pressure": 1013},
            "weather": [{"description": "clear sky"}],
            "wind": {"speed": 3.0},
        }
        second_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(side_effect=[first_response, second_response])
            mock_client.return_value.__aenter__.return_value.get = mock_get

            hpa_result = await plugin.execute(
                {"location": "Seoul", "pressure_unit": "hpa"}
            )
            inhg_result = await plugin.execute(
                {"location": "Seoul", "pressure_unit": "inhg"}
            )

            assert hpa_result["pressure_unit"] == "hpa"
            assert inhg_result["pressure_unit"] == "inhg"
            assert hpa_result["pressure"] != inhg_result["pressure"]
            assert mock_get.await_count == 2

    @pytest.mark.asyncio
    async def test_response_cache_expires_after_ttl(self):
        """Cached API responses should expire once TTL has elapsed."""
        plugin = WeatherPlugin(config={"api_key": "test_key", "cache_ttl_seconds": 1})

        first_response = AsyncMock()
        first_response.json.return_value = {
            "name": "Seoul",
            "main": {"temp": 10.0, "humidity": 55},
            "weather": [{"description": "mist"}],
            "wind": {"speed": 1.0},
        }
        first_response.raise_for_status = AsyncMock()

        second_response = AsyncMock()
        second_response.json.return_value = {
            "name": "Seoul",
            "main": {"temp": 12.0, "humidity": 55},
            "weather": [{"description": "mist"}],
            "wind": {"speed": 1.0},
        }
        second_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(side_effect=[first_response, second_response])
            mock_client.return_value.__aenter__.return_value.get = mock_get

            first = await plugin.execute({"location": "Seoul"})
            await plugin.execute({"location": "Seoul"})
            assert mock_get.await_count == 1

            import asyncio

            await asyncio.sleep(1.05)
            third = await plugin.execute({"location": "Seoul"})

            assert mock_get.await_count == 2
            assert first["temperature"] != third["temperature"]

    @pytest.mark.asyncio
    async def test_refresh_cache_bypasses_cached_response(self):
        """refresh_cache should skip cache hits and force a fresh API call."""
        plugin = WeatherPlugin(config={"api_key": "test_key", "cache_ttl_seconds": 30})

        first_response = AsyncMock()
        first_response.json.return_value = {
            "name": "Seoul",
            "main": {"temp": 20.0, "humidity": 40},
            "weather": [{"description": "clear sky"}],
            "wind": {"speed": 2.0},
        }
        first_response.raise_for_status = AsyncMock()

        second_response = AsyncMock()
        second_response.json.return_value = {
            "name": "Seoul",
            "main": {"temp": 21.5, "humidity": 41},
            "weather": [{"description": "clear sky"}],
            "wind": {"speed": 2.1},
        }
        second_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(side_effect=[first_response, second_response])
            mock_client.return_value.__aenter__.return_value.get = mock_get

            first = await plugin.execute({"location": "Seoul"})
            refreshed = await plugin.execute(
                {"location": "Seoul", "refresh_cache": True}
            )

            assert mock_get.await_count == 2
            assert first["temperature"] != refreshed["temperature"]

    @pytest.mark.asyncio
    async def test_refresh_cache_validation_rejects_non_boolean_values(
        self, api_plugin
    ):
        """refresh_cache should require explicit boolean input values."""
        with patch("httpx.AsyncClient") as mock_client:
            with pytest.raises(ValueError, match="refresh_cache must be a boolean"):
                await api_plugin.execute(
                    {
                        "location": "Seoul",
                        "refresh_cache": "yes",
                    }
                )

            mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_location_required(self, mock_plugin):
        """Test that location parameter is required."""
        with pytest.raises(ValueError, match="location is required"):
            await mock_plugin.execute({})

    @pytest.mark.asyncio
    async def test_location_cannot_be_blank(self, mock_plugin):
        """Test that blank location strings are rejected early."""
        with pytest.raises(ValueError, match="location cannot be empty"):
            await mock_plugin.execute({"location": "   "})

    @pytest.mark.asyncio
    async def test_run_tool_formats_output(self, mock_plugin):
        """Test that run_tool returns formatted string."""
        result = await mock_plugin.run_tool("Tokyo")

        assert "Tokyo" in result
        assert "Temperature:" in result
        assert "22.5°C" in result
        assert "Feels Like:" in result
        assert "Dew Point: 15.6°C" in result
        assert "Condition:" in result
        assert "Humidity:" in result
        assert "Wind Speed:" in result
        assert "Wind Gust:" in result
        assert "Wind Direction:" in result
        assert "Cloudiness:" in result
        assert "Daylight:" in result
        assert "Pressure:" in result
        assert "Visibility:" in result

    @pytest.mark.asyncio
    async def test_run_tool_supports_json_payload_input(self):
        """run_tool should accept JSON payload strings for advanced options."""
        plugin = WeatherPlugin(config={"units": "metric"})

        with patch.object(
            plugin,
            "execute",
            AsyncMock(
                return_value={
                    "location": "Seoul",
                    "temperature": 68.0,
                    "temperature_unit": "°F",
                    "feels_like": 66.2,
                    "condition": "Clear Sky",
                    "humidity": 45,
                    "wind_speed": 7.8,
                    "wind_speed_unit": "mph",
                    "units": "imperial",
                }
            ),
        ) as execute_mock:
            result = await plugin.run_tool(
                '{"location":"Seoul","units":"imperial","lang":"ko"}'
            )

        execute_mock.assert_awaited_once_with(
            {"location": "Seoul", "units": "imperial", "lang": "ko"}
        )
        assert "Weather in Seoul:" in result
        assert "Temperature: 68.0°F" in result
        assert "Wind Speed: 7.8 mph" in result

    @pytest.mark.asyncio
    async def test_run_tool_rejects_invalid_json_payload(self):
        """run_tool should surface JSON parse failures with a clear error."""
        plugin = WeatherPlugin(config={})

        with pytest.raises(ValueError, match="tool_input JSON payload is invalid"):
            await plugin.run_tool('{"location": "Seoul"')

    @pytest.mark.asyncio
    async def test_run_tool_rejects_non_object_json_payload(self):
        """run_tool JSON input must decode to an object payload."""
        plugin = WeatherPlugin(config={})

        with pytest.raises(
            ValueError,
            match="tool_input JSON payload must be an object",
        ):
            await plugin.run_tool('["Seoul", "imperial"]')

    @pytest.mark.asyncio
    async def test_run_tool_includes_precipitation_line_when_present(self):
        """Formatted output should include precipitation summaries when available."""
        plugin = WeatherPlugin(config={"units": "metric"})

        with patch.object(
            plugin,
            "execute",
            AsyncMock(
                return_value={
                    "location": "Seattle",
                    "temperature": 9.8,
                    "feels_like": 7.4,
                    "condition": "Light Rain",
                    "humidity": 92,
                    "pressure": 1009,
                    "wind_speed": 11.2,
                    "visibility": 6.8,
                    "visibility_unit": "km",
                    "precipitation_1h": 0.8,
                    "precipitation_3h": 2.1,
                    "precipitation_type": "rain",
                    "units": "metric",
                }
            ),
        ):
            result = await plugin.run_tool("Seattle")

        assert "Precipitation: Rain (1h 0.8 mm, 3h 2.1 mm)" in result

    @pytest.mark.asyncio
    async def test_run_tool_includes_heat_index_when_available(self):
        """Formatted output should include heat index when execute provides it."""
        plugin = WeatherPlugin(config={"units": "metric"})

        with patch.object(
            plugin,
            "execute",
            AsyncMock(
                return_value={
                    "location": "Miami",
                    "temperature": 35.0,
                    "temperature_unit": "°C",
                    "feels_like": 39.4,
                    "heat_index": 45.1,
                    "heat_index_unit": "°C",
                    "condition": "Scattered Clouds",
                    "humidity": 60,
                    "wind_speed": 9.0,
                    "wind_speed_unit": "km/h",
                    "units": "metric",
                }
            ),
        ):
            result = await plugin.run_tool("Miami")

        assert "Heat Index: 45.1°C" in result

    @pytest.mark.asyncio
    async def test_run_tool_includes_wind_chill_when_available(self):
        """Formatted output should include wind chill when execute provides it."""
        plugin = WeatherPlugin(config={"units": "metric"})

        with patch.object(
            plugin,
            "execute",
            AsyncMock(
                return_value={
                    "location": "Reykjavik",
                    "temperature": 1.8,
                    "temperature_unit": "°C",
                    "feels_like": -2.4,
                    "wind_chill": -5.7,
                    "wind_chill_unit": "°C",
                    "condition": "Overcast Clouds",
                    "humidity": 71,
                    "wind_speed": 24.0,
                    "wind_speed_unit": "km/h",
                    "units": "metric",
                }
            ),
        ):
            result = await plugin.run_tool("Reykjavik")

        assert "Wind Chill: -5.7°C" in result

    @pytest.mark.asyncio
    async def test_run_tool_formats_pressure_units_from_execute_result(self):
        """run_tool should show the pressure unit returned by execute()."""
        plugin = WeatherPlugin(config={"units": "metric"})

        with patch.object(
            plugin,
            "execute",
            AsyncMock(
                return_value={
                    "location": "London",
                    "temperature": 12.5,
                    "feels_like": 10.9,
                    "condition": "Cloudy",
                    "humidity": 70,
                    "pressure": 29.91,
                    "pressure_unit": "inhg",
                    "wind_speed": 9.0,
                    "units": "metric",
                }
            ),
        ):
            result = await plugin.run_tool("London")

        assert "Pressure: 29.91 inHg" in result

    @pytest.mark.asyncio
    async def test_run_tool_formats_wind_gust_when_available(self):
        """run_tool should render wind gust details when execute returns them."""
        plugin = WeatherPlugin(config={"units": "metric"})

        with patch.object(
            plugin,
            "execute",
            AsyncMock(
                return_value={
                    "location": "Dublin",
                    "temperature": 12.0,
                    "feels_like": 10.8,
                    "condition": "Windy",
                    "humidity": 73,
                    "wind_speed": 18.3,
                    "wind_speed_unit": "km/h",
                    "wind_gust": 30.6,
                    "wind_gust_unit": "km/h",
                    "units": "metric",
                }
            ),
        ):
            result = await plugin.run_tool("Dublin")

        assert "Wind Gust: 30.6 km/h" in result

    @pytest.mark.asyncio
    async def test_run_tool_formats_wind_beaufort_when_available(self):
        """run_tool should render Beaufort wind-force details when available."""
        plugin = WeatherPlugin(config={"units": "metric"})

        with patch.object(
            plugin,
            "execute",
            AsyncMock(
                return_value={
                    "location": "Dublin",
                    "temperature": 12.0,
                    "feels_like": 10.8,
                    "condition": "Windy",
                    "humidity": 73,
                    "wind_speed": 18.3,
                    "wind_speed_unit": "km/h",
                    "wind_beaufort": 5,
                    "wind_beaufort_label": "Fresh Breeze",
                    "units": "metric",
                }
            ),
        ):
            result = await plugin.run_tool("Dublin")

        assert "Wind Force: Beaufort 5 (Fresh Breeze)" in result

    @pytest.mark.asyncio
    async def test_run_tool_formats_wind_direction_when_available(self):
        """run_tool should render wind direction degrees with cardinal direction."""
        plugin = WeatherPlugin(config={"units": "metric"})

        with patch.object(
            plugin,
            "execute",
            AsyncMock(
                return_value={
                    "location": "Lisbon",
                    "temperature": 16.2,
                    "feels_like": 15.0,
                    "condition": "Clear Sky",
                    "humidity": 58,
                    "wind_speed": 9.4,
                    "wind_speed_unit": "km/h",
                    "wind_direction_degrees": 247,
                    "wind_direction_cardinal": "wsw",
                    "units": "metric",
                }
            ),
        ):
            result = await plugin.run_tool("Lisbon")

        assert "Wind Direction: 247° (WSW)" in result

    @pytest.mark.asyncio
    async def test_real_api_call_success(self, api_plugin):
        """Test successful API call with real data."""
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "name": "London",
            "main": {
                "temp": 15.3,
                "feels_like": 14.7,
                "humidity": 72,
                "pressure": 1008,
            },
            "weather": [{"description": "light rain"}],
            "wind": {"speed": 5.2, "gust": 8.4, "deg": 219},  # m/s
            "clouds": {"all": 88},
            "sys": {"sunrise": 1700000000, "sunset": 1700036000},
            "dt": 1700018000,
            "visibility": 7500,  # meters
        }
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await api_plugin.execute({"location": "London"})

            assert result["location"] == "London"
            assert result["temperature"] == 15.3
            assert result["temperature_unit"] == "°C"
            assert result["dew_point"] == 10.3
            assert result["dew_point_unit"] == "°C"
            assert result["heat_index"] is None
            assert result["heat_index_unit"] is None
            assert result["wind_chill"] is None
            assert result["wind_chill_unit"] is None
            assert result["feels_like"] == 14.7
            assert result["condition"] == "Light Rain"
            assert result["humidity"] == 72
            assert result["cloudiness"] == 88
            assert result["daylight_status"] == "day"
            assert result["pressure"] == 1008
            assert result["wind_speed"] == 18.7  # 5.2 m/s * 3.6 = 18.72 km/h
            assert result["wind_speed_unit"] == "km/h"
            assert result["wind_gust"] == 30.2  # 8.4 m/s * 3.6 = 30.24 km/h
            assert result["wind_gust_unit"] == "km/h"
            assert result["wind_beaufort"] == 3
            assert result["wind_beaufort_label"] == "Gentle Breeze"
            assert result["wind_direction_degrees"] == 219.0
            assert result["wind_direction_cardinal"] == "SW"
            assert result["visibility"] == 7.5
            assert result["visibility_unit"] == "km"

    @pytest.mark.asyncio
    async def test_real_api_call_includes_heat_index_for_hot_humid_conditions(
        self, api_plugin
    ):
        """Heat index should be calculated when conditions are hot and humid."""
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "name": "Miami",
            "main": {
                "temp": 35.0,
                "humidity": 60,
            },
            "weather": [{"description": "scattered clouds"}],
            "wind": {"speed": 2.5},
        }
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await api_plugin.execute({"location": "Miami"})

            assert result["temperature"] == 35.0
            assert result["temperature_unit"] == "°C"
            assert result["heat_index"] == 45.1
            assert result["heat_index_unit"] == "°C"

    @pytest.mark.asyncio
    async def test_real_api_call_includes_wind_chill_for_cold_windy_conditions(
        self, api_plugin
    ):
        """Wind chill should be calculated when conditions are cold and windy."""
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "name": "Reykjavik",
            "main": {
                "temp": 2.0,
                "humidity": 70,
            },
            "weather": [{"description": "overcast clouds"}],
            "wind": {"speed": 8.0},  # m/s -> 28.8 km/h
        }
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await api_plugin.execute({"location": "Reykjavik"})

            assert result["temperature"] == 2.0
            assert result["wind_speed"] == 28.8
            assert result["wind_chill"] == -3.7
            assert result["wind_chill_unit"] == "°C"

    @pytest.mark.asyncio
    async def test_real_api_call_normalizes_wrapped_wind_direction_values(
        self, api_plugin
    ):
        """Wind direction degrees should normalize into 0-360 with cardinal labels."""
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "name": "Busan",
            "main": {"temp": 17.4, "humidity": 61},
            "weather": [{"description": "clear sky"}],
            "wind": {"speed": 3.3, "deg": 405},
        }
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await api_plugin.execute({"location": "Busan"})

            assert result["wind_direction_degrees"] == 45.0
            assert result["wind_direction_cardinal"] == "NE"

    @pytest.mark.asyncio
    async def test_real_api_call_defaults_feels_like_to_temperature(self, api_plugin):
        """Test API responses without feels_like fall back to measured temperature."""
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "name": "London",
            "main": {"temp": 11.2, "humidity": 80},
            "weather": [{"description": "mist"}],
            "wind": {"speed": 4.0},
        }
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await api_plugin.execute({"location": "London"})

            assert result["temperature"] == 11.2
            assert result["feels_like"] == 11.2

    @pytest.mark.asyncio
    async def test_api_response_without_visibility_or_pressure(self, api_plugin):
        """Missing optional visibility/pressure fields should map to None values."""
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "name": "London",
            "main": {"temp": 11.2, "humidity": 80},
            "weather": [{"description": "mist"}],
            "wind": {"speed": 4.0},
        }
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await api_plugin.execute({"location": "London"})

            assert result["pressure"] is None
            assert result["cloudiness"] is None
            assert result["daylight_status"] is None
            assert result["visibility"] is None
            assert result["visibility_unit"] is None
            assert result["wind_gust"] is None
            assert result["wind_gust_unit"] is None

    @pytest.mark.asyncio
    async def test_api_response_includes_precipitation_details_when_available(
        self, api_plugin
    ):
        """Rain/snow payloads should be surfaced as normalized precipitation fields."""
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "name": "London",
            "main": {"temp": 8.4, "humidity": 86},
            "weather": [{"description": "light snow"}],
            "wind": {"speed": 3.8},
            "rain": {"1h": 0.7, "3h": 1.4},
            "snow": {"1h": 0.3},
        }
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await api_plugin.execute({"location": "London"})

            assert result["precipitation_1h"] == 1.0
            assert result["precipitation_3h"] == 1.4
            assert result["precipitation_type"] == "mixed"

    @pytest.mark.asyncio
    async def test_api_response_marks_night_when_outside_sunrise_window(
        self, api_plugin
    ):
        """daylight_status should be night when observation is outside sunrise/sunset."""
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "name": "London",
            "main": {"temp": 8.8, "humidity": 81},
            "weather": [{"description": "broken clouds"}],
            "wind": {"speed": 4.2},
            "clouds": {"all": 82},
            "sys": {"sunrise": 1700000000, "sunset": 1700036000},
            "dt": 1700041000,
        }
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await api_plugin.execute({"location": "London"})

            assert result["cloudiness"] == 82
            assert result["daylight_status"] == "night"

    @pytest.mark.asyncio
    async def test_location_not_found(self, api_plugin):
        """Test handling of invalid location."""
        from httpx import HTTPStatusError, Request, Response

        mock_response = Response(
            status_code=404, request=Request("GET", "http://test.com")
        )

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock()
            mock_get.side_effect = HTTPStatusError(
                "Not Found", request=mock_response.request, response=mock_response
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            with pytest.raises(ValueError, match="Location not found"):
                await api_plugin.execute({"location": "InvalidCityXYZ"})

    @pytest.mark.asyncio
    async def test_invalid_api_key(self, api_plugin):
        """Test handling of invalid API key."""
        from httpx import HTTPStatusError, Request, Response

        mock_response = Response(
            status_code=401, request=Request("GET", "http://test.com")
        )

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock()
            mock_get.side_effect = HTTPStatusError(
                "Unauthorized", request=mock_response.request, response=mock_response
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            with pytest.raises(ValueError, match="Invalid API key"):
                await api_plugin.execute({"location": "London"})

    @pytest.mark.asyncio
    async def test_api_timeout(self, api_plugin):
        """Test handling of API timeout."""
        from httpx import TimeoutException

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock()
            mock_get.side_effect = TimeoutException("Request timed out")
            mock_client.return_value.__aenter__.return_value.get = mock_get

            with pytest.raises(ValueError, match="Weather API request timed out"):
                await api_plugin.execute({"location": "London"})

    @pytest.mark.asyncio
    async def test_imperial_units(self):
        """Test imperial units configuration."""
        plugin = WeatherPlugin(config={"api_key": "test_key", "units": "imperial"})

        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "name": "New York",
            "main": {"temp": 68.5, "humidity": 55, "pressure": 1002},
            "weather": [{"description": "clear sky"}],
            "wind": {"speed": 10.5},  # mph in imperial mode
            "visibility": 1609,
        }
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await plugin.execute({"location": "New York"})

            assert result["temperature"] == 68.5
            assert result["temperature_unit"] == "°F"
            assert result["dew_point"] == 51.7
            assert result["dew_point_unit"] == "°F"
            assert result["pressure"] == 1002
            assert result["wind_speed"] == 10.5  # No conversion for imperial
            assert result["wind_speed_unit"] == "mph"
            assert result["wind_gust"] is None
            assert result["wind_gust_unit"] is None
            assert result["wind_beaufort"] == 3
            assert result["wind_beaufort_label"] == "Gentle Breeze"
            assert result["visibility"] == 1.0
            assert result["visibility_unit"] == "mi"

    @pytest.mark.asyncio
    async def test_run_tool_formats_imperial_units(self):
        """Test run_tool output reflects imperial units."""
        plugin = WeatherPlugin(config={"units": "imperial"})

        with patch.object(
            plugin,
            "execute",
            AsyncMock(
                return_value={
                    "location": "New York",
                    "temperature": 70.0,
                    "condition": "Clear Sky",
                    "humidity": 40,
                    "wind_speed": 8.0,
                }
            ),
        ):
            result = await plugin.run_tool("New York")

        assert "70.0°F" in result
        assert "8.0 mph" in result

    @pytest.mark.asyncio
    async def test_units_override_changes_mock_response_units(self):
        """Test per-request units override works even when plugin default is metric."""
        plugin = WeatherPlugin(config={"units": "metric"})

        result = await plugin.execute({"location": "Seoul", "units": "fahrenheit"})

        assert result["location"] == "Seoul"
        assert result["units"] == "imperial"
        assert result["temperature"] == 72.5
        assert result["temperature_unit"] == "°F"
        assert result["feels_like"] == 70.3
        assert result["wind_speed"] == 7.6
        assert result["wind_speed_unit"] == "mph"
        assert result["wind_gust"] == 11.6
        assert result["wind_gust_unit"] == "mph"
        assert result["visibility"] == 6.2
        assert result["visibility_unit"] == "mi"

    @pytest.mark.asyncio
    async def test_standard_units_override_changes_mock_response_units(self):
        """Test standard/kelvin override returns Kelvin and m/s in mock mode."""
        plugin = WeatherPlugin(config={"units": "metric"})

        result = await plugin.execute({"location": "Seoul", "units": "kelvin"})

        assert result["location"] == "Seoul"
        assert result["units"] == "standard"
        assert result["temperature"] == 295.6
        assert result["temperature_unit"] == "K"
        assert result["dew_point"] == 288.7
        assert result["dew_point_unit"] == "K"
        assert result["feels_like"] == 294.4
        assert result["wind_speed"] == 3.4
        assert result["wind_speed_unit"] == "m/s"
        assert result["wind_gust"] == 5.2
        assert result["wind_gust_unit"] == "m/s"
        assert result["visibility"] == 10000.0
        assert result["visibility_unit"] == "m"

    @pytest.mark.asyncio
    async def test_pressure_unit_override_changes_pressure_output_in_mock_mode(self):
        """pressure_unit override should convert pressure values in mock mode."""
        plugin = WeatherPlugin(config={"units": "metric"})

        result = await plugin.execute({"location": "Seoul", "pressure_unit": "kPa"})

        assert result["pressure"] == 101.3
        assert result["pressure_unit"] == "kpa"

    @pytest.mark.asyncio
    async def test_standard_units_preserve_api_wind_speed_in_ms(self):
        """Test API wind speed is not re-converted when units are standard."""
        plugin = WeatherPlugin(config={"api_key": "test_key", "units": "standard"})

        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "name": "Reykjavik",
            "main": {"temp": 275.2, "humidity": 70},
            "weather": [{"description": "overcast clouds"}],
            "wind": {"speed": 4.6},  # m/s for standard mode
        }
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await plugin.execute({"location": "Reykjavik"})

            assert result["units"] == "standard"
            assert result["temperature"] == 275.2
            assert result["temperature_unit"] == "K"
            assert result["wind_speed"] == 4.6
            assert result["wind_speed_unit"] == "m/s"
            assert result["wind_beaufort"] == 3
            assert result["wind_beaufort_label"] == "Gentle Breeze"

    @pytest.mark.asyncio
    async def test_run_tool_formats_standard_units(self):
        """Test run_tool output reflects Kelvin/m-s units for standard mode."""
        plugin = WeatherPlugin(config={"units": "standard"})

        with patch.object(
            plugin,
            "execute",
            AsyncMock(
                return_value={
                    "location": "Oslo",
                    "temperature": 279.7,
                    "condition": "Cloudy",
                    "humidity": 74,
                    "wind_speed": 5.2,
                    "units": "standard",
                }
            ),
        ):
            result = await plugin.run_tool("Oslo")

        assert "279.7K" in result
        assert "5.2 m/s" in result

    @pytest.mark.asyncio
    async def test_units_override_validates_supported_values(self, api_plugin):
        """Test execute validates invalid per-request units overrides."""
        with patch("httpx.AsyncClient") as mock_client:
            with pytest.raises(
                ValueError,
                match="Unsupported units. Use metric/celsius, imperial/fahrenheit, or standard/kelvin",
            ):
                await api_plugin.execute({"location": "Seoul", "units": "rankine"})

            mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_units_override_updates_api_request_parameters(self, api_plugin):
        """Test per-request units override is propagated to OpenWeather params."""
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "name": "Seoul",
            "main": {"temp": 70.0, "humidity": 55},
            "weather": [{"description": "clear sky"}],
            "wind": {"speed": 10.0},
        }
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.get = mock_get

            result = await api_plugin.execute(
                {"location": "Seoul", "units": "imperial"}
            )

            _, kwargs = mock_get.call_args
            assert kwargs["params"]["units"] == "imperial"
            assert result["wind_speed"] == 10.0
            assert result["units"] == "imperial"

    @pytest.mark.asyncio
    async def test_run_tool_uses_units_from_execute_result(self):
        """Test run_tool formatting follows resolved units returned by execute."""
        plugin = WeatherPlugin(config={"units": "metric"})

        with patch.object(
            plugin,
            "execute",
            AsyncMock(
                return_value={
                    "location": "New York",
                    "temperature": 70.0,
                    "condition": "Clear Sky",
                    "humidity": 40,
                    "wind_speed": 8.0,
                    "units": "imperial",
                }
            ),
        ):
            result = await plugin.run_tool("New York")

        assert "70.0°F" in result
        assert "8.0 mph" in result

    @pytest.mark.asyncio
    async def test_pressure_unit_override_converts_api_pressure(self, api_plugin):
        """API pressure values should convert using requested pressure_unit."""
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "name": "London",
            "main": {
                "temp": 15.3,
                "feels_like": 14.7,
                "humidity": 72,
                "pressure": 1013,
            },
            "weather": [{"description": "light rain"}],
            "wind": {"speed": 5.2},
        }
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await api_plugin.execute(
                {"location": "London", "pressure_unit": "inhg"}
            )

            assert result["pressure"] == 29.91
            assert result["pressure_unit"] == "inhg"

    @pytest.mark.asyncio
    async def test_language_override_updates_api_request_parameters(self, api_plugin):
        """Test per-request language override is propagated to OpenWeather params."""
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "name": "Seoul",
            "main": {"temp": 12.0, "humidity": 48},
            "weather": [{"description": "clear sky"}],
            "wind": {"speed": 2.5},
        }
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.get = mock_get

            await api_plugin.execute({"location": "Seoul", "lang": "ko"})

            _, kwargs = mock_get.call_args
            assert kwargs["params"]["lang"] == "ko"

    @pytest.mark.asyncio
    async def test_language_config_applies_when_no_override(self):
        """Test plugin-level language config is included in API params."""
        plugin = WeatherPlugin(config={"api_key": "test_key", "lang": "pt-BR"})
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "name": "Lisbon",
            "main": {"temp": 18.0, "humidity": 61},
            "weather": [{"description": "céu limpo"}],
            "wind": {"speed": 3.0},
        }
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.get = mock_get

            await plugin.execute({"location": "Lisbon"})

            _, kwargs = mock_get.call_args
            assert kwargs["params"]["lang"] == "pt_br"

    @pytest.mark.asyncio
    async def test_invalid_language_override_blocks_api_call(self, api_plugin):
        """Test invalid lang values fail fast before outbound API requests."""
        with patch("httpx.AsyncClient") as mock_client:
            with pytest.raises(
                ValueError,
                match="lang must be an ISO 639-1 code",
            ):
                await api_plugin.execute({"location": "Seoul", "lang": "korean"})

            mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_coordinate_location_query(self, api_plugin):
        """Test coordinates are sent as lat/lon params."""
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "name": "Seoul",
            "main": {"temp": 20.0, "humidity": 60},
            "weather": [{"description": "clear sky"}],
            "wind": {"speed": 3.0},
        }
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.get = mock_get

            result = await api_plugin.execute({"location": "37.5665, 126.9780"})

            _, kwargs = mock_get.call_args
            assert kwargs["params"]["lat"] == 37.5665
            assert kwargs["params"]["lon"] == 126.978
            assert "q" not in kwargs["params"]
            assert result["location"] == "Seoul"

    @pytest.mark.asyncio
    async def test_structured_coordinate_query(self, api_plugin):
        """Test structured latitude/longitude inputs map to lat/lon params."""
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "name": "Seoul",
            "main": {"temp": 20.0, "humidity": 60},
            "weather": [{"description": "clear sky"}],
            "wind": {"speed": 3.0},
        }
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.get = mock_get

            result = await api_plugin.execute(
                {"latitude": "37.5665", "longitude": 126.9780}
            )

            _, kwargs = mock_get.call_args
            assert kwargs["params"]["lat"] == 37.5665
            assert kwargs["params"]["lon"] == 126.978
            assert "q" not in kwargs["params"]
            assert result["location"] == "Seoul"

    @pytest.mark.asyncio
    async def test_city_query_accepts_country_code(self, api_plugin):
        """Test optional country_code disambiguates city queries."""
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "name": "Paris",
            "main": {"temp": 14.2, "humidity": 50},
            "weather": [{"description": "clear sky"}],
            "wind": {"speed": 3.5},
        }
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.get = mock_get

            result = await api_plugin.execute(
                {"location": "Paris", "country_code": "fr"}
            )

            _, kwargs = mock_get.call_args
            assert kwargs["params"]["q"] == "Paris,FR"
            assert result["location"] == "Paris"

    @pytest.mark.asyncio
    async def test_city_query_accepts_state_and_country_code(self, api_plugin):
        """Test location queries can include optional state_code for disambiguation."""
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "name": "Springfield",
            "main": {"temp": 16.8, "humidity": 49},
            "weather": [{"description": "scattered clouds"}],
            "wind": {"speed": 3.2},
        }
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.get = mock_get

            result = await api_plugin.execute(
                {
                    "location": "Springfield",
                    "state_code": " il ",
                    "country_code": "us",
                }
            )

            _, kwargs = mock_get.call_args
            assert kwargs["params"]["q"] == "Springfield,IL,US"
            assert result["location"] == "Springfield"

    @pytest.mark.asyncio
    async def test_zip_code_query_accepts_country_code(self, api_plugin):
        """Test zip_code queries map to OpenWeatherMap zip params."""
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "name": "Mountain View",
            "main": {"temp": 20.1, "humidity": 45},
            "weather": [{"description": "clear sky"}],
            "wind": {"speed": 2.8},
        }
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.get = mock_get

            result = await api_plugin.execute(
                {"zip_code": "94040", "country_code": "us"}
            )

            _, kwargs = mock_get.call_args
            assert kwargs["params"]["zip"] == "94040,US"
            assert result["location"] == "Mountain View"

    @pytest.mark.asyncio
    async def test_zip_code_query_without_country_code(self, api_plugin):
        """Test zip_code can be used without country_code."""
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "name": "Sample City",
            "main": {"temp": 16.3, "humidity": 58},
            "weather": [{"description": "cloudy"}],
            "wind": {"speed": 4.1},
        }
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.get = mock_get

            await api_plugin.execute({"zip_code": "SW1A 1AA"})

            _, kwargs = mock_get.call_args
            assert kwargs["params"]["zip"] == "SW1A 1AA"

    @pytest.mark.asyncio
    async def test_city_id_query_maps_to_openweather_id_param(self, api_plugin):
        """Test city_id queries map to OpenWeatherMap id params."""
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "name": "London",
            "main": {"temp": 17.1, "humidity": 52},
            "weather": [{"description": "clear sky"}],
            "wind": {"speed": 3.4},
        }
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.get = mock_get

            result = await api_plugin.execute({"city_id": "2643743"})

            _, kwargs = mock_get.call_args
            assert kwargs["params"]["id"] == 2643743
            assert "q" not in kwargs["params"]
            assert "zip" not in kwargs["params"]
            assert "lat" not in kwargs["params"]
            assert "lon" not in kwargs["params"]
            assert result["location"] == "London"

    @pytest.mark.asyncio
    async def test_city_id_validation_and_conflicts(self, api_plugin):
        """Test city_id validation and mutual exclusion with other location inputs."""
        with patch("httpx.AsyncClient") as mock_client:
            with pytest.raises(ValueError, match="city_id must be a positive integer"):
                await api_plugin.execute({"city_id": 0})

            with pytest.raises(ValueError, match="city_id cannot be empty"):
                await api_plugin.execute({"city_id": "   "})

            with pytest.raises(ValueError, match="city_id must be a positive integer"):
                await api_plugin.execute({"city_id": "abc"})

            with pytest.raises(
                ValueError,
                match="city_id cannot be combined with location, zip_code, state_code, country_code, latitude, or longitude",
            ):
                await api_plugin.execute({"city_id": 2643743, "location": "London"})

            mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_structured_coordinates_require_both_values(self, api_plugin):
        """Test latitude/longitude must be supplied together."""
        with patch("httpx.AsyncClient") as mock_client:
            with pytest.raises(
                ValueError, match="latitude and longitude must be provided together"
            ):
                await api_plugin.execute({"latitude": 37.5665})

            mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_structured_coordinates_require_numeric_values(self, api_plugin):
        """Test structured coordinates validate numeric input types."""
        with patch("httpx.AsyncClient") as mock_client:
            with pytest.raises(
                ValueError, match="latitude and longitude must be numeric values"
            ):
                await api_plugin.execute({"latitude": "north", "longitude": "west"})

            mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_country_code_validation(self, api_plugin):
        """Test country_code must be a non-empty 2-letter ISO string."""
        with patch("httpx.AsyncClient") as mock_client:
            with pytest.raises(
                ValueError, match="country_code must be a 2-letter ISO country code"
            ):
                await api_plugin.execute({"location": "Paris", "country_code": "FRA"})

            with pytest.raises(ValueError, match="country_code cannot be empty"):
                await api_plugin.execute({"location": "Paris", "country_code": "   "})

            mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_state_code_validation(self, api_plugin):
        """Test state_code must be a non-empty region code with safe characters."""
        with patch("httpx.AsyncClient") as mock_client:
            with pytest.raises(
                ValueError,
                match="state_code must contain only letters, numbers, or hyphens",
            ):
                await api_plugin.execute({"location": "Paris", "state_code": "IL!"})

            with pytest.raises(ValueError, match="state_code cannot be empty"):
                await api_plugin.execute({"location": "Paris", "state_code": "   "})

            mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_zip_code_validation(self, api_plugin):
        """Test zip_code must be a non-empty postal code string."""
        with patch("httpx.AsyncClient") as mock_client:
            with pytest.raises(
                ValueError,
                match="zip_code must contain only letters, numbers, spaces, or hyphens",
            ):
                await api_plugin.execute({"zip_code": "94040!"})

            with pytest.raises(ValueError, match="zip_code cannot be empty"):
                await api_plugin.execute({"zip_code": "  "})

            mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_country_code_cannot_be_combined_with_coordinates(self, api_plugin):
        """Test country_code is rejected for explicit latitude/longitude queries."""
        with patch("httpx.AsyncClient") as mock_client:
            with pytest.raises(
                ValueError,
                match="country_code cannot be used with latitude/longitude inputs",
            ):
                await api_plugin.execute(
                    {
                        "latitude": 48.8566,
                        "longitude": 2.3522,
                        "country_code": "FR",
                    }
                )

            mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_state_code_cannot_be_combined_with_coordinates(self, api_plugin):
        """Test state_code is rejected for explicit latitude/longitude queries."""
        with patch("httpx.AsyncClient") as mock_client:
            with pytest.raises(
                ValueError,
                match="state_code cannot be used with latitude/longitude inputs",
            ):
                await api_plugin.execute(
                    {
                        "latitude": 48.8566,
                        "longitude": 2.3522,
                        "state_code": "IDF",
                    }
                )

            mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_zip_code_cannot_be_combined_with_location(self, api_plugin):
        """Test zip_code cannot be mixed with location queries."""
        with patch("httpx.AsyncClient") as mock_client:
            with pytest.raises(
                ValueError, match="zip_code cannot be used with location"
            ):
                await api_plugin.execute({"location": "Paris", "zip_code": "75001"})

            mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_state_code_cannot_be_combined_with_zip_code(self, api_plugin):
        """Test state_code is rejected when zip_code input is used."""
        with patch("httpx.AsyncClient") as mock_client:
            with pytest.raises(
                ValueError,
                match="state_code cannot be used with zip_code input",
            ):
                await api_plugin.execute(
                    {
                        "zip_code": "75001",
                        "state_code": "IDF",
                    }
                )

            mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_zip_code_cannot_be_combined_with_coordinates(self, api_plugin):
        """Test zip_code is rejected when coordinates are provided."""
        with patch("httpx.AsyncClient") as mock_client:
            with pytest.raises(
                ValueError,
                match="zip_code cannot be used with latitude/longitude inputs",
            ):
                await api_plugin.execute(
                    {
                        "latitude": 48.8566,
                        "longitude": 2.3522,
                        "zip_code": "75001",
                    }
                )

            mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_coordinate_location_validation(self, api_plugin):
        """Test invalid coordinates fail fast before API call."""
        with patch("httpx.AsyncClient") as mock_client:
            with pytest.raises(ValueError, match="latitude must be between -90 and 90"):
                await api_plugin.execute({"location": "123.45, 127.0"})

            mock_client.assert_not_called()

    def test_manifest_version(self, api_plugin):
        """Test that manifest version is updated."""
        manifest = api_plugin.get_manifest()
        assert manifest.version == "1.25.0"
        assert "OpenWeatherMap" in manifest.description
        assert "units" in manifest.config_schema
        assert "standard/kelvin" in manifest.config_schema["units"]
        assert "pressure_unit" in manifest.config_schema
        assert "lang" in manifest.config_schema
        assert "cache_ttl_seconds" in manifest.config_schema
        assert "cache_max_entries" in manifest.config_schema
        assert "city_id" in manifest.inputs
        assert "zip_code" in manifest.inputs
        assert "country_code" in manifest.inputs
        assert "state_code" in manifest.inputs
        assert "latitude" in manifest.inputs
        assert "longitude" in manifest.inputs
        assert "units" in manifest.inputs
        assert "pressure_unit" in manifest.inputs
        assert "lang" in manifest.inputs
        assert "refresh_cache" in manifest.inputs
        assert "feels_like" in manifest.outputs
        assert "temperature_unit" in manifest.outputs
        assert "heat_index" in manifest.outputs
        assert "heat_index_unit" in manifest.outputs
        assert "pressure" in manifest.outputs
        assert "pressure_unit" in manifest.outputs
        assert "wind_speed_unit" in manifest.outputs
        assert "wind_gust" in manifest.outputs
        assert "wind_gust_unit" in manifest.outputs
        assert "wind_beaufort" in manifest.outputs
        assert "wind_beaufort_label" in manifest.outputs
        assert "wind_direction_degrees" in manifest.outputs
        assert "wind_direction_cardinal" in manifest.outputs
        assert "cloudiness" in manifest.outputs
        assert "daylight_status" in manifest.outputs
        assert "visibility" in manifest.outputs
        assert "visibility_unit" in manifest.outputs
        assert "precipitation_1h" in manifest.outputs
        assert "precipitation_3h" in manifest.outputs
        assert "precipitation_type" in manifest.outputs
        assert (
            "required when city_id, zip_code, and latitude/longitude"
            in manifest.inputs["location"]
        )

    def test_tool_description(self, api_plugin):
        """Test tool description includes API information."""
        description = api_plugin.get_tool_description()
        assert "OpenWeatherMap" in description
        assert "API key" in description
        assert "country code" in description
        assert "state_code" in description
        assert "city_id" in description
        assert "zip_code" in description
        assert "coordinates" in description
        assert "standard/kelvin" in description
        assert "pressure_unit" in description
        assert "feels-like temperature" in description
        assert "heat-index temperature" in description
        assert "pressure" in description
        assert "Beaufort" in description
        assert "wind direction" in description
        assert "cloud coverage" in description
        assert "daylight status" in description
        assert "visibility" in description
        assert "precipitation" in description
        assert "lang" in description
        assert "cache_ttl_seconds" in description
        assert "refresh_cache" in description
