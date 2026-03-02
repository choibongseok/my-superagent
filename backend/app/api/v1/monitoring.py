"""
Monitoring API endpoints for real-time system status.
Provides agent status, performance metrics, error tracking, and alerts.
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_

from app.core.database import get_db
from app.models.user import User
from app.models.task import Task
from app.models.budget import CostRecord
from app.models.workflow_execution import WorkflowExecution
from app.api.dependencies import get_current_user
from pydantic import BaseModel, Field

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


# --- Schemas ---

class AgentStatus(BaseModel):
    """Status of an individual agent."""
    agent_name: str
    status: str  # "active", "idle", "error"
    last_execution: Optional[datetime] = None
    success_rate: float
    avg_duration_seconds: float
    total_executions: int
    recent_errors: int


class SystemMetrics(BaseModel):
    """Overall system performance metrics."""
    total_tasks: int
    active_tasks: int
    completed_tasks: int
    failed_tasks: int
    avg_task_duration_seconds: float
    tasks_per_hour: float
    total_cost_usd: float
    active_workflows: int


class ErrorSummary(BaseModel):
    """Summary of recent errors."""
    error_type: str
    count: int
    last_occurrence: datetime
    affected_agents: List[str]
    sample_message: Optional[str] = None


class PerformanceMetric(BaseModel):
    """Performance metric over time."""
    timestamp: datetime
    metric_name: str
    value: float
    unit: str


class AlertRule(BaseModel):
    """Alert configuration."""
    id: Optional[int] = None
    rule_name: str
    condition: str  # e.g., "error_rate > 0.1"
    threshold: float
    enabled: bool = True
    last_triggered: Optional[datetime] = None


class MonitoringDashboard(BaseModel):
    """Complete monitoring dashboard data."""
    system_metrics: SystemMetrics
    agent_statuses: List[AgentStatus]
    recent_errors: List[ErrorSummary]
    performance_trends: List[PerformanceMetric]
    active_alerts: List[str]


# --- Helper Functions ---

def calculate_agent_metrics(
    db: Session,
    agent_name: str,
    hours: int = 24
) -> AgentStatus:
    """Calculate performance metrics for a specific agent."""
    since = datetime.utcnow() - timedelta(hours=hours)
    
    tasks = db.query(Task).filter(
        Task.task_type == agent_name,
        Task.created_at >= since
    ).all()
    
    if not tasks:
        return AgentStatus(
            agent_name=agent_name,
            status="idle",
            success_rate=0.0,
            avg_duration_seconds=0.0,
            total_executions=0,
            recent_errors=0
        )
    
    total = len(tasks)
    completed = sum(1 for t in tasks if t.status == "completed")
    failed = sum(1 for t in tasks if t.status == "failed")
    
    durations = [
        (t.updated_at - t.created_at).total_seconds()
        for t in tasks
        if t.status == "completed" and t.updated_at
    ]
    avg_duration = sum(durations) / len(durations) if durations else 0.0
    
    # Determine current status
    recent_tasks = [t for t in tasks if t.created_at >= datetime.utcnow() - timedelta(hours=1)]
    if recent_tasks:
        has_recent_error = any(t.status == "failed" for t in recent_tasks)
        status = "error" if has_recent_error else "active"
    else:
        status = "idle"
    
    last_execution = max((t.created_at for t in tasks), default=None)
    
    return AgentStatus(
        agent_name=agent_name,
        status=status,
        last_execution=last_execution,
        success_rate=completed / total if total > 0 else 0.0,
        avg_duration_seconds=avg_duration,
        total_executions=total,
        recent_errors=failed
    )


def calculate_system_metrics(db: Session, hours: int = 24) -> SystemMetrics:
    """Calculate overall system performance metrics."""
    since = datetime.utcnow() - timedelta(hours=hours)
    
    # Task metrics
    total_tasks = db.query(func.count(Task.id)).scalar() or 0
    active_tasks = db.query(func.count(Task.id)).filter(
        Task.status.in_(["pending", "running"])
    ).scalar() or 0
    
    completed_tasks = db.query(func.count(Task.id)).filter(
        Task.status == "completed",
        Task.created_at >= since
    ).scalar() or 0
    
    failed_tasks = db.query(func.count(Task.id)).filter(
        Task.status == "failed",
        Task.created_at >= since
    ).scalar() or 0
    
    # Average duration
    durations = db.query(
        func.avg(
            func.extract('epoch', Task.updated_at - Task.created_at)
        )
    ).filter(
        Task.status == "completed",
        Task.created_at >= since,
        Task.updated_at.isnot(None)
    ).scalar() or 0.0
    
    # Tasks per hour
    tasks_per_hour = completed_tasks / hours if hours > 0 else 0.0
    
    # Total cost from cost records
    total_cost = db.query(func.sum(CostRecord.cost_usd)).filter(
        CostRecord.created_at >= since
    ).scalar() or 0.0
    
    # Active workflows
    active_workflows = db.query(func.count(WorkflowExecution.id)).filter(
        WorkflowExecution.status.in_(["pending", "running"])
    ).scalar() or 0
    
    return SystemMetrics(
        total_tasks=total_tasks,
        active_tasks=active_tasks,
        completed_tasks=completed_tasks,
        failed_tasks=failed_tasks,
        avg_task_duration_seconds=float(durations),
        tasks_per_hour=tasks_per_hour,
        total_cost_usd=float(total_cost),
        active_workflows=active_workflows
    )


def get_error_summary(db: Session, hours: int = 24) -> List[ErrorSummary]:
    """Get summary of recent errors grouped by type."""
    since = datetime.utcnow() - timedelta(hours=hours)
    
    failed_tasks = db.query(Task).filter(
        Task.status == "failed",
        Task.created_at >= since
    ).order_by(desc(Task.created_at)).all()
    
    # Group by error type
    error_groups: Dict[str, List[Task]] = {}
    for task in failed_tasks:
        error_msg = task.result.get("error", "Unknown error") if task.result else "Unknown error"
        # Extract error type from message
        error_type = error_msg.split(":")[0] if ":" in error_msg else "GeneralError"
        
        if error_type not in error_groups:
            error_groups[error_type] = []
        error_groups[error_type].append(task)
    
    # Build summaries
    summaries = []
    for error_type, tasks in error_groups.items():
        affected_agents = list(set(t.task_type for t in tasks if t.task_type))
        sample_message = tasks[0].result.get("error") if tasks[0].result else None
        
        summaries.append(ErrorSummary(
            error_type=error_type,
            count=len(tasks),
            last_occurrence=tasks[0].created_at,
            affected_agents=affected_agents,
            sample_message=sample_message
        ))
    
    return sorted(summaries, key=lambda x: x.count, reverse=True)


def get_performance_trends(db: Session, hours: int = 24) -> List[PerformanceMetric]:
    """Get performance metrics over time."""
    since = datetime.utcnow() - timedelta(hours=hours)
    
    # Group tasks by hour and calculate metrics
    metrics = []
    
    for hour_offset in range(hours):
        hour_start = since + timedelta(hours=hour_offset)
        hour_end = hour_start + timedelta(hours=1)
        
        # Task completion rate
        completed = db.query(func.count(Task.id)).filter(
            Task.status == "completed",
            Task.created_at >= hour_start,
            Task.created_at < hour_end
        ).scalar() or 0
        
        metrics.append(PerformanceMetric(
            timestamp=hour_start,
            metric_name="task_completion_rate",
            value=float(completed),
            unit="tasks/hour"
        ))
        
        # Error rate
        failed = db.query(func.count(Task.id)).filter(
            Task.status == "failed",
            Task.created_at >= hour_start,
            Task.created_at < hour_end
        ).scalar() or 0
        
        total = completed + failed
        error_rate = failed / total if total > 0 else 0.0
        
        metrics.append(PerformanceMetric(
            timestamp=hour_start,
            metric_name="error_rate",
            value=error_rate,
            unit="percentage"
        ))
        
        # Average cost per task
        cost = db.query(func.avg(CostRecord.cost_usd)).filter(
            CostRecord.created_at >= hour_start,
            CostRecord.created_at < hour_end
        ).scalar() or 0.0
        
        metrics.append(PerformanceMetric(
            timestamp=hour_start,
            metric_name="avg_cost_per_task",
            value=float(cost),
            unit="USD"
        ))
    
    return metrics


def check_alerts(system_metrics: SystemMetrics, agent_statuses: List[AgentStatus]) -> List[str]:
    """Check for alert conditions and return active alerts."""
    alerts = []
    
    # High error rate alert
    if system_metrics.completed_tasks > 0:
        error_rate = system_metrics.failed_tasks / (system_metrics.completed_tasks + system_metrics.failed_tasks)
        if error_rate > 0.1:  # 10% error threshold
            alerts.append(f"⚠️ High error rate: {error_rate:.1%}")
    
    # Agent failure alert
    for agent in agent_statuses:
        if agent.status == "error":
            alerts.append(f"⚠️ Agent {agent.agent_name} experiencing errors")
    
    # High cost alert
    if system_metrics.total_cost_usd > 100:  # $100 threshold
        alerts.append(f"💰 High cost detected: ${system_metrics.total_cost_usd:.2f}")
    
    # Slow performance alert
    if system_metrics.avg_task_duration_seconds > 300:  # 5 minutes threshold
        alerts.append(f"🐌 Slow task execution: avg {system_metrics.avg_task_duration_seconds:.0f}s")
    
    return alerts


# --- API Endpoints ---

@router.get("/dashboard", response_model=MonitoringDashboard)
async def get_monitoring_dashboard(
    hours: int = Query(24, ge=1, le=168, description="Time window in hours"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get complete monitoring dashboard with all metrics.
    
    - **hours**: Time window for metrics (1-168 hours)
    
    Returns:
    - System-wide performance metrics
    - Individual agent status and performance
    - Recent error summaries
    - Performance trends over time
    - Active alerts
    """
    # Calculate all metrics
    system_metrics = calculate_system_metrics(db, hours)
    
    # Get status for all known agents
    agent_types = ["research", "docs", "sheets", "slides"]
    agent_statuses = [
        calculate_agent_metrics(db, agent_type, hours)
        for agent_type in agent_types
    ]
    
    error_summary = get_error_summary(db, hours)
    performance_trends = get_performance_trends(db, hours)
    
    # Check for alerts
    active_alerts = check_alerts(system_metrics, agent_statuses)
    
    return MonitoringDashboard(
        system_metrics=system_metrics,
        agent_statuses=agent_statuses,
        recent_errors=error_summary,
        performance_trends=performance_trends,
        active_alerts=active_alerts
    )


