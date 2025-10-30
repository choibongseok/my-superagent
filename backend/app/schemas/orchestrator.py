"""Schemas for multi-agent orchestrator and task planning."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# Multi-Agent Orchestrator Schemas

class ComplexTaskRequest(BaseModel):
    """Request schema for complex task execution."""

    task_description: str = Field(
        ..., description="Complex task description requiring multiple agents"
    )
    context: Optional[Dict[str, Any]] = Field(
        default=None, description="Additional context for task execution"
    )


class AgentTaskInfo(BaseModel):
    """Information about a single agent task."""

    task_id: str
    agent_type: str
    description: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ComplexTaskResponse(BaseModel):
    """Response schema for complex task execution."""

    success: bool
    synthesis: Optional[str] = Field(
        None, description="Synthesized result from all agents"
    )
    tasks: List[AgentTaskInfo] = Field(
        default_factory=list, description="Individual task results"
    )
    statistics: Dict[str, int] = Field(
        default_factory=dict, description="Execution statistics"
    )
    error: Optional[str] = None


# Task Planner Schemas

class PlanRequest(BaseModel):
    """Request schema for task planning."""

    goal: str = Field(..., description="High-level goal to accomplish")
    context: Optional[Dict[str, Any]] = Field(
        default=None, description="Additional context for planning"
    )
    constraints: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Resource constraints (max_time, max_cost, max_tokens)",
    )


class PlanStepInfo(BaseModel):
    """Information about a single plan step."""

    step_id: str
    description: str
    agent_type: str
    estimated_time: int = Field(..., description="Estimated time in seconds")
    estimated_cost: float = Field(..., description="Estimated cost in USD")
    estimated_tokens: int = Field(..., description="Estimated token count")
    dependencies: List[str] = Field(default_factory=list)
    success_criteria: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    status: str = "planned"
    actual_time: Optional[int] = None
    actual_cost: Optional[float] = None


class PlanResponse(BaseModel):
    """Response schema for task planning."""

    success: bool
    goal: str
    steps: List[PlanStepInfo] = Field(default_factory=list)
    total_estimated_time: int = Field(..., description="Total estimated time in seconds")
    total_estimated_cost: float = Field(..., description="Total estimated cost in USD")
    total_estimated_tokens: int = Field(..., description="Total estimated tokens")
    constraints: Dict[str, Any] = Field(default_factory=dict)
    created_at: str
    error: Optional[str] = None


class ProgressResponse(BaseModel):
    """Response schema for plan progress."""

    total_steps: int
    completed: int
    in_progress: int
    failed: int
    blocked: int
    progress_percentage: float
    estimated_time: int
    actual_time: int
    estimated_cost: float
    actual_cost: float
    time_variance: int
    cost_variance: float
