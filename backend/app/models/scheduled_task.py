"""Scheduled Task model for recurring tasks."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class ScheduledTask(Base):
    """
    Scheduled/recurring task configuration.
    
    Allows users to schedule tasks to run:
    - Daily (e.g., "every day at 9 AM")
    - Weekly (e.g., "every Monday at 10 AM")
    - Monthly (e.g., "1st of every month")
    - Custom cron expressions (e.g., "0 9 * * MON-FRI" = weekdays 9 AM)
    
    Features:
    - Automatic task creation based on schedule
    - Email/notification on completion
    - Pause/resume functionality
    - Next run time calculation
    """
    
    __tablename__ = "scheduled_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Task configuration
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    task_type = Column(String(50), nullable=False)  # research, docs, sheets, slides
    prompt_template = Column(Text, nullable=False)  # Template with {date}, {week}, etc.
    
    # Schedule configuration
    schedule_type = Column(String(50), nullable=False)  # daily, weekly, monthly, cron
    # For daily: hour=9, minute=0 -> "9:00 AM"
    # For weekly: day_of_week=1 (Monday), hour=10 -> "Every Monday at 10 AM"
    # For monthly: day_of_month=1, hour=9 -> "1st of every month at 9 AM"
    # For cron: cron_expression="0 9 * * 1-5" -> "Weekdays at 9 AM"
    schedule_config = Column(JSON, nullable=False)
    cron_expression = Column(String(100), nullable=True)  # For custom schedules
    
    # Execution metadata
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    last_run_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True, index=True)
    run_count = Column(Integer, default=0, nullable=False)
    
    # Notification settings
    notify_on_completion = Column(Boolean, default=True, nullable=False)
    notification_email = Column(String(255), nullable=True)
    notification_channels = Column(JSON, nullable=True)  # ['email', 'slack', 'webhook']
    
    # Output configuration
    output_config = Column(JSON, nullable=True)  # Drive folder, naming pattern, etc.
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="scheduled_tasks")
    executions = relationship(
        "ScheduledTaskExecution",
        back_populates="scheduled_task",
        cascade="all, delete-orphan",
        order_by="desc(ScheduledTaskExecution.started_at)"
    )

    def __repr__(self):
        return f"<ScheduledTask {self.name} ({self.schedule_type})>"


class ScheduledTaskExecution(Base):
    """
    Records individual executions of a scheduled task.
    
    Tracks:
    - When the task ran
    - Result (success/failure)
    - Output (created document/spreadsheet URLs)
    - Errors
    """
    
    __tablename__ = "scheduled_task_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scheduled_task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("scheduled_tasks.id"),
        nullable=False,
        index=True
    )
    task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id"),
        nullable=True,
        index=True
    )  # Link to actual Task record
    
    # Execution metadata
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)
    status = Column(
        String(50),
        default="running",
        nullable=False
    )  # running, completed, failed, cancelled
    
    # Result
    success = Column(Boolean, default=False, nullable=False)
    error_message = Column(Text, nullable=True)
    output_data = Column(JSON, nullable=True)  # Document URLs, etc.
    
    # Relationships
    scheduled_task = relationship("ScheduledTask", back_populates="executions")
    task = relationship("Task")  # Link to the actual task that was executed

    def __repr__(self):
        return f"<ScheduledTaskExecution {self.id} ({self.status})>"
