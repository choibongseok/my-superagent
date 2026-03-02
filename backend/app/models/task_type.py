"""
Task Type Models for FactoryHub Integration

This module defines the schema for different task types:
- LLMTask: Traditional agent-based tasks (Research, Docs, Sheets, Slides)
- ScriptTask: Python/Node.js script execution
- APITask: External API calls with authentication
- DataTransformTask: ETL operations (CSV to JSON, data cleaning, etc.)
"""

from enum import Enum
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, validator
from datetime import datetime


class TaskCategory(str, Enum):
    """Task category classification"""
    LLM = "llm"  # LangChain agent tasks
    SCRIPT = "script"  # Code execution tasks
    API = "api"  # External API calls
    DATA_TRANSFORM = "data_transform"  # ETL operations
    WORKFLOW = "workflow"  # Multi-step workflows


class TaskStatus(str, Enum):
    """Task execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResourceQuota(BaseModel):
    """Resource limits for task execution"""
    max_cpu_percent: float = Field(default=50.0, ge=0, le=100)
    max_memory_mb: int = Field(default=512, ge=0)
    max_execution_time_seconds: int = Field(default=300, ge=0)
    max_disk_mb: int = Field(default=1024, ge=0)


class BaseTaskDefinition(BaseModel):
    """Base class for all task definitions"""
    task_id: Optional[str] = None
    category: TaskCategory
    name: str
    description: Optional[str] = None
    resource_quota: ResourceQuota = Field(default_factory=ResourceQuota)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    
    class Config:
        use_enum_values = True


class LLMTask(BaseTaskDefinition):
    """Traditional LangChain agent task"""
    category: TaskCategory = TaskCategory.LLM
    agent_type: str = Field(..., description="Agent type: research, docs, sheets, slides")
    model: str = Field(default="gpt-4o-mini")
    prompt: str
    context: Dict[str, Any] = Field(default_factory=dict)
    max_tokens: Optional[int] = None
    temperature: float = Field(default=0.7, ge=0, le=2)


class ScriptTask(BaseTaskDefinition):
    """Python/Node.js script execution task"""
    category: TaskCategory = TaskCategory.SCRIPT
    runtime: str = Field(..., description="Runtime: python3.11, node18, bash")
    script_content: str = Field(..., description="Script code to execute")
    script_args: List[str] = Field(default_factory=list)
    environment_vars: Dict[str, str] = Field(default_factory=dict)
    working_directory: Optional[str] = None
    
    @validator('runtime')
    def validate_runtime(cls, v):
        allowed_runtimes = ['python3.12', 'python3.11', 'python3.10', 'python3', 'node18', 'node20', 'bash']
        if v not in allowed_runtimes:
            raise ValueError(f"Runtime must be one of {allowed_runtimes}")
        return v


class APITask(BaseTaskDefinition):
    """External API call task"""
    category: TaskCategory = TaskCategory.API
    method: str = Field(..., description="HTTP method: GET, POST, PUT, DELETE, PATCH")
    url: str
    headers: Dict[str, str] = Field(default_factory=dict)
    query_params: Dict[str, str] = Field(default_factory=dict)
    body: Optional[Dict[str, Any]] = None
    auth_type: Optional[str] = Field(default=None, description="Auth type: bearer, basic, api_key, oauth2")
    auth_credentials: Optional[Dict[str, str]] = Field(default=None)
    retry_count: int = Field(default=3, ge=0, le=10)
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    
    @validator('method')
    def validate_method(cls, v):
        allowed_methods = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']
        if v.upper() not in allowed_methods:
            raise ValueError(f"Method must be one of {allowed_methods}")
        return v.upper()


class DataTransformTask(BaseTaskDefinition):
    """ETL and data transformation task"""
    category: TaskCategory = TaskCategory.DATA_TRANSFORM
    operation: str = Field(..., description="Operation: csv_to_json, json_to_csv, clean_data, aggregate, filter")
    input_format: str = Field(..., description="Input format: csv, json, xlsx, parquet")
    output_format: str = Field(..., description="Output format: csv, json, xlsx, parquet")
    input_data: Optional[str] = Field(default=None, description="Input data as string or file path")
    input_file_path: Optional[str] = None
    output_file_path: Optional[str] = None
    transform_config: Dict[str, Any] = Field(default_factory=dict)
    
    @validator('operation')
    def validate_operation(cls, v):
        allowed_operations = [
            'csv_to_json', 'json_to_csv', 'excel_to_json',
            'clean_data', 'aggregate', 'filter', 'merge', 'pivot'
        ]
        if v not in allowed_operations:
            raise ValueError(f"Operation must be one of {allowed_operations}")
        return v


class TaskResult(BaseModel):
    """Task execution result"""
    task_id: str
    status: TaskStatus
    result: Optional[Any] = None
    error: Optional[str] = None
    execution_time_seconds: Optional[float] = None
    resource_usage: Optional[Dict[str, Any]] = None
    output_file_paths: List[str] = Field(default_factory=list)
    logs: List[str] = Field(default_factory=list)
    completed_at: Optional[datetime] = None
    
    class Config:
        use_enum_values = True
