"""Rate limit override model for admin-controlled custom quotas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from app.models.base import Base


class RateLimitOverride(Base):
    """
    Admin-controlled rate limit overrides for specific users.
    
    Allows administrators to grant temporary or permanent custom rate limits
    to VIP users, testing accounts, or users with special needs.
    """
    
    __tablename__ = "rate_limit_overrides"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    endpoint_pattern = Column(
        String(255), 
        nullable=False,
        comment="Endpoint pattern to match, e.g., '/api/v1/tasks/*' or '*' for all"
    )
    custom_limit = Column(
        Integer, 
        nullable=False,
        comment="Custom rate limit in requests per minute"
    )
    expires_at = Column(
        DateTime,
        nullable=True,
        comment="Optional expiration time for temporary overrides"
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        comment="Admin user who created this override"
    )
    reason = Column(
        String(500),
        nullable=True,
        comment="Optional reason for the override"
    )
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="rate_limit_overrides")
    creator = relationship("User", foreign_keys=[created_by])
    
    # Indexes for performance
    __table_args__ = (
        Index("ix_rate_limit_override_user_endpoint", "user_id", "endpoint_pattern"),
        Index("ix_rate_limit_override_expires_at", "expires_at"),
    )
    
    def __repr__(self) -> str:
        return (
            f"<RateLimitOverride(user_id={self.user_id}, "
            f"endpoint={self.endpoint_pattern}, limit={self.custom_limit})>"
        )
    
    def is_active(self) -> bool:
        """Check if this override is currently active (not expired)."""
        if self.expires_at is None:
            return True
        return datetime.utcnow() < self.expires_at
    
    def matches_endpoint(self, endpoint: str) -> bool:
        """
        Check if this override applies to the given endpoint.
        
        Supports wildcard patterns:
        - '*' matches all endpoints
        - '/api/v1/tasks/*' matches all task endpoints
        - '/api/v1/tasks/create' matches exact endpoint
        """
        if self.endpoint_pattern == "*":
            return True
        
        if self.endpoint_pattern.endswith("/*"):
            prefix = self.endpoint_pattern[:-2]
            return endpoint.startswith(prefix)
        
        return self.endpoint_pattern == endpoint
