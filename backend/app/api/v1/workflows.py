"""
API endpoints for multi-agent workflow execution.

Routes:
- GET /api/v1/workflows - List available workflows
- POST /api/v1/workflows/execute - Execute a workflow
- GET /api/v1/workflows/{execution_id}/status - Get workflow status
- GET /api/v1/workflows/history - Get user's workflow history
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.models.user import User
from app.models.workflow_execution import WorkflowExecution, WorkflowStatus
from app.workflows import get_workflow, list_workflows
from app.agents.coordinator import AgentCoordinator
from app.agents.protocols import MessageStatus
from app.core.config import settings
from app.core.redis import get_redis_client

router = APIRouter()


class WorkflowExecuteRequest(BaseModel):
    """Request to execute a workflow."""
    workflow_id: str = Field(..., description="ID of the workflow to execute")
    inputs: Dict[str, Any] = Field(default_factory=dict, description="Workflow inputs")


class WorkflowExecuteResponse(BaseModel):
    """Response from workflow execution."""
    execution_id: str
    workflow_id: str
    workflow_name: str
    status: str
    message: str


class WorkflowStatusResponse(BaseModel):
    """Workflow execution status."""
    execution_id: str
    workflow_id: str
    workflow_name: str
    status: str
    current_step: Optional[str]
    initial_inputs: Dict[str, Any]
    step_results: Dict[str, Any]
    final_output: Optional[Dict[str, Any]]
    error: Optional[str]
    started_at: str
    completed_at: Optional[str]
    duration_seconds: float


class WorkflowListItem(BaseModel):
    """Workflow metadata for listing."""
    id: str
    name: str
    description: str
    steps: int
    metadata: Dict[str, Any]


@router.get("/workflows", response_model=List[WorkflowListItem])
async def list_available_workflows(
    current_user: User = Depends(get_current_user),
) -> List[WorkflowListItem]:
    """
    List all available multi-agent workflows.
    
    Returns workflow metadata including name, description, and step count.
    """
    workflows = list_workflows()
    return [WorkflowListItem(**wf) for wf in workflows]


@router.post("/workflows/execute", response_model=WorkflowExecuteResponse)
async def execute_workflow(
    request: WorkflowExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkflowExecuteResponse:
    """
    Execute a multi-agent workflow.
    
    The workflow runs asynchronously. Use the execution_id to check status.
    
    Args:
        request: Workflow execution request with workflow_id and inputs
        
    Returns:
        Execution details including execution_id for status tracking
    """
    # Get workflow definition
    try:
        workflow = get_workflow(request.workflow_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow not found: {request.workflow_id}"
        )
    
    # Merge inputs
    workflow.initial_inputs.update(request.inputs)
    
    # Create execution record
    execution = WorkflowExecution(
        execution_id=workflow.workflow_id,
        workflow_id=request.workflow_id,
        workflow_name=workflow.name,
        user_id=current_user.id,
        status=WorkflowStatus.RUNNING,
        initial_inputs=workflow.initial_inputs,
        step_results={},
        metadata=workflow.metadata,
        started_at=datetime.utcnow(),
    )
    
    db.add(execution)
    db.commit()
    db.refresh(execution)
    
    # Execute workflow asynchronously
    # TODO: Move this to Celery task for production
    try:
        # Initialize coordinator
        # TODO: Get agent registry from dependency injection
        agent_registry = {}  # Placeholder
        coordinator = AgentCoordinator(get_redis_client(), agent_registry)
        
        # Execute workflow
        result = await coordinator.execute_workflow(
            workflow=workflow,
            initial_inputs=workflow.initial_inputs,
            user_id=current_user.id,
        )
        
        # Update execution record
        execution.status = WorkflowStatus(result.status.value)
        execution.step_results = {k: v.to_dict() for k, v in result.step_results.items()}
        execution.final_output = result.final_output
        execution.error = result.error
        execution.completed_at = datetime.utcnow()
        
        db.commit()
        
        return WorkflowExecuteResponse(
            execution_id=execution.execution_id,
            workflow_id=execution.workflow_id,
            workflow_name=execution.workflow_name,
            status=execution.status.value,
            message=f"Workflow {'completed' if result.status == MessageStatus.COMPLETED else 'failed'}"
        )
        
    except Exception as e:
        execution.status = WorkflowStatus.FAILED
        execution.error = str(e)
        execution.completed_at = datetime.utcnow()
        db.commit()
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Workflow execution failed: {str(e)}"
        )


@router.get("/workflows/{execution_id}/status", response_model=WorkflowStatusResponse)
async def get_workflow_status(
    execution_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkflowStatusResponse:
    """
    Get the status of a workflow execution.
    
    Args:
        execution_id: Workflow execution ID
        
    Returns:
        Current status, step results, and final output if completed
    """
    execution = db.query(WorkflowExecution).filter(
        WorkflowExecution.execution_id == execution_id,
        WorkflowExecution.user_id == current_user.id,
    ).first()
    
    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow execution not found"
        )
    
    return WorkflowStatusResponse(
        execution_id=execution.execution_id,
        workflow_id=execution.workflow_id,
        workflow_name=execution.workflow_name,
        status=execution.status.value,
        current_step=execution.current_step,
        initial_inputs=execution.initial_inputs,
        step_results=execution.step_results,
        final_output=execution.final_output,
        error=execution.error,
        started_at=execution.started_at.isoformat(),
        completed_at=execution.completed_at.isoformat() if execution.completed_at else None,
        duration_seconds=execution.duration_seconds,
    )


@router.get("/workflows/history", response_model=List[WorkflowStatusResponse])
async def get_workflow_history(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[WorkflowStatusResponse]:
    """
    Get user's workflow execution history.
    
    Args:
        limit: Maximum number of results (default 20)
        offset: Pagination offset (default 0)
        
    Returns:
        List of workflow executions ordered by most recent
    """
    executions = db.query(WorkflowExecution).filter(
        WorkflowExecution.user_id == current_user.id,
    ).order_by(
        WorkflowExecution.created_at.desc()
    ).limit(limit).offset(offset).all()
    
    return [
        WorkflowStatusResponse(
            execution_id=ex.execution_id,
            workflow_id=ex.workflow_id,
            workflow_name=ex.workflow_name,
            status=ex.status.value,
            current_step=ex.current_step,
            initial_inputs=ex.initial_inputs,
            step_results=ex.step_results,
            final_output=ex.final_output,
            error=ex.error,
            started_at=ex.started_at.isoformat(),
            completed_at=ex.completed_at.isoformat() if ex.completed_at else None,
            duration_seconds=ex.duration_seconds,
        )
        for ex in executions
    ]
