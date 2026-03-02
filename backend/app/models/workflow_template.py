"""
Workflow Template Models
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4, UUID
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, JSON, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from app.models.base import Base


class WorkflowTemplate(Base):
    """Workflow template for multi-agent task execution"""
    __tablename__ = "workflow_templates"
    __table_args__ = (
        Index('ix_workflow_templates_created_by_public', 'created_by_id', 'is_public'),
        Index('ix_workflow_templates_category_public', 'category', 'is_public'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    version = Column(String(20), default="v1", nullable=False)
    
    # Workflow definition
    steps = Column(JSON, nullable=False)  # List[Dict] - agent steps with dependencies
    variables = Column(JSON, default=list)  # List[Dict] - required input variables
    triggers = Column(JSON, default=list)  # List[str] - event triggers
    
    # Metadata
    tags = Column(JSON, default=list)  # List[str] - categorization tags
    category = Column(String(100), nullable=True, index=True)
    is_public = Column(Boolean, default=True, nullable=False)
    
    # Ownership
    created_by_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    created_by = relationship("User", back_populates="workflow_templates")
    executions = relationship("WorkflowExecution", back_populates="template", cascade="all, delete-orphan")


class WorkflowExecution(Base):
    """Workflow execution tracking"""
    __tablename__ = "workflow_executions"
    __table_args__ = (
        Index('ix_workflow_executions_user_status', 'user_id', 'status'),
        Index('ix_workflow_executions_started_at', 'started_at'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    workflow_template_id = Column(Integer, ForeignKey("workflow_templates.id"), nullable=False)
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Execution state
    status = Column(String(50), default="pending", nullable=False, index=True)  # pending/running/completed/failed
    current_step = Column(Integer, default=0, nullable=False)
    total_steps = Column(Integer, nullable=False)
    
    # Input/Output
    input_variables = Column(JSON, default=dict)  # Dict[str, Any] - variable values
    results = Column(JSON, default=dict)  # Dict[str, Any] - step results
    error_message = Column(Text, nullable=True)
    
    # Timestamps
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    template = relationship("WorkflowTemplate", back_populates="executions")
    user = relationship("User", back_populates="workflow_executions")
