"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from redis import Redis

from app.api.v1 import api_router as api_router_v1
from app.api.v2 import api_router as api_router_v2
from app.core.cache import cache
from app.core.config import settings
from app.core.database import engine
from app.core.metrics import init_metrics, metrics_app
from app.core.redis_rate_limiter import init_rate_limiter
from app.middleware.api_version import APIVersionMiddleware
from app.middleware.cache import CacheMiddleware
from app.middleware.metrics import MetricsMiddleware
from app.middleware.rate_limiter import RateLimitMiddleware
from app.models.base import Base

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper()),
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

    # Connect to Redis
    try:
        await cache.connect()
        logger.info("Redis cache connected")
        
        # Initialize rate limiter with Redis client
        if settings.RATE_LIMIT_ENABLED:
            # Create synchronous Redis client for rate limiter
            redis_client = Redis.from_url(
                settings.REDIS_URL,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
                decode_responses=False
            )
            init_rate_limiter(redis_client)
            logger.info("Rate limiter initialized")
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}. Continuing without cache/rate limiting.")

    yield

    logger.info("Shutting down AgentHQ Backend...")

    # Disconnect from Redis
    try:
        await cache.disconnect()
        logger.info("Redis cache disconnected")
    except Exception:
        pass

    await engine.dispose()


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI Super Agent Hub - Backend API",
    docs_url="/docs" if settings.DEBUG else None,
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

# Add API version negotiation middleware
app.add_middleware(APIVersionMiddleware)

# Add rate limiting middleware
if settings.RATE_LIMIT_ENABLED:
    app.add_middleware(RateLimitMiddleware)

# Add cache middleware
app.add_middleware(CacheMiddleware, cache_ttl=settings.REDIS_DEFAULT_TTL)

# Mount metrics endpoint for Prometheus
if settings.ENABLE_METRICS:
    app.mount("/metrics", metrics_app)

# Include API routers
app.include_router(api_router_v1, prefix="/api/v1")
app.include_router(api_router_v2, prefix="/api/v2")


@app.get("/", tags=["health"])
async def root():
    """Root endpoint."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs" if settings.DEBUG else "disabled",
    }


@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
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
