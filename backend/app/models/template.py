"""Template model for marketplace."""

from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Template(Base, TimestampMixin):
    """Template model for marketplace."""

    __tablename__ = "templates"

    # Primary fields
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Category and classification
    category: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )  # docs, sheets, slides, research
    tags: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Ownership
    author_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    team_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Template content
    prompt_template: Mapped[str] = mapped_column(Text, nullable=False)
    parameters: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )  # Input parameters schema
    example_inputs: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )  # Example inputs
    example_outputs: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )  # Example outputs

    # Publishing and visibility
    is_public: Mapped[bool] = mapped_column(default=False, index=True)
    is_official: Mapped[bool] = mapped_column(
        default=False, index=True
    )  # Official templates from platform
    is_featured: Mapped[bool] = mapped_column(
        default=False, index=True
    )  # Featured in marketplace

    # Usage and engagement metrics
    usage_count: Mapped[int] = mapped_column(default=0, index=True)
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    rating_count: Mapped[int] = mapped_column(default=0)

    # Versioning
    version: Mapped[str] = mapped_column(String(20), default="1.0.0")
    changelog: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parent_template_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("templates.id", ondelete="SET NULL"), nullable=True
    )  # For template forking

    # Composite indexes for common queries
    __table_args__ = (
        Index("ix_templates_category_public", "category", "is_public"),
        Index("ix_templates_author_public", "author_id", "is_public"),
        Index("ix_templates_usage_rating", "usage_count", "rating"),
        Index("ix_templates_featured_public", "is_featured", "is_public"),
    )

    def __repr__(self) -> str:
        return f"<Template(id={self.id}, name={self.name}, category={self.category})>"


class TemplateRating(Base, TimestampMixin):
    """Template rating and review."""

    __tablename__ = "template_ratings"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    template_id: Mapped[UUID] = mapped_column(
        ForeignKey("templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Rating
    rating: Mapped[int] = mapped_column(nullable=False)  # 1-5 stars
    review: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Helpfulness
    helpful_count: Mapped[int] = mapped_column(default=0)
    unhelpful_count: Mapped[int] = mapped_column(default=0)

    # Unique constraint: one rating per user per template
    __table_args__ = (
        Index("ix_template_ratings_unique", "template_id", "user_id", unique=True),
        Index("ix_template_ratings_template", "template_id", "rating"),
    )

    def __repr__(self) -> str:
        return f"<TemplateRating(template_id={self.template_id}, user_id={self.user_id}, rating={self.rating})>"
