"""Task management endpoints."""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.websocket import manager as ws_manager
from app.models.task import Task as TaskModel
from app.models.task import TaskStatus, TaskType
from app.models.user import User
from app.schemas.task import (
    PreRunReliabilityRequest,
    PreRunReliabilityResponse,
    ReliabilityGateCheck,
    ShareLinkResponse,
    SmartExitHintAction,
    SmartExitHintsResponse,
    Task,
    TaskCreate,
    TaskList,
    TaskPreviewModifyRequest,
    TaskPreviewRequest,
    TaskPreviewResponse,
    TaskPreviewStep,
)

router = APIRouter(tags=["tasks"])
logger = logging.getLogger(__name__)

TASK_TITLE_DEFAULTS = {
    "docs": "Untitled Document",
    "sheets": "Untitled Spreadsheet",
    "slides": "Untitled Presentation",
}

TASK_TITLE_METADATA_KEYS = {
    "docs": ("title", "document_title"),
    "sheets": ("title", "sheet_title", "spreadsheet_title"),
    "slides": ("title", "deck_title", "presentation_title"),
}


def _build_task_kwargs(
    *,
    user_id: UUID,
    prompt: str,
    task_type: TaskType | str,
    metadata: dict | None,
) -> dict:
    """Build Task model kwargs with explicit task metadata mapping."""
    return {
        "user_id": user_id,
        "prompt": prompt,
        "task_type": task_type,
        "status": TaskStatus.PENDING,
        "task_metadata": metadata,
    }


def _resolve_task_title(task_type: str, metadata: dict | None) -> str:
    """Resolve task title from metadata with sensible per-type fallbacks."""
    fallback = TASK_TITLE_DEFAULTS.get(task_type)
    if fallback is None:
        raise ValueError(f"No title default configured for task type: {task_type}")

    if not isinstance(metadata, dict):
        return fallback

    for key in TASK_TITLE_METADATA_KEYS.get(task_type, ("title",)):
        value = metadata.get(key)
        if isinstance(value, str):
            normalized_value = value.strip()
            if normalized_value:
                return normalized_value

    return fallback


def _safe_status(value: TaskStatus) -> str:
    """Return a status string consistently for smart hint payloads."""
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _task_deep_link(task_id: UUID, section: str = "") -> str:
    """Build frontend deep-link for task actions.

    Frontend links power #280 Resume Card Deep-Link by enabling resume from
    notifications, alerts, and follow-up cards.
    """
    base = (settings.FRONTEND_URL or "").rstrip("/")
    if not base:
        base = "http://localhost:3000"

    task_id = str(task_id)
    if section:
        section = section.lstrip("/")
        return f"{base}/tasks/{task_id}/{section}"
    return f"{base}/tasks/{task_id}"


