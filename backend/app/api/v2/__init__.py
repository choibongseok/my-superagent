"""API v2 router."""

from fastapi import APIRouter

from app.api.v2 import tasks, health

# Create v2 API router
api_router = APIRouter()

# Include v2 routes
api_router.include_router(health.router, tags=["health"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])

# Future v2 endpoints will be added here
# api_router.include_router(workflows.router, prefix="/workflows", tags=["workflows"])
# api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
