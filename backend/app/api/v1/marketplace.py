"""
Marketplace API — Browse, install, and rate templates
"""

from datetime import datetime, timezone, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, desc, asc, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.models.marketplace import (
    MarketplaceTemplate,
    TemplateInstall,
    MarketplaceRating,
    TemplateCategory,
)
from app.schemas.marketplace import (
    TemplateCreate,
    TemplateUpdate,
    TemplateListItem,
    TemplateDetail,
    TemplateInstallCreate,
    TemplateInstallResponse,
    TemplateInstallUpdate,
    TemplateRatingCreate,
    TemplateRatingResponse,
    MarketplaceListParams,
    MarketplaceListResponse,
    TemplateStats,
    MarketplaceStats,
)

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


# ============================================================================
# Browse Templates
# ============================================================================

@router.get("/templates", response_model=MarketplaceListResponse)
async def list_marketplace_templates(
    category: Optional[TemplateCategory] = Query(None),
    search: Optional[str] = Query(None),
    featured_only: bool = Query(False),
    verified_only: bool = Query(False),
    sort_by: str = Query("popular", regex="^(popular|recent|rating|installs|name)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Browse marketplace templates with filtering and sorting
    
    - **category**: Filter by template category
    - **search**: Search in name, description, and tags
    - **featured_only**: Show only featured templates
    - **verified_only**: Show only verified templates
    - **sort_by**: popular, recent, rating, installs, or name
    - **page**: Page number (starts at 1)
    - **limit**: Results per page (max 100)
    """
    # Build query
    query = select(MarketplaceTemplate).where(
        MarketplaceTemplate.is_public == True,
        MarketplaceTemplate.is_archived == False,
    )
    
    # Apply filters
    if category:
        query = query.where(MarketplaceTemplate.category == category)
    
    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                MarketplaceTemplate.name.ilike(search_term),
                MarketplaceTemplate.description.ilike(search_term),
                MarketplaceTemplate.tags.cast(str).ilike(search_term),
            )
        )
    
    if featured_only:
        query = query.where(MarketplaceTemplate.is_featured == True)
    
    if verified_only:
        query = query.where(MarketplaceTemplate.is_verified == True)
    
    # Apply sorting
    if sort_by == "popular":
        query = query.order_by(desc(MarketplaceTemplate.view_count))
    elif sort_by == "recent":
        query = query.order_by(desc(MarketplaceTemplate.published_at))
    elif sort_by == "rating":
        query = query.order_by(desc(MarketplaceTemplate.rating_avg))
    elif sort_by == "installs":
        query = query.order_by(desc(MarketplaceTemplate.install_count))
    elif sort_by == "name":
        query = query.order_by(asc(MarketplaceTemplate.name))
    
    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    result = await db.execute(count_query)
    total = result.scalar() or 0
    
    # Paginate
    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)
    
    result = await db.execute(query)
    templates = result.scalars().all()
    
    total_pages = (total + limit - 1) // limit
    
    return MarketplaceListResponse(
        templates=[TemplateListItem.model_validate(t) for t in templates],
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


@router.get("/templates/{template_id}", response_model=TemplateDetail)
async def get_template_detail(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Get detailed information about a specific template
    """
    query = select(MarketplaceTemplate).where(
        MarketplaceTemplate.id == template_id,
        MarketplaceTemplate.is_public == True,
        MarketplaceTemplate.is_archived == False,
    )
    
    result = await db.execute(query)
    template = result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )
    
    # Increment view count
    template.view_count += 1
    await db.commit()
    
    return TemplateDetail.model_validate(template)


# ============================================================================
# Install Templates
# ============================================================================

@router.post("/templates/{template_id}/install", response_model=TemplateInstallResponse)
async def install_template(
    template_id: UUID,
    install_data: TemplateInstallCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Install a marketplace template to your workspace
    """
    # Check if template exists and is public
    query = select(MarketplaceTemplate).where(
        MarketplaceTemplate.id == template_id,
        MarketplaceTemplate.is_public == True,
        MarketplaceTemplate.is_archived == False,
    )
    
    result = await db.execute(query)
    template = result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found or not available",
        )
    
    # Check if already installed
    existing_query = select(TemplateInstall).where(
        TemplateInstall.template_id == template_id,
        TemplateInstall.user_id == current_user.id,
    )
    
    result = await db.execute(existing_query)
    existing_install = result.scalar_one_or_none()
    
    if existing_install:
        # Reactivate if it was deactivated
        if not existing_install.is_active:
            existing_install.is_active = True
            existing_install.updated_at = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(existing_install)
        
        return TemplateInstallResponse.model_validate(existing_install)
    
    # Create new installation
    install = TemplateInstall(
        template_id=template_id,
        user_id=current_user.id,
        installed_name=install_data.installed_name or template.name,
        customizations=install_data.customizations,
    )
    
    db.add(install)
    
    # Increment install count
    template.install_count += 1
    
    await db.commit()
    await db.refresh(install)
    
    return TemplateInstallResponse.model_validate(install)


@router.get("/my-templates", response_model=List[TemplateInstallResponse])
async def list_my_installed_templates(
    active_only: bool = Query(True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all templates installed by the current user
    """
    query = select(TemplateInstall).where(
        TemplateInstall.user_id == current_user.id
    )
    
    if active_only:
        query = query.where(TemplateInstall.is_active == True)
    
    query = query.order_by(desc(TemplateInstall.last_used_at), desc(TemplateInstall.installed_at))
    
    result = await db.execute(query)
    installs = result.scalars().all()
    
    return [TemplateInstallResponse.model_validate(i) for i in installs]


@router.patch("/my-templates/{install_id}", response_model=TemplateInstallResponse)
async def update_installed_template(
    install_id: UUID,
    update_data: TemplateInstallUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update an installed template (rename, customize, deactivate)
    """
    query = select(TemplateInstall).where(
        TemplateInstall.id == install_id,
        TemplateInstall.user_id == current_user.id,
    )
    
    result = await db.execute(query)
    install = result.scalar_one_or_none()
    
    if not install:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Installation not found",
        )
    
    # Update fields
    if update_data.installed_name is not None:
        install.installed_name = update_data.installed_name
    if update_data.customizations is not None:
        install.customizations = update_data.customizations
    if update_data.is_active is not None:
        install.is_active = update_data.is_active
    if update_data.is_favorited is not None:
        install.is_favorited = update_data.is_favorited
    
    install.updated_at = datetime.now(timezone.utc)
    
    await db.commit()
    await db.refresh(install)
    
    return TemplateInstallResponse.model_validate(install)


# ============================================================================
# Rate Templates
# ============================================================================

@router.post("/templates/{template_id}/rate", response_model=TemplateRatingResponse)
async def rate_template(
    template_id: UUID,
    rating_data: TemplateRatingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Rate a template (1-5 stars) and optionally leave a review
    """
    # Check if template exists
    query = select(MarketplaceTemplate).where(
        MarketplaceTemplate.id == template_id,
        MarketplaceTemplate.is_public == True,
    )
    
    result = await db.execute(query)
    template = result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )
    
    # Check for existing rating
    existing_query = select(MarketplaceRating).where(
        MarketplaceRating.template_id == template_id,
        MarketplaceRating.user_id == current_user.id,
    )
    
    result = await db.execute(existing_query)
    existing_rating = result.scalar_one_or_none()
    
    if existing_rating:
        # Update existing rating
        existing_rating.rating = rating_data.rating
        existing_rating.review = rating_data.review
        existing_rating.updated_at = datetime.now(timezone.utc)
        rating = existing_rating
    else:
        # Create new rating
        rating = MarketplaceRating(
            template_id=template_id,
            user_id=current_user.id,
            rating=rating_data.rating,
            review=rating_data.review,
        )
        db.add(rating)
    
    await db.commit()
    
    # Update template rating stats
    template.update_rating_stats()
    await db.commit()
    await db.refresh(rating)
    
    return TemplateRatingResponse.model_validate(rating)


@router.get("/templates/{template_id}/ratings", response_model=List[TemplateRatingResponse])
async def list_template_ratings(
    template_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    List ratings and reviews for a template
    """
    query = (
        select(MarketplaceRating)
        .where(
            MarketplaceRating.template_id == template_id,
            MarketplaceRating.is_deleted == False,
        )
        .order_by(desc(MarketplaceRating.helpful_count), desc(MarketplaceRating.created_at))
        .limit(limit)
    )
    
    result = await db.execute(query)
    ratings = result.scalars().all()
    
    return [TemplateRatingResponse.model_validate(r) for r in ratings]


# ============================================================================
# Publishing (Creator Features)
# ============================================================================

@router.post("/templates", response_model=TemplateDetail)
async def publish_template(
    template_data: TemplateCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Publish a new template to the marketplace
    """
    template = MarketplaceTemplate(
        name=template_data.name,
        description=template_data.description,
        category=template_data.category,
        tags=template_data.tags,
        template_data=template_data.template_data,
        prompt_template=template_data.prompt_template,
        config=template_data.config,
        creator_id=current_user.id,
        creator_name=current_user.full_name,
        is_public=template_data.is_public,
        published_at=datetime.now(timezone.utc) if template_data.is_public else None,
    )
    
    db.add(template)
    await db.commit()
    await db.refresh(template)
    
    return TemplateDetail.model_validate(template)


@router.get("/my-published-templates", response_model=List[TemplateListItem])
async def list_my_published_templates(
    include_archived: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List templates published by the current user
    """
    query = select(MarketplaceTemplate).where(
        MarketplaceTemplate.creator_id == current_user.id
    )
    
    if not include_archived:
        query = query.where(MarketplaceTemplate.is_archived == False)
    
    query = query.order_by(desc(MarketplaceTemplate.created_at))
    
    result = await db.execute(query)
    templates = result.scalars().all()
    
    return [TemplateListItem.model_validate(t) for t in templates]


@router.patch("/my-templates/{template_id}", response_model=TemplateDetail)
async def update_my_template(
    template_id: UUID,
    update_data: TemplateUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update a template you've published
    """
    query = select(MarketplaceTemplate).where(
        MarketplaceTemplate.id == template_id,
        MarketplaceTemplate.creator_id == current_user.id,
    )
    
    result = await db.execute(query)
    template = result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found or you don't have permission",
        )
    
    # Update fields
    update_dict = update_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(template, field, value)
    
    template.updated_at = datetime.now(timezone.utc)
    
    # Update published_at if making public for the first time
    if update_data.is_public and not template.published_at:
        template.published_at = datetime.now(timezone.utc)
    
    await db.commit()
    await db.refresh(template)
    
    return TemplateDetail.model_validate(template)


# ============================================================================
# Statistics
# ============================================================================

@router.get("/stats", response_model=MarketplaceStats)
async def get_marketplace_stats(
    db: AsyncSession = Depends(get_db),
):
    """
    Get overall marketplace statistics
    """
    # Count totals
    total_templates_result = await db.execute(
        select(func.count()).select_from(MarketplaceTemplate).where(
            MarketplaceTemplate.is_public == True,
            MarketplaceTemplate.is_archived == False,
        )
    )
    total_templates = total_templates_result.scalar() or 0
    
    total_installs_result = await db.execute(
        select(func.sum(MarketplaceTemplate.install_count)).where(
            MarketplaceTemplate.is_public == True
        )
    )
    total_installs = total_installs_result.scalar() or 0
    
    total_ratings_result = await db.execute(
        select(func.count()).select_from(TemplateRating).where(
            MarketplaceRating.is_deleted == False
        )
    )
    total_ratings = total_ratings_result.scalar() or 0
    
    featured_count_result = await db.execute(
        select(func.count()).select_from(MarketplaceTemplate).where(
            MarketplaceTemplate.is_featured == True,
            MarketplaceTemplate.is_public == True,
        )
    )
    featured_count = featured_count_result.scalar() or 0
    
    verified_count_result = await db.execute(
        select(func.count()).select_from(MarketplaceTemplate).where(
            MarketplaceTemplate.is_verified == True,
            MarketplaceTemplate.is_public == True,
        )
    )
    verified_count = verified_count_result.scalar() or 0
    
    # Category counts
    category_counts_result = await db.execute(
        select(
            MarketplaceTemplate.category,
            func.count(MarketplaceTemplate.id)
        )
        .where(
            MarketplaceTemplate.is_public == True,
            MarketplaceTemplate.is_archived == False,
        )
        .group_by(MarketplaceTemplate.category)
    )
    categories_count = {cat.value: count for cat, count in category_counts_result.all()}
    
    # Top templates
    top_query = (
        select(MarketplaceTemplate)
        .where(
            MarketplaceTemplate.is_public == True,
            MarketplaceTemplate.is_archived == False,
        )
        .order_by(desc(MarketplaceTemplate.install_count))
        .limit(10)
    )
    result = await db.execute(top_query)
    top_templates = result.scalars().all()
    
    return MarketplaceStats(
        total_templates=total_templates,
        total_installs=total_installs,
        total_ratings=total_ratings,
        featured_count=featured_count,
        verified_count=verified_count,
        categories_count=categories_count,
        top_templates=[TemplateListItem.model_validate(t) for t in top_templates],
    )