def _build_smart_exit_actions(task: TaskModel) -> list[SmartExitHintAction]:
    """Build prioritized follow-through actions for completed/failed/inflight tasks."""
    actions: list[SmartExitHintAction] = [
        SmartExitHintAction(
            id="view",
            label="View task",
            path=f"/api/v1/tasks/{task.id}",
            method="GET",
            description="Review task details and raw output.",
            enabled=True,
            requires_input=False,
            deep_link=_task_deep_link(task.id),
        )
    ]

    if task.status == TaskStatus.COMPLETED:
        actions.extend(
            [
                SmartExitHintAction(
                    id="share",
                    label="Create share link",
                    path=f"/api/v1/tasks/{task.id}/share",
                    method="POST",
                    description="Generate a public share link for teammates.",
                    requires_input=False,
                    deep_link=_task_deep_link(task.id, "share"),
                ),
                SmartExitHintAction(
                    id="schedule",
                    label="Schedule recurrence",
                    path=f"/api/v1/tasks/{task.id}/schedule",
                    method="POST",
                    description="Set this task to run on a cadence.",
                    requires_input=True,
                    deep_link=_task_deep_link(task.id, "schedule"),
                ),
                SmartExitHintAction(
                    id="poll",
                    label="Poll status",
                    path=f"/api/v1/tasks/{task.id}",
                    method="GET",
                    description="Confirm the final result is still available.",
                    deep_link=_task_deep_link(task.id),
                ),
            ]
        )
    elif task.status == TaskStatus.FAILED:
        actions.extend(
            [
                SmartExitHintAction(
                    id="recovery_deck",
                    label="Open recovery deck",
                    path=f"/api/v1/tasks/{task.id}/recovery-deck",
                    method="GET",
                    description="Get failure analysis and recovery guidance.",
                    deep_link=_task_deep_link(task.id, "recovery-deck"),
                ),
                SmartExitHintAction(
                    id="retry",
                    label="Retry task",
                    path=f"/api/v1/tasks/{task.id}/retry",
                    method="POST",
                    description="Clone and rerun with the same input.",
                    deep_link=_task_deep_link(task.id, "retry"),
                ),
                SmartExitHintAction(
                    id="resume_template",
                    label="Resume with template",
                    path=f"/api/v1/tasks/{task.id}/resume-template",
                    method="GET",
                    description="Get a resume payload with suggested improvements.",
                    deep_link=_task_deep_link(task.id, "resume-template"),
                ),
            ]
        )
    elif task.status in {TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.PROCESSING}:
        actions.extend(
            [
                SmartExitHintAction(
                    id="poll",
                    label="Poll status",
                    path=f"/api/v1/tasks/{task.id}",
                    method="GET",
                    description="Get the latest execution state.",
                    deep_link=_task_deep_link(task.id),
                ),
                SmartExitHintAction(
                    id="cancel",
                    label="Cancel task",
                    path=f"/api/v1/tasks/{task.id}",
                    method="DELETE",
                    description="Stop an in-flight task and release resources.",
                    deep_link=_task_deep_link(task.id, "cancel"),
                ),
            ]
        )
    else:
        actions.append(
            SmartExitHintAction(
                id="share",
                label="Create share link",
                path=f"/api/v1/tasks/{task.id}/share",
                method="POST",
                description="Generate a link if you want to reuse this output.",
                requires_input=False,
                deep_link=_task_deep_link(task.id, "share"),
            )
        )

    return actions[:3]


def _estimate_prompt_complexity(prompt: str) -> tuple[int, list[str]]:
    """Return a complexity penalty and human-readable reasons."""
    checks: list[str] = []
    penalty = 0
    normalized = prompt.strip()

    # Length-based complexity risk.
    char_count = len(normalized)
    if char_count > 3000:
        penalty += 30
        checks.append("Prompt is very long; split into smaller tasks to reduce failure risk.")
    elif char_count > 1800:
        penalty += 18
        checks.append("Prompt is long; consider narrowing scope before execution.")

    words = re.findall(r"\w+", normalized)
    if len(words) > 500:
        penalty += 12
        checks.append("Prompt has many sections; reduce to top 3 goals for stability.")
    elif len(words) > 250:
        penalty += 8

    # Instruction ambiguity risk.
    ambiguous_markers = ["everything", "all", "entire", "as much as possible"]
    lower_prompt = normalized.lower()
    if any(marker in lower_prompt for marker in ambiguous_markers):
        penalty += 8
        checks.append("Prompt contains broad instructions; define explicit scope.")

    return penalty, checks


def _compute_risk_level(score: int) -> str:
    """Bucket reliability score into human-readable risk levels."""
    if score >= 80:
        return "low"
    if score >= 60:
        return "medium"
    return "high"


def _requires_google_workspace(task_type: TaskType) -> bool:
    """Whether a task type depends on Google credentials."""
    return task_type in {TaskType.DOCS, TaskType.SHEETS, TaskType.SLIDES}


