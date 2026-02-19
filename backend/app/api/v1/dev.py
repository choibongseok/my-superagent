"""Developer API Mode endpoints.

Authentication via ``X-API-Key`` header for task creation/retrieval.
API key issuance requires a valid Bearer JWT (same as regular auth).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.api_key import ApiKey, generate_api_key, hash_api_key
from app.models.task import Task as TaskModel, TaskStatus, TaskType
from app.models.user import User

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Schemas ───────────────────────────────────────────────────────────────────


class ApiKeyCreate(BaseModel):
    """Request body for creating a new API key."""

    name: str = Field(..., min_length=1, max_length=255, description="Human-readable label for the key")


class ApiKeyResponse(BaseModel):
    """Response after creating a new API key.

    The ``key`` field is returned **only once** at creation time. It is never
    stored in plaintext and cannot be retrieved again.
    """

    id: UUID
    name: str
    key: str = Field(..., description="Plaintext API key — store it safely, shown only once")
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyInfo(BaseModel):
    """API key metadata (no plaintext key)."""

    id: UUID
    name: str
    is_active: bool
    last_used_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class DevTaskCreate(BaseModel):
    """Request body for creating a task via the Developer API."""

    prompt: str = Field(..., min_length=1, max_length=5000)
    task_type: TaskType
    metadata: Optional[Dict[str, Any]] = None


class DevTaskResponse(BaseModel):
    """Task response for the Developer API."""

    id: UUID
    user_id: UUID
    prompt: str
    task_type: TaskType
    status: TaskStatus
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    document_url: Optional[str] = None
    document_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── API Key dependency ────────────────────────────────────────────────────────


async def get_api_key_user(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve an ``X-API-Key`` header to the owning ``User``.

    Looks up the SHA-256 hash of the provided key, checks that the key is
    active, updates ``last_used_at``, and returns the associated user.

    Raises:
        HTTPException 401: Missing, invalid, or inactive key.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
            headers={"WWW-Authenticate": "X-API-Key"},
        )

    key_hash = hash_api_key(x_api_key)

    result = await db.execute(
        select(ApiKey).where(ApiKey.key_hash == key_hash)
    )
    api_key_obj = result.scalar_one_or_none()

    if not api_key_obj or not api_key_obj.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key",
            headers={"WWW-Authenticate": "X-API-Key"},
        )

    # Update last_used_at asynchronously (best-effort; don't fail the request)
    try:
        api_key_obj.last_used_at = datetime.now(timezone.utc)
        await db.commit()
    except Exception:
        await db.rollback()
        logger.warning("Failed to update last_used_at for api key %s", api_key_obj.id)

    # Load the owning user
    user_result = await db.execute(
        select(User).where(User.id == api_key_obj.user_id)
    )
    user = user_result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User associated with this API key is not active",
            headers={"WWW-Authenticate": "X-API-Key"},
        )

    return user


# ── Developer task endpoints ──────────────────────────────────────────────────


@router.post(
    "/tasks",
    response_model=DevTaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task (API key auth)",
)
async def dev_create_task(
    task_data: DevTaskCreate,
    current_user: Annotated[User, Depends(get_api_key_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskModel:
    """Create a new task authenticated with ``X-API-Key``.

    Supports task types: ``research``, ``docs``, ``sheets``, ``slides``.
    The task is queued to Celery immediately after creation.
    """
    task = TaskModel(
        user_id=current_user.id,
        prompt=task_data.prompt,
        task_type=task_data.task_type,
        status=TaskStatus.PENDING,
        task_metadata=task_data.metadata,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # Queue to Celery
    try:
        from app.agents.celery_app import (
            process_docs_task,
            process_research_task,
            process_sheets_task,
            process_slides_task,
        )

        task_id_str = str(task.id)
        user_id_str = str(current_user.id)

        if task_data.task_type == TaskType.RESEARCH:
            celery_task = process_research_task.apply_async(
                args=[task_id_str, task_data.prompt, user_id_str]
            )
        elif task_data.task_type == TaskType.DOCS:
            celery_task = process_docs_task.apply_async(
                args=[task_id_str, task_data.prompt, user_id_str, task_data.prompt[:80]]
            )
        elif task_data.task_type == TaskType.SHEETS:
            celery_task = process_sheets_task.apply_async(
                args=[task_id_str, task_data.prompt, user_id_str, task_data.prompt[:80]]
            )
        elif task_data.task_type == TaskType.SLIDES:
            celery_task = process_slides_task.apply_async(
                args=[task_id_str, task_data.prompt, user_id_str, task_data.prompt[:80]]
            )
        else:
            raise ValueError(f"Unknown task type: {task_data.task_type}")

        task.celery_task_id = celery_task.id
        task.status = TaskStatus.IN_PROGRESS
        await db.commit()
        await db.refresh(task)

    except Exception as exc:
        task.status = TaskStatus.FAILED
        task.error_message = f"Failed to queue task: {exc}"
        await db.commit()
        logger.error("Failed to queue dev task %s: %s", task.id, exc)

    return task


@router.get(
    "/tasks/{task_id}",
    response_model=DevTaskResponse,
    summary="Get a task (API key auth)",
)
async def dev_get_task(
    task_id: UUID,
    current_user: Annotated[User, Depends(get_api_key_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskModel:
    """Retrieve a task by ID. The task must belong to the API key owner."""
    result = await db.execute(
        select(TaskModel).where(
            TaskModel.id == task_id,
            TaskModel.user_id == current_user.id,
        )
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    return task


# ── API key management (requires Bearer JWT) ──────────────────────────────────


@router.post(
    "/api-keys",
    response_model=ApiKeyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Issue a new API key (Bearer JWT required)",
)
async def create_api_key(
    body: ApiKeyCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Generate and store a new API key for the authenticated user.

    The plaintext key is returned **once** in the response and is not stored.
    Only the SHA-256 hash is persisted.
    """
    plaintext_key = generate_api_key()
    key_hash = hash_api_key(plaintext_key)

    api_key_obj = ApiKey(
        user_id=current_user.id,
        key_hash=key_hash,
        name=body.name,
        is_active=True,
    )
    db.add(api_key_obj)
    await db.commit()
    await db.refresh(api_key_obj)

    logger.info("Created API key %s for user %s", api_key_obj.id, current_user.id)

    return {
        "id": api_key_obj.id,
        "name": api_key_obj.name,
        "key": plaintext_key,
        "created_at": api_key_obj.created_at,
    }
