"""
Marketplace Schemas — Request/Response models for template marketplace
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict

from app.models.marketplace import TemplateCategory


# ============================================================================
# Template Schemas
# ============================================================================

class TemplateBase(BaseModel):
    """Base template schema"""
    name: str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    category: TemplateCategory
    tags: Optional[List[str]] = Field(None, max_length=10)
    template_data: Dict[str, Any]
    prompt_template: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


class TemplateCreate(TemplateBase):
    """Schema for creating a new marketplace template"""
    is_public: bool = True


class TemplateUpdate(BaseModel):
    """Schema for updating a template"""
    name: Optional[str] = Field(None, min_length=3, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    category: Optional[TemplateCategory] = None
    tags: Optional[List[str]] = None
    template_data: Optional[Dict[str, Any]] = None
    prompt_template: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    is_public: Optional[bool] = None
    is_archived: Optional[bool] = None


class TemplateListItem(BaseModel):
    """Minimal template info for list views"""
    id: UUID
    name: str
    description: Optional[str]
    category: TemplateCategory
    tags: Optional[List[str]]
    creator_id: UUID
    creator_name: Optional[str]
    is_featured: bool
    is_verified: bool
    install_count: int
    rating_avg: float
    rating_count: int
    created_at: datetime
    published_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class TemplateDetail(TemplateListItem):
    """Full template details"""
    template_data: Dict[str, Any]
    prompt_template: Optional[str]
    config: Optional[Dict[str, Any]]
    view_count: int
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Installation Schemas
# ============================================================================

class TemplateInstallCreate(BaseModel):
    """Schema for installing a template"""
    installed_name: Optional[str] = Field(None, max_length=200)
    customizations: Optional[Dict[str, Any]] = None


class TemplateInstallResponse(BaseModel):
    """Response after installing a template"""
    id: UUID
    template_id: UUID
    user_id: UUID
    installed_name: Optional[str]
    customizations: Optional[Dict[str, Any]]
    usage_count: int
    is_active: bool
    is_favorited: bool
    installed_at: datetime
    last_used_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class TemplateInstallUpdate(BaseModel):
    """Schema for updating an installation"""
    installed_name: Optional[str] = None
    customizations: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    is_favorited: Optional[bool] = None


# ============================================================================
# Rating Schemas
# ============================================================================

class TemplateRatingCreate(BaseModel):
    """Schema for creating/updating a rating"""
    rating: int = Field(..., ge=1, le=5, description="Rating from 1-5 stars")
    review: Optional[str] = Field(None, max_length=2000)


class TemplateRatingResponse(BaseModel):
    """Response for a template rating"""
    id: UUID
    template_id: UUID
    user_id: UUID
    rating: int
    review: Optional[str]
    helpful_count: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Marketplace List/Search Schemas
# ============================================================================

class MarketplaceListParams(BaseModel):
    """Query parameters for marketplace listing"""
    category: Optional[TemplateCategory] = None
    search: Optional[str] = None
    tags: Optional[List[str]] = None
    featured_only: bool = False
    verified_only: bool = False
    sort_by: str = Field("popular", pattern="^(popular|recent|rating|installs|name)$")
    page: int = Field(1, ge=1)
    limit: int = Field(20, ge=1, le=100)


class MarketplaceListResponse(BaseModel):
    """Paginated marketplace listing"""
    templates: List[TemplateListItem]
    total: int
    page: int
    limit: int
    total_pages: int


# ============================================================================
# Statistics Schemas
# ============================================================================

class TemplateStats(BaseModel):
    """Statistics for a template"""
    template_id: UUID
    install_count: int
    view_count: int
    rating_avg: float
    rating_count: int
    active_users: int  # Users who used it in last 30 days


class MarketplaceStats(BaseModel):
    """Overall marketplace statistics"""
    total_templates: int
    total_installs: int
    total_ratings: int
    featured_count: int
    verified_count: int
    categories_count: Dict[str, int]
    top_templates: List[TemplateListItem]