async def _build_reliability_signal(
    task_type: TaskType,
    prompt: str,
    current_user: User,
    db: AsyncSession,
) -> dict:
    """Return a deterministic reliability profile before task execution."""
    checks: list[ReliabilityGateCheck] = []
    score = 100
    recommendations: list[str] = []

    # Credential checks.
    if _requires_google_workspace(task_type) and not current_user.google_access_token:
        score -= 45
        checks.append(
            ReliabilityGateCheck(
                id="google_auth",
                name="Google credentials",
                status="fail",
                message="Google credentials are missing or expired.",
                suggested_action="Reconnect Google account",
                suggested_path="/api/v1/auth/google",
            )
        )
        recommendations.append("Connect Google first to avoid immediate auth failures.")
    else:
        checks.append(
            ReliabilityGateCheck(
                id="google_auth",
                name="Google credentials",
                status="pass",
                message="Google credentials are available.",
                suggested_action="",
            )
        )

    # Prompt complexity checks.
    complexity_penalty, complexity_checks = _estimate_prompt_complexity(prompt)
    score -= complexity_penalty
    for check in complexity_checks:
        checks.append(
            ReliabilityGateCheck(
                id="prompt_complexity",
                name="Prompt scope",
                status="warning",
                message=check,
                suggested_action="Simplify/trim prompt",
            )
        )

    # Historical failure checks from this user/task_type.
    lookback_days = 14
    recent_window_start = datetime.now(tz=timezone.utc) - timedelta(days=lookback_days)
    recent_tasks = (
        await db.execute(
            select(TaskModel)
            .where(
                TaskModel.user_id == current_user.id,
                TaskModel.task_type == task_type,
                TaskModel.created_at >= recent_window_start,
            )
            .order_by(TaskModel.created_at.desc())
            .limit(40)
        )
    ).scalars().all()

    total_recent = len(recent_tasks)
    failed_recent = [t for t in recent_tasks if t.status == TaskStatus.FAILED]
    failed_count = len(failed_recent)
    failure_rate = (failed_count / total_recent) if total_recent else 0.0

    # Similar prompt repetition penalty.
    repeated_failures = sum(
        1 for t in failed_recent if t.prompt.strip().lower() == prompt.strip().lower()
    )

    if total_recent >= 5:
        score -= int(failure_rate * 45)

    if failed_count >= 4:
        score -= 18
        checks.append(
            ReliabilityGateCheck(
                id="recent_failures",
                name="Recent failure pattern",
                status="warning",
                message=(
                    f"{failed_count} failures in the last {lookback_days} days "
                    "for this task type."
                ),
                suggested_action="Review recovery deck and template before retry",
            )
        )
        recommendations.append(
            "Repeat failures detected. Use Recovery Deck for guided remediation."
        )

    if repeated_failures:
        score -= min(25, repeated_failures * 8)
        checks.append(
            ReliabilityGateCheck(
                id="repeated_prompt",
                name="Repeated prompt failures",
                status="warning",
                message=(
                    f"This exact prompt failed {repeated_failures} time(s) "
                    "recently."
                ),
                suggested_action="Retry with a simplified version",
                suggested_path="/api/v1/tasks/{id}/recovery-deck",
            )
        )
        recommendations.append(
            "Use a slightly narrowed version of the prompt before re-running."
        )

    # Safety net.
    score = max(20, min(100, score))
    reliability_score = score
    go_no_go = reliability_score >= 65

    checks.append(
        ReliabilityGateCheck(
            id="execution_readiness",
            name="Execution readiness",
            status="pass" if go_no_go else "fail",
            message=(
                "Execution can proceed immediately."
                if go_no_go
                else "Execution should be delayed until key issues are addressed."
            ),
            suggested_action=("Proceed" if go_no_go else "Address warnings and rerun gate."),
            suggested_path=None,
        )
    )

    if not recommendations:
        recommendations.append("No blocking issues detected. You can proceed with execution.")

    return {
        "reliability_score": reliability_score,
        "failure_probability": round(1 - (reliability_score / 100), 3),
        "risk_level": _compute_risk_level(reliability_score),
        "go_no_go": go_no_go,
        "recent_failures": failed_count,
        "repeat_failure_count": repeated_failures,
        "checks": checks,
        "recommendations": recommendations,
    }


