"""Shared Prompt Library endpoints."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.prompt import SharedPrompt
from app.models.user import User
from app.schemas.prompt import SharedPromptCreate, SharedPromptList, SharedPromptResponse

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", response_model=SharedPromptList)
async def list_public_prompts(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    List all public prompts from the shared library.

    Results are ordered by use_count descending so the most popular prompts
    appear first, with created_at as a tie-breaker.

    Args:
        db: Database session
        current_user: Authenticated user (required to access the library)
        page: Page number (1-indexed)
        page_size: Items per page

    Returns:
        SharedPromptList: Paginated list of public prompts
    """
    base_query = select(SharedPrompt).where(SharedPrompt.is_public.is_(True))

    count_result = await db.execute(
        select(func.count()).select_from(base_query.subquery())
    )
    total = count_result.scalar_one()

    query = (
        base_query
        .order_by(SharedPrompt.use_count.desc(), SharedPrompt.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await db.execute(query)
    prompts = result.scalars().all()

    return SharedPromptList(
        prompts=prompts,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/", response_model=SharedPromptResponse, status_code=status.HTTP_201_CREATED)
async def create_prompt(
    prompt_data: SharedPromptCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Create a new prompt in the shared library.

    The prompt is owned by the authenticated user.  Set ``is_public=true``
    to make it visible to all users via the GET endpoint.

    Args:
        prompt_data: Prompt content and visibility settings
        current_user: Authenticated user (becomes the prompt owner)
        db: Database session

    Returns:
        SharedPromptResponse: The created prompt
    """
    prompt = SharedPrompt(
        user_id=current_user.id,
        title=prompt_data.title,
        content=prompt_data.content,
        is_public=prompt_data.is_public,
        use_count=0,
    )

    db.add(prompt)
    await db.commit()
    await db.refresh(prompt)

    logger.info(
        "Created shared prompt %s (user=%s, public=%s)",
        prompt.id,
        current_user.id,
        prompt.is_public,
    )
    return prompt
