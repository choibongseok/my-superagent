"""API endpoints for template marketplace."""

import logging
import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
from app.agents.celery_app import (
    process_docs_task,
    process_research_task,
    process_sheets_task,
    process_slides_task,
)
from app.models.task import Task as TaskModel
from app.models.task import TaskStatus
from app.services.template_service import TemplateService

router = APIRouter()
logger = logging.getLogger(__name__)

OUTPUT_TYPE_NORMALIZER = re.compile(r"[^a-z0-9]+")

CATEGORY_TO_TASK_TYPE = {
    "research": "research",
    "analysis": "research",
    "document": "docs",
    "documents": "docs",
    "doc": "docs",
    "docs": "docs",
    "google doc": "docs",
    "google docs": "docs",
    "gdoc": "docs",
    "gdocs": "docs",
    "spreadsheet": "sheets",
    "spreadsheets": "sheets",
    "sheet": "sheets",
    "sheets": "sheets",
    "google sheet": "sheets",
    "google sheets": "sheets",
    "gsheet": "sheets",
    "gsheets": "sheets",
    "presentation": "slides",
    "presentations": "slides",
    "slide": "slides",
    "slides": "slides",
    "deck": "slides",
    "slide deck": "slides",
    "google slide": "slides",
    "google slides": "slides",
    "gslide": "slides",
    "gslides": "slides",
}

TASK_TITLE_DEFAULTS = {
    "docs": "Template Document",
    "sheets": "Template Spreadsheet",
    "slides": "Template Presentation",
}

TASK_TITLE_INPUT_KEYS = {
    "docs": (
        "title",
        "name",
        "document_title",
        "doc_title",
        "document.title",
        "document.name",
    ),
    "sheets": (
        "title",
        "name",
        "spreadsheet_title",
        "sheet_title",
        "spreadsheet.title",
        "spreadsheet.name",
    ),
    "slides": (
        "title",
        "name",
        "presentation_title",
        "slide_title",
        "deck_title",
        "presentation.title",
        "presentation.name",
        "deck.title",
    ),
}


def _normalize_output_type(output_type: str) -> str:
    """Normalize category-like strings for resilient task-type mapping."""
    normalized_output_type = OUTPUT_TYPE_NORMALIZER.sub(
        " ",
        output_type.strip().lower(),
    ).strip()
    return normalized_output_type


def _resolve_input_value(inputs: dict, key_path: str):
    """Resolve dotted input keys (e.g., ``document.title``) from payloads."""
    current_value = inputs
    for key in key_path.split("."):
        if not isinstance(current_value, dict):
            return None
        current_value = current_value.get(key)

    return current_value


def _resolve_task_type(output_type: str | None) -> str:
    """Resolve template output type to internal task type."""
    if not isinstance(output_type, str):
        return "research"

    normalized_output_type = _normalize_output_type(output_type)
    if not normalized_output_type:
        return "research"

    return CATEGORY_TO_TASK_TYPE.get(normalized_output_type, "research")


def _resolve_task_title(task_type: str, inputs: dict) -> str:
    """Resolve task title from inputs with sensible per-type fallbacks."""
    fallback_title = TASK_TITLE_DEFAULTS.get(task_type)
    if fallback_title is None:
        raise ValueError(f"No default title configured for task type: {task_type}")

    for key in TASK_TITLE_INPUT_KEYS.get(task_type, ("title",)):
        value = _resolve_input_value(inputs, key)
        if isinstance(value, str):
            normalized_value = value.strip()
            if normalized_value:
                return normalized_value

    return fallback_title


def _to_iso(value):
    """Normalize optional datetime values for API schema compatibility."""
    if value is None:
        return None

    if isinstance(value, str):
        return value

    return value.isoformat()


def _template_response_from_model(template) -> TemplateResponse:
    """Build `TemplateResponse` from a SQLAlchemy template model."""
    payload = dict(getattr(template, "__dict__", {}))
    payload["created_at"] = _to_iso(payload.get("created_at"))
    payload["updated_at"] = _to_iso(payload.get("updated_at"))
    payload.pop("_sa_instance_state", None)
    return TemplateResponse.model_validate(payload)


def _template_list_item_from_model(template) -> TemplateListItem:
    """Build `TemplateListItem` from a SQLAlchemy template model."""
    payload = dict(getattr(template, "__dict__", {}))
    payload["created_at"] = _to_iso(payload.get("created_at"))
    payload.pop("_sa_instance_state", None)
    return TemplateListItem.model_validate(payload)


def _template_rating_response_from_model(rating) -> TemplateRatingResponse:
    """Build `TemplateRatingResponse` from a SQLAlchemy rating model."""
    payload = dict(getattr(rating, "__dict__", {}))
    payload["created_at"] = _to_iso(payload.get("created_at"))
    payload["updated_at"] = _to_iso(payload.get("updated_at"))
    payload.pop("_sa_instance_state", None)
    return TemplateRatingResponse.model_validate(payload)


