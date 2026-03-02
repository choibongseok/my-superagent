"""Workspace management endpoints."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_current_user, get_db
from backend.app.models.user import User
from backend.app.models.workspace_insight import WorkspaceInsight, WorkspaceCleanupLog
from backend.app.schemas.workspace import (
    WorkspaceInsightResponse,
    WorkspaceCleanupRequest,
    WorkspaceCleanupResponse
)
from backend.app.services.workspace_analyzer import WorkspaceAnalyzer

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.post("/analyze", response_model=WorkspaceInsightResponse)
async def analyze_workspace(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Analyze user's Drive workspace for insights.
    
    Returns:
    - Total file count and size
    - Duplicate files
    - Stale files (not accessed in 90+ days)
    - Storage breakdown by file type
    - Organization suggestions
    """
    try:
        analyzer = WorkspaceAnalyzer(db, current_user.id)
        insight = await analyzer.analyze_workspace()
        
        return WorkspaceInsightResponse(
            id=insight.id,
            user_id=insight.user_id,
            analyzed_at=insight.analyzed_at,
            total_files=insight.total_files,
            total_size_bytes=insight.total_size_bytes,
            duplicate_files=insight.duplicate_files,
            stale_files=insight.stale_files,
            storage_breakdown=insight.storage_breakdown,
            organization_suggestions=insight.organization_suggestions
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Workspace analysis failed: {str(e)}")


@router.get("/insights", response_model=List[WorkspaceInsightResponse])
async def get_workspace_insights(
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get recent workspace insights for current user."""
    insights = db.query(WorkspaceInsight).filter(
        WorkspaceInsight.user_id == current_user.id
    ).order_by(WorkspaceInsight.analyzed_at.desc()).limit(limit).all()
    
    return [
        WorkspaceInsightResponse(
            id=i.id,
            user_id=i.user_id,
            analyzed_at=i.analyzed_at,
            total_files=i.total_files,
            total_size_bytes=i.total_size_bytes,
            duplicate_files=i.duplicate_files,
            stale_files=i.stale_files,
            storage_breakdown=i.storage_breakdown,
            organization_suggestions=i.organization_suggestions
        )
        for i in insights
    ]


@router.get("/insights/{insight_id}", response_model=WorkspaceInsightResponse)
async def get_workspace_insight(
    insight_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get specific workspace insight."""
    insight = db.query(WorkspaceInsight).filter(
        WorkspaceInsight.id == insight_id,
        WorkspaceInsight.user_id == current_user.id
    ).first()
    
    if not insight:
        raise HTTPException(status_code=404, detail="Insight not found")
    
    return WorkspaceInsightResponse(
        id=insight.id,
        user_id=insight.user_id,
        analyzed_at=insight.analyzed_at,
        total_files=insight.total_files,
        total_size_bytes=insight.total_size_bytes,
        duplicate_files=insight.duplicate_files,
        stale_files=insight.stale_files,
        storage_breakdown=insight.storage_breakdown,
        organization_suggestions=insight.organization_suggestions
    )


@router.post("/organize", response_model=WorkspaceCleanupResponse)
async def organize_workspace(
    request: WorkspaceCleanupRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Execute workspace organization based on a suggestion.
    
    Supported operations:
    - archive_old_files: Move stale files to Archive folder
    - organize_by_year: Create year-based folder structure
    - remove_duplicates: Delete duplicate files (keep newest)
    """
    try:
        analyzer = WorkspaceAnalyzer(db, current_user.id)
        cleanup_log = await analyzer.organize_files(
            insight_id=request.insight_id,
            suggestion_type=request.suggestion_type
        )
        
        return WorkspaceCleanupResponse(
            id=cleanup_log.id,
            user_id=cleanup_log.user_id,
            insight_id=cleanup_log.insight_id,
            operation_type=cleanup_log.operation_type,
            performed_at=cleanup_log.performed_at,
            files_affected=cleanup_log.files_affected,
            bytes_freed=cleanup_log.bytes_freed,
            details=cleanup_log.details,
            error_message=cleanup_log.error_message
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Organization failed: {str(e)}")


@router.get("/cleanup-logs", response_model=List[WorkspaceCleanupResponse])
async def get_cleanup_logs(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get workspace cleanup operation history."""
    logs = db.query(WorkspaceCleanupLog).filter(
        WorkspaceCleanupLog.user_id == current_user.id
    ).order_by(WorkspaceCleanupLog.performed_at.desc()).limit(limit).all()
    
    return [
        WorkspaceCleanupResponse(
            id=log.id,
            user_id=log.user_id,
            insight_id=log.insight_id,
            operation_type=log.operation_type,
            performed_at=log.performed_at,
            files_affected=log.files_affected,
            bytes_freed=log.bytes_freed,
            details=log.details,
            error_message=log.error_message
        )
        for log in logs
    ]
