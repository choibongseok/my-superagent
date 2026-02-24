from __future__ import annotations

"""Analytics API for Agent Performance metrics and LangFuse data visualization.

This module provides endpoints for:
- Real-time performance metrics
- LLM cost tracking
- Agent comparison views
- Task success rates
- LangFuse trace data
"""

from collections import defaultdict
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime, timedelta
import logging

from app.core.database import get_db
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.api.v1.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])


# Pydantic models for responses
from pydantic import BaseModel, Field


class PerformanceMetrics(BaseModel):
    """Real-time performance metrics."""
    avg_response_time_seconds: float = Field(..., description="Average task completion time")
    success_rate: float = Field(..., description="Task success rate (0-1)")
    total_tasks: int = Field(..., description="Total tasks executed")
    completed_tasks: int = Field(..., description="Successfully completed tasks")
    failed_tasks: int = Field(..., description="Failed tasks")
    pending_tasks: int = Field(..., description="Currently pending tasks")


class AgentStats(BaseModel):
    """Statistics for a specific agent type."""
    agent_type: str
    task_count: int
    avg_duration_seconds: float
    success_rate: float
    total_cost_usd: float = 0.0  # Placeholder for future LLM cost tracking


class CostBreakdown(BaseModel):
    """LLM cost breakdown by agent and model."""
    total_cost_usd: float
    by_agent: Dict[str, float]
    by_model: Dict[str, float]
    by_date: Dict[str, float]


class TaskTrend(BaseModel):
    """Task execution trend over time."""
    date: str
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    avg_duration_seconds: float


class CostTrustTaskCard(BaseModel):
    """Task-level cost and trust snapshot for transparent execution insights."""

    task_id: UUID
    task_type: str
    status: str
    prompt: str
    created_at: datetime
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    estimated_cost_usd: float = 0.0
    actual_cost_usd: float = 0.0
    estimated_tokens: int = 0
    actual_tokens: int = 0
    retry_depth: int = 0
    trust_score: float | None = None
    model: str | None = None


class CostTrustDashboard(BaseModel):
    """Cost + trust dashboard for task execution transparency."""

    period_start: str
    period_end: str
    time_range_hours: int
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    cancelled_tasks: int
    total_estimated_cost_usd: float
    total_actual_cost_usd: float
    total_estimated_tokens: int
    total_actual_tokens: int
    avg_completion_time_seconds: float
    average_trust_score: float | None
    retry_tasks: int
    retry_rate: float
    budget_limit_usd: float | None = None
    projected_monthly_cost_usd: float | None = None
    budget_used_pct: float | None = None
    budget_status: str | None = None
    budget_warning: str | None = None
    trust_health: str = Field(default="stable", description="Trust signal derived from quality scores")
    recommendations: list[str] = Field(default_factory=list)
    cards: list[CostTrustTaskCard]



def _truncate_text(value: str, max_length: int) -> str:
    """Normalize and truncate free-form prompt/result text for cards."""
    normalized = " ".join(value.split())
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 1].rstrip() + "…"


def _collect_outcome_actions(task: Task) -> list[OutcomeAction]:
    """Build next-step actions for a task outcome."""
    actions: list[OutcomeAction] = [
        OutcomeAction(
            id="view-task",
            label="View task",
            path=f"/api/v1/tasks/{task.id}",
            method="GET",
            description="Open task details.",
        )
    ]

    if task.status == TaskStatus.COMPLETED:
        actions.append(
            OutcomeAction(
                id="share",
                label="Share result",
                path=f"/api/v1/tasks/{task.id}/share",
                method="POST",
                description="Generate a share link for this output.",
            )
        )
        actions.append(
            OutcomeAction(
                id="schedule",
                label="Schedule recurrence",
                path=f"/api/v1/tasks/{task.id}/schedule",
                method="POST",
                description="Turn this task into a recurring schedule.",
            )
        )
    elif task.status == TaskStatus.FAILED:
        actions.append(
            OutcomeAction(
                id="recovery",
                label="Open recovery deck",
                path=f"/api/v1/tasks/{task.id}/recovery-deck",
                method="GET",
                description="Get step-by-step recovery guidance.",
            )
        )
        actions.append(
            OutcomeAction(
                id="retry",
                label="Retry task",
                path=f"/api/v1/tasks/{task.id}/retry",
                method="POST",
                description="Retry immediately with same settings.",
            )
        )
    elif task.status in {TaskStatus.PENDING, TaskStatus.IN_PROGRESS}:
        actions.append(
            OutcomeAction(
                id="retry-queued",
                label="Poll progress",
                path=f"/api/v1/tasks/{task.id}",
                method="GET",
                description="Check for status updates.",
            )
        )

    return actions