def _build_task_kwargs(
    *,
    user_id,
    prompt: str,
    task_type: str,
    template_id: UUID,
    inputs: dict,
) -> dict:
    """Build Task model kwargs with metadata field compatibility."""
    metadata_payload = {
        "template_id": str(template_id),
        "inputs": inputs,
    }

    task_kwargs = {
        "user_id": user_id,
        "prompt": prompt,
        "task_type": task_type,
        "status": TaskStatus.PENDING,
    }

    # SQLAlchemy model uses task_metadata, but keep metadata fallback for mocks/tests.
    task_model_dict = getattr(TaskModel, "__dict__", {})
    metadata_field = (
        "task_metadata" if "task_metadata" in task_model_dict else "metadata"
    )
    task_kwargs[metadata_field] = metadata_payload

    return task_kwargs


def _queue_task(
    *, task_type: str, task_id: str, prompt: str, user_id: str, inputs: dict
):
    """Queue a Celery task based on normalized task type."""
    if task_type == "research":
        return process_research_task.apply_async(args=[task_id, prompt, user_id])

    if task_type == "docs":
        return process_docs_task.apply_async(
            args=[
                task_id,
                prompt,
                user_id,
                _resolve_task_title("docs", inputs),
            ]
        )

    if task_type == "sheets":
        return process_sheets_task.apply_async(
            args=[
                task_id,
                prompt,
                user_id,
                _resolve_task_title("sheets", inputs),
            ]
        )

    if task_type == "slides":
        return process_slides_task.apply_async(
            args=[
                task_id,
                prompt,
                user_id,
                _resolve_task_title("slides", inputs),
            ]
        )

    raise ValueError(f"Unknown task type: {task_type}")


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

        return _template_response_from_model(template)

    except Exception as e:
        logger.error(f"Template creation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Template creation failed: {str(e)}",
        )


@router.get("/marketplace", response_model=TemplateSearchResponse)
async def get_template_marketplace(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    query: str | None = Query(default=None, description="Search templates by keyword"),
    category: str | None = Query(default=None, description="Filter by category"),
    featured: bool | None = Query(
        default=None,
        description="Filter featured templates only when true",
    ),
    official: bool | None = Query(
        default=None,
        description="Filter official templates only when true",
    ),
    min_rating: float | None = Query(
        default=None,
        ge=0.0,
        le=5.0,
        description="Minimum rating threshold",
    ),
    sort_by: str = Query(
        default="usage_count",
        description="Sort by: usage_count, rating, created_at",
    ),
    sort_order: str = Query(
        default="desc",
        description="Sort order: asc or desc",
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Items per page",
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Pagination offset",
    ),
):
    """Discover public templates from the marketplace."""
    valid_sort_fields = {"usage_count", "rating", "created_at"}
    if sort_by not in valid_sort_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid sort_by value",
        )

    if sort_order.lower() not in {"asc", "desc"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="sort_order must be asc or desc",
        )

    service = TemplateService(db)
    search_request = TemplateSearchRequest(
        query=query,
        category=category,
        is_official=official,
        is_featured=featured,
        min_rating=min_rating,
        sort_by=sort_by,
        sort_order=sort_order.lower(),
        limit=limit,
        offset=offset,
    )

    # Marketplace intentionally exposes only public templates.
    templates, total = await service.search_templates(search_request, user_id=None)

    return TemplateSearchResponse(
        total=total,
        templates=[_template_list_item_from_model(t) for t in templates],
        limit=limit,
        offset=offset,
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

    return _template_response_from_model(template)


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
    template = await service.update_template(
        template_id, template_data, current_user.id
    )

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found or access denied",
        )

    return _template_response_from_model(template)


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
            templates=[_template_list_item_from_model(t) for t in templates],
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
            template_id,
            use_request.inputs,
            current_user.id,
            use_request.output_type,
        )

        task_type = _resolve_task_type(result.get("output_type"))

        # Create task in database
        task = TaskModel(
            **_build_task_kwargs(
                user_id=current_user.id,
                prompt=result["prompt"],
                task_type=task_type,
                template_id=template_id,
                inputs=use_request.inputs,
            )
        )

        db.add(task)
        await db.commit()
        await db.refresh(task)

        # Queue task to Celery
        try:
            task_id_str = str(task.id)
            user_id_str = str(current_user.id)

            celery_task = _queue_task(
                task_type=task_type,
                task_id=task_id_str,
                prompt=result["prompt"],
                user_id=user_id_str,
                inputs=use_request.inputs,
            )

            # Store Celery task ID and update status
            task.celery_task_id = celery_task.id
            task.status = TaskStatus.PROCESSING
            await db.commit()
            await db.refresh(task)

            logger.info(f"Created task {task.id} from template {template_id}")

        except Exception as celery_error:
            # If Celery queuing fails, mark task as failed
            task.status = TaskStatus.FAILED
            task.error_message = f"Failed to queue task: {str(celery_error)}"
            await db.commit()
            logger.error(f"Failed to queue task from template: {celery_error}")

        return TemplateUseResponse(
            template_id=UUID(result["template_id"]),
            task_id=task.id,
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
    templates, total = await service.get_user_templates(current_user.id, limit, offset)

    return TemplateSearchResponse(
        total=total,
        templates=[_template_list_item_from_model(t) for t in templates],
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
        rating = await service.create_rating(template_id, current_user.id, rating_data)

        return _template_rating_response_from_model(rating)

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

    return [_template_rating_response_from_model(r) for r in ratings]
