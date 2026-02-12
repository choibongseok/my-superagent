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

    @pytest.mark.asyncio
    async def test_location_required(self, mock_plugin):
        """Test that location parameter is required."""
        with pytest.raises(ValueError, match="location is required"):
            await mock_plugin.execute({})

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
            "main": {
                "temp": 15.3,
                "humidity": 72
            },
            "weather": [
                {"description": "light rain"}
            ],
            "wind": {
                "speed": 5.2  # m/s
            }
        }
        mock_response.raise_for_status = AsyncMock()
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            
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
            status_code=404,
            request=Request("GET", "http://test.com")
        )
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock()
            mock_get.side_effect = HTTPStatusError(
                "Not Found",
                request=mock_response.request,
                response=mock_response
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get
            
            with pytest.raises(ValueError, match="Location not found"):
                await api_plugin.execute({"location": "InvalidCityXYZ"})

    @pytest.mark.asyncio
    async def test_invalid_api_key(self, api_plugin):
        """Test handling of invalid API key."""
        from httpx import HTTPStatusError, Request, Response
        
        mock_response = Response(
            status_code=401,
            request=Request("GET", "http://test.com")
        )
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock()
            mock_get.side_effect = HTTPStatusError(
                "Unauthorized",
                request=mock_response.request,
                response=mock_response
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
            "main": {
                "temp": 68.5,  # Fahrenheit
                "humidity": 55
            },
            "weather": [
                {"description": "clear sky"}
            ],
            "wind": {
                "speed": 10.5  # mph in imperial mode
            }
        }
        mock_response.raise_for_status = AsyncMock()
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            
            result = await plugin.execute({"location": "New York"})
            
            assert result["temperature"] == 68.5
            assert result["wind_speed"] == 10.5  # No conversion for imperial

    def test_manifest_version(self, api_plugin):
        """Test that manifest version is updated."""
        manifest = api_plugin.get_manifest()
        assert manifest.version == "1.1.0"
        assert "OpenWeatherMap" in manifest.description

    def test_tool_description(self, api_plugin):
        """Test tool description includes API information."""
        description = api_plugin.get_tool_description()
        assert "OpenWeatherMap" in description
        assert "API key" in description
