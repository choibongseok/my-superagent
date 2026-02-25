"""
Analytics API 종합 테스트

⚠️ STATUS: WORK IN PROGRESS - Auth/DB fixture 이슈 해결 필요

이 모듈은 /api/v1/analytics/* 엔드포인트의 기능을 검증합니다:
- Performance metrics
- Agent statistics
- Task trends
- Dashboard summary
- Weekly ROI
- Token usage tracking
- Cost breakdown
- Budget alerts

현재 이슈:
- AsyncSession fixtures와 sync test functions 간의 호환성 문제
- Auth dependency override 필요
- prompts_api.py 패턴으로 async 버전으로 재작성 필요

다음 단계:
1. async/await 패턴으로 전환
2. _make_user, _auth_headers 헬퍼 함수 활용
3. @pytest.mark.asyncio 데코레이터 추가
"""

import pytest
import uuid
from datetime import datetime, timedelta, UTC
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models.user import User
from app.models.task import Task, TaskStatus
from app.models.token_usage import TokenUsage
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.core.security import create_access_token


@pytest.fixture
def client():
    """테스트 클라이언트"""
    return TestClient(app)


@pytest.fixture
def test_user(db_session: Session):
    """테스트 사용자 생성"""
    user = User(
        id=str(uuid.uuid4()),
        email="analytics_test@example.com",
        google_id="analytics_12345",
        full_name="Analytics Tester"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_workspace(db_session: Session, test_user: User):
    """테스트 워크스페이스 생성"""
    workspace = Workspace(
        id=str(uuid.uuid4()),
        name="Analytics Test Workspace",
        owner_id=test_user.id
    )
    db_session.add(workspace)
    db_session.commit()
    db_session.refresh(workspace)
    
    # Add owner as member
    member = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=test_user.id,
        role="owner"
    )
    db_session.add(member)
    db_session.commit()
    
    return workspace


