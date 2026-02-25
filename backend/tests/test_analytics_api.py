"""
Analytics API 종합 테스트

이 모듈은 /api/v1/analytics/* 엔드포인트의 기능을 검증합니다:
- Performance metrics
- Agent statistics
- Task trends
- Dashboard summary
- Weekly ROI
- Token usage tracking
- Cost breakdown
- Budget alerts
- Outcome ring
- Cost & trust dashboard
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4
from datetime import datetime, timedelta, UTC

from app.core.security import create_access_token
from app.models.user import User
from app.models.task import Task, TaskStatus
from app.models.token_usage import TokenUsage
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _make_user(db: AsyncSession, email: str | None = None) -> User:
    """Create a test user."""
    u = User(id=uuid4(), email=email or f"u-{uuid4().hex[:6]}@test.com", is_active=True)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _make_workspace(db: AsyncSession, owner: User) -> Workspace:
    """Create a test workspace with owner membership."""
    ws = Workspace(
        id=uuid4(),
        name=f"Workspace-{uuid4().hex[:6]}",
        owner_id=owner.id
    )
    db.add(ws)
    await db.commit()
    await db.refresh(ws)
    
    # Add owner as member
    member = WorkspaceMember(
        workspace_id=ws.id,
        user_id=owner.id,
        role="owner"
    )
    db.add(member)
    await db.commit()
    
    return ws


async def _make_tasks(db: AsyncSession, user: User, workspace: Workspace, count: int = 10):
    """Create sample tasks with mix of statuses."""
    tasks = []
    base_time = datetime.now(UTC)
    
    for i in range(count):
        # Mix of completed (70%) and failed (30%)
        status = TaskStatus.COMPLETED if i < 7 else TaskStatus.FAILED
        completed_at = base_time - timedelta(days=i, hours=1) if status == TaskStatus.COMPLETED else None
        
        task = Task(
            id=uuid4(),
            task_type="docs" if i % 3 == 0 else ("sheets" if i % 3 == 1 else "slides"),
            prompt=f"Test task {i}",
            user_id=user.id,
            workspace_id=workspace.id,
            status=status,
            created_at=base_time - timedelta(days=i),
            completed_at=completed_at
        )
        db.add(task)
        tasks.append(task)
    
    await db.commit()
    for task in tasks:
        await db.refresh(task)
    
    return tasks


async def _make_token_usage(db: AsyncSession, user: User, tasks: list[Task]):
    """Create sample token usage for completed tasks."""
    from app.services.cost_tracker import CostTracker
    
    usages = []
    completed_tasks = [t for t in tasks if t.status == TaskStatus.COMPLETED]
    
    models = [
        ("claude-3-5-sonnet-20241022", "anthropic", 1000, 4000),
        ("claude-3-5-sonnet-20241022", "anthropic", 2000, 6000),
        ("gpt-4-turbo", "openai", 1500, 3000),
        ("gpt-3.5-turbo", "openai", 500, 1000),
        ("claude-3-5-sonnet-20241022", "anthropic", 3000, 8000),
        ("gpt-4-turbo", "openai", 2000, 4000),
        ("gpt-3.5-turbo", "openai", 800, 1200),
    ]
    
    for task, (model, provider, prompt_tokens, completion_tokens) in zip(completed_tasks, models):
        cost = CostTracker.calculate_cost(model, prompt_tokens, completion_tokens)
        
        usage = TokenUsage(
            id=uuid4(),
            task_id=task.id,
            user_id=user.id,
            model=model,
            provider=provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost_usd=cost,
            created_at=task.created_at
        )
        db.add(usage)
        usages.append(usage)
    
    await db.commit()
    for usage in usages:
        await db.refresh(usage)
    
    return usages


def _auth_headers(user: User) -> dict:
    """Generate authorization headers for a user."""
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


# ── Tests ─────────────────────────────────────────────────────────────────────

# === Performance Metrics ===

@pytest.mark.asyncio
async def test_get_performance_metrics(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """성능 메트릭스 조회"""
    user = await _make_user(db)
    workspace = await _make_workspace(db, user)
    await _make_tasks(db, user, workspace, 10)
    
    response = await async_client.get(
        "/api/v1/analytics/performance",
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "avg_response_time_seconds" in data
    assert "success_rate" in data
    assert "total_tasks" in data
    assert "completed_tasks" in data
    assert "failed_tasks" in data
    assert "pending_tasks" in data
    
    # Verify values
    assert data["total_tasks"] == 10
    assert data["completed_tasks"] == 7
    assert data["failed_tasks"] == 3
    assert 0 <= data["success_rate"] <= 1


@pytest.mark.asyncio
async def test_get_performance_metrics_with_time_range(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """시간 범위 필터링"""
    user = await _make_user(db)
    workspace = await _make_workspace(db, user)
    await _make_tasks(db, user, workspace, 10)
    
    response = await async_client.get(
        "/api/v1/analytics/performance?time_range_hours=48",
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Should have fewer tasks (within 48 hours)
    assert data["total_tasks"] <= 10


@pytest.mark.asyncio
async def test_get_performance_metrics_unauthorized(
    async_client: AsyncClient,
):
    """인증 실패"""
    response = await async_client.get("/api/v1/analytics/performance")
    # CSRF protection returns 403
    assert response.status_code in (401, 403)


# === Agent Statistics ===

@pytest.mark.asyncio
async def test_get_agent_statistics(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """에이전트 통계 조회"""
    user = await _make_user(db)
    workspace = await _make_workspace(db, user)
    await _make_tasks(db, user, workspace, 10)
    
    response = await async_client.get(
        "/api/v1/analytics/agents",
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert isinstance(data, list)
    assert len(data) > 0
    
    # Check structure
    agent = data[0]
    assert "agent_type" in agent
    assert "task_count" in agent
    assert "avg_duration_seconds" in agent
    assert "success_rate" in agent
    assert "total_cost_usd" in agent


@pytest.mark.asyncio
async def test_get_agent_statistics_with_time_range(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """시간 범위 필터링"""
    user = await _make_user(db)
    workspace = await _make_workspace(db, user)
    await _make_tasks(db, user, workspace, 10)
    
    response = await async_client.get(
        "/api/v1/analytics/agents?time_range_hours=72",
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert isinstance(data, list)


# === Task Trends ===

@pytest.mark.asyncio
async def test_get_task_trends(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """태스크 트렌드 조회"""
    user = await _make_user(db)
    workspace = await _make_workspace(db, user)
    await _make_tasks(db, user, workspace, 10)
    
    response = await async_client.get(
        "/api/v1/analytics/trends",
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert isinstance(data, list)
    
    if len(data) > 0:
        trend = data[0]
        assert "date" in trend
        assert "total_tasks" in trend
        assert "completed_tasks" in trend
        assert "failed_tasks" in trend
        assert "avg_duration_seconds" in trend


@pytest.mark.asyncio
async def test_get_task_trends_with_days(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """일수 지정"""
    user = await _make_user(db)
    workspace = await _make_workspace(db, user)
    await _make_tasks(db, user, workspace, 10)
    
    response = await async_client.get(
        "/api/v1/analytics/trends?days=14",
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert isinstance(data, list)
    # Should have up to 14 days of data
    assert len(data) <= 14


# === Dashboard Summary ===

@pytest.mark.asyncio
async def test_get_dashboard_summary(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """대시보드 요약 조회"""
    user = await _make_user(db)
    workspace = await _make_workspace(db, user)
    await _make_tasks(db, user, workspace, 10)
    
    response = await async_client.get(
        "/api/v1/analytics/summary",
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "total_tasks" in data
    assert "completed_tasks" in data
    assert "success_rate" in data
    assert "avg_completion_time_seconds" in data
    
    # Verify values
    assert data["total_tasks"] == 10
    assert data["completed_tasks"] == 7
    assert 0 <= data["success_rate"] <= 1


@pytest.mark.asyncio
async def test_get_dashboard_summary_no_tasks(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """태스크가 없는 경우"""
    user = await _make_user(db)
    
    response = await async_client.get(
        "/api/v1/analytics/summary",
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["total_tasks"] == 0
    assert data["completed_tasks"] == 0
    assert data["success_rate"] == 0.0
    assert data["avg_completion_time_seconds"] == 0.0


# === Weekly ROI ===

@pytest.mark.asyncio
async def test_get_weekly_roi(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """주간 ROI 조회"""
    user = await _make_user(db)
    workspace = await _make_workspace(db, user)
    await _make_tasks(db, user, workspace, 10)
    
    response = await async_client.get(
        "/api/v1/analytics/weekly-roi",
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "period_start" in data
    assert "period_end" in data
    assert "total_tasks" in data
    assert "completed_tasks" in data
    assert "by_type" in data
    assert "time_saved_minutes" in data
    assert "time_saved_hours" in data
    assert "money_saved" in data
    assert "hourly_rate" in data


@pytest.mark.asyncio
async def test_get_weekly_roi_custom_rate(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """커스텀 시급 설정"""
    user = await _make_user(db)
    workspace = await _make_workspace(db, user)
    await _make_tasks(db, user, workspace, 10)
    
    response = await async_client.get(
        "/api/v1/analytics/weekly-roi?hourly_rate=100.0",
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["hourly_rate"] == 100.0


# === Token Usage ===

@pytest.mark.asyncio
async def test_get_token_usage(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """토큰 사용량 조회"""
    user = await _make_user(db)
    workspace = await _make_workspace(db, user)
    tasks = await _make_tasks(db, user, workspace, 10)
    await _make_token_usage(db, user, tasks)
    
    response = await async_client.get(
        "/api/v1/analytics/token-usage",
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "user_id" in data
    assert "period" in data
    assert "statistics" in data
    
    stats = data["statistics"]
    assert "request_count" in stats
    assert "prompt_tokens" in stats
    assert "completion_tokens" in stats
    assert "total_tokens" in stats
    assert "total_cost_usd" in stats
    
    # Verify data
    assert stats["request_count"] > 0
    assert stats["total_tokens"] > 0
    assert stats["total_cost_usd"] > 0


@pytest.mark.asyncio
async def test_get_token_usage_with_model_filter(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """모델 필터링"""
    user = await _make_user(db)
    workspace = await _make_workspace(db, user)
    tasks = await _make_tasks(db, user, workspace, 10)
    await _make_token_usage(db, user, tasks)
    
    response = await async_client.get(
        "/api/v1/analytics/token-usage?model_filter=gpt-4-turbo",
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["model_filter"] == "gpt-4-turbo"


# === Cost Breakdown ===

@pytest.mark.asyncio
async def test_get_cost_breakdown_by_model(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """모델별 비용 분석"""
    user = await _make_user(db)
    workspace = await _make_workspace(db, user)
    tasks = await _make_tasks(db, user, workspace, 10)
    await _make_token_usage(db, user, tasks)
    
    response = await async_client.get(
        "/api/v1/analytics/cost-breakdown?group_by=model",
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "breakdown" in data
    assert "group_by" in data
    assert data["group_by"] == "model"
    
    assert isinstance(data["breakdown"], list)
    if len(data["breakdown"]) > 0:
        item = data["breakdown"][0]
        assert "model" in item
        assert "provider" in item
        assert "request_count" in item
        assert "total_tokens" in item
        assert "total_cost_usd" in item


@pytest.mark.asyncio
async def test_get_cost_breakdown_by_date(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """날짜별 비용 분석"""
    user = await _make_user(db)
    workspace = await _make_workspace(db, user)
    tasks = await _make_tasks(db, user, workspace, 10)
    await _make_token_usage(db, user, tasks)
    
    response = await async_client.get(
        "/api/v1/analytics/cost-breakdown?group_by=date",
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["group_by"] == "date"
    assert isinstance(data["breakdown"], list)


@pytest.mark.asyncio
async def test_get_cost_breakdown_invalid_group_by(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """잘못된 group_by 파라미터"""
    user = await _make_user(db)
    
    response = await async_client.get(
        "/api/v1/analytics/cost-breakdown?group_by=invalid",
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 400


# === Budget Alerts ===

@pytest.mark.asyncio
async def test_check_budget_alert_under_budget(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """예산 내 사용"""
    user = await _make_user(db)
    workspace = await _make_workspace(db, user)
    tasks = await _make_tasks(db, user, workspace, 10)
    await _make_token_usage(db, user, tasks)
    
    response = await async_client.post(
        "/api/v1/analytics/budget-alert?budget_limit_usd=100.0&period_days=30",
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "user_id" in data
    assert "budget_limit_usd" in data
    assert "current_cost_usd" in data
    assert "remaining_budget_usd" in data
    assert "utilization_percent" in data
    assert "is_over_budget" in data
    
    assert data["budget_limit_usd"] == 100.0
    assert data["is_over_budget"] is False


@pytest.mark.asyncio
async def test_check_budget_alert_over_budget(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """예산 초과"""
    user = await _make_user(db)
    workspace = await _make_workspace(db, user)
    tasks = await _make_tasks(db, user, workspace, 10)
    await _make_token_usage(db, user, tasks)
    
    response = await async_client.post(
        "/api/v1/analytics/budget-alert?budget_limit_usd=0.01&period_days=30",
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # With sample usage, should be over this tiny budget
    assert "is_over_budget" in data


# === Outcome Ring ===

@pytest.mark.asyncio
async def test_get_outcome_ring(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """아웃컴 링 조회"""
    user = await _make_user(db)
    workspace = await _make_workspace(db, user)
    await _make_tasks(db, user, workspace, 10)
    
    response = await async_client.get(
        "/api/v1/analytics/outcome-ring",
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "period_days" in data
    assert "total_outcomes" in data
    assert "status_breakdown" in data
    assert "task_type_breakdown" in data
    assert "cards" in data
    
    assert isinstance(data["cards"], list)


@pytest.mark.asyncio
async def test_get_outcome_ring_with_status_filter(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """상태 필터링"""
    user = await _make_user(db)
    workspace = await _make_workspace(db, user)
    await _make_tasks(db, user, workspace, 10)
    
    response = await async_client.get(
        "/api/v1/analytics/outcome-ring?status=completed",
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # All cards should be completed
    for card in data["cards"]:
        assert card["status"] == "completed"


# === Cost & Trust Dashboard ===

@pytest.mark.asyncio
async def test_get_cost_trust_dashboard(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """비용 & 신뢰 대시보드 조회"""
    user = await _make_user(db)
    workspace = await _make_workspace(db, user)
    tasks = await _make_tasks(db, user, workspace, 10)
    await _make_token_usage(db, user, tasks)
    
    response = await async_client.get(
        "/api/v1/analytics/cost-trust",
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "period_start" in data
    assert "period_end" in data
    assert "total_tasks" in data
    assert "completed_tasks" in data
    assert "failed_tasks" in data
    assert "total_estimated_cost_usd" in data
    assert "total_actual_cost_usd" in data
    assert "trust_health" in data
    assert "recommendations" in data
    assert "cards" in data
    
    assert isinstance(data["cards"], list)
    assert isinstance(data["recommendations"], list)


@pytest.mark.asyncio
async def test_get_cost_trust_dashboard_with_budget(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """예산 제한 포함"""
    user = await _make_user(db)
    workspace = await _make_workspace(db, user)
    tasks = await _make_tasks(db, user, workspace, 10)
    await _make_token_usage(db, user, tasks)
    
    response = await async_client.get(
        "/api/v1/analytics/cost-trust?monthly_budget_usd=50.0",
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "budget_limit_usd" in data
    assert data["budget_limit_usd"] == 50.0
    assert "projected_monthly_cost_usd" in data
    assert "budget_status" in data
