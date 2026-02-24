"""
Marketplace Models — Template sharing, discovery, and installation
"""

from datetime import datetime, timezone
from typing import Optional, List
import uuid
from sqlalchemy import Column, String, Text, Integer, Float, Boolean, ForeignKey, DateTime, Enum as SQLEnum, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import enum

from app.core.database import Base


class TemplateCategory(str, enum.Enum):
    """Template categories for marketplace"""
    BUSINESS = "business"
    EDUCATION = "education"
    RESEARCH = "research"
    MARKETING = "marketing"
    PRODUCTIVITY = "productivity"
    DATA_ANALYSIS = "data_analysis"
    REPORTING = "reporting"
    OTHER = "other"


class MarketplaceTemplate(Base):
    """
    Public template in the marketplace
    """
    __tablename__ = "marketplace_templates"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Template metadata
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(SQLEnum(TemplateCategory), nullable=False, default=TemplateCategory.OTHER)
    tags = Column(JSONB, nullable=True)  # List of searchable tags
    
    # Template content
    template_data = Column(JSONB, nullable=False)  # The actual template structure
    prompt_template = Column(Text, nullable=True)  # Optional default prompt
    config = Column(JSONB, nullable=True)  # Additional configuration
    
    # Creator
    creator_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    creator_name = Column(String(200), nullable=True)  # Cached for display
    
    # Visibility and status
    is_public = Column(Boolean, default=True, nullable=False)
    is_featured = Column(Boolean, default=False, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)  # Official/verified templates
    is_archived = Column(Boolean, default=False, nullable=False)
    
    # Usage stats
    install_count = Column(Integer, default=0, nullable=False)
    view_count = Column(Integer, default=0, nullable=False)
    rating_avg = Column(Float, default=0.0, nullable=False)
    rating_count = Column(Integer, default=0, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    creator = relationship("User", back_populates="marketplace_templates")
    installs = relationship("TemplateInstall", back_populates="template", cascade="all, delete-orphan")
    ratings = relationship("TemplateRating", back_populates="template", cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index('idx_marketplace_category', 'category'),
        Index('idx_marketplace_is_public', 'is_public'),
        Index('idx_marketplace_featured', 'is_featured'),
        Index('idx_marketplace_rating', 'rating_avg'),
        Index('idx_marketplace_installs', 'install_count'),
    )
    
    def update_rating_stats(self):
        """Recalculate rating average and count"""
        if not self.ratings:
            self.rating_avg = 0.0
            self.rating_count = 0
        else:
            ratings = [r.rating for r in self.ratings if not r.is_deleted]
            self.rating_count = len(ratings)
            self.rating_avg = sum(ratings) / len(ratings) if ratings else 0.0


class TemplateInstall(Base):
    """
    Track template installations by users
    """
    __tablename__ = "template_installs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # References
    template_id = Column(UUID(as_uuid=True), ForeignKey("marketplace_templates.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Installation metadata
    workspace_id = Column(UUID(as_uuid=True), nullable=True)  # If user has workspaces
    installed_name = Column(String(200), nullable=True)  # Custom name given by user
    customizations = Column(JSONB, nullable=True)  # User customizations to the template
    
    # Usage tracking
    usage_count = Column(Integer, default=0, nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    is_favorited = Column(Boolean, default=False, nullable=False)
    
    # Timestamps
    installed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    template = relationship("MarketplaceTemplate", back_populates="installs")
    user = relationship("User", back_populates="template_installs")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('template_id', 'user_id', name='uq_template_user_install'),
        Index('idx_install_user', 'user_id'),
        Index('idx_install_template', 'template_id'),
    )


class TemplateRating(Base):
    """
    User ratings and reviews for marketplace templates
    """
    __tablename__ = "marketplace_template_ratings"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # References
    template_id = Column(UUID(as_uuid=True), ForeignKey("marketplace_templates.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Rating data
    rating = Column(Integer, nullable=False)  # 1-5 stars
    review = Column(Text, nullable=True)
    
    # Helpfulness tracking
    helpful_count = Column(Integer, default=0, nullable=False)
    
    # Status
    is_deleted = Column(Boolean, default=False, nullable=False)
    is_flagged = Column(Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    template = relationship("MarketplaceTemplate", back_populates="ratings")
    user = relationship("User", back_populates="template_ratings")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('template_id', 'user_id', name='uq_template_user_rating'),
        Index('idx_rating_template', 'template_id'),
        Index('idx_rating_user', 'user_id'),
    )