@pytest.fixture
def auth_headers(test_user: User):
    """인증 헤더 생성"""
    token = create_access_token(data={"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_tasks(db_session: Session, test_user: User, test_workspace: Workspace):
    """샘플 태스크 생성"""
    tasks = []
    base_time = datetime.now(UTC)
    
    for i in range(10):
        # Mix of completed and failed tasks
        status = TaskStatus.COMPLETED if i < 7 else TaskStatus.FAILED
        completed_at = base_time - timedelta(days=i, hours=1) if status == TaskStatus.COMPLETED else None
        
        task = Task(
            id=str(uuid.uuid4()),
            task_type="docs" if i % 3 == 0 else ("sheets" if i % 3 == 1 else "slides"),
            prompt=f"Test task {i}",
            user_id=test_user.id,
            workspace_id=test_workspace.id,
            status=status,
            created_at=base_time - timedelta(days=i),
            completed_at=completed_at
        )
        db_session.add(task)
        tasks.append(task)
    
    db_session.commit()
    for task in tasks:
        db_session.refresh(task)
    
    return tasks


@pytest.fixture
def sample_token_usage(db_session: Session, test_user: User, sample_tasks):
    """샘플 토큰 사용 데이터 생성"""
    usages = []
    
    # Only add usage for completed tasks
    completed_tasks = [t for t in sample_tasks if t.status == TaskStatus.COMPLETED]
    
    models = [
        ("claude-3-5-sonnet-20241022", "anthropic", 1000, 4000),
        ("claude-3-5-sonnet-20241022", "anthropic", 2000, 6000),
        ("gpt-4-turbo", "openai", 1500, 3000),
        ("gpt-3.5-turbo", "openai", 500, 1000),
        ("claude-3-5-sonnet-20241022", "anthropic", 3000, 8000),
        ("gpt-4-turbo", "openai", 2000, 4000),
        ("gpt-3.5-turbo", "openai", 800, 1200),
    ]
    
    from app.services.cost_tracker import CostTracker
    
    for task, (model, provider, prompt_tokens, completion_tokens) in zip(completed_tasks, models):
        cost = CostTracker.calculate_cost(model, prompt_tokens, completion_tokens)
        
        usage = TokenUsage(
            id=str(uuid.uuid4()),
            task_id=str(task.id),
            user_id=str(test_user.id),
            model=model,
            provider=provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost_usd=cost,
            created_at=task.created_at
        )
        db_session.add(usage)
        usages.append(usage)
    
    db_session.commit()
    for usage in usages:
        db_session.refresh(usage)
    
    return usages


class TestPerformanceMetrics:
    """Performance metrics API 테스트"""
    
    def test_get_performance_metrics(
        self, client, auth_headers, test_user, sample_tasks
    ):
        """성능 메트릭스 조회"""
        response = client.get(
            "/api/v1/analytics/performance",
            headers=auth_headers
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
    
    def test_get_performance_metrics_with_time_range(
        self, client, auth_headers, test_user, sample_tasks
    ):
        """시간 범위 필터링"""
        response = client.get(
            "/api/v1/analytics/performance?time_range_hours=48",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have fewer tasks (within 48 hours)
        assert data["total_tasks"] <= 10
    
    def test_get_performance_metrics_unauthorized(self, client):
        """인증 실패"""
        response = client.get("/api/v1/analytics/performance")
        assert response.status_code == 401


class TestAgentStatistics:
    """Agent statistics API 테스트"""
    
    def test_get_agent_statistics(
        self, client, auth_headers, test_user, sample_tasks
    ):
        """에이전트 통계 조회"""
        response = client.get(
            "/api/v1/analytics/agents",
            headers=auth_headers
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
    
    def test_get_agent_statistics_with_time_range(
        self, client, auth_headers, test_user, sample_tasks
    ):
        """시간 범위 필터링"""
        response = client.get(
            "/api/v1/analytics/agents?time_range_hours=72",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)


class TestTaskTrends:
    """Task trends API 테스트"""
    
    def test_get_task_trends(
        self, client, auth_headers, test_user, sample_tasks
    ):
        """태스크 트렌드 조회"""
        response = client.get(
            "/api/v1/analytics/trends",
            headers=auth_headers
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
    
    def test_get_task_trends_with_days(
        self, client, auth_headers, test_user, sample_tasks
    ):
        """일수 지정"""
        response = client.get(
            "/api/v1/analytics/trends?days=14",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        # Should have up to 14 days of data
        assert len(data) <= 14


class TestDashboardSummary:
    """Dashboard summary API 테스트"""
    
    def test_get_dashboard_summary(
        self, client, auth_headers, test_user, sample_tasks
    ):
        """대시보드 요약 조회"""
        response = client.get(
            "/api/v1/analytics/summary",
            headers=auth_headers
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
    
    def test_get_dashboard_summary_no_tasks(
        self, client, auth_headers, test_user
    ):
        """태스크가 없는 경우"""
        response = client.get(
            "/api/v1/analytics/summary",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total_tasks"] == 0
        assert data["completed_tasks"] == 0
        assert data["success_rate"] == 0.0
        assert data["avg_completion_time_seconds"] == 0.0


class TestWeeklyROI:
    """Weekly ROI API 테스트"""
    
    def test_get_weekly_roi(
        self, client, auth_headers, test_user, sample_tasks
    ):
        """주간 ROI 조회"""
        response = client.get(
            "/api/v1/analytics/weekly-roi",
            headers=auth_headers
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
    
    def test_get_weekly_roi_custom_rate(
        self, client, auth_headers, test_user, sample_tasks
    ):
        """커스텀 시급 설정"""
        response = client.get(
            "/api/v1/analytics/weekly-roi?hourly_rate=100.0",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["hourly_rate"] == 100.0


class TestTokenUsageAPI:
    """Token usage API 테스트"""
    
    def test_get_token_usage(
        self, client, auth_headers, test_user, sample_token_usage
    ):
        """토큰 사용량 조회"""
        response = client.get(
            "/api/v1/analytics/token-usage",
            headers=auth_headers
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
    
    def test_get_token_usage_with_model_filter(
        self, client, auth_headers, test_user, sample_token_usage
    ):
        """모델 필터링"""
        response = client.get(
            "/api/v1/analytics/token-usage?model_filter=gpt-4-turbo",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["model_filter"] == "gpt-4-turbo"


class TestCostBreakdownAPI:
    """Cost breakdown API 테스트"""
    
    def test_get_cost_breakdown_by_model(
        self, client, auth_headers, test_user, sample_token_usage
    ):
        """모델별 비용 분석"""
        response = client.get(
            "/api/v1/analytics/cost-breakdown?group_by=model",
            headers=auth_headers
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
    
    def test_get_cost_breakdown_by_date(
        self, client, auth_headers, test_user, sample_token_usage
    ):
        """날짜별 비용 분석"""
        response = client.get(
            "/api/v1/analytics/cost-breakdown?group_by=date",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["group_by"] == "date"
        assert isinstance(data["breakdown"], list)
    
    def test_get_cost_breakdown_invalid_group_by(
        self, client, auth_headers
    ):
        """잘못된 group_by 파라미터"""
        response = client.get(
            "/api/v1/analytics/cost-breakdown?group_by=invalid",
            headers=auth_headers
        )
        
        assert response.status_code == 400


class TestBudgetAlerts:
    """Budget alerts API 테스트"""
    
    def test_check_budget_alert_under_budget(
        self, client, auth_headers, test_user, sample_token_usage
    ):
        """예산 내 사용"""
        response = client.post(
            "/api/v1/analytics/budget-alert?budget_limit_usd=100.0&period_days=30",
            headers=auth_headers
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
    
    def test_check_budget_alert_over_budget(
        self, client, auth_headers, test_user, sample_token_usage
    ):
        """예산 초과"""
        response = client.post(
            "/api/v1/analytics/budget-alert?budget_limit_usd=0.01&period_days=30",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # With sample usage, should be over this tiny budget
        # (actual result depends on cost calculation)
        assert "is_over_budget" in data


class TestOutcomeRing:
    """Outcome ring API 테스트"""
    
    def test_get_outcome_ring(
        self, client, auth_headers, test_user, sample_tasks
    ):
        """아웃컴 링 조회"""
        response = client.get(
            "/api/v1/analytics/outcome-ring",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "period_days" in data
        assert "total_outcomes" in data
        assert "status_breakdown" in data
        assert "task_type_breakdown" in data
        assert "cards" in data
        
        assert isinstance(data["cards"], list)
    
    def test_get_outcome_ring_with_status_filter(
        self, client, auth_headers, test_user, sample_tasks
    ):
        """상태 필터링"""
        response = client.get(
            "/api/v1/analytics/outcome-ring?status=completed",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # All cards should be completed
        for card in data["cards"]:
            assert card["status"] == "completed"


class TestCostTrustDashboard:
    """Cost & trust dashboard API 테스트"""
    
    def test_get_cost_trust_dashboard(
        self, client, auth_headers, test_user, sample_tasks, sample_token_usage
    ):
        """비용 & 신뢰 대시보드 조회"""
        response = client.get(
            "/api/v1/analytics/cost-trust",
            headers=auth_headers
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
    
    def test_get_cost_trust_dashboard_with_budget(
        self, client, auth_headers, test_user, sample_tasks, sample_token_usage
    ):
        """예산 제한 포함"""
        response = client.get(
            "/api/v1/analytics/cost-trust?monthly_budget_usd=50.0",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "budget_limit_usd" in data
        assert data["budget_limit_usd"] == 50.0
        assert "projected_monthly_cost_usd" in data
        assert "budget_status" in data


# pytest 실행 시 자동 탐지
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