def _safe_task_type(value: TaskStatus | str) -> str:
    """Return a consistent task type string."""
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _safe_status(value: TaskStatus | str) -> str:
    """Return a consistent status string."""
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _failure_category(task: Task) -> str | None:
    """Map failed task messages to recovery categories."""
    if task.status != TaskStatus.FAILED:
        return None

    try:
        from app.services.error_recovery import classify_error

        return classify_error(task.error_message).category.value
    except Exception:
        return None


def _meta_dict(value: Any) -> dict[str, Any]:
    """Return a dict for task/task-result metadata payloads."""
    return value if isinstance(value, dict) else {}


def _extract_float(value: Any, keys: tuple[str, ...], default: float = 0.0) -> float:
    """Pick the first float-convertible value for the given keys."""
    for key in keys:
        if key in value and value[key] is not None:
            try:
                return float(value[key])
            except (TypeError, ValueError):
                continue
    return default


def _extract_int(value: Any, keys: tuple[str, ...], default: int = 0) -> int:
    """Pick the first int-convertible value for the given keys."""
    for key in keys:
        if key in value and value[key] is not None:
            try:
                return int(value[key])
            except (TypeError, ValueError):
                continue
    return default


def _build_task_cost_snapshot(task: Task) -> dict[str, Any]:
    """Build a stable cost/trust metadata snapshot for a single task."""
    metadata = _meta_dict(getattr(task, "task_metadata", None))
    result = _meta_dict(getattr(task, "result", None))
    result_meta = _meta_dict(result.get("metadata", {}))

    model = (
        metadata.get("model")
        or metadata.get("llm_model")
        or result.get("model")
        or result_meta.get("model")
        or result_meta.get("llm_model")
    )

    return {
        "estimated_cost_usd": _extract_float(
            {**metadata, **result},
            ("estimated_cost_usd", "estimated_cost", "cost_estimate", "estimated_spend_usd"),
            0.0,
        ),
        "actual_cost_usd": _extract_float(
            {**metadata, **result},
            ("actual_cost_usd", "actual_cost", "final_cost_usd", "spent_usd"),
            0.0,
        ),
        "estimated_tokens": _extract_int(
            {**metadata, **result},
            ("estimated_tokens", "estimated_token_count", "token_estimate"),
            0,
        ),
        "actual_tokens": _extract_int(
            {**metadata, **result},
            ("actual_tokens", "token_count", "tokens"),
            0,
        ),
        "retry_depth": max(0, _extract_int(metadata, ("retry_depth", "retry_count"), 0)),
        "model": model,
    }


async def _build_qa_score_map(db: AsyncSession, tasks: list[Task]) -> dict[UUID, float]:
    """Build latest QA score per task (if available)."""
    from app.models.qa_result import QAResult

    if not tasks:
        return {}

    task_ids = [t.id for t in tasks]
    qa_query = select(QAResult.task_id, func.avg(QAResult.overall_score)).where(
        QAResult.task_id.in_(task_ids)
    ).group_by(QAResult.task_id)

    rows = (await db.execute(qa_query)).all()
    return {row[0]: round(float(row[1]), 2) for row in rows if row[1] is not None}


@router.get("/performance", response_model=PerformanceMetrics)
async def get_performance_metrics(
    current_user: User = Depends(get_current_user),
    time_range_hours: int = Query(24, ge=1, le=168),  # 1 hour to 1 week
    db: AsyncSession = Depends(get_db),
):
    """
    Get real-time performance metrics for the current user.
    
    **Metrics include:**
    - Average response time
    - Success rate
    - Task counts by status
    
    **Parameters:**
    - `time_range_hours`: Time range for metrics (1-168 hours, default: 24)
    """
    try:
        # Calculate time threshold
        time_threshold = datetime.utcnow() - timedelta(hours=time_range_hours)
        
        # Get all tasks in time range
        query = select(Task).where(
            and_(
                Task.user_id == current_user.id,
                Task.created_at >= time_threshold
            )
        )
        result = await db.execute(query)
        tasks = result.scalars().all()
        
        if not tasks:
            return PerformanceMetrics(
                avg_response_time_seconds=0.0,
                success_rate=0.0,
                total_tasks=0,
                completed_tasks=0,
                failed_tasks=0,
                pending_tasks=0,
            )
        
        # Calculate metrics
        total_tasks = len(tasks)
        completed_tasks = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
        failed_tasks = sum(1 for t in tasks if t.status == TaskStatus.FAILED)
        pending_tasks = sum(1 for t in tasks if t.status == TaskStatus.PENDING)
        
        # Calculate average response time (only for completed tasks)
        completed_with_time = [
            (t.completed_at - t.created_at).total_seconds()
            for t in tasks
            if t.status == TaskStatus.COMPLETED and t.completed_at
        ]
        avg_response_time = (
            sum(completed_with_time) / len(completed_with_time)
            if completed_with_time else 0.0
        )
        
        success_rate = completed_tasks / total_tasks if total_tasks > 0 else 0.0
        
        logger.info(
            f"Performance metrics calculated for user {current_user.id}: "
            f"{completed_tasks}/{total_tasks} tasks completed"
        )
        
        return PerformanceMetrics(
            avg_response_time_seconds=round(avg_response_time, 2),
            success_rate=round(success_rate, 4),
            total_tasks=total_tasks,
            completed_tasks=completed_tasks,
            failed_tasks=failed_tasks,
            pending_tasks=pending_tasks,
        )
        
    except Exception as e:
        logger.error(f"Failed to calculate performance metrics: {e}")
        raise


