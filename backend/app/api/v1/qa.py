"""Quality Assurance API endpoints.

Provides:
- POST /qa/validate       — ad-hoc text validation (no DB storage)
- POST /qa/validate/quick — lightweight score-only check
- POST /tasks/{id}/qa     — validate a task's output and persist result
- GET  /tasks/{id}/qa     — retrieve stored QA results for a task
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.qa_result import QAResult
from app.models.task import Task
from app.models.user import User
from app.schemas.qa import (
    QAConfidence,
    QAQuickResponse,
    QAResultListResponse,
    QAResultResponse,
    QAScores,
    QASuggestion,
    QAValidationRequest,
    QAValidationResponse,
)
from app.services.qa_service import qa_service

logger = logging.getLogger(__name__)

router = APIRouter()


# --------------------------------------------------------------------------
# Ad-hoc validation (no DB, no auth required for convenience)
# --------------------------------------------------------------------------

@router.post("/qa/validate", response_model=QAValidationResponse)
async def validate_text(body: QAValidationRequest):
    """Run full QA validation on arbitrary text.

    No authentication required — useful for playground / previews.
    Results are NOT persisted.
    """
    result = qa_service.validate(
        text=body.text,
        prompt=body.prompt,
        task_type=body.task_type,
    )
    return _to_response(result)


@router.post("/qa/validate/quick", response_model=QAQuickResponse)
async def validate_text_quick(body: QAValidationRequest):
    """Lightweight score-only QA check."""
    result = qa_service.validate_quick(body.text, body.prompt)
    return QAQuickResponse(**result)


# --------------------------------------------------------------------------
# Task-bound validation (persisted)
# --------------------------------------------------------------------------

@router.post(
    "/tasks/{task_id}/qa",
    response_model=QAResultResponse,
    status_code=status.HTTP_201_CREATED,
)
async def validate_task(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Validate a completed task's output and save the QA result.

    Only the task owner can trigger validation.
    The task must be in 'completed' status with a non-empty result.
    """
    task = await _get_task_or_404(task_id, db)

    # Ownership check
    if task.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your task")

    if task.status.value != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task is not completed (status={task.status.value})",
        )

    # Extract text to validate
    text = _extract_text(task)
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Task has no textual output to validate",
        )

    # Run QA
    qa_result = qa_service.validate(
        text=text,
        prompt=task.prompt,
        task_type=task.task_type.value if task.task_type else None,
        result_data=task.result,
    )

    # Persist
    qa_row = QAResult(
        task_id=task.id,
        overall_score=qa_result["overall_score"],
        grammar_score=qa_result["scores"]["grammar"],
        fact_check_score=qa_result["scores"]["fact_check"],
        structure_score=qa_result["scores"]["structure"],
        readability_score=qa_result["scores"]["readability"],
        completeness_score=qa_result["scores"]["completeness"],
        grammar_issues=qa_result["details"]["grammar"],
        fact_check_results=qa_result["details"]["fact_check"],
        structure_analysis=qa_result["details"]["structure"],
        readability_metrics=qa_result["details"]["readability"],
        missing_sections=qa_result["details"]["completeness"],
        auto_fix_suggestions={"suggestions": qa_result["suggestions"]},
        confidence_level=qa_result["confidence"]["level"],
        confidence_score=qa_result["confidence"]["score"],
        validation_time_ms=qa_result["metadata"]["validation_time_ms"],
        validator_version=qa_result["metadata"]["validator_version"],
    )
    db.add(qa_row)
    await db.commit()
    await db.refresh(qa_row)

    return _row_to_response(qa_row, qa_result)


@router.get("/tasks/{task_id}/qa", response_model=QAResultListResponse)
async def get_task_qa_results(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve all QA validation results for a task."""
    task = await _get_task_or_404(task_id, db)

    if task.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your task")

    stmt = (
        select(QAResult)
        .where(QAResult.task_id == task_id)
        .order_by(QAResult.created_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()

    results = []
    for row in rows:
        results.append(_row_to_response(row))

    return QAResultListResponse(results=results, total=len(results))


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

async def _get_task_or_404(task_id: UUID, db: AsyncSession) -> Task:
    stmt = select(Task).where(Task.id == task_id)
    task = (await db.execute(stmt)).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


def _extract_text(task: Task) -> Optional[str]:
    """Extract the primary text content from a task result."""
    if not task.result:
        return None

    result = task.result

    # Try common keys in order of priority
    for key in ("content", "text", "summary", "report", "output", "research_summary"):
        if key in result and isinstance(result[key], str):
            return result[key]

    # Try nested research results
    if "findings" in result and isinstance(result["findings"], list):
        parts = []
        for finding in result["findings"]:
            if isinstance(finding, str):
                parts.append(finding)
            elif isinstance(finding, dict):
                parts.append(finding.get("content", finding.get("text", str(finding))))
        if parts:
            return "\n\n".join(parts)

    # Fallback: serialize entire result
    import json
    try:
        return json.dumps(result, indent=2, default=str)
    except Exception:
        return None


def _to_response(qa_dict: dict) -> QAValidationResponse:
    return QAValidationResponse(
        overall_score=qa_dict["overall_score"],
        grade=qa_dict["grade"],
        scores=QAScores(**qa_dict["scores"]),
        suggestions=[QASuggestion(**s) for s in qa_dict["suggestions"]],
        confidence=QAConfidence(**qa_dict["confidence"]),
        metadata=qa_dict["metadata"],
    )


def _row_to_response(row: QAResult, qa_dict: Optional[dict] = None) -> QAResultResponse:
    """Convert a QAResult DB row to API response."""
    suggestions_raw = (row.auto_fix_suggestions or {}).get("suggestions", [])
    return QAResultResponse(
        id=row.id,
        task_id=row.task_id,
        overall_score=row.overall_score,
        grade=_letter_grade(row.overall_score),
        scores=QAScores(
            grammar=row.grammar_score or 0,
            structure=row.structure_score or 0,
            readability=row.readability_score or 0,
            completeness=row.completeness_score or 0,
            fact_check=row.fact_check_score or 0,
        ),
        suggestions=[QASuggestion(**s) for s in suggestions_raw if isinstance(s, dict)],
        confidence=QAConfidence(
            level=row.confidence_level or "unknown",
            score=row.confidence_score or 0,
        ),
        metadata={
            "validation_time_ms": row.validation_time_ms,
            "validator_version": row.validator_version,
        },
        created_at=row.created_at,
    )


def _letter_grade(score: float) -> str:
    if score >= 90:
        return "A"
    elif score >= 80:
        return "B"
    elif score >= 70:
        return "C"
    elif score >= 60:
        return "D"
    return "F"
