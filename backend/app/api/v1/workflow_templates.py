"""
Workflow Template API Endpoints
"""
from typing import Any, Dict, List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.api.dependencies import get_current_user, get_db
from app.models.user import User
from app.models.workflow_template import WorkflowTemplate, WorkflowExecution
from app.schemas.workflow_template import (
    WorkflowTemplateCreate,
    WorkflowTemplateUpdate,
    WorkflowTemplateResponse,
    WorkflowExecuteRequest,
    WorkflowExecutionResponse,
    WorkflowTemplateListResponse,
)
from app.services.workflow_executor import WorkflowExecutor

router = APIRouter()


@router.post("/workflow-templates", response_model=WorkflowTemplateResponse, status_code=status.HTTP_201_CREATED)
def create_workflow_template(
    template_data: WorkflowTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkflowTemplate:
    """Create a new workflow template"""
    
    # Convert Pydantic models to dicts for JSON storage
    steps = [step.model_dump() for step in template_data.steps]
    variables = [var.model_dump() for var in template_data.variables]
    
    template = WorkflowTemplate(
        name=template_data.name,
        description=template_data.description,
        version=template_data.version,
        steps=steps,
        variables=variables,
        triggers=template_data.triggers,
        tags=template_data.tags,
        category=template_data.category,
        is_public=template_data.is_public,
        created_by_id=current_user.id,
    )
    
    db.add(template)
    db.commit()
    db.refresh(template)
    
    return template


@router.get("/workflow-templates", response_model=WorkflowTemplateListResponse)
def list_workflow_templates(
    category: Optional[str] = Query(None, description="Filter by category"),
    tags: Optional[List[str]] = Query(None, description="Filter by tags"),
    is_public: bool = Query(True, description="Show public templates"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """List workflow templates"""
    
    query = db.query(WorkflowTemplate)
    
    # Filter by visibility
    if is_public:
        query = query.filter(
            or_(
                WorkflowTemplate.is_public == True,
                WorkflowTemplate.created_by_id == current_user.id
            )
        )
    else:
        query = query.filter(WorkflowTemplate.created_by_id == current_user.id)
    
    # Filter by category
    if category:
        query = query.filter(WorkflowTemplate.category == category)
    
    # Filter by tags (if any tag matches)
    if tags:
        for tag in tags:
            query = query.filter(WorkflowTemplate.tags.contains([tag]))
    
    # Count total
    total = query.count()
    
    # Paginate
    offset = (page - 1) * page_size
    templates = query.order_by(WorkflowTemplate.created_at.desc()).offset(offset).limit(page_size).all()
    
    return {
        "templates": templates,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/workflow-templates/{template_id}", response_model=WorkflowTemplateResponse)
def get_workflow_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkflowTemplate:
    """Get a workflow template by ID"""
    
    template = db.query(WorkflowTemplate).filter(WorkflowTemplate.id == template_id).first()
    
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow template {template_id} not found"
        )
    
    # Check access permissions
    if not template.is_public and template.created_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this template"
        )
    
    return template


@router.patch("/workflow-templates/{template_id}", response_model=WorkflowTemplateResponse)
def update_workflow_template(
    template_id: int,
    update_data: WorkflowTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkflowTemplate:
    """Update a workflow template"""
    
    template = db.query(WorkflowTemplate).filter(WorkflowTemplate.id == template_id).first()
    
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow template {template_id} not found"
        )
    
    # Only creator can update
    if template.created_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to update this template"
        )
    
    # Update fields
    update_dict = update_data.model_dump(exclude_unset=True)
    
    # Convert nested Pydantic models to dicts
    if "steps" in update_dict and update_dict["steps"]:
        update_dict["steps"] = [step.model_dump() if hasattr(step, "model_dump") else step for step in update_dict["steps"]]
    if "variables" in update_dict and update_dict["variables"]:
        update_dict["variables"] = [var.model_dump() if hasattr(var, "model_dump") else var for var in update_dict["variables"]]
    
    for key, value in update_dict.items():
        setattr(template, key, value)
    
    db.commit()
    db.refresh(template)
    
    return template


@router.delete("/workflow-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a workflow template"""
    
    template = db.query(WorkflowTemplate).filter(WorkflowTemplate.id == template_id).first()
    
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow template {template_id} not found"
        )
    
    # Only creator can delete
    if template.created_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to delete this template"
        )
    
    db.delete(template)
    db.commit()


@router.post("/workflow-templates/{template_id}/execute", response_model=WorkflowExecutionResponse, status_code=status.HTTP_201_CREATED)
async def execute_workflow_template(
    template_id: int,
    execute_request: WorkflowExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkflowExecution:
    """Execute a workflow template"""
    
    template = db.query(WorkflowTemplate).filter(WorkflowTemplate.id == template_id).first()
    
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow template {template_id} not found"
        )
    
    # Check access permissions
    if not template.is_public and template.created_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to execute this template"
        )
    
    # Validate required variables
    required_vars = [var for var in template.variables if var.get("required", True)]
    missing_vars = [var["name"] for var in required_vars if var["name"] not in execute_request.input_variables]
    
    if missing_vars:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required variables: {', '.join(missing_vars)}"
        )
    
    # Create execution record
    execution = WorkflowExecution(
        workflow_template_id=template.id,
        user_id=current_user.id,
        status="pending",
        current_step=0,
        total_steps=len(template.steps),
        input_variables=execute_request.input_variables,
    )
    
    db.add(execution)
    db.commit()
    db.refresh(execution)
    
    # Execute workflow asynchronously
    executor = WorkflowExecutor(db)
    try:
        await executor.execute_workflow(execution.id, template, execute_request.input_variables)
    except Exception as e:
        execution.status = "failed"
        execution.error_message = str(e)
        db.commit()
        db.refresh(execution)
    
    return execution


@router.get("/workflow-executions/{execution_id}", response_model=WorkflowExecutionResponse)
def get_workflow_execution(
    execution_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkflowExecution:
    """Get workflow execution status"""
    
    execution = db.query(WorkflowExecution).filter(WorkflowExecution.id == execution_id).first()
    
    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow execution {execution_id} not found"
        )
    
    # Only creator can view
    if execution.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view this execution"
        )
    
    return execution


@router.get("/workflow-executions", response_model=List[WorkflowExecutionResponse])
def list_workflow_executions(
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[WorkflowExecution]:
    """List workflow executions for current user"""
    
    query = db.query(WorkflowExecution).filter(WorkflowExecution.user_id == current_user.id)
    
    if status_filter:
        query = query.filter(WorkflowExecution.status == status_filter)
    
    offset = (page - 1) * page_size
    executions = query.order_by(WorkflowExecution.started_at.desc()).offset(offset).limit(page_size).all()
    
    return executions
