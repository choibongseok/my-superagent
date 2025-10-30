"""API endpoints for multi-agent orchestration and task planning."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import MultiAgentOrchestrator
from app.agents.task_planner import TaskPlanner
from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.orchestrator import (
    AgentTaskInfo,
    ComplexTaskRequest,
    ComplexTaskResponse,
    PlanRequest,
    PlanResponse,
    PlanStepInfo,
    ProgressResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/complex-task", response_model=ComplexTaskResponse)
async def execute_complex_task(
    request: ComplexTaskRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Execute complex task using multi-agent collaboration.

    This endpoint:
    1. Decomposes task into agent-specific subtasks
    2. Executes subtasks with dependency management
    3. Synthesizes results into coherent response

    Args:
        request: Complex task request
        current_user: Authenticated user
        db: Database session

    Returns:
        ComplexTaskResponse with synthesis and task details
    """
    try:
        logger.info(
            f"Complex task request from user {current_user.id}: {request.task_description}"
        )

        # Initialize orchestrator
        # TODO: Get Google credentials from user session/database
        orchestrator = MultiAgentOrchestrator(
            user_id=str(current_user.id),
            google_credentials=None,  # Will be implemented in Phase 5
        )

        # Execute complex task
        result = await orchestrator.execute_complex_task(request.task_description)

        # Convert to response schema
        response = ComplexTaskResponse(
            success=result["success"],
            synthesis=result.get("synthesis"),
            tasks=[
                AgentTaskInfo(
                    task_id=t["task_id"],
                    agent_type=t["agent_type"],
                    description=t["description"],
                    status=t["status"],
                    result=t.get("result"),
                    error=t.get("error"),
                )
                for t in result.get("tasks", [])
            ],
            statistics=result.get("statistics", {}),
            error=result.get("error"),
        )

        logger.info(
            f"Complex task completed: {response.statistics.get('successful', 0)} successful tasks"
        )

        return response

    except Exception as e:
        logger.error(f"Complex task execution failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Complex task execution failed: {str(e)}",
        )


@router.post("/plan", response_model=PlanResponse)
async def create_plan(
    request: PlanRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Create execution plan for goal.

    This endpoint:
    1. Decomposes goal into executable steps
    2. Estimates resources (time, cost, tokens)
    3. Validates against constraints

    Args:
        request: Plan request with goal and constraints
        current_user: Authenticated user
        db: Database session

    Returns:
        PlanResponse with detailed execution plan
    """
    try:
        logger.info(f"Plan request from user {current_user.id}: {request.goal}")

        # Initialize task planner
        planner = TaskPlanner()

        # Create plan
        plan = await planner.plan(
            goal=request.goal,
            context=request.context,
            constraints=request.constraints,
        )

        # Convert to response schema
        response = PlanResponse(
            success=True,
            goal=plan.goal,
            steps=[
                PlanStepInfo(
                    step_id=step.step_id,
                    description=step.description,
                    agent_type=step.agent_type,
                    estimated_time=step.estimated_time,
                    estimated_cost=step.estimated_cost,
                    estimated_tokens=step.estimated_tokens,
                    dependencies=step.dependencies,
                    success_criteria=step.success_criteria,
                    risks=step.risks,
                    status=step.status.value,
                    actual_time=step.actual_time,
                    actual_cost=step.actual_cost,
                )
                for step in plan.steps
            ],
            total_estimated_time=plan.total_estimated_time,
            total_estimated_cost=plan.total_estimated_cost,
            total_estimated_tokens=plan.total_estimated_tokens,
            constraints=plan.constraints,
            created_at=plan.created_at,
        )

        # Validate constraints
        if request.constraints:
            validation = planner.validate_constraints(plan, request.constraints)
            if not all(validation.values()):
                logger.warning(
                    f"Plan violates constraints: {validation}"
                )

        logger.info(
            f"Plan created: {len(plan.steps)} steps, "
            f"{plan.total_estimated_time}s, ${plan.total_estimated_cost:.2f}"
        )

        return response

    except Exception as e:
        logger.error(f"Plan creation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Plan creation failed: {str(e)}",
        )


@router.post("/execute-plan", response_model=ComplexTaskResponse)
async def execute_plan(
    plan_request: PlanRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Create and execute plan in one step.

    This is a convenience endpoint that combines:
    1. Plan creation (via TaskPlanner)
    2. Plan execution (via MultiAgentOrchestrator)

    Args:
        plan_request: Plan request with goal
        current_user: Authenticated user
        db: Database session

    Returns:
        ComplexTaskResponse with execution results
    """
    try:
        logger.info(
            f"Execute plan request from user {current_user.id}: {plan_request.goal}"
        )

        # Step 1: Create plan
        planner = TaskPlanner()
        plan = await planner.plan(
            goal=plan_request.goal,
            context=plan_request.context,
            constraints=plan_request.constraints,
        )

        logger.info(f"Plan created with {len(plan.steps)} steps")

        # Step 2: Execute via orchestrator
        orchestrator = MultiAgentOrchestrator(
            user_id=str(current_user.id),
            google_credentials=None,
        )

        result = await orchestrator.execute_complex_task(plan_request.goal)

        # Convert to response
        response = ComplexTaskResponse(
            success=result["success"],
            synthesis=result.get("synthesis"),
            tasks=[
                AgentTaskInfo(
                    task_id=t["task_id"],
                    agent_type=t["agent_type"],
                    description=t["description"],
                    status=t["status"],
                    result=t.get("result"),
                    error=t.get("error"),
                )
                for t in result.get("tasks", [])
            ],
            statistics=result.get("statistics", {}),
            error=result.get("error"),
        )

        logger.info("Plan execution completed")

        return response

    except Exception as e:
        logger.error(f"Plan execution failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Plan execution failed: {str(e)}",
        )
