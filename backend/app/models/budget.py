"""Budget tracking models for LLM cost management."""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, ForeignKey, JSON, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
import enum

from app.core.database import Base


class BudgetPeriod(str, enum.Enum):
    """Budget period types."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class BudgetAlertLevel(str, enum.Enum):
    """Budget alert severity levels."""
    WARNING = "warning"  # 75% threshold
    CRITICAL = "critical"  # 90% threshold
    EXCEEDED = "exceeded"  # 100% threshold


class UserBudget(Base):
    """
    User budget limits and tracking.
    
    Tracks LLM costs and enforces budget limits per user.
    """
    __tablename__ = "user_budgets"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Budget configuration
    period = Column(SAEnum(BudgetPeriod), nullable=False, default=BudgetPeriod.MONTHLY)
    limit_usd = Column(Float, nullable=False)  # Budget limit in USD
    
    # Current period tracking
    current_spend_usd = Column(Float, nullable=False, default=0.0)
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    
    # Alert settings
    enable_alerts = Column(Boolean, nullable=False, default=True)
    alert_email = Column(String, nullable=True)  # Override user email
    warning_threshold_pct = Column(Integer, nullable=False, default=75)  # % of budget
    critical_threshold_pct = Column(Integer, nullable=False, default=90)
    
    # Alert state
    last_warning_sent = Column(DateTime(timezone=True), nullable=True)
    last_critical_sent = Column(DateTime(timezone=True), nullable=True)
    budget_exceeded = Column(Boolean, nullable=False, default=False)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="budgets")
    alerts = relationship("BudgetAlert", back_populates="budget", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<UserBudget(user_id={self.user_id}, limit=${self.limit_usd}, spend=${self.current_spend_usd})>"
    
    @property
    def usage_percentage(self) -> float:
        """Calculate current budget usage percentage."""
        if self.limit_usd == 0:
            return 0.0
        return (self.current_spend_usd / self.limit_usd) * 100
    
    @property
    def remaining_usd(self) -> float:
        """Calculate remaining budget in USD."""
        return max(0.0, self.limit_usd - self.current_spend_usd)


class BudgetAlert(Base):
    """
    Budget alert history.
    
    Records all budget alerts sent to users.
    """
    __tablename__ = "budget_alerts"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    budget_id = Column(PGUUID(as_uuid=True), ForeignKey("user_budgets.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Alert details
    level = Column(SAEnum(BudgetAlertLevel), nullable=False)
    spend_usd = Column(Float, nullable=False)
    limit_usd = Column(Float, nullable=False)
    usage_percentage = Column(Float, nullable=False)
    
    # Notification status
    email_sent = Column(Boolean, nullable=False, default=False)
    email_sent_at = Column(DateTime(timezone=True), nullable=True)
    
    # Metadata
    message = Column(String, nullable=True)
    alert_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    
    # Relationships
    budget = relationship("UserBudget", back_populates="alerts")
    user = relationship("User")
    
    def __repr__(self):
        return f"<BudgetAlert(user_id={self.user_id}, level={self.level}, usage={self.usage_percentage}%)>"


class CostRecord(Base):
    """
    Individual LLM cost records from LangFuse.
    
    Tracks every LLM API call cost for detailed analytics.
    """
    __tablename__ = "cost_records"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    task_id = Column(PGUUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True)
    
    # LangFuse integration
    langfuse_trace_id = Column(String, nullable=True)
    langfuse_span_id = Column(String, nullable=True)
    
    # Cost details
    model = Column(String, nullable=False)  # e.g., "gpt-4", "claude-3-opus"
    agent_type = Column(String, nullable=False)  # research, docs, sheets, slides
    
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    
    cost_usd = Column(Float, nullable=False)
    
    # Metadata
    cost_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User")
    task = relationship("Task")
    
    def __repr__(self):
        return f"<CostRecord(user_id={self.user_id}, model={self.model}, cost=${self.cost_usd})>"
