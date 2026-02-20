"""Analytics API for Agent Performance metrics and LangFuse data visualization.

This module provides endpoints for:
- Real-time performance metrics
- LLM cost tracking
- Agent comparison views
- Task success rates
- LangFuse trace data
"""

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
    
    **Note:** This is a placeholder implementation. Full integration with
    LangFuse API will be implemented in the next phase.
    
    **Future features:**
    - Real-time LangFuse trace data
    - Model-specific pricing
    - Token usage tracking
    - Cost optimization suggestions
    """
    # Placeholder implementation
    logger.info(f"Cost breakdown requested for user {current_user.id}")
    
    return CostBreakdown(
        total_cost_usd=0.0,
        by_agent={
            "research": 0.0,
            "docs": 0.0,
            "sheets": 0.0,
            "slides": 0.0,
        },
        by_model={
            "gpt-4-turbo-preview": 0.0,
            "gpt-3.5-turbo": 0.0,
        },
        by_date={
            datetime.utcnow().strftime('%Y-%m-%d'): 0.0,
        },
    )


__all__ = ["router"]
