"""Token usage tracking model."""
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.models.base import Base


class TokenUsage(Base):
    """Track LLM token usage and costs per task."""
    
    __tablename__ = "token_usage"
    
    id = Column(String, primary_key=True)
    task_id = Column(String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Model information
    model = Column(String, nullable=False, index=True)  # e.g., "claude-3-5-sonnet-20241022"
    provider = Column(String, nullable=False)  # e.g., "anthropic", "openai"
    
    # Token counts
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    
    # Cost in USD
    cost_usd = Column(Float, nullable=False, default=0.0)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    # Relationships
    task = relationship("Task", back_populates="token_usages")
    user = relationship("User", back_populates="token_usages")
    
    # Indexes for analytics queries
    __table_args__ = (
        Index("ix_token_usage_user_created", "user_id", "created_at"),
        Index("ix_token_usage_model_created", "model", "created_at"),
        Index("ix_token_usage_task_created", "task_id", "created_at"),
    )
    
    def __repr__(self):
        return (
            f"<TokenUsage(id={self.id}, task_id={self.task_id}, model={self.model}, "
            f"total_tokens={self.total_tokens}, cost_usd={self.cost_usd:.4f})>"
        )