@router.post("/", response_model=Task, status_code=status.HTTP_201_CREATED)
async def create_task(
    task_data: TaskCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Create a new task.
    
    Args:
        task_data: Task creation data
        current_user: Authenticated user
        db: Database session
        
    Returns:
        Task: Created task
    """
    # Create task
    task_kwargs = _build_task_kwargs(
        user_id=current_user.id,
        prompt=task_data.prompt,
        task_type=task_data.task_type,
        metadata=task_data.metadata,
    )
    task = TaskModel(**task_kwargs)
    
    db.add(task)
    
    # Update user's last task created timestamp for activity tracking
    from datetime import datetime, timezone
    current_user.last_task_created_at = datetime.now(timezone.utc)
    
    await db.commit()
    await db.refresh(task)
    
    # Emit WebSocket event: task created
    await ws_manager.task_created(current_user.id, task.id, str(task_data.task_type.value))

    # Queue task to Celery based on task_type
    try:
        from app.agents.celery_app import (
            process_research_task,
            process_docs_task,
            process_sheets_task,
            process_slides_task,
        )
        
        task_id_str = str(task.id)
        user_id_str = str(current_user.id)
        
        if task_data.task_type == "research":
            celery_task = process_research_task.apply_async(
                args=[task_id_str, task_data.prompt, user_id_str]
            )
        elif task_data.task_type == "docs":
            title = _resolve_task_title("docs", task_data.metadata)
            celery_task = process_docs_task.apply_async(
                args=[task_id_str, task_data.prompt, user_id_str, title]
            )
        elif task_data.task_type == "sheets":
            title = _resolve_task_title("sheets", task_data.metadata)
            celery_task = process_sheets_task.apply_async(
                args=[task_id_str, task_data.prompt, user_id_str, title]
            )
        elif task_data.task_type == "slides":
            title = _resolve_task_title("slides", task_data.metadata)
            celery_task = process_slides_task.apply_async(
                args=[task_id_str, task_data.prompt, user_id_str, title]
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown task type: {task_data.task_type}",
            )
        
        # Store Celery task ID
        task.celery_task_id = celery_task.id
        task.status = TaskStatus.IN_PROGRESS
        await db.commit()
        await db.refresh(task)
        
    except Exception as e:
        # If Celery queuing fails, mark task as failed
        task.status = TaskStatus.FAILED
        task.error_message = f"Failed to queue task: {str(e)}"
        await db.commit()
        logger.error(f"Failed to queue task {task.id}: {str(e)}")
        await ws_manager.task_failed(current_user.id, task.id, str(e))
    
    return task


def _preview_to_response(preview) -> TaskPreviewResponse:
    """Convert a PreviewResult to a TaskPreviewResponse."""
    return TaskPreviewResponse(
        preview_id=preview.preview_id,
        prompt=preview.prompt,
        task_type=preview.task_type,
        steps=[
            TaskPreviewStep(
                order=s.order,
                description=s.description,
                agent_type=s.agent_type,
                detail=s.detail,
            )
            for s in preview.steps
        ],
        output_format=preview.output_format,
        estimated_time_seconds=preview.estimated_time_seconds,
        estimated_cost_usd=preview.estimated_cost_usd,
        estimated_tokens=preview.estimated_tokens,
        notes=preview.notes,
        metadata=preview.metadata,
        smart=getattr(preview, "smart", False),
        original_prompt=getattr(preview, "original_prompt", None),
    )


async def _get_llm_caller():
    """Build a lightweight LLM caller for smart previews.

    Returns None if no API key is available (triggers heuristic fallback).
    """
    from app.core.config import settings

    api_key = getattr(settings, "OPENAI_API_KEY", None)
    if not api_key:
        return None

    async def caller(system_prompt: str, user_prompt: str) -> str:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import SystemMessage, HumanMessage

        llm = ChatOpenAI(
            model="gpt-3.5-turbo",
            temperature=0.3,
            max_tokens=1000,
            api_key=api_key,
        )
        resp = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        return resp.content

    return caller


@router.post(
    "/reliability-gate",
    response_model=PreRunReliabilityResponse,
    status_code=status.HTTP_200_OK,
)
async def run_reliability_gate(
    request: PreRunReliabilityRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Run a pre-execution reliability gate for one task run (#261).

    Returns an execution readiness signal before queueing, including:
    - estimated failure probability/risk score
    - history-based failure pattern signal
    - actionable remediation options for a safer retry
    """
    reliability = await _build_reliability_signal(
        request.task_type,
        request.prompt,
        current_user,
        db,
    )

    return PreRunReliabilityResponse(
        task_type=request.task_type,
        reliability_score=reliability["reliability_score"],
        failure_probability=reliability["failure_probability"],
        risk_level=reliability["risk_level"],
        go_no_go=reliability["go_no_go"],
        recent_failures=reliability["recent_failures"],
        repeat_failure_count=reliability["repeat_failure_count"],
        checks=reliability["checks"],
        recommendations=reliability["recommendations"],
        can_execute_immediately=reliability["go_no_go"],
    )


@router.post("/preview", response_model=TaskPreviewResponse)
async def preview_task(
    request: TaskPreviewRequest,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Generate an execution preview for a task without running it.

    Returns a step-by-step plan with estimated time, cost, and tokens.
    The preview is cached for 10 minutes. Use the returned ``preview_id``
    to execute the task via ``POST /tasks/preview/{preview_id}/execute``.

    Set ``smart=true`` to use an LLM for contextual step descriptions
    (falls back to heuristic if the LLM is unavailable).
    """
    from app.services.task_preview import TaskPreviewService

    svc = TaskPreviewService()
    task_type = request.task_type.value if hasattr(request.task_type, "value") else str(request.task_type)

    if request.smart:
        llm_caller = await _get_llm_caller()
        preview = await svc.generate_smart_preview(
            prompt=request.prompt,
            task_type=task_type,
            metadata=request.metadata,
            user_id=str(current_user.id),
            llm_caller=llm_caller,
        )
    else:
        preview = svc.generate_preview(
            prompt=request.prompt,
            task_type=task_type,
            metadata=request.metadata,
            user_id=str(current_user.id),
        )

    return _preview_to_response(preview)


@router.get("/preview/{preview_id}", response_model=TaskPreviewResponse)
async def get_preview(
    preview_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Retrieve a cached task preview by ID.

    Previews expire after 10 minutes.
    """
    from app.services.task_preview import TaskPreviewService

    svc = TaskPreviewService()
    preview = svc.get_preview(preview_id)

    if preview is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Preview not found or expired",
        )

    return _preview_to_response(preview)


@router.put("/preview/{preview_id}", response_model=TaskPreviewResponse)
async def modify_preview(
    preview_id: str,
    request: TaskPreviewModifyRequest,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Modify the prompt of an existing preview and regenerate.

    Consumes the old preview and returns a new one with a fresh
    ``preview_id``.  The ``original_prompt`` field shows what was
    changed from.

    Set ``smart=true`` for LLM-powered regeneration.
    """
    from app.services.task_preview import TaskPreviewService

    svc = TaskPreviewService()

    if request.smart:
        llm_caller = await _get_llm_caller()
        preview = await svc.modify_preview_smart(
            preview_id=preview_id,
            new_prompt=request.prompt,
            llm_caller=llm_caller,
            user_id=str(current_user.id),
        )
    else:
        preview = svc.modify_preview(
            preview_id=preview_id,
            new_prompt=request.prompt,
            user_id=str(current_user.id),
        )

    if preview is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Preview not found, expired, or already executed",
        )

    return _preview_to_response(preview)


@router.post("/preview/{preview_id}/execute", response_model=Task, status_code=status.HTTP_201_CREATED)
async def execute_preview(
    preview_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Execute a previously generated preview.

    Consumes the preview (single-use) and creates a real task from
    the previewed prompt and task type.
    """
    from app.services.task_preview import TaskPreviewService

    svc = TaskPreviewService()
    preview = svc.consume_preview(preview_id)

    if preview is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Preview not found, expired, or already executed",
        )

    # Create the task from the preview
    task_type_val = preview.task_type
    preview_metadata = dict(preview.metadata or {})
    if not isinstance(preview_metadata, dict):
        preview_metadata = {}

    preview_metadata.update(
        {
            "preview_id": preview.preview_id,
            "estimated_cost_usd": preview.estimated_cost_usd,
            "estimated_tokens": preview.estimated_tokens,
            "estimated_time_seconds": preview.estimated_time_seconds,
            "source": "preview",
        }
    )

    task_kwargs = _build_task_kwargs(
        user_id=current_user.id,
        prompt=preview.prompt,
        task_type=task_type_val,
        metadata=preview_metadata,
    )
    task = TaskModel(**task_kwargs)

    db.add(task)
    await db.commit()
    await db.refresh(task)

    await ws_manager.task_created(current_user.id, task.id, task_type_val)

    # Queue to Celery
    try:
        from app.agents.celery_app import (
            process_research_task,
            process_docs_task,
            process_sheets_task,
            process_slides_task,
        )

        task_id_str = str(task.id)
        user_id_str = str(current_user.id)

        if task_type_val == "research":
            celery_task = process_research_task.apply_async(
                args=[task_id_str, preview.prompt, user_id_str]
            )
        elif task_type_val == "docs":
            title = _resolve_task_title("docs", preview.metadata)
            celery_task = process_docs_task.apply_async(
                args=[task_id_str, preview.prompt, user_id_str, title]
            )
        elif task_type_val == "sheets":
            title = _resolve_task_title("sheets", preview.metadata)
            celery_task = process_sheets_task.apply_async(
                args=[task_id_str, preview.prompt, user_id_str, title]
            )
        elif task_type_val == "slides":
            title = _resolve_task_title("slides", preview.metadata)
            celery_task = process_slides_task.apply_async(
                args=[task_id_str, preview.prompt, user_id_str, title]
            )
        else:
            raise ValueError(f"Unknown task type: {task_type_val}")

        task.celery_task_id = celery_task.id
        task.status = TaskStatus.IN_PROGRESS
        await db.commit()
        await db.refresh(task)

    except Exception as e:
        task.status = TaskStatus.FAILED
        task.error_message = f"Failed to queue task: {str(e)}"
        await db.commit()
        logger.error(f"Failed to queue previewed task {task.id}: {str(e)}")
        await ws_manager.task_failed(current_user.id, task.id, str(e))

    return task


@router.get("/", response_model=TaskList)
async def list_tasks(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: TaskStatus | None = None,
):
    """
    List user tasks.
    
    Args:
        current_user: Authenticated user
        db: Database session
        page: Page number
        page_size: Items per page
        status: Filter by status
        
    Returns:
        TaskList: List of tasks with pagination
    """
    # Build query
    query = select(TaskModel).where(TaskModel.user_id == current_user.id)
    
    if status:
        query = query.where(TaskModel.status == status)
    
    query = query.order_by(TaskModel.created_at.desc())
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()
    
    # Apply pagination
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    # Execute query
    result = await db.execute(query)
    tasks = result.scalars().all()
    
    return TaskList(
        tasks=tasks,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{task_id}", response_model=Task)
async def get_task(
    task_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get task by ID.
    
    Args:
        task_id: Task ID
        current_user: Authenticated user
        db: Database session
        
    Returns:
        Task: Task details
    """
    result = await db.execute(
        select(TaskModel).where(
            TaskModel.id == task_id,
            TaskModel.user_id == current_user.id,
        )
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    
    return task


@router.get(
    "/{task_id}/smart-exit-hints",
    response_model=SmartExitHintsResponse,
    status_code=status.HTTP_200_OK,
)
async def get_smart_exit_hints(
    task_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Return concise follow-up actions after a task finishes or stalls (#260).

    This endpoint powers the post-task experience by suggesting next actions
    based on status:
    - completed: share, schedule, or re-check
    - failed: recovery and retry paths
    - in-flight: poll + cancel
    """
    result = await db.execute(
        select(TaskModel).where(
            TaskModel.id == task_id,
            TaskModel.user_id == current_user.id,
        )
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    if task.status == TaskStatus.COMPLETED:
        next_focus = "Share or schedule this outcome"
    elif task.status == TaskStatus.FAILED:
        next_focus = "Recover and rerun with fixes"
    elif task.status in {TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.PROCESSING}:
        next_focus = "Monitor progress or cancel"
    else:
        next_focus = "Review output and decide next steps"

    return SmartExitHintsResponse(
        task_id=task.id,
        task_type=str(task.task_type.value if hasattr(task.task_type, "value") else task.task_type),
        status=_safe_status(task.status),
        next_focus=next_focus,
        actions=_build_smart_exit_actions(task),
    )


@router.post("/{task_id}/retry", response_model=Task, status_code=status.HTTP_201_CREATED)
async def retry_task(
    task_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Retry a failed task.

    Only tasks in FAILED status can be retried.  A clone of the original task
    is created with status PENDING and queued to Celery; the original task is
    left untouched.

    Args:
        task_id: Original (failed) task ID
        current_user: Authenticated user
        db: Database session

    Returns:
        Task: The newly created retry task
    """
    result = await db.execute(
        select(TaskModel).where(
            TaskModel.id == task_id,
            TaskModel.user_id == current_user.id,
        )
    )
    original = result.scalar_one_or_none()

    if not original:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    if original.status != TaskStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only failed tasks can be retried (current status: {original.status})",
        )

    # Clone the task with reset status
    retry_metadata = original.task_metadata
    if not isinstance(retry_metadata, dict):
        retry_metadata = {}
    else:
        retry_metadata = dict(retry_metadata)

    retry_depth = retry_metadata.get("retry_depth", 0)
    try:
        retry_depth = int(retry_depth)
    except (TypeError, ValueError):
        retry_depth = 0

    retry_metadata.update(
        {
            "retry_depth": retry_depth + 1,
            "retry_of": str(original.id),
        }
    )

    task_kwargs = _build_task_kwargs(
        user_id=current_user.id,
        prompt=original.prompt,
        task_type=original.task_type,
        metadata=retry_metadata,
    )
    retry_task_obj = TaskModel(**task_kwargs)

    db.add(retry_task_obj)
    
    # Update user's last task created timestamp for activity tracking
    from datetime import datetime, timezone
    current_user.last_task_created_at = datetime.now(timezone.utc)
    
    await db.commit()
    await db.refresh(retry_task_obj)

    # Emit WebSocket event: retry task created
    task_type_val = str(original.task_type.value if hasattr(original.task_type, "value") else original.task_type)
    await ws_manager.task_created(current_user.id, retry_task_obj.id, task_type_val)

    # Queue to Celery (mirrors create_task logic)
    try:
        from app.agents.celery_app import (
            process_docs_task,
            process_research_task,
            process_sheets_task,
            process_slides_task,
        )

        task_id_str = str(retry_task_obj.id)
        user_id_str = str(current_user.id)
        task_type_val = str(original.task_type.value if hasattr(original.task_type, "value") else original.task_type)

        if task_type_val == "research":
            celery_task = process_research_task.apply_async(
                args=[task_id_str, original.prompt, user_id_str]
            )
        elif task_type_val == "docs":
            title = _resolve_task_title("docs", original.task_metadata)
            celery_task = process_docs_task.apply_async(
                args=[task_id_str, original.prompt, user_id_str, title]
            )
        elif task_type_val == "sheets":
            title = _resolve_task_title("sheets", original.task_metadata)
            celery_task = process_sheets_task.apply_async(
                args=[task_id_str, original.prompt, user_id_str, title]
            )
        elif task_type_val == "slides":
            title = _resolve_task_title("slides", original.task_metadata)
            celery_task = process_slides_task.apply_async(
                args=[task_id_str, original.prompt, user_id_str, title]
            )
        else:
            raise ValueError(f"Unknown task type: {task_type_val}")

        retry_task_obj.celery_task_id = celery_task.id
        retry_task_obj.status = TaskStatus.IN_PROGRESS
        await db.commit()
        await db.refresh(retry_task_obj)

    except Exception as e:
        retry_task_obj.status = TaskStatus.FAILED
        retry_task_obj.error_message = f"Failed to queue retry task: {str(e)}"
        await db.commit()
        await db.refresh(retry_task_obj)
        logger.error(f"Failed to queue retry for task {task_id}: {str(e)}")
        await ws_manager.task_failed(current_user.id, retry_task_obj.id, str(e))

    return retry_task_obj


@router.post("/{task_id}/share", response_model=ShareLinkResponse, status_code=status.HTTP_200_OK)
async def create_share_link(
    task_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    ttl_days: int = Query(default=7, ge=1, le=365, description="Share link TTL in days"),
):
    """Generate (or refresh) a public share link for a task.

    - Creates a unique ``share_token`` on the task.
    - Sets ``expires_at`` to ``now + ttl_days``.
    - Calling again overwrites the previous token/expiry.
    - The share link is accessible at ``GET /r/{share_token}``.

    Args:
        task_id: Task to share (must belong to the authenticated user)
        ttl_days: Days until the share link expires (default 7, max 365)

    Returns:
        ShareLinkResponse with the token, URL, and expiry timestamp
    """
    result = await db.execute(
        select(TaskModel).where(
            TaskModel.id == task_id,
            TaskModel.user_id == current_user.id,
        )
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    # (Re-)generate share token and expiry
    new_token = uuid4()
    now_utc = datetime.now(tz=timezone.utc)
    expires = now_utc + timedelta(days=ttl_days)

    task.share_token = new_token
    task.expires_at = expires
    await db.commit()
    await db.refresh(task)

    share_url = f"/r/{new_token}"
    logger.info(
        "Share link created for task %s by user %s — expires %s",
        task_id,
        current_user.id,
        expires.isoformat(),
    )

    return ShareLinkResponse(
        task_id=task.id,
        share_token=new_token,
        share_url=share_url,
        expires_at=expires,
    )


@router.get("/{task_id}/recovery")
async def get_error_recovery(
    task_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get user-friendly error recovery info for a failed task.

    Returns actionable suggestions so the frontend can render helpful
    recovery UI instead of raw technical error messages.

    Only available for tasks in FAILED status.
    """
    from app.services.error_recovery import classify_error, error_to_dict

    result = await db.execute(
        select(TaskModel).where(
            TaskModel.id == task_id,
            TaskModel.user_id == current_user.id,
        )
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    if task.status != TaskStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Recovery info is only available for failed tasks (current status: {task.status})",
        )

    friendly = classify_error(task.error_message)
    return {
        "task_id": str(task.id),
        "error": error_to_dict(friendly),
    }


@router.get("/{task_id}/recovery-deck")
async def get_recovery_deck(
    task_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get structured recovery guidance for a failed task.

    In addition to the friendly error payload, this endpoint returns:
    - failure class/stage (for UI grouping)
    - actionable checklist and rewrite suggestions
    - one-click retry hint for quick recovery loops
    """
    from app.services.error_recovery import build_recovery_deck, classify_error, error_to_dict

    result = await db.execute(
        select(TaskModel).where(
            TaskModel.id == task_id,
            TaskModel.user_id == current_user.id,
        )
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    if task.status != TaskStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Recovery info is only available for failed tasks (current status: {task.status})",
        )

    # Count repeated failures for the same user/task template.
    recent_failures = await db.scalar(
        select(func.count())
        .where(
            TaskModel.user_id == current_user.id,
            TaskModel.task_type == task.task_type,
            TaskModel.prompt == task.prompt,
            TaskModel.status == TaskStatus.FAILED,
            TaskModel.id != task.id,
        )
    )

    friendly = classify_error(task.error_message)
    deck = build_recovery_deck(
        task.error_message,
        repeat_failure_count=int(recent_failures or 0),
    )
    deck["one_click_retry"] = {
        "enabled": True,
        "label": "Retry task",
        "method": "POST",
        "path": f"/api/v1/tasks/{task.id}/retry",
    }

    return {
        "task_id": str(task.id),
        "error": error_to_dict(friendly),
        "recovery_deck": deck,
    }


@router.get("/{task_id}/resume-template")
async def get_resume_template(
    task_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Build a one-click resume blueprint for a failed task.

    This endpoint is part of the "One-Second Resume" flow (#258):
    it provides everything needed for a fast retry experience, including
    the original execution context and suggested rewrite options.
    """
    from app.services.error_recovery import build_recovery_deck, classify_error, error_to_dict

    result = await db.execute(
        select(TaskModel).where(
            TaskModel.id == task_id,
            TaskModel.user_id == current_user.id,
        )
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    if task.status != TaskStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Resume template is only available for failed tasks "
                f"(current status: {task.status})"
            ),
        )

    recent_failures = await db.scalar(
        select(func.count())
        .where(
            TaskModel.user_id == current_user.id,
            TaskModel.task_type == task.task_type,
            TaskModel.prompt == task.prompt,
            TaskModel.status == TaskStatus.FAILED,
            TaskModel.id != task.id,
        )
    )

    friendly = classify_error(task.error_message)
    deck = build_recovery_deck(
        task.error_message,
        repeat_failure_count=int(recent_failures or 0),
    )

    resume_payload = {
        "task_id": str(task.id),
        "task_type": task.task_type.value,
        "prompt": task.prompt,
        "task_metadata": task.task_metadata or {},
        "retry": {
            "enabled": True,
            "method": "POST",
            "path": f"/api/v1/tasks/{task.id}/retry",
            "label": "Resume immediately",
        },
        "error": error_to_dict(friendly),
        "recovery_deck": deck,
        "preflight": {
            "checks": deck.get("checklist", []),
            "rewrite_suggestions": deck.get("rewrite_suggestions", []),
            "failure_stage": deck.get("failure_stage"),
            "qa_failure_class": deck.get("qa_failure_class"),
            "auto_retry_available": deck.get("auto_retry_available", False),
            "repeat_failure_count": int(recent_failures or 0),
        },
    }

    return resume_payload


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_task(
    task_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Cancel a task.
    
    Args:
        task_id: Task ID
        current_user: Authenticated user
        db: Database session
    """
    result = await db.execute(
        select(TaskModel).where(
            TaskModel.id == task_id,
            TaskModel.user_id == current_user.id,
        )
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    
    if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot cancel completed, failed, or already cancelled task",
        )
    
    # Update task status
    task.status = TaskStatus.CANCELLED
    await db.commit()

    # Emit WebSocket event: task cancelled
    await ws_manager.task_cancelled(current_user.id, task.id)

    # Cancel Celery task if it exists
    if task.celery_task_id:
        try:
            from app.agents.celery_app import celery_app
            celery_app.control.revoke(task.celery_task_id, terminate=True)
            logger.info(f"Cancelled Celery task {task.celery_task_id} for task {task_id}")
        except Exception as e:
            logger.error(f"Failed to cancel Celery task {task.celery_task_id}: {str(e)}")
            # Don't fail the request if Celery cancellation fails
