"""API v1 router."""

from fastapi import APIRouter

from app.api.v1 import (
    auth, health, tasks, chats, messages, workspaces, templates,
    orchestrator, analytics, scheduled_tasks, budget, workflows, monitoring,
    api_keys, performance
)
from app.api.v1.admin import rate_limits as admin_rate_limits

api_router = APIRouter()

# Include sub-routers
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(chats.router, tags=["chats"])
api_router.include_router(messages.router, tags=["messages"])
api_router.include_router(workspaces.router, prefix="/workspaces", tags=["workspaces"])
api_router.include_router(orchestrator.router, prefix="/orchestrator", tags=["orchestrator"])
api_router.include_router(templates.router, prefix="/templates", tags=["templates"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(scheduled_tasks.router, prefix="/scheduled-tasks", tags=["scheduled-tasks"])
api_router.include_router(budget.router, tags=["budget"])
api_router.include_router(workflows.router, tags=["workflows"])
api_router.include_router(monitoring.router, tags=["monitoring"])
api_router.include_router(api_keys.router, tags=["api-keys"])
api_router.include_router(performance.router, tags=["performance"])

# Admin routes
api_router.include_router(admin_rate_limits.router, prefix="/admin/rate-limits", tags=["admin", "rate-limits"])
