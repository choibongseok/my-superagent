"""Schemas for Smart Task Chaining (#227)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.task import TaskType
from app.models.task_chain import ChainStatus, StepStatus


# ── Request schemas ──────────────────────────────────────────────────────────


class ChainStepCreate(BaseModel):
    """Schema for a single step when creating a chain."""

    prompt_template: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description=(
            "Prompt template for this step. "
            "Use {{previous_output}} to reference the output from the prior step."
        ),
    )
    task_type: TaskType
    step_metadata: Optional[Dict[str, Any]] = None


class ChainCreate(BaseModel):
    """Create a new task chain."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    steps: List[ChainStepCreate] = Field(..., min_length=1, max_length=10)
    chain_metadata: Optional[Dict[str, Any]] = None


class ChainUpdate(BaseModel):
    """Update an existing chain (only allowed in DRAFT status)."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None


class ChainStepUpdate(BaseModel):
    """Update a step in a DRAFT chain."""

    prompt_template: Optional[str] = Field(default=None, min_length=1, max_length=5000)
    task_type: Optional[TaskType] = None


# ── Response schemas ─────────────────────────────────────────────────────────


class ChainStepResponse(BaseModel):
    """Response schema for a chain step."""

    id: UUID
    step_order: int
    prompt_template: str
    task_type: TaskType
    status: StepStatus
    resolved_prompt: Optional[str] = None
    task_id: Optional[UUID] = None
    output_summary: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    step_metadata: Optional[Dict[str, Any]] = None

    model_config = {"from_attributes": True}


class ChainResponse(BaseModel):
    """Response schema for a task chain."""

    id: UUID
    user_id: UUID
    name: str
    description: Optional[str] = None
    status: ChainStatus
    current_step_index: int
    steps: List[ChainStepResponse]
    chain_metadata: Optional[Dict[str, Any]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChainListResponse(BaseModel):
    """Paginated chain list."""

    chains: List[ChainResponse]
    total: int
