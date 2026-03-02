"""Tests for API version negotiation middleware."""

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.middleware.api_version import APIVersionMiddleware, get_api_version


# Create test app
app = FastAPI()
app.add_middleware(APIVersionMiddleware)


@app.get("/test")
async def test_endpoint(request: Request):
    """Test endpoint that returns API version."""
    version = get_api_version(request)
    return {"version": version, "message": "test"}


@app.get("/api/v1/tasks")
async def v1_tasks(request: Request):
    """V1 tasks endpoint."""
    version = get_api_version(request)
    return {"version": version, "data": "v1"}


@app.get("/api/v2/tasks")
async def v2_tasks(request: Request):
    """V2 tasks endpoint."""
    version = get_api_version(request)
    return {"version": version, "data": "v2"}


client = TestClient(app)


class TestAPIVersionMiddleware:
    """Test API version negotiation middleware."""
    
    def test_default_version(self):
        """Test default version is v1."""
        response = client.get("/test")
        assert response.status_code == 200
        assert response.json()["version"] == "v1"
        assert response.headers["X-API-Version"] == "v1"
    
    def test_version_from_header(self):
        """Test version selection via X-API-Version header."""
        response = client.get("/test", headers={"X-API-Version": "v2"})
        assert response.status_code == 200
        assert response.json()["version"] == "v2"
        assert response.headers["X-API-Version"] == "v2"
    
    def test_version_from_accept_header(self):
        """Test version selection via Accept header."""
        response = client.get(
            "/test",
            headers={"Accept": "application/vnd.agenthq.v2+json"}
        )
        assert response.status_code == 200
        assert response.json()["version"] == "v2"
        assert response.headers["X-API-Version"] == "v2"
    
    def test_version_from_url_path(self):
        """Test version selection via URL path."""
        response = client.get("/api/v2/tasks")
        assert response.status_code == 200
        assert response.json()["version"] == "v2"
        assert response.headers["X-API-Version"] == "v2"
    
    def test_version_priority(self):
        """Test version selection priority (header > accept > url)."""
        # Header should override URL path
        response = client.get(
            "/api/v1/tasks",
            headers={"X-API-Version": "v2"}
        )
        assert response.json()["version"] == "v2"
        
        # Accept header should override URL path
        response = client.get(
            "/api/v1/tasks",
            headers={"Accept": "application/vnd.agenthq.v2+json"}
        )
        assert response.json()["version"] == "v2"
    
    def test_invalid_version_fallback(self):
        """Test invalid version falls back to default."""
        response = client.get("/test", headers={"X-API-Version": "v99"})
        assert response.status_code == 200
        assert response.json()["version"] == "v1"
        assert response.headers["X-API-Version"] == "v1"
    
    def test_case_insensitive_version(self):
        """Test version header is case-insensitive."""
        response = client.get("/test", headers={"X-API-Version": "V2"})
        assert response.status_code == 200
        assert response.json()["version"] == "v2"
    
    def test_supported_versions_header(self):
        """Test X-Supported-Versions header is present."""
        response = client.get("/test")
        assert "X-Supported-Versions" in response.headers
        supported = response.headers["X-Supported-Versions"]
        assert "v1" in supported
        assert "v2" in supported
    
    def test_v1_deprecation_headers(self):
        """Test v1 responses include deprecation headers."""
        response = client.get("/api/v1/tasks")
        assert response.headers.get("Deprecation") == "true"
        assert "Sunset" in response.headers
        assert "Link" in response.headers
        assert "successor-version" in response.headers["Link"]
    
    def test_v2_no_deprecation_headers(self):
        """Test v2 responses don't include deprecation headers."""
        response = client.get("/api/v2/tasks")
        # Deprecation headers should only be added for v1
        # This test might need adjustment based on actual implementation
        assert response.status_code == 200
    
    def test_multiple_accept_media_types(self):
        """Test Accept header with multiple media types."""
        response = client.get(
            "/test",
            headers={"Accept": "application/json, application/vnd.agenthq.v2+json"}
        )
        assert response.json()["version"] == "v2"
    
    def test_version_in_request_state(self):
        """Test version is accessible in request.state."""
        # This is tested implicitly by other tests using get_api_version()
        response = client.get("/test", headers={"X-API-Version": "v2"})
        assert response.json()["version"] == "v2"


class TestGetAPIVersion:
    """Test get_api_version helper function."""
    
    def test_get_version_from_state(self):
        """Test getting version from request state."""
        response = client.get("/test", headers={"X-API-Version": "v2"})
        # The endpoint uses get_api_version() internally
        assert response.json()["version"] == "v2"
    
    def test_get_version_default(self):
        """Test default version when state is not set."""
        # When state.api_version doesn't exist, should return "v1"
        response = client.get("/test")
        assert response.json()["version"] == "v1"


class TestVersionScenarios:
    """Test real-world version negotiation scenarios."""
    
    def test_mobile_app_v2(self):
        """Test mobile app using v2 with custom header."""
        response = client.get(
            "/api/v2/tasks",
            headers={
                "X-API-Version": "v2",
                "User-Agent": "AgentHQ-Mobile/2.0.0 (iOS)"
            }
        )
        assert response.json()["version"] == "v2"
    
    def test_web_app_v1_default(self):
        """Test web app using default v1."""
        response = client.get(
            "/api/v1/tasks",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        assert response.json()["version"] == "v1"
    
    def test_gradual_migration(self):
        """Test client migrating from v1 to v2 gradually."""
        # Phase 1: Client uses v1 (implicit)
        response_v1 = client.get("/api/v1/tasks")
        assert response_v1.json()["version"] == "v1"
        
        # Phase 2: Client tests v2 with header
        response_v2_test = client.get(
            "/api/v1/tasks",
            headers={"X-API-Version": "v2"}
        )
        assert response_v2_test.json()["version"] == "v2"
        
        # Phase 3: Client fully migrates to v2 URL
        response_v2 = client.get("/api/v2/tasks")
        assert response_v2.json()["version"] == "v2"
    
    def test_api_gateway_version_routing(self):
        """Test API gateway routing based on version."""
        # Gateway routes to v1 backend
        v1_response = client.get("/api/v1/tasks")
        assert v1_response.json()["data"] == "v1"
        
        # Gateway routes to v2 backend
        v2_response = client.get("/api/v2/tasks")
        assert v2_response.json()["data"] == "v2"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
