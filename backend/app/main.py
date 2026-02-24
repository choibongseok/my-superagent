"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from app.api.v1 import api_router
from app.core.cache import cache
from app.core.config import settings
from app.core.database import engine
from app.core.metrics import init_metrics, metrics_app
from app.core.websocket import manager as ws_manager
from app.middleware.cache import CacheMiddleware
from app.middleware.metrics import MetricsMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.models.base import Base

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Starting AgentHQ Backend...")

    # Initialize metrics
    if settings.ENABLE_METRICS:
        init_metrics()
        logger.info("Metrics initialized")

    # Create database tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database initialized")

    # Start WebSocket heartbeat loop
    ws_manager.start_heartbeat()
    logger.info("WebSocket heartbeat started")

    # Connect to Redis
    try:
        await cache.connect()
        logger.info("Redis cache connected")
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}. Continuing without cache.")

    yield

    logger.info("Shutting down AgentHQ Backend...")

    # Stop WebSocket heartbeat
    ws_manager.stop_heartbeat()

    # Disconnect from Redis
    try:
        await cache.disconnect()
        logger.info("Redis cache disconnected")
    except Exception:
        pass

    await engine.dispose()


# OpenAPI tags for grouping endpoints
tags_metadata = [
    {
        "name": "health",
        "description": "Health check and system status endpoints.",
    },
    {
        "name": "auth",
        "description": "Authentication and authorization endpoints. Supports Google OAuth 2.0 and JWT tokens.",
    },
    {
        "name": "tasks",
        "description": "Task management endpoints. Create, retrieve, cancel, and retry AI agent tasks.",
    },
    {
        "name": "orchestrator",
        "description": "Multi-agent orchestration endpoints. Coordinate Docs, Sheets, and Slides agents.",
    },
    {
        "name": "memory",
        "description": "Memory and conversation history endpoints. Search past interactions and contexts.",
    },
    {
        "name": "webhooks",
        "description": "Webhook endpoints for Google Drive notifications and external integrations.",
    },
    {
        "name": "analytics",
        "description": "Usage analytics and metrics endpoints.",
    },
    {
        "name": "workspaces",
        "description": "Workspace and team management endpoints.",
    },
]

# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
**AgentHQ** is a Google Workspace AI automation platform powered by Claude and LangChain.

## Features

- 🤖 **Multi-Agent System**: Specialized agents for Docs, Sheets, and Slides
- 🔗 **Orchestration**: Coordinate multiple agents for complex workflows  
- 💾 **Memory System**: Conversation history with semantic search (pgvector)
- 🔔 **Webhooks**: Google Drive change detection and auto-triggers
- 📊 **Analytics**: Usage tracking and performance metrics

## Authentication

All API endpoints (except `/health` and `/docs`) require JWT authentication:

1. Obtain access token via Google OAuth 2.0 (`/api/v1/auth/login`)
2. Include token in requests: `Authorization: Bearer <token>`

## Rate Limiting

Default rate limit: **60 requests/minute** per IP address.

## Support

- **Documentation**: [GitHub Repository](https://github.com/choibongseok/my-superagent)
- **Issues**: [GitHub Issues](https://github.com/choibongseok/my-superagent/issues)
    """,
    contact={
        "name": "AgentHQ Support",
        "url": "https://github.com/choibongseok/my-superagent",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
    openapi_tags=tags_metadata,
    docs_url=None,  # Custom docs endpoint below
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add Gzip compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Add metrics middleware (should be first to measure everything)
if settings.ENABLE_METRICS:
    app.add_middleware(MetricsMiddleware)

# Add rate limiting middleware
app.add_middleware(
    RateLimitMiddleware,
    requests_per_minute=settings.RATE_LIMIT_PER_MINUTE,
)

# Add cache middleware
app.add_middleware(CacheMiddleware, cache_ttl=settings.REDIS_DEFAULT_TTL)

# Mount metrics endpoint for Prometheus
if settings.ENABLE_METRICS:
    app.mount("/metrics", metrics_app)

# Include API router
app.include_router(api_router, prefix="/api/v1")


def custom_openapi():
    """Custom OpenAPI schema with enhanced documentation."""
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=tags_metadata,
        contact=app.contact,
        license_info=app.license_info,
    )

    # Add security schemes
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Enter JWT token obtained from `/api/v1/auth/login` endpoint",
        }
    }

    # Add global security requirement
    openapi_schema["security"] = [{"BearerAuth": []}]

    # Add example servers
    openapi_schema["servers"] = [
        {
            "url": "http://localhost:8000",
            "description": "Local development server",
        },
        {
            "url": settings.API_URL if hasattr(settings, "API_URL") else "https://api.agenthq.example.com",
            "description": "Production server",
        },
    ]

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    """Custom Swagger UI with enhanced styling."""
    if not settings.DEBUG:
        raise HTTPException(status_code=404, detail="Not found")
    
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title=f"{app.title} - API Documentation",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
        swagger_favicon_url="https://fastapi.tiangolo.com/img/favicon.png",
    )


@app.get(
    "/",
    tags=["health"],
    summary="Root endpoint",
    description="Returns basic API information and links to documentation.",
    response_description="API metadata and status",
)
async def root():
    """Root endpoint."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs" if settings.DEBUG else "disabled",
        "api_prefix": "/api/v1",
    }


@app.get(
    "/health",
    tags=["health"],
    summary="Health check",
    description="Check if the API is running and healthy. Returns environment information.",
    response_description="Health status and environment",
)
async def health_check():
    """Health check endpoint."""
    from datetime import datetime, timezone
    
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.now(timezone.UTC).isoformat(),
    }


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error": str(exc) if settings.DEBUG else "An error occurred",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
