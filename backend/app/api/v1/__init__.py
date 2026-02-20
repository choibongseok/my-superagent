"""API v1 router."""

from fastapi import APIRouter

from app.api.v1 import auth, health, tasks, chats, messages, workspaces, templates, orchestrator, analytics, share, dev, prompts, qa, webhooks
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
api_router.include_router(analytics.router, tags=["analytics"])
api_router.include_router(share.router, tags=["share"])  # Public share viewer (no auth)
api_router.include_router(dev.router, prefix="/dev", tags=["dev"])  # Developer API Mode
api_router.include_router(prompts.router, prefix="/prompts", tags=["prompts"])  # Shared Prompt Library
api_router.include_router(qa.router, tags=["qa"])  # Quality Assurance validation
api_router.include_router(webhooks.router, tags=["webhooks"])  # Webhook notifications
