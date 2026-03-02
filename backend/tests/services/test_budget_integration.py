"""Integration tests for Budget Tracking service."""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch, call

from app.services.budget_service import BudgetService
from app.models.budget import (
    UserBudget,
    BudgetAlert,
    CostRecord,
    BudgetPeriod,
    BudgetAlertLevel,
)
from app.models.user import User


@pytest.fixture
def mock_db():
    """Create mock async database session."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    db.get = AsyncMock()
    return db


@pytest.fixture
def test_user():
    """Create a test user."""
    return User(
        id=uuid4(),
        email="budget_test@example.com",
        full_name="Budget Test User",
    )


@pytest.fixture
def budget_service(mock_db):
    """Create budget service instance."""
    return BudgetService(mock_db)


class TestBudgetCreation:
    """Test budget creation and management."""

    @pytest.mark.asyncio
    async def test_create_monthly_budget(self, budget_service, test_user, mock_db):
        """Test creating a monthly budget."""
        # Mock execute to return no existing budget
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_db.execute.return_value = mock_result

        budget = await budget_service.get_or_create_budget(
            user_id=test_user.id,
            period=BudgetPeriod.MONTHLY,
            limit_usd=100.0,
        )

        # Verify budget was created
        assert mock_db.add.called
        assert mock_db.commit.called
        
        added_budget = mock_db.add.call_args[0][0]
        assert isinstance(added_budget, UserBudget)
        assert added_budget.user_id == test_user.id
        assert added_budget.period == BudgetPeriod.MONTHLY
        assert added_budget.limit_usd == 100.0
        assert added_budget.current_spend_usd == 0.0

    @pytest.mark.asyncio
    async def test_get_existing_budget(self, budget_service, test_user, mock_db):
        """Test retrieving existing budget instead of creating new one."""
        # Create mock existing budget
        existing_budget = UserBudget(
            id=uuid4(),
            user_id=test_user.id,
            period=BudgetPeriod.MONTHLY,
            limit_usd=100.0,
            current_spend_usd=25.0,
            period_start=datetime.utcnow(),
            period_end=datetime.utcnow() + timedelta(days=30),
        )
        
        # Mock execute to return existing budget
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=existing_budget)
        mock_db.execute.return_value = mock_result

        budget = await budget_service.get_or_create_budget(
            user_id=test_user.id,
            period=BudgetPeriod.MONTHLY,
            limit_usd=200.0,  # Different limit
        )

        # Should return existing budget, not create new
        assert budget.id == existing_budget.id
        assert budget.limit_usd == 100.0  # Original limit preserved
        assert not mock_db.add.called  # No new budget added


class TestCostRecording:
    """Test cost recording and budget updates."""

    @pytest.mark.asyncio
    async def test_record_single_cost(self, budget_service, test_user, mock_db):
        """Test recording a single cost."""
        # Mock budget lookup
        budget = UserBudget(
            id=uuid4(),
            user_id=test_user.id,
            period=BudgetPeriod.MONTHLY,
            limit_usd=100.0,
            current_spend_usd=0.0,
            period_start=datetime.utcnow(),
            period_end=datetime.utcnow() + timedelta(days=30),
            enable_alerts=False,
        )
        
        mock_result = AsyncMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[budget])))
        mock_db.execute.return_value = mock_result

        # Record cost
        cost_record = await budget_service.record_cost(
            user_id=test_user.id,
            cost_usd=5.50,
            model="gpt-4",
            agent_type="research",
            input_tokens=1000,
            output_tokens=500,
        )

        # Verify cost record was added
        assert mock_db.add.call_count == 1
        added_cost = mock_db.add.call_args[0][0]
        assert isinstance(added_cost, CostRecord)
        assert added_cost.cost_usd == 5.50
        assert added_cost.model == "gpt-4"
        assert added_cost.agent_type == "research"
        assert added_cost.input_tokens == 1000
        assert added_cost.output_tokens == 500
        assert added_cost.total_tokens == 1500

        # Verify budget spend was updated
        assert budget.current_spend_usd == 5.50

    @pytest.mark.asyncio
    async def test_cost_with_metadata(self, budget_service, test_user, mock_db):
        """Test recording cost with metadata."""
        # Mock budget lookup
        budget = UserBudget(
            id=uuid4(),
            user_id=test_user.id,
            period=BudgetPeriod.MONTHLY,
            limit_usd=100.0,
            current_spend_usd=0.0,
            period_start=datetime.utcnow(),
            period_end=datetime.utcnow() + timedelta(days=30),
            enable_alerts=False,
        )
        
        mock_result = AsyncMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[budget])))
        mock_db.execute.return_value = mock_result

        metadata = {
            "request_id": "test-123",
            "endpoint": "/api/research",
            "duration_ms": 1500,
        }

        cost_record = await budget_service.record_cost(
            user_id=test_user.id,
            cost_usd=2.0,
            model="gpt-4",
            agent_type="research",
            metadata=metadata,
        )

        # Verify metadata was stored
        added_cost = mock_db.add.call_args[0][0]
        assert added_cost.metadata == metadata


class TestBudgetAlerts:
    """Test budget alert system."""

    @pytest.mark.asyncio
    async def test_warning_alert_triggered(self, budget_service, test_user, mock_db):
        """Test warning alert at 75% threshold."""
        budget = UserBudget(
            id=uuid4(),
            user_id=test_user.id,
            period=BudgetPeriod.MONTHLY,
            limit_usd=100.0,
            current_spend_usd=0.0,
            period_start=datetime.utcnow(),
            period_end=datetime.utcnow() + timedelta(days=30),
            enable_alerts=True,
            warning_threshold_pct=75,
            critical_threshold_pct=90,
        )
        
        # Mock budget lookups
        mock_result1 = AsyncMock()
        mock_result1.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[budget])))
        
        mock_result2 = AsyncMock()
        mock_result2.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[budget])))
        
        mock_db.execute.side_effect = [mock_result1, mock_result2]
        mock_db.get.return_value = test_user

        # Mock email service
        with patch.object(
            budget_service.email_service, "send_email", new_callable=AsyncMock
        ) as mock_send:
            # Record cost to reach 76%
            await budget_service.record_cost(
                user_id=test_user.id,
                cost_usd=76.0,
                model="gpt-4",
                agent_type="research",
            )

            # Verify email was sent
            assert mock_send.called
            call_args = mock_send.call_args[1]
            assert "⚠️" in call_args["subject"]

    @pytest.mark.asyncio
    async def test_critical_alert_triggered(self, budget_service, test_user, mock_db):
        """Test critical alert at 90% threshold."""
        budget = UserBudget(
            id=uuid4(),
            user_id=test_user.id,
            period=BudgetPeriod.MONTHLY,
            limit_usd=100.0,
            current_spend_usd=0.0,
            period_start=datetime.utcnow(),
            period_end=datetime.utcnow() + timedelta(days=30),
            enable_alerts=True,
            warning_threshold_pct=75,
            critical_threshold_pct=90,
        )
        
        # Mock budget lookups
        mock_result1 = AsyncMock()
        mock_result1.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[budget])))
        
        mock_result2 = AsyncMock()
        mock_result2.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[budget])))
        
        mock_db.execute.side_effect = [mock_result1, mock_result2]
        mock_db.get.return_value = test_user

        with patch.object(
            budget_service.email_service, "send_email", new_callable=AsyncMock
        ) as mock_send:
            # Record cost to reach 92%
            await budget_service.record_cost(
                user_id=test_user.id,
                cost_usd=92.0,
                model="gpt-4",
                agent_type="research",
            )

            assert mock_send.called
            call_args = mock_send.call_args[1]
            assert "🚨" in call_args["subject"]
            assert "CRITICAL" in call_args["body"]

    @pytest.mark.asyncio
    async def test_exceeded_alert_triggered(self, budget_service, test_user, mock_db):
        """Test exceeded alert at 100% threshold."""
        budget = UserBudget(
            id=uuid4(),
            user_id=test_user.id,
            period=BudgetPeriod.MONTHLY,
            limit_usd=100.0,
            current_spend_usd=0.0,
            period_start=datetime.utcnow(),
            period_end=datetime.utcnow() + timedelta(days=30),
            enable_alerts=True,
            budget_exceeded=False,
            warning_threshold_pct=75,
            critical_threshold_pct=90,
        )
        
        # Mock budget lookups
        mock_result1 = AsyncMock()
        mock_result1.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[budget])))
        
        mock_result2 = AsyncMock()
        mock_result2.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[budget])))
        
        mock_db.execute.side_effect = [mock_result1, mock_result2]
        mock_db.get.return_value = test_user

        with patch.object(
            budget_service.email_service, "send_email", new_callable=AsyncMock
        ) as mock_send:
            # Record cost to exceed budget
            await budget_service.record_cost(
                user_id=test_user.id,
                cost_usd=105.0,
                model="gpt-4",
                agent_type="research",
            )

            assert budget.budget_exceeded
            assert mock_send.called
            call_args = mock_send.call_args[1]
            assert "🛑" in call_args["subject"]
            assert "exceeded" in call_args["body"].lower()

    @pytest.mark.asyncio
    async def test_alerts_disabled(self, budget_service, test_user, mock_db):
        """Test alerts are not sent when disabled."""
        budget = UserBudget(
            id=uuid4(),
            user_id=test_user.id,
            period=BudgetPeriod.MONTHLY,
            limit_usd=100.0,
            current_spend_usd=0.0,
            period_start=datetime.utcnow(),
            period_end=datetime.utcnow() + timedelta(days=30),
            enable_alerts=False,  # Alerts disabled
        )
        
        # Mock budget lookups
        mock_result1 = AsyncMock()
        mock_result1.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[budget])))
        
        mock_result2 = AsyncMock()
        mock_result2.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))  # No budgets with alerts enabled
        
        mock_db.execute.side_effect = [mock_result1, mock_result2]

        with patch.object(
            budget_service.email_service, "send_email", new_callable=AsyncMock
        ) as mock_send:
            # Record cost to exceed budget
            await budget_service.record_cost(
                user_id=test_user.id,
                cost_usd=105.0,
                model="gpt-4",
                agent_type="research",
            )

            # No alert should be sent
            assert not mock_send.called


class TestCostSummary:
    """Test cost summary and analytics."""

    @pytest.mark.asyncio
    async def test_basic_cost_summary(self, budget_service, test_user, mock_db):
        """Test basic cost summary generation."""
        # Mock total cost query
        mock_result_total = AsyncMock()
        mock_result_total.scalar = MagicMock(return_value=30.0)
        
        # Mock by_agent query
        mock_result_agent = AsyncMock()
        mock_row_research = MagicMock()
        mock_row_research.agent_type = "research"
        mock_row_research.cost = 10.0
        mock_row_docs = MagicMock()
        mock_row_docs.agent_type = "docs"
        mock_row_docs.cost = 15.0
        mock_row_sheets = MagicMock()
        mock_row_sheets.agent_type = "sheets"
        mock_row_sheets.cost = 5.0
        mock_result_agent.__iter__ = MagicMock(return_value=iter([mock_row_research, mock_row_docs, mock_row_sheets]))
        
        # Mock by_model query
        mock_result_model = AsyncMock()
        mock_row_gpt4 = MagicMock()
        mock_row_gpt4.model = "gpt-4"
        mock_row_gpt4.cost = 25.0
        mock_row_claude = MagicMock()
        mock_row_claude.model = "claude-3-opus"
        mock_row_claude.cost = 5.0
        mock_result_model.__iter__ = MagicMock(return_value=iter([mock_row_gpt4, mock_row_claude]))
        
        # Mock budget query
        mock_result_budget = AsyncMock()
        mock_result_budget.scalar_one_or_none = MagicMock(return_value=None)
        
        mock_db.execute.side_effect = [
            mock_result_total,
            mock_result_agent,
            mock_result_model,
            mock_result_budget,
        ]

        summary = await budget_service.get_cost_summary(user_id=test_user.id)

        assert summary["total_cost_usd"] == pytest.approx(30.0, 0.01)
        assert "research" in summary["by_agent"]
        assert "docs" in summary["by_agent"]
        assert "sheets" in summary["by_agent"]
        assert "gpt-4" in summary["by_model"]
        assert "claude-3-opus" in summary["by_model"]


class TestPeriodCalculations:
    """Test budget period date calculations."""

    def test_calculate_daily_period(self, budget_service):
        """Test daily period calculation."""
        start, end = budget_service._calculate_period_dates(BudgetPeriod.DAILY)
        
        assert start.hour == 0
        assert start.minute == 0
        assert (end - start).days == 1

    def test_calculate_weekly_period(self, budget_service):
        """Test weekly period starts on Monday."""
        start, end = budget_service._calculate_period_dates(BudgetPeriod.WEEKLY)
        
        assert start.weekday() == 0  # Monday
        assert (end - start).days == 7

    def test_calculate_monthly_period(self, budget_service):
        """Test monthly period starts on 1st."""
        start, end = budget_service._calculate_period_dates(BudgetPeriod.MONTHLY)
        
        assert start.day == 1
        # End should be next month
        assert end.month != start.month or end.year != start.year

    def test_calculate_yearly_period(self, budget_service):
        """Test yearly period starts on January 1st."""
        start, end = budget_service._calculate_period_dates(BudgetPeriod.YEARLY)
        
        assert start.month == 1
        assert start.day == 1
        assert end.year == start.year + 1


# Run tests with:
# pytest backend/tests/services/test_budget_integration.py -v
# pytest backend/tests/services/test_budget_integration.py -v -k "test_create_budget"
# pytest backend/tests/services/test_budget_integration.py -v --cov=app.services.budget_service
