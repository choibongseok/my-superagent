"""Schemas for template marketplace."""

from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# Template Base Schemas

class TemplateBase(BaseModel):
    """Base template schema."""

    name: str = Field(..., description="Template name", max_length=255)
    description: Optional[str] = Field(None, description="Template description")
    category: str = Field(..., description="Template category")
    tags: Optional[List[str]] = Field(default=None, description="Template tags")
    prompt_template: str = Field(..., description="Prompt template with variables")
    parameters: Optional[Dict[str, Any]] = Field(
        default=None, description="Input parameter schema"
    )
    example_inputs: Optional[Dict[str, Any]] = Field(
        default=None, description="Example inputs"
    )
    example_outputs: Optional[Dict[str, Any]] = Field(
        default=None, description="Example outputs"
    )


class TemplateCreate(TemplateBase):
    """Schema for creating template."""

    team_id: Optional[UUID] = Field(default=None, description="Team ID")
    is_public: bool = Field(default=False, description="Public visibility")


class TemplateUpdate(BaseModel):
    """Schema for updating template."""

    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    prompt_template: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    example_inputs: Optional[Dict[str, Any]] = None
    example_outputs: Optional[Dict[str, Any]] = None
    is_public: Optional[bool] = None
    changelog: Optional[str] = None


class TemplateResponse(TemplateBase):
    """Schema for template response."""

    id: UUID
    author_id: UUID
    team_id: Optional[UUID] = None
    is_public: bool
    is_official: bool
    is_featured: bool
    usage_count: int
    rating: float
    rating_count: int
    version: str
    changelog: Optional[str] = None
    parent_template_id: Optional[UUID] = None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class TemplateListItem(BaseModel):
    """Schema for template list item (minimal info)."""

    id: UUID
    name: str
    description: Optional[str] = None
    category: str
    tags: Optional[List[str]] = None
    author_id: UUID
    is_official: bool
    is_featured: bool
    usage_count: int
    rating: float
    rating_count: int
    created_at: str

    model_config = {"from_attributes": True}


class TemplateSearchRequest(BaseModel):
    """Schema for template search request."""

    query: Optional[str] = Field(None, description="Search query")
    category: Optional[str] = Field(None, description="Filter by category")
    tags: Optional[List[str]] = Field(None, description="Filter by tags")
    author_id: Optional[UUID] = Field(None, description="Filter by author")
    is_official: Optional[bool] = Field(None, description="Filter official templates")
    is_featured: Optional[bool] = Field(None, description="Filter featured templates")
    min_rating: Optional[float] = Field(None, ge=0.0, le=5.0)
    sort_by: Optional[str] = Field(
        "usage_count", description="Sort by: usage_count, rating, created_at"
    )
    sort_order: Optional[str] = Field("desc", description="Sort order: asc, desc")
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)


class TemplateSearchResponse(BaseModel):
    """Schema for template search response."""

    total: int
    templates: List[TemplateListItem]
    limit: int
    offset: int


class TemplateUseRequest(BaseModel):
    """Schema for using template."""

    inputs: Dict[str, Any] = Field(..., description="Template input values")
    output_type: Optional[str] = Field(None, description="Desired output type")


class TemplateUseResponse(BaseModel):
    """Schema for template use response."""

    template_id: UUID
    task_id: UUID
    prompt: str


# Template Rating Schemas

class TemplateRatingCreate(BaseModel):
    """Schema for creating template rating."""

    rating: int = Field(..., ge=1, le=5, description="Rating (1-5 stars)")
    review: Optional[str] = Field(None, description="Review text")


class TemplateRatingUpdate(BaseModel):
    """Schema for updating template rating."""

    rating: Optional[int] = Field(None, ge=1, le=5)
    review: Optional[str] = None


class TemplateRatingResponse(BaseModel):
    """Schema for template rating response."""

    id: UUID
    template_id: UUID
    user_id: UUID
    rating: int
    review: Optional[str] = None
    helpful_count: int
    unhelpful_count: int
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class TemplateRatingHelpfulRequest(BaseModel):
    """Schema for marking rating as helpful/unhelpful."""

    helpful: bool = Field(..., description="True for helpful, False for unhelpful")


# Template Statistics

class TemplateStatistics(BaseModel):
    """Schema for template statistics."""

    total_templates: int
    total_usage: int
    total_ratings: int
    average_rating: float
    by_category: Dict[str, int]
    top_templates: List[TemplateListItem]
