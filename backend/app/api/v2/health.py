"""Health check endpoint for API v2."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response model."""
    
    status: str
    version: str
    api_version: str
    environment: str


@router.get("/health", response_model=HealthResponse)
async def health_check_v2():
    """
    Health check endpoint (v2).
    
    Differences from v1:
    - Returns explicit api_version field
    - Structured response model
    - More detailed status information
    """
    return HealthResponse(
        status="healthy",
        version=settings.APP_VERSION,
        api_version="v2",
        environment=settings.ENVIRONMENT,
    )
