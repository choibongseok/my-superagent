"""Health check endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/ping")
async def ping():
    """Simple ping endpoint."""
    return {"message": "pong"}


@router.get("/status")
async def status():
    """Detailed status endpoint."""
    return {
        "status": "operational",
        "services": {
            "api": "healthy",
            "database": "healthy",
            "redis": "healthy",
        },
    }
