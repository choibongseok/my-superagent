"""Task Chain API — Smart Task Chaining (#227).

Endpoints:
  POST   /chains               → create a new task chain (DRAFT)
  GET    /chains               → list user's chains (paginated)
  GET    /chains/{id}          → get chain details with steps
  PATCH  /chains/{id}          → update chain metadata (DRAFT only)
  DELETE /chains/{id}          → delete a chain
  POST   /chains/{id}/start    → start or resume chain execution
  POST   /chains/{id}/cancel   → cancel a running chain
  POST   /chains/{id}/retry    → retry a failed chain from the failed step
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.task_chain import ChainStatus
from app.models.user import User
from app.schemas.chain import (
    ChainCreate,
    ChainListResponse,
    ChainResponse,
    ChainUpdate,
)
from app.services import chain_service

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_chain_or_404(
    db: AsyncSession,
    chain_id: UUID,
    user_id: UUID,
):
    """Fetch a chain belonging to the user or raise 404."""
    chain = await chain_service.get_chain(db, chain_id, user_id)
    if chain is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chain not found",
        )
    return chain


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.post(
    "/chains",
    response_model=ChainResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new task chain",
)
async def create_chain(
    body: ChainCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create a multi-step task chain in DRAFT status.

    Each step defines a prompt template and task type.
    Use ``{{previous_output}}`` in prompt templates to pipe the prior step's
    output into the next step.
    """
    chain = await chain_service.create_chain(db, current_user.id, body)
    await db.commit()
    # Re-fetch to avoid MissingGreenlet on lazy-loaded attributes after commit
    chain = await chain_service.get_chain(db, chain.id, current_user.id)
    logger.info("Chain %s created by user %s (%d steps)", chain.id, current_user.id, len(chain.steps))
    return chain


@router.get(
    "/chains",
    response_model=ChainListResponse,
    summary="List task chains",
)
async def list_chains(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    """Return the current user's task chains, newest first."""
    chains, total = await chain_service.list_chains(
        db, current_user.id, offset=offset, limit=limit,
    )
    return ChainListResponse(chains=chains, total=total)


@router.get(
    "/chains/{chain_id}",
    response_model=ChainResponse,
    summary="Get chain details",
)
async def get_chain(
    chain_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Retrieve a chain and its steps."""
    return await _get_chain_or_404(db, chain_id, current_user.id)


@router.patch(
    "/chains/{chain_id}",
    response_model=ChainResponse,
    summary="Update chain metadata",
)
async def update_chain(
    chain_id: UUID,
    body: ChainUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Update a chain's name or description. Only allowed while in DRAFT status."""
    chain = await _get_chain_or_404(db, chain_id, current_user.id)
    try:
        chain = await chain_service.update_chain(db, chain, body)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    await db.commit()
    chain = await chain_service.get_chain(db, chain_id, current_user.id)
    return chain


@router.delete(
    "/chains/{chain_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a chain",
)
async def delete_chain(
    chain_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Delete a chain and all its steps."""
    chain = await _get_chain_or_404(db, chain_id, current_user.id)
    await chain_service.delete_chain(db, chain)
    await db.commit()
    logger.info("Chain %s deleted by user %s", chain_id, current_user.id)


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

@router.post(
    "/chains/{chain_id}/start",
    response_model=ChainResponse,
    summary="Start chain execution",
)
async def start_chain(
    chain_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Start (or resume) executing a task chain.

    Steps are executed sequentially; each step's output is piped into the
    next step's prompt via the ``{{previous_output}}`` placeholder.
    """
    chain = await _get_chain_or_404(db, chain_id, current_user.id)
    try:
        chain = await chain_service.start_chain(db, chain)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    await db.commit()
    chain = await chain_service.get_chain(db, chain_id, current_user.id)
    logger.info("Chain %s started by user %s", chain.id, current_user.id)
    return chain


@router.post(
    "/chains/{chain_id}/cancel",
    response_model=ChainResponse,
    summary="Cancel a running chain",
)
async def cancel_chain(
    chain_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Cancel a running or paused chain. Pending steps are marked as skipped."""
    chain = await _get_chain_or_404(db, chain_id, current_user.id)
    try:
        chain = await chain_service.cancel_chain(db, chain)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    await db.commit()
    chain = await chain_service.get_chain(db, chain_id, current_user.id)
    logger.info("Chain %s cancelled by user %s", chain.id, current_user.id)
    return chain


@router.post(
    "/chains/{chain_id}/retry",
    response_model=ChainResponse,
    summary="Retry a failed chain",
)
async def retry_chain(
    chain_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Retry a failed chain from the step that failed."""
    chain = await _get_chain_or_404(db, chain_id, current_user.id)
    if chain.status != ChainStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only FAILED chains can be retried",
        )
    try:
        chain = await chain_service.start_chain(db, chain)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    await db.commit()
    chain = await chain_service.get_chain(db, chain_id, current_user.id)
    logger.info("Chain %s retried by user %s", chain.id, current_user.id)
    return chain
