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
        assert result["feels_like"] == 21.3
        assert result["condition"] == "Partly Cloudy"
        assert result["humidity"] == 65
        assert result["wind_speed"] == 12.3

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
    async def test_refresh_cache_validation_rejects_non_boolean_values(self, api_plugin):
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
        assert "Condition:" in result
        assert "Humidity:" in result
        assert "Wind Speed:" in result

    @pytest.mark.asyncio
    async def test_real_api_call_success(self, api_plugin):
        """Test successful API call with real data."""
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "name": "London",
            "main": {"temp": 15.3, "feels_like": 14.7, "humidity": 72},
            "weather": [{"description": "light rain"}],
            "wind": {"speed": 5.2},  # m/s
        }
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await api_plugin.execute({"location": "London"})

            assert result["location"] == "London"
            assert result["temperature"] == 15.3
            assert result["feels_like"] == 14.7
            assert result["condition"] == "Light Rain"
            assert result["humidity"] == 72
            assert result["wind_speed"] == 18.7  # 5.2 m/s * 3.6 = 18.72 km/h

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
            "main": {"temp": 68.5, "humidity": 55},  # Fahrenheit
            "weather": [{"description": "clear sky"}],
            "wind": {"speed": 10.5},  # mph in imperial mode
        }
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await plugin.execute({"location": "New York"})

            assert result["temperature"] == 68.5
            assert result["wind_speed"] == 10.5  # No conversion for imperial

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
        assert result["feels_like"] == 70.3
        assert result["wind_speed"] == 7.6

    @pytest.mark.asyncio
    async def test_standard_units_override_changes_mock_response_units(self):
        """Test standard/kelvin override returns Kelvin and m/s in mock mode."""
        plugin = WeatherPlugin(config={"units": "metric"})

        result = await plugin.execute({"location": "Seoul", "units": "kelvin"})

        assert result["location"] == "Seoul"
        assert result["units"] == "standard"
        assert result["temperature"] == 295.6
        assert result["feels_like"] == 294.4
        assert result["wind_speed"] == 3.4

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
            assert result["wind_speed"] == 4.6

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
                match="city_id cannot be combined with location, zip_code, country_code, latitude, or longitude",
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
    async def test_zip_code_cannot_be_combined_with_location(self, api_plugin):
        """Test zip_code cannot be mixed with location queries."""
        with patch("httpx.AsyncClient") as mock_client:
            with pytest.raises(
                ValueError, match="zip_code cannot be used with location"
            ):
                await api_plugin.execute({"location": "Paris", "zip_code": "75001"})

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
        assert manifest.version == "1.12.0"
        assert "OpenWeatherMap" in manifest.description
        assert "units" in manifest.config_schema
        assert "standard/kelvin" in manifest.config_schema["units"]
        assert "lang" in manifest.config_schema
        assert "cache_ttl_seconds" in manifest.config_schema
        assert "cache_max_entries" in manifest.config_schema
        assert "city_id" in manifest.inputs
        assert "zip_code" in manifest.inputs
        assert "country_code" in manifest.inputs
        assert "latitude" in manifest.inputs
        assert "longitude" in manifest.inputs
        assert "units" in manifest.inputs
        assert "lang" in manifest.inputs
        assert "refresh_cache" in manifest.inputs
        assert "feels_like" in manifest.outputs
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
        assert "city_id" in description
        assert "zip_code" in description
        assert "coordinates" in description
        assert "standard/kelvin" in description
        assert "feels-like temperature" in description
        assert "lang" in description
        assert "cache_ttl_seconds" in description
        assert "refresh_cache" in description
