"""Workspace schemas."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class WorkspaceInsightResponse(BaseModel):
    """Response schema for workspace insights."""
    
    id: int
    user_id: int
    analyzed_at: datetime
    total_files: int
    total_size_bytes: int
    duplicate_files: Optional[List[Dict[str, Any]]] = None
    stale_files: Optional[List[Dict[str, Any]]] = None
    storage_breakdown: Optional[Dict[str, Any]] = None
    organization_suggestions: Optional[List[Dict[str, Any]]] = None
    
    class Config:
        from_attributes = True


class WorkspaceCleanupRequest(BaseModel):
    """Request schema for workspace cleanup operations."""
    
    insight_id: int = Field(..., description="ID of the workspace insight")
    suggestion_type: str = Field(
        ...,
        description="Type of organization operation (archive_old_files, organize_by_year, remove_duplicates)"
    )


class WorkspaceCleanupResponse(BaseModel):
    """Response schema for workspace cleanup operations."""
    
    id: int
    user_id: int
    insight_id: Optional[int] = None
    operation_type: str
    performed_at: datetime
    files_affected: int
    bytes_freed: int
    details: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    
    class Config:
        from_attributes = True
