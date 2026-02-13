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
        assert result["condition"] == "Partly Cloudy"
        assert result["humidity"] == 65
        assert result["wind_speed"] == 12.3

    def test_units_aliases_are_normalized(self):
        """Test celsius/fahrenheit aliases normalize to OpenWeather units."""
        celsius_plugin = WeatherPlugin(config={"units": "celsius"})
        fahrenheit_plugin = WeatherPlugin(config={"units": "F"})

        assert celsius_plugin.units == "metric"
        assert fahrenheit_plugin.units == "imperial"

    def test_invalid_units_are_rejected(self):
        """Test unsupported units fail fast with a helpful message."""
        with pytest.raises(
            ValueError,
            match="Unsupported units. Use metric/celsius or imperial/fahrenheit",
        ):
            WeatherPlugin(config={"units": "kelvin"})

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
        assert "Condition:" in result
        assert "Humidity:" in result
        assert "Wind Speed:" in result

    @pytest.mark.asyncio
    async def test_real_api_call_success(self, api_plugin):
        """Test successful API call with real data."""
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "name": "London",
            "main": {"temp": 15.3, "humidity": 72},
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
            assert result["condition"] == "Light Rain"
            assert result["humidity"] == 72
            assert result["wind_speed"] == 18.7  # 5.2 m/s * 3.6 = 18.72 km/h

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
        assert result["wind_speed"] == 7.6

    @pytest.mark.asyncio
    async def test_units_override_validates_supported_values(self, api_plugin):
        """Test execute validates invalid per-request units overrides."""
        with patch("httpx.AsyncClient") as mock_client:
            with pytest.raises(
                ValueError,
                match="Unsupported units. Use metric/celsius or imperial/fahrenheit",
            ):
                await api_plugin.execute({"location": "Seoul", "units": "kelvin"})

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
    async def test_coordinate_location_validation(self, api_plugin):
        """Test invalid coordinates fail fast before API call."""
        with patch("httpx.AsyncClient") as mock_client:
            with pytest.raises(ValueError, match="latitude must be between -90 and 90"):
                await api_plugin.execute({"location": "123.45, 127.0"})

            mock_client.assert_not_called()

    def test_manifest_version(self, api_plugin):
        """Test that manifest version is updated."""
        manifest = api_plugin.get_manifest()
        assert manifest.version == "1.5.0"
        assert "OpenWeatherMap" in manifest.description
        assert "units" in manifest.config_schema
        assert "country_code" in manifest.inputs
        assert "latitude" in manifest.inputs
        assert "longitude" in manifest.inputs
        assert "units" in manifest.inputs
        assert "required when latitude/longitude" in manifest.inputs["location"]

    def test_tool_description(self, api_plugin):
        """Test tool description includes API information."""
        description = api_plugin.get_tool_description()
        assert "OpenWeatherMap" in description
        assert "API key" in description
        assert "country code" in description
        assert "coordinates" in description
