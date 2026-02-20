"""Automatic Quality Score Badge service (#228).

Auto-triggers QA validation when a task completes and persists the result.
The score is then displayed as a badge on share links.

Design decisions:
- Runs synchronously in the Celery worker (QA is CPU-only, ~5-50ms)
- Does NOT block task completion — failures are logged and swallowed
- Only runs if no QA result already exists for the task
- Low scores are shown with improvement tips, never hidden
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.qa_result import QAResult
from app.models.task import Task
from app.services.qa_service import qa_service

logger = logging.getLogger(__name__)


def _extract_text_from_result(result: Optional[Dict[str, Any]]) -> Optional[str]:
    """Extract primary text content from a task result dict."""
    if not result or not isinstance(result, dict):
        return None

    for key in ("content", "text", "summary", "report", "output", "research_summary"):
        if key in result and isinstance(result[key], str) and result[key].strip():
            return result[key]

    if "findings" in result and isinstance(result["findings"], list):
        parts = []
        for f in result["findings"]:
            if isinstance(f, str):
                parts.append(f)
            elif isinstance(f, dict):
                parts.append(f.get("content", f.get("text", str(f))))
        if parts:
            return "\n\n".join(parts)

    return None


async def auto_qa_on_completion(
    db: AsyncSession,
    task_id: UUID,
) -> Optional[QAResult]:
    """Run QA validation on a completed task and persist the result.

    Returns the QAResult row if validation ran, None if skipped/failed.
    This function never raises — errors are logged and swallowed.
    """
    try:
        # Load task
        stmt = select(Task).where(Task.id == task_id)
        task = (await db.execute(stmt)).scalar_one_or_none()
        if not task:
            logger.warning("auto_qa: task %s not found", task_id)
            return None

        if task.status.value != "completed":
            return None

        # Skip if already has a QA result
        existing = (
            await db.execute(
                select(QAResult.id).where(QAResult.task_id == task_id).limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None:
            logger.debug("auto_qa: task %s already has QA result, skipping", task_id)
            return None

        # Extract text
        text = _extract_text_from_result(task.result)
        if not text or len(text.strip()) < 20:
            logger.debug("auto_qa: task %s has no meaningful text output", task_id)
            return None

        # Run QA (CPU-only, typically <50ms)
        task_type = task.task_type.value if hasattr(task.task_type, "value") else str(task.task_type)
        qa_result = qa_service.validate(
            text=text,
            prompt=task.prompt,
            task_type=task_type,
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

        logger.info(
            "auto_qa: task %s scored %.1f (%s) in %dms",
            task_id,
            qa_row.overall_score,
            qa_row.get_grade(),
            qa_row.validation_time_ms or 0,
        )
        return qa_row

    except Exception:
        logger.exception("auto_qa: unexpected error for task %s", task_id)
        return None