@router.get("/agents/{agent_name}", response_model=AgentStatus)
async def get_agent_status(
    agent_name: str,
    hours: int = Query(24, ge=1, le=168),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get detailed status for a specific agent.
    
    - **agent_name**: Agent type (research, docs, sheets, slides)
    - **hours**: Time window for metrics
    """
    valid_agents = ["research", "docs", "sheets", "slides"]
    if agent_name not in valid_agents:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid agent name. Must be one of: {', '.join(valid_agents)}"
        )
    
    return calculate_agent_metrics(db, agent_name, hours)


@router.get("/metrics", response_model=SystemMetrics)
async def get_system_metrics(
    hours: int = Query(24, ge=1, le=168),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get overall system performance metrics."""
    return calculate_system_metrics(db, hours)


@router.get("/errors", response_model=List[ErrorSummary])
async def get_error_summary_endpoint(
    hours: int = Query(24, ge=1, le=168),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get summary of recent errors grouped by type."""
    return get_error_summary(db, hours)


@router.get("/trends", response_model=List[PerformanceMetric])
async def get_performance_trends_endpoint(
    hours: int = Query(24, ge=1, le=168),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get performance metrics over time for visualization."""
    return get_performance_trends(db, hours)


@router.get("/alerts", response_model=List[str])
async def get_active_alerts(
    hours: int = Query(24, ge=1, le=168),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check for active alerts based on current metrics."""
    system_metrics = calculate_system_metrics(db, hours)
    agent_types = ["research", "docs", "sheets", "slides"]
    agent_statuses = [
        calculate_agent_metrics(db, agent_type, hours)
        for agent_type in agent_types
    ]
    
    return check_alerts(system_metrics, agent_statuses)


@router.get("/health", response_model=Dict[str, Any])
async def monitoring_health_check(db: Session = Depends(get_db)):
    """
    Health check endpoint for monitoring system.
    No authentication required for uptime monitoring.
    """
    try:
        # Check database connectivity
        db.execute("SELECT 1")
        db_status = "healthy"
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "database": db_status,
        "monitoring_api": "operational"
    }
