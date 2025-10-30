"""API endpoints for template marketplace."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.template import (
    TemplateCreate,
    TemplateListItem,
    TemplateRatingCreate,
    TemplateRatingResponse,
    TemplateResponse,
    TemplateSearchRequest,
    TemplateSearchResponse,
    TemplateUpdate,
    TemplateUseRequest,
    TemplateUseResponse,
)
from app.services.template_service import TemplateService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    template_data: TemplateCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Create new template.

    Args:
        template_data: Template creation data
        current_user: Authenticated user
        db: Database session

    Returns:
        Created template
    """
    try:
        service = TemplateService(db)
        template = await service.create_template(template_data, current_user.id)

        return TemplateResponse.model_validate(template)

    except Exception as e:
        logger.error(f"Template creation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Template creation failed: {str(e)}",
        )


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get template by ID.

    Args:
        template_id: Template ID
        current_user: Authenticated user
        db: Database session

    Returns:
        Template details
    """
    service = TemplateService(db)
    template = await service.get_template(template_id)

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    # Check access (public or owner)
    if not template.is_public and template.author_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to private template",
        )

    return TemplateResponse.model_validate(template)


@router.put("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: UUID,
    template_data: TemplateUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Update template.

    Args:
        template_id: Template ID
        template_data: Update data
        current_user: Authenticated user
        db: Database session

    Returns:
        Updated template
    """
    service = TemplateService(db)
    template = await service.update_template(template_id, template_data, current_user.id)

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found or access denied",
        )

    return TemplateResponse.model_validate(template)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Delete template.

    Args:
        template_id: Template ID
        current_user: Authenticated user
        db: Database session
    """
    service = TemplateService(db)
    success = await service.delete_template(template_id, current_user.id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found or access denied",
        )


@router.post("/search", response_model=TemplateSearchResponse)
async def search_templates(
    search_request: TemplateSearchRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Search templates with filters.

    Args:
        search_request: Search parameters
        current_user: Authenticated user
        db: Database session

    Returns:
        Search results with pagination
    """
    try:
        service = TemplateService(db)
        templates, total = await service.search_templates(
            search_request, current_user.id
        )

        return TemplateSearchResponse(
            total=total,
            templates=[TemplateListItem.model_validate(t) for t in templates],
            limit=search_request.limit,
            offset=search_request.offset,
        )

    except Exception as e:
        logger.error(f"Template search failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Template search failed: {str(e)}",
        )


@router.post("/{template_id}/use", response_model=TemplateUseResponse)
async def use_template(
    template_id: UUID,
    use_request: TemplateUseRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Use template to generate prompt.

    This endpoint:
    1. Validates template access
    2. Substitutes input values into template
    3. Increments usage count
    4. Returns generated prompt

    Args:
        template_id: Template ID
        use_request: Template inputs
        current_user: Authenticated user
        db: Database session

    Returns:
        Generated prompt and task info
    """
    try:
        service = TemplateService(db)
        result = await service.use_template(
            template_id, use_request.inputs, current_user.id
        )

        # TODO: Create task with generated prompt (Phase 1 integration)
        task_id = UUID("00000000-0000-0000-0000-000000000000")  # Placeholder

        return TemplateUseResponse(
            template_id=UUID(result["template_id"]),
            task_id=task_id,
            prompt=result["prompt"],
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Template use failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Template use failed: {str(e)}",
        )


@router.get("/user/my-templates", response_model=TemplateSearchResponse)
async def get_my_templates(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 20,
    offset: int = 0,
):
    """
    Get current user's templates.

    Args:
        current_user: Authenticated user
        db: Database session
        limit: Page limit
        offset: Page offset

    Returns:
        User's templates with pagination
    """
    service = TemplateService(db)
    templates, total = await service.get_user_templates(
        current_user.id, limit, offset
    )

    return TemplateSearchResponse(
        total=total,
        templates=[TemplateListItem.model_validate(t) for t in templates],
        limit=limit,
        offset=offset,
    )


# Rating endpoints

@router.post("/{template_id}/ratings", response_model=TemplateRatingResponse)
async def create_rating(
    template_id: UUID,
    rating_data: TemplateRatingCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Create or update rating for template.

    Args:
        template_id: Template ID
        rating_data: Rating data
        current_user: Authenticated user
        db: Database session

    Returns:
        Created/updated rating
    """
    try:
        service = TemplateService(db)
        rating = await service.create_rating(
            template_id, current_user.id, rating_data
        )

        return TemplateRatingResponse.model_validate(rating)

    except Exception as e:
        logger.error(f"Rating creation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Rating creation failed: {str(e)}",
        )


@router.get("/{template_id}/ratings", response_model=list[TemplateRatingResponse])
async def get_template_ratings(
    template_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 20,
    offset: int = 0,
):
    """
    Get ratings for template.

    Args:
        template_id: Template ID
        current_user: Authenticated user
        db: Database session
        limit: Page limit
        offset: Page offset

    Returns:
        Template ratings
    """
    service = TemplateService(db)
    ratings, total = await service.get_template_ratings(template_id, limit, offset)

    return [TemplateRatingResponse.model_validate(r) for r in ratings]
