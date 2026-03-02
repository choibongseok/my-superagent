"""API version negotiation middleware."""

import logging
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class APIVersionMiddleware(BaseHTTPMiddleware):
    """
    Middleware for API version negotiation.
    
    Supports version selection via:
    1. X-API-Version header
    2. Accept header (application/vnd.agenthq.v2+json)
    3. URL prefix (/api/v2/* or /api/v1/*)
    
    Default: v1 (for backward compatibility)
    """
    
    SUPPORTED_VERSIONS = {"v1", "v2"}
    DEFAULT_VERSION = "v1"
    
    def __init__(self, app: ASGIApp, **options):
        """Initialize middleware."""
        super().__init__(app, **options)
    
    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """Process request and determine API version."""
        
        # Extract version from request
        api_version = self._extract_version(request)
        
        # Validate version
        if api_version not in self.SUPPORTED_VERSIONS:
            logger.warning(
                f"Unsupported API version requested: {api_version}, "
                f"falling back to {self.DEFAULT_VERSION}"
            )
            api_version = self.DEFAULT_VERSION
        
        # Store version in request state for handlers to access
        request.state.api_version = api_version
        
        # Add version info to response headers
        response = await call_next(request)
        response.headers["X-API-Version"] = api_version
        response.headers["X-Supported-Versions"] = ", ".join(sorted(self.SUPPORTED_VERSIONS))
        
        # Add deprecation warning if using v1
        if api_version == "v1" and request.url.path.startswith("/api/v1"):
            response.headers["Deprecation"] = "true"
            response.headers["Sunset"] = "Sat, 1 Jun 2026 00:00:00 GMT"
            response.headers["Link"] = '</api/v2/docs>; rel="successor-version"'
        
        return response
    
    def _extract_version(self, request: Request) -> str:
        """
        Extract API version from request.
        
        Priority:
        1. X-API-Version header
        2. Accept header (application/vnd.agenthq.v2+json)
        3. URL path (/api/v2/*)
        4. Default to v1
        """
        
        # 1. Check X-API-Version header
        header_version = request.headers.get("X-API-Version", "").lower()
        if header_version in self.SUPPORTED_VERSIONS:
            logger.debug(f"Version from X-API-Version header: {header_version}")
            return header_version
        
        # 2. Check Accept header for custom media type
        accept_header = request.headers.get("Accept", "").lower()
        for version in self.SUPPORTED_VERSIONS:
            if f"application/vnd.agenthq.{version}+json" in accept_header:
                logger.debug(f"Version from Accept header: {version}")
                return version
        
        # 3. Extract from URL path
        path = request.url.path
        for version in self.SUPPORTED_VERSIONS:
            if path.startswith(f"/api/{version}/"):
                logger.debug(f"Version from URL path: {version}")
                return version
        
        # 4. Default to v1 for backward compatibility
        logger.debug(f"No explicit version, defaulting to {self.DEFAULT_VERSION}")
        return self.DEFAULT_VERSION


def get_api_version(request: Request) -> str:
    """
    Helper function to get API version from request state.
    
    Usage in route handlers:
        from app.middleware.api_version import get_api_version
        
        @router.get("/endpoint")
        async def handler(request: Request):
            version = get_api_version(request)
            if version == "v2":
                # v2 behavior
            else:
                # v1 behavior (backward compatible)
    """
    return getattr(request.state, "api_version", "v1")
