"""
Recovery Suggestion Model - AI-powered failure recovery recommendations
"""
from datetime import datetime, UTC
from sqlalchemy import Column, String, Integer, Text, JSON, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base
import uuid
import enum


class RecoverySuggestionType(str, enum.Enum):
    """Types of recovery actions available"""
    RETRY = "retry"
    FIX_PERMISSIONS = "fix_permissions"
    SIMPLIFY_PROMPT = "simplify_prompt"
    CHANGE_TEMPLATE = "change_template"
    MANUAL_INTERVENTION = "manual_intervention"
    CONTACT_SUPPORT = "contact_support"


class RecoverySuggestion(Base):
    """
    AI-generated suggestions for recovering from task failures.
    
    After a task fails, this model stores 1-3 actionable recovery options
    that the user can execute with a single click.
    """
    __tablename__ = "recovery_suggestions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Related task
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    
    # Suggestion details
    suggestion_type = Column(SQLEnum(RecoverySuggestionType), nullable=False, index=True)
    title = Column(String(200), nullable=False)  # "Retry with more permissions"
    description = Column(Text, nullable=False)  # Detailed explanation
    confidence_score = Column(Integer, nullable=False, default=50)  # 0-100
    
    # Action payload (what to do when user clicks)
    action_payload = Column(JSON, nullable=False)  # {"action": "retry", "params": {...}}
    
    # Metadata
    error_category = Column(String(100), nullable=True, index=True)  # From error_recovery
    estimated_success_rate = Column(Integer, nullable=True)  # 0-100
    priority = Column(Integer, nullable=False, default=1)  # 1=highest, 3=lowest
    
    # Tracking
    was_selected = Column(Integer, nullable=False, default=0)  # Boolean
    selection_timestamp = Column(Integer, nullable=True)  # When user clicked
    outcome_success = Column(Integer, nullable=True)  # Did it work? (0/1)
    
    # Timestamps
    created_at = Column(Integer, nullable=False, default=lambda: int(datetime.now(UTC).timestamp()))
    expires_at = Column(Integer, nullable=True)  # Suggestions expire after 24h
    
    # Relationships
    task = relationship("Task", back_populates="recovery_suggestions")
    
    def to_dict(self):
        """Convert to API response format"""
        return {
            "id": str(self.id),
            "task_id": str(self.task_id),
            "type": self.suggestion_type.value,
            "title": self.title,
            "description": self.description,
            "confidence_score": self.confidence_score,
            "action_payload": self.action_payload,
            "error_category": self.error_category,
            "estimated_success_rate": self.estimated_success_rate,
            "priority": self.priority,
            "was_selected": bool(self.was_selected),
            "created_at": self.created_at,
            "expires_at": self.expires_at
        }
