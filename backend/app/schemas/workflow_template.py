"""
Workflow Template API Schemas
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class WorkflowVariable(BaseModel):
    """Variable definition for workflow template"""
    name: str = Field(..., description="Variable name (e.g., company_name)")
    type: str = Field(..., description="Variable type (string, number, date, etc.)")
    description: str = Field(..., description="Human-readable description")
    required: bool = Field(True, description="Whether the variable is required")
    default: Optional[Any] = Field(None, description="Default value if not provided")


class WorkflowStep(BaseModel):
    """Step definition for workflow template"""
    id: str = Field(..., description="Unique step identifier")
    agent_type: str = Field(..., description="Agent type (research, sheets, docs, slides)")
    description: str = Field(..., description="Step description")
    inputs: Dict[str, Any] = Field(default_factory=dict, description="Step inputs (can reference variables)")
    depends_on: List[str] = Field(default_factory=list, description="List of step IDs this step depends on")
    condition: Optional[str] = Field(None, description="Conditional expression (e.g., '{{step1.success}} == true')")


class WorkflowTemplateCreate(BaseModel):
    """Request schema for creating workflow template"""
    name: str = Field(..., min_length=1, max_length=255, description="Template name")
    description: Optional[str] = Field(None, description="Template description")
    version: str = Field("v1", description="Template version")
    steps: List[WorkflowStep] = Field(..., min_items=1, description="Workflow steps")
    variables: List[WorkflowVariable] = Field(default_factory=list, description="Template variables")
    triggers: List[str] = Field(default_factory=list, description="Event triggers")
    tags: List[str] = Field(default_factory=list, description="Categorization tags")
    category: Optional[str] = Field(None, max_length=100, description="Template category")
    is_public: bool = Field(True, description="Whether the template is publicly visible")


class WorkflowTemplateUpdate(BaseModel):
    """Request schema for updating workflow template"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    version: Optional[str] = None
    steps: Optional[List[WorkflowStep]] = None
    variables: Optional[List[WorkflowVariable]] = None
    triggers: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    category: Optional[str] = Field(None, max_length=100)
    is_public: Optional[bool] = None


class WorkflowTemplateResponse(BaseModel):
    """Response schema for workflow template"""
    id: int
    name: str
    description: Optional[str]
    version: str
    steps: List[Dict[str, Any]]
    variables: List[Dict[str, Any]]
    triggers: List[str]
    tags: List[str]
    category: Optional[str]
    is_public: bool
    created_by_id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class WorkflowExecuteRequest(BaseModel):
    """Request schema for executing workflow"""
    input_variables: Dict[str, Any] = Field(default_factory=dict, description="Variable values for execution")


class WorkflowExecutionResponse(BaseModel):
    """Response schema for workflow execution"""
    id: int
    workflow_template_id: int
    user_id: str
    status: str
    current_step: int
    total_steps: int
    input_variables: Dict[str, Any]
    results: Dict[str, Any]
    error_message: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class WorkflowTemplateListResponse(BaseModel):
    """Response schema for listing workflow templates"""
    templates: List[WorkflowTemplateResponse]
    total: int
    page: int
    page_size: int
