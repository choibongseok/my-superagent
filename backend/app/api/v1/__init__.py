"""API v1 router."""

from fastapi import APIRouter


from app.api.v1 import auth, health, tasks, chats, messages, workspaces,orchestrator
api_router = APIRouter()

# Include sub-routers
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(chats.router, tags=["chats"])
api_router.include_router(messages.router, tags=["messages"])
api_router.include_router(workspaces.router, prefix="/workspaces", tags=["workspaces"])
api_router.include_router(orchestrator.router, prefix="/orchestrator", tags=["orchestrator"])