@router.get("/agents", response_model=List[AgentStats])
async def get_agent_statistics(
    current_user: User = Depends(get_current_user),
    time_range_hours: int = Query(24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
):
    """
    Get statistics breakdown by agent type.
    
    **Returns:**
    - Task count per agent
    - Average duration per agent
    - Success rate per agent
    """
    try:
        time_threshold = datetime.utcnow() - timedelta(hours=time_range_hours)
        
        # Query tasks grouped by task_type (agent type)
        query = select(
            Task.task_type,
            func.count(Task.id).label('task_count'),
            func.count(
                func.nullif(Task.status == TaskStatus.COMPLETED, False)
            ).label('completed_count'),
        ).where(
            and_(
                Task.user_id == current_user.id,
                Task.created_at >= time_threshold
            )
        ).group_by(Task.task_type)
        
        result = await db.execute(query)
        agent_data = result.all()
        
        if not agent_data:
            return []
        
        # Build statistics for each agent
        agent_stats = []
        for row in agent_data:
            agent_type = row.task_type
            task_count = row.task_count
            completed_count = row.completed_count or 0
            
            # Calculate average duration for completed tasks
            duration_query = select(
                func.avg(
                    func.extract('epoch', Task.completed_at - Task.created_at)
                )
            ).where(
                and_(
                    Task.user_id == current_user.id,
                    Task.task_type == agent_type,
                    Task.status == TaskStatus.COMPLETED,
                    Task.completed_at.isnot(None),
                    Task.created_at >= time_threshold
                )
            )
            duration_result = await db.execute(duration_query)
            avg_duration = duration_result.scalar() or 0.0
            
            success_rate = completed_count / task_count if task_count > 0 else 0.0
            
            agent_stats.append(AgentStats(
                agent_type=agent_type,
                task_count=task_count,
                avg_duration_seconds=round(float(avg_duration), 2),
                success_rate=round(success_rate, 4),
                total_cost_usd=0.0,  # Placeholder - implement LangFuse integration
            ))
        
        logger.info(f"Agent statistics retrieved for user {current_user.id}")
        
        return agent_stats
        
    except Exception as e:
        logger.error(f"Failed to get agent statistics: {e}")
        raise


@router.get("/trends", response_model=List[TaskTrend])
async def get_task_trends(
    current_user: User = Depends(get_current_user),
    days: int = Query(7, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
):
    """
    Get task execution trends over time (daily aggregation).
    
    **Parameters:**
    - `days`: Number of days to include (1-30, default: 7)
    """
    try:
        time_threshold = datetime.utcnow() - timedelta(days=days)
        
        # Get all tasks in time range
        query = select(Task).where(
            and_(
                Task.user_id == current_user.id,
                Task.created_at >= time_threshold
            )
        ).order_by(Task.created_at)
        
        result = await db.execute(query)
        tasks = result.scalars().all()
        
        if not tasks:
            return []
        
        # Group tasks by date
        trends_by_date: Dict[str, Dict[str, Any]] = {}
        
        for task in tasks:
            date_key = task.created_at.strftime('%Y-%m-%d')
            
            if date_key not in trends_by_date:
                trends_by_date[date_key] = {
                    'total_tasks': 0,
                    'completed_tasks': 0,
                    'failed_tasks': 0,
                    'durations': [],
                }
            
            trends_by_date[date_key]['total_tasks'] += 1
            
            if task.status == TaskStatus.COMPLETED:
                trends_by_date[date_key]['completed_tasks'] += 1
                if task.completed_at:
                    duration = (task.completed_at - task.created_at).total_seconds()
                    trends_by_date[date_key]['durations'].append(duration)
            elif task.status == TaskStatus.FAILED:
                trends_by_date[date_key]['failed_tasks'] += 1
        
        # Build trend objects
        trends = []
        for date_key in sorted(trends_by_date.keys()):
            data = trends_by_date[date_key]
            avg_duration = (
                sum(data['durations']) / len(data['durations'])
                if data['durations'] else 0.0
            )
            
            trends.append(TaskTrend(
                date=date_key,
                total_tasks=data['total_tasks'],
                completed_tasks=data['completed_tasks'],
                failed_tasks=data['failed_tasks'],
                avg_duration_seconds=round(avg_duration, 2),
            ))
        
        logger.info(f"Task trends retrieved for user {current_user.id} ({len(trends)} days)")
        
        return trends
        
    except Exception as e:
        logger.error(f"Failed to get task trends: {e}")
        raise


class OutcomeAction(BaseModel):
    """Action card for outcome follow-through (#255/#262 idea support)."""

    id: str
    label: str
    path: str
    method: str = Field(default="GET", description="HTTP method for action")
    enabled: bool = True
    description: str | None = None


class OutcomeRingCard(BaseModel):
    """One completed/failed task card in the outcome ring."""

    task_id: UUID
    task_type: str
    status: str
    prompt: str
    created_at: datetime
    completed_at: datetime | None = None
    completion_seconds: float | None = None
    result_preview: str | None = None
    document_url: str | None = None
    failure_category: str | None = None
    actions: list[OutcomeAction] = Field(default_factory=list)


class OutcomeRingResponse(BaseModel):
    """Task outcome ring response for post-task follow-through."""

    period_days: int
    period_start: str
    period_end: str
    total_outcomes: int
    status_breakdown: Dict[str, int]
    task_type_breakdown: Dict[str, int]
    cards: list[OutcomeRingCard]



@router.get("/outcome-ring", response_model=OutcomeRingResponse)
async def get_outcome_ring(
    current_user: User = Depends(get_current_user),
    period_days: int = Query(7, ge=1, le=180),
    limit: int = Query(20, ge=1, le=100),
    status: TaskStatus | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Return a compact ring of recent task outcomes with follow-through actions."""
    period_start = datetime.utcnow() - timedelta(days=period_days)
    period_end = datetime.utcnow()

    query = select(Task).where(
        Task.user_id == current_user.id,
        Task.created_at >= period_start,
    ).order_by(Task.created_at.desc())

    if status is not None:
        query = query.where(Task.status == status)

    query = query.limit(limit)

    tasks = (await db.execute(query)).scalars().all()

    status_breakdown: Dict[str, int] = defaultdict(int)
    task_type_breakdown: Dict[str, int] = defaultdict(int)

    cards: list[OutcomeRingCard] = []

    for task in tasks:
        status_value = _safe_status(task.status)
        status_breakdown[status_value] += 1

        ttype = _safe_task_type(task.task_type)
        task_type_breakdown[ttype] += 1

        completion_seconds: float | None = None
        if task.completed_at is not None:
            completion_seconds = round((task.completed_at - task.created_at).total_seconds(), 2)

        preview = None
        if isinstance(task.result, dict):
            result_content = task.result.get("content")
            if isinstance(result_content, str) and result_content.strip():
                preview = _truncate_text(result_content, 180)

        cards.append(
            OutcomeRingCard(
                task_id=task.id,
                task_type=ttype,
                status=status_value,
                prompt=_truncate_text(task.prompt, 120),
                created_at=task.created_at,
                completed_at=task.completed_at,
                completion_seconds=completion_seconds,
                result_preview=preview,
                document_url=task.document_url,
                failure_category=_failure_category(task),
                actions=_collect_outcome_actions(task),
            )
        )

    return OutcomeRingResponse(
        period_days=period_days,
        period_start=period_start.isoformat(),
        period_end=period_end.isoformat(),
        total_outcomes=len(cards),
        status_breakdown=dict(status_breakdown),
        task_type_breakdown=dict(task_type_breakdown),
        cards=cards,
    )




class DashboardSummary(BaseModel):
    """One-metric dashboard summary (#214)."""

    total_tasks: int = Field(..., description="Total tasks ever created by this user")
    completed_tasks: int = Field(..., description="Tasks with status=completed")
    success_rate: float = Field(..., description="Completed / total (0.0–1.0); 0 when no tasks")
    avg_completion_time_seconds: float = Field(
        ..., description="Mean seconds from created_at to completed_at; 0 when no completed tasks"
    )


@router.get("/summary", response_model=DashboardSummary)
async def get_dashboard_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return a single-page dashboard summary for the authenticated user.

    Counts all tasks ever created (no time-range filter) and computes:
    - ``total_tasks`` — lifetime task count
    - ``completed_tasks`` — tasks that reached COMPLETED status
    - ``success_rate`` — ``completed / total`` (float 0–1; ``0.0`` when total is 0)
    - ``avg_completion_time_seconds`` — mean of ``(completed_at - created_at)``
      for completed tasks that have a ``completed_at`` timestamp; ``0.0`` when none

    **Requires authentication.**
    """
    # All tasks for this user
    query = select(Task).where(Task.user_id == current_user.id)
    result = await db.execute(query)
    tasks = result.scalars().all()

    total_tasks = len(tasks)
    completed_tasks = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)

    success_rate = (completed_tasks / total_tasks) if total_tasks > 0 else 0.0

    # Average completion time (seconds) over tasks that have completed_at set
    durations = [
        (t.completed_at - t.created_at).total_seconds()
        for t in tasks
        if t.status == TaskStatus.COMPLETED and getattr(t, "completed_at", None) is not None
    ]
    avg_completion_time_seconds = (sum(durations) / len(durations)) if durations else 0.0

    logger.info(
        "Dashboard summary for user %s: %d/%d tasks completed (%.1f%%)",
        current_user.id,
        completed_tasks,
        total_tasks,
        success_rate * 100,
    )

    return DashboardSummary(
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        success_rate=round(success_rate, 4),
        avg_completion_time_seconds=round(avg_completion_time_seconds, 2),
    )


# ── #230 Workspace ROI Dashboard ──────────────────────────────────────

# Default manual-work estimates (minutes) per task type.
# Users can override via the `hourly_rate` query parameter for money calc.
_MANUAL_MINUTES: Dict[str, float] = {
    "docs": 30.0,
    "sheets": 45.0,
    "slides": 60.0,
    "research": 90.0,
}


class WeeklyROI(BaseModel):
    """Weekly productivity ROI report."""

    period_start: str = Field(..., description="ISO date of period start (Monday)")
    period_end: str = Field(..., description="ISO date of period end (Sunday)")
    total_tasks: int
    completed_tasks: int
    by_type: Dict[str, int] = Field(default_factory=dict, description="Completed tasks by type")
    time_saved_minutes: float = Field(..., description="Estimated minutes saved vs manual work")
    time_saved_hours: float = Field(..., description="Same value in hours for display")
    money_saved: float = Field(..., description="time_saved_hours * hourly_rate")
    hourly_rate: float = Field(..., description="Rate used for money calculation")
    currency: str = "USD"
    avg_quality_score: Optional[float] = Field(None, description="Mean QA overall_score (null if none)")
    best_task: Optional[Dict[str, Any]] = Field(None, description="Highest QA-scored task")
    vs_previous_week: Optional[Dict[str, Any]] = Field(
        None, description="Comparison with the previous week"
    )


def _week_bounds(reference: datetime) -> tuple[datetime, datetime]:
    """Return (monday 00:00, sunday 23:59:59) for the ISO week containing *reference*."""
    monday = (reference - timedelta(days=reference.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    sunday = monday + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return monday, sunday


async def _aggregate_week(
    db: AsyncSession,
    user_id: UUID,
    start: datetime,
    end: datetime,
) -> Dict[str, Any]:
    """Aggregate task stats for a single week window."""
    from app.models.qa_result import QAResult

    query = select(Task).where(
        and_(
            Task.user_id == user_id,
            Task.created_at >= start,
            Task.created_at <= end,
        )
    )
    result = await db.execute(query)
    tasks = result.scalars().all()

    total = len(tasks)
    completed = [t for t in tasks if t.status == TaskStatus.COMPLETED]
    by_type: Dict[str, int] = {}
    saved_minutes = 0.0

    for t in completed:
        ttype = t.task_type.value if hasattr(t.task_type, "value") else str(t.task_type)
        by_type[ttype] = by_type.get(ttype, 0) + 1
        saved_minutes += _MANUAL_MINUTES.get(ttype, 30.0)

    # QA scores
    task_ids = [t.id for t in completed]
    avg_qa: Optional[float] = None
    best_task_info: Optional[Dict[str, Any]] = None

    if task_ids:
        qa_query = select(QAResult).where(QAResult.task_id.in_(task_ids))
        qa_result = await db.execute(qa_query)
        qa_rows = qa_result.scalars().all()
        if qa_rows:
            scores = [q.overall_score for q in qa_rows]
            avg_qa = round(sum(scores) / len(scores), 1)
            best_qa = max(qa_rows, key=lambda q: q.overall_score)
            best_task_obj = next((t for t in completed if t.id == best_qa.task_id), None)
            if best_task_obj:
                prompt_preview = (best_task_obj.prompt[:80] + "…") if len(best_task_obj.prompt) > 80 else best_task_obj.prompt
                best_task_info = {
                    "task_id": str(best_task_obj.id),
                    "prompt": prompt_preview,
                    "quality_score": best_qa.overall_score,
                    "task_type": best_task_obj.task_type.value if hasattr(best_task_obj.task_type, "value") else str(best_task_obj.task_type),
                }

    return {
        "total": total,
        "completed": len(completed),
        "by_type": by_type,
        "saved_minutes": round(saved_minutes, 1),
        "avg_qa": avg_qa,
        "best_task": best_task_info,
    }


@router.get("/weekly-roi", response_model=WeeklyROI)
async def get_weekly_roi(
    current_user: User = Depends(get_current_user),
    hourly_rate: float = Query(50.0, ge=0, description="Hourly rate for money-saved calculation"),
    currency: str = Query("USD", max_length=3),
    db: AsyncSession = Depends(get_db),
):
    """Return a weekly ROI report showing estimated time/money saved.

    Compares with the previous week when data is available.
    """
    now = datetime.utcnow()
    this_start, this_end = _week_bounds(now)
    prev_start = this_start - timedelta(weeks=1)
    prev_end = this_start - timedelta(seconds=1)

    this_week = await _aggregate_week(db, current_user.id, this_start, this_end)
    prev_week = await _aggregate_week(db, current_user.id, prev_start, prev_end)

    saved_hours = round(this_week["saved_minutes"] / 60, 2)
    money_saved = round(saved_hours * hourly_rate, 2)

    # Comparison
    vs_previous: Optional[Dict[str, Any]] = None
    if prev_week["total"] > 0:
        prev_hours = prev_week["saved_minutes"] / 60
        delta_hours = saved_hours - prev_hours
        pct = round((delta_hours / prev_hours) * 100, 1) if prev_hours > 0 else 0.0
        vs_previous = {
            "prev_time_saved_hours": round(prev_hours, 2),
            "delta_hours": round(delta_hours, 2),
            "delta_pct": pct,
        }

    logger.info(
        "Weekly ROI for user %s: %d tasks, %.1fh saved, $%.2f value",
        current_user.id,
        this_week["completed"],
        saved_hours,
        money_saved,
    )

    return WeeklyROI(
        period_start=this_start.strftime("%Y-%m-%d"),
        period_end=this_end.strftime("%Y-%m-%d"),
        total_tasks=this_week["total"],
        completed_tasks=this_week["completed"],
        by_type=this_week["by_type"],
        time_saved_minutes=this_week["saved_minutes"],
        time_saved_hours=saved_hours,
        money_saved=money_saved,
        hourly_rate=hourly_rate,
        currency=currency,
        avg_quality_score=this_week["avg_qa"],
        best_task=this_week["best_task"],
        vs_previous_week=vs_previous,
    )


@router.get("/cost", response_model=CostBreakdown)
async def get_cost_breakdown(
    current_user: User = Depends(get_current_user),
    time_range_hours: int = Query(24, ge=1, le=720),  # Up to 30 days
    db: AsyncSession = Depends(get_db),
):
    """
    Get LLM cost breakdown.

    This endpoint now returns heuristic cost estimates captured at task-creation time,
    grouped by task type and model.
    """
    time_threshold = datetime.utcnow() - timedelta(hours=time_range_hours)
    query = select(Task).where(
        and_(
            Task.user_id == current_user.id,
            Task.created_at >= time_threshold,
        )
    )
    result = await db.execute(query)
    tasks = result.scalars().all()

    by_agent: Dict[str, float] = {
        "research": 0.0,
        "docs": 0.0,
        "sheets": 0.0,
        "slides": 0.0,
    }
    by_model: Dict[str, float] = {
        "gpt-4-turbo-preview": 0.0,
        "gpt-3.5-turbo": 0.0,
        "unknown": 0.0,
    }
    by_date: Dict[str, float] = defaultdict(float)
    total_cost = 0.0

    for task in tasks:
        snapshot = _build_task_cost_snapshot(task)

        # Prefer concrete actual_cost for billing visibility when present,
        # otherwise fall back to estimated cost from preview planning.
        cost = snapshot["actual_cost_usd"] or snapshot["estimated_cost_usd"]
        if cost <= 0:
            continue

        total_cost += cost
        agent_key = _safe_task_type(task.task_type)
        by_agent[agent_key] = by_agent.get(agent_key, 0.0) + cost

        model = snapshot.get("model") or "unknown"
        by_model[model] = by_model.get(model, 0.0) + cost

        day_key = task.created_at.strftime("%Y-%m-%d")
        by_date[day_key] += cost

    logger.info(f"Cost breakdown calculated for user {current_user.id}: ${round(total_cost, 4)}")

    return CostBreakdown(
        total_cost_usd=round(total_cost, 4),
        by_agent={k: round(v, 4) for k, v in by_agent.items()},
        by_model={k: round(v, 4) for k, v in by_model.items()},
        by_date={k: round(v, 4) for k, v in by_date.items()} or {
            datetime.utcnow().strftime('%Y-%m-%d'): 0.0
        },
    )


def _budget_status(total_cost: float, monthly_budget_usd: float | None, observed_hours: int) -> tuple[float | None, float | None, str | None]:
    if monthly_budget_usd is None:
        return None, None, None

    if observed_hours <= 0:
        return None, None, None

    projected_monthly_cost = round((total_cost / observed_hours) * 24 * 30, 4)
    used_pct = round((projected_monthly_cost / monthly_budget_usd) * 100, 2)

    if used_pct >= 100:
        status = "exceeded"
    elif used_pct >= 85:
        status = "warning"
    else:
        status = "ok"

    return projected_monthly_cost, used_pct, status


def _build_cost_trust_recommendations(
    *,
    budget_status: str | None,
    monthly_budget_usd: float | None,
    projected_monthly_cost_usd: float | None,
    budget_used_pct: float | None,
    avg_trust: float | None,
    retry_rate: float,
    failed_count: int,
    total_tasks: int,
    total_cost_for_budget: float,
) -> tuple[str | None, list[str], str]:
    """Create actionable recommendations for cost/trust governance."""
    warning: str | None = None
    recommendations: list[str] = []

    if budget_status in {"warning", "exceeded"} and monthly_budget_usd and projected_monthly_cost_usd is not None:
        margin = projected_monthly_cost_usd - monthly_budget_usd
        if margin <= 0:
            margin = 0.0
        if budget_status == "exceeded":
            warning = (
                "Projected monthly spend may exceed budget. Consider reducing frequent high-cost tasks, "
                "tightening prompts, or increasing budget to avoid interruption."
            )
            recommendations.append("Review large-cost tasks and switch to lighter execution paths.")
        else:
            warning = (
                f"Projected spend is at {budget_used_pct:.0f}% of budget; "
                "run lower-cost alternatives to stay under the limit."
            )
            recommendations.append("Enable periodic cost checks for recurring automations.")
        recommendations.append(f"Estimated overage if trend continues: ${round(margin, 2)}.")

    if avg_trust is not None and avg_trust < 70:
        recommendations.append("Trust score is below 70. Enable deeper review prompts before auto-run tasks.")

    if retry_rate >= 30:
        recommendations.append("High retry rate detected. Review task retries and add validation for flaky inputs.")

    if failed_count and total_tasks:
        failure_rate = (failed_count / total_tasks) * 100
        if failure_rate >= 25:
            recommendations.append("High failure rate detected. Pause non-critical automation and inspect recent failures.")

    if total_cost_for_budget == 0 and total_tasks:
        recommendations.append("No cost data available for this period yet; ensure cost telemetry is enabled.")

    if not recommendations:
        recommendations.append("No immediate action required. System appears healthy.")

    if avg_trust is None:
        trust_health = "unknown" if budget_status else "stable"
    elif avg_trust < 70:
        trust_health = "needs_attention"
    elif avg_trust < 85:
        trust_health = "stable"
    else:
        trust_health = "strong"

    return warning, recommendations, trust_health


@router.get("/cost-trust", response_model=CostTrustDashboard)
async def get_cost_and_trust_dashboard(
    current_user: User = Depends(get_current_user),
    time_range_hours: int = Query(168, ge=1, le=720, description="Observation window in hours"),
    monthly_budget_usd: float | None = Query(default=None, ge=0.0, description="Optional monthly budget for projection alerts"),
    limit: int = Query(default=25, ge=1, le=100, description="Recent task cards to include"),
    db: AsyncSession = Depends(get_db),
):
    """
    Cost & trust dashboard for transparent execution governance.

    Returns task-level cost snapshots, trust scores, retry counts and optional
    monthly budget pressure indicator.
    """
    period_end = datetime.utcnow()
    period_start = period_end - timedelta(hours=time_range_hours)

    query = (
        select(Task)
        .where(
            and_(
                Task.user_id == current_user.id,
                Task.created_at >= period_start,
            )
        )
        .order_by(Task.created_at.desc())
    )
    result = await db.execute(query)
    tasks = result.scalars().all()

    qa_scores = await _build_qa_score_map(db, tasks)

    total_estimated_cost = 0.0
    total_actual_cost = 0.0
    total_estimated_tokens = 0
    total_actual_tokens = 0
    durations = []
    retry_count = 0
    trust_scores = []

    cards: list[CostTrustTaskCard] = []

    for task in tasks:
        snapshot = _build_task_cost_snapshot(task)
        cost_est = snapshot["estimated_cost_usd"]
        cost_actual = snapshot["actual_cost_usd"]
        tokens_est = snapshot["estimated_tokens"]
        tokens_actual = snapshot["actual_tokens"]

        duration_seconds = None
        if task.completed_at:
            duration_seconds = (task.completed_at - task.created_at).total_seconds()
            durations.append(duration_seconds)

        trust_score = qa_scores.get(task.id)
        if trust_score is not None:
            trust_scores.append(trust_score)

        total_estimated_cost += cost_est
        total_actual_cost += cost_actual
        total_estimated_tokens += tokens_est
        total_actual_tokens += tokens_actual

        if snapshot["retry_depth"] > 0:
            retry_count += 1

        cards.append(
            CostTrustTaskCard(
                task_id=task.id,
                task_type=_safe_task_type(task.task_type),
                status=_safe_status(task.status),
                prompt=_truncate_text(task.prompt, 120),
                created_at=task.created_at,
                completed_at=task.completed_at,
                duration_seconds=duration_seconds,
                estimated_cost_usd=round(cost_est, 4),
                actual_cost_usd=round(cost_actual, 4),
                estimated_tokens=tokens_est,
                actual_tokens=tokens_actual,
                retry_depth=snapshot["retry_depth"],
                trust_score=trust_score,
                model=snapshot["model"],
            )
        )

    cards = sorted(cards, key=lambda c: c.created_at, reverse=True)[:limit]
    total_cost_for_budget = total_actual_cost if total_actual_cost > 0 else total_estimated_cost
    avg_duration = (sum(durations) / len(durations)) if durations else 0.0
    avg_trust = (sum(trust_scores) / len(trust_scores)) if trust_scores else None
    retry_rate = round((retry_count / len(tasks)) * 100, 2) if tasks else 0.0

    observed_hours = max(int((period_end - period_start).total_seconds() // 3600), 1)
    projected_cost, budget_pct, budget_status = _budget_status(
        total_cost_for_budget,
        monthly_budget_usd,
        observed_hours,
    )

    failed_count = sum(1 for t in tasks if t.status == TaskStatus.FAILED)
    cancelled_count = sum(1 for t in tasks if t.status == TaskStatus.CANCELLED)

    budget_warning, recommendations, trust_health = _build_cost_trust_recommendations(
        budget_status=budget_status,
        monthly_budget_usd=monthly_budget_usd,
        projected_monthly_cost_usd=projected_cost,
        budget_used_pct=budget_pct,
        avg_trust=avg_trust,
        retry_rate=retry_rate,
        failed_count=failed_count,
        total_tasks=len(tasks),
        total_cost_for_budget=total_cost_for_budget,
    )

    return CostTrustDashboard(
        period_start=period_start.isoformat(),
        period_end=period_end.isoformat(),
        time_range_hours=time_range_hours,
        total_tasks=len(tasks),
        completed_tasks=sum(1 for t in tasks if t.status == TaskStatus.COMPLETED),
        failed_tasks=failed_count,
        cancelled_tasks=cancelled_count,
        total_estimated_cost_usd=round(total_estimated_cost, 4),
        total_actual_cost_usd=round(total_actual_cost, 4),
        total_estimated_tokens=total_estimated_tokens,
        total_actual_tokens=total_actual_tokens,
        avg_completion_time_seconds=round(avg_duration, 2),
        average_trust_score=round(avg_trust, 2) if avg_trust is not None else None,
        retry_tasks=retry_count,
        retry_rate=retry_rate,
        budget_limit_usd=monthly_budget_usd,
        projected_monthly_cost_usd=projected_cost,
        budget_used_pct=budget_pct,
        budget_status=budget_status,
        budget_warning=budget_warning,
        trust_health=trust_health,
        recommendations=recommendations,
        cards=cards,
    )


__all__ = ["router"]
