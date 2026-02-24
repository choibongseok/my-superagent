"""Tests for token usage tracking and cost calculation."""

import pytest
from datetime import datetime, timedelta
from app.services.cost_tracker import CostTracker, MODEL_PRICING


class TestCostCalculation:
    """Test LLM cost calculation logic."""
    
    def test_calculate_cost_claude_sonnet(self):
        """Test cost calculation for Claude 3.5 Sonnet."""
        model = "claude-3-5-sonnet-20241022"
        prompt_tokens = 1000
        completion_tokens = 500
        
        cost = CostTracker.calculate_cost(model, prompt_tokens, completion_tokens)
        
        # Expected: (1000 / 1M * $3) + (500 / 1M * $15) = $0.003 + $0.0075 = $0.0105
        expected = (1000 / 1_000_000 * 3.0) + (500 / 1_000_000 * 15.0)
        assert cost == pytest.approx(expected, rel=1e-6)
        assert cost == pytest.approx(0.0105, rel=1e-4)
    
    def test_calculate_cost_gpt4(self):
        """Test cost calculation for GPT-4."""
        model = "gpt-4"
        prompt_tokens = 2000
        completion_tokens = 1000
        
        cost = CostTracker.calculate_cost(model, prompt_tokens, completion_tokens)
        
        # Expected: (2000 / 1M * $30) + (1000 / 1M * $60) = $0.06 + $0.06 = $0.12
        expected = (2000 / 1_000_000 * 30.0) + (1000 / 1_000_000 * 60.0)
        assert cost == pytest.approx(expected, rel=1e-6)
        assert cost == pytest.approx(0.12, rel=1e-4)
    
    def test_calculate_cost_unknown_model_uses_default(self):
        """Test cost calculation for unknown model uses default pricing."""
        model = "unknown-model"
        prompt_tokens = 1000
        completion_tokens = 500
        
        cost = CostTracker.calculate_cost(model, prompt_tokens, completion_tokens)
        
        # Should use default pricing (same as Claude Sonnet)
        expected = (1000 / 1_000_000 * 3.0) + (500 / 1_000_000 * 15.0)
        assert cost == pytest.approx(expected, rel=1e-6)
    
    def test_calculate_cost_zero_tokens(self):
        """Test cost calculation with zero tokens."""
        model = "claude-3-5-sonnet-20241022"
        
        cost = CostTracker.calculate_cost(model, 0, 0)
        assert cost == 0.0
    
    def test_calculate_cost_large_numbers(self):
        """Test cost calculation with large token counts."""
        model = "gpt-4"
        prompt_tokens = 100_000
        completion_tokens = 50_000
        
        cost = CostTracker.calculate_cost(model, prompt_tokens, completion_tokens)
        
        # Expected: (100k / 1M * $30) + (50k / 1M * $60) = $3 + $3 = $6
        expected = (100_000 / 1_000_000 * 30.0) + (50_000 / 1_000_000 * 60.0)
        assert cost == pytest.approx(expected, rel=1e-6)
        assert cost == pytest.approx(6.0, rel=1e-4)


class TestModelPricing:
    """Test model pricing configuration."""
    
    def test_all_models_have_input_output_pricing(self):
        """Verify all model entries have input and output pricing."""
        for model, pricing in MODEL_PRICING.items():
            assert "input" in pricing, f"{model} missing input pricing"
            assert "output" in pricing, f"{model} missing output pricing"
            assert pricing["input"] > 0, f"{model} has invalid input pricing"
            assert pricing["output"] > 0, f"{model} has invalid output pricing"
    
    def test_default_pricing_exists(self):
        """Verify default pricing exists as fallback."""
        assert "default" in MODEL_PRICING
        assert MODEL_PRICING["default"]["input"] > 0
        assert MODEL_PRICING["default"]["output"] > 0
    
    def test_output_pricing_higher_than_input(self):
        """Verify output tokens are priced higher than input (common pattern)."""
        for model, pricing in MODEL_PRICING.items():
            if model == "gpt-3.5-turbo-16k":  # Exception
                continue
            assert pricing["output"] >= pricing["input"], (
                f"{model} has output pricing lower than input"
            )


class TestCostTrackerDB:
    """Test CostTracker database operations."""
    
    @pytest.fixture
    def sample_usage_data(self):
        """Sample token usage data for testing."""
        return {
            "task_id": "test-task-123",
            "user_id": "test-user-456",
            "model": "claude-3-5-sonnet-20241022",
            "provider": "anthropic",
            "prompt_tokens": 1000,
            "completion_tokens": 500,
        }
    
    def test_track_usage_creates_record(self, db_session, sample_usage_data):
        """Test that track_usage creates a TokenUsage record."""
        from app.models.token_usage import TokenUsage
        
        usage = CostTracker.track_usage(
            db=db_session,
            **sample_usage_data
        )
        
        assert usage.id is not None
        assert usage.task_id == sample_usage_data["task_id"]
        assert usage.user_id == sample_usage_data["user_id"]
        assert usage.model == sample_usage_data["model"]
        assert usage.provider == sample_usage_data["provider"]
        assert usage.prompt_tokens == sample_usage_data["prompt_tokens"]
        assert usage.completion_tokens == sample_usage_data["completion_tokens"]
        assert usage.total_tokens == 1500
        assert usage.cost_usd > 0
    
    def test_get_user_usage_aggregates_correctly(
        self, db_session, sample_usage_data
    ):
        """Test that get_user_usage returns correct aggregations."""
        # Create multiple usage records
        CostTracker.track_usage(
            db=db_session,
            **sample_usage_data
        )
        
        sample_usage_data["task_id"] = "test-task-456"
        sample_usage_data["prompt_tokens"] = 2000
        sample_usage_data["completion_tokens"] = 1000
        CostTracker.track_usage(
            db=db_session,
            **sample_usage_data
        )
        
        # Get aggregated stats
        stats = CostTracker.get_user_usage(
            db=db_session,
            user_id=sample_usage_data["user_id"]
        )
        
        assert stats["user_id"] == sample_usage_data["user_id"]
        assert stats["statistics"]["request_count"] == 2
        assert stats["statistics"]["prompt_tokens"] == 3000
        assert stats["statistics"]["completion_tokens"] == 1500
        assert stats["statistics"]["total_tokens"] == 4500
        assert stats["statistics"]["total_cost_usd"] > 0
    
    def test_get_user_usage_with_date_filter(
        self, db_session, sample_usage_data
    ):
        """Test that get_user_usage respects date filters."""
        CostTracker.track_usage(
            db=db_session,
            **sample_usage_data
        )
        
        # Query with future date range (should return 0)
        tomorrow = datetime.utcnow() + timedelta(days=1)
        next_week = datetime.utcnow() + timedelta(days=7)
        
        stats = CostTracker.get_user_usage(
            db=db_session,
            user_id=sample_usage_data["user_id"],
            start_date=tomorrow,
            end_date=next_week
        )
        
        assert stats["statistics"]["request_count"] == 0
        assert stats["statistics"]["total_tokens"] == 0
    
    def test_get_cost_breakdown_by_model(
        self, db_session, sample_usage_data
    ):
        """Test cost breakdown grouped by model."""
        # Create usage for Claude
        CostTracker.track_usage(
            db=db_session,
            **sample_usage_data
        )
        
        # Create usage for GPT-4
        sample_usage_data["task_id"] = "test-task-789"
        sample_usage_data["model"] = "gpt-4"
        sample_usage_data["provider"] = "openai"
        CostTracker.track_usage(
            db=db_session,
            **sample_usage_data
        )
        
        # Get breakdown
        breakdown = CostTracker.get_cost_breakdown(
            db=db_session,
            user_id=sample_usage_data["user_id"],
            group_by="model"
        )
        
        assert len(breakdown) == 2
        models = {item["model"] for item in breakdown}
        assert "claude-3-5-sonnet-20241022" in models
        assert "gpt-4" in models
    
    def test_check_budget_alert_under_budget(
        self, db_session, sample_usage_data
    ):
        """Test budget alert when under budget."""
        CostTracker.track_usage(
            db=db_session,
            **sample_usage_data
        )
        
        is_over_budget, alert_info = CostTracker.check_budget_alert(
            db=db_session,
            user_id=sample_usage_data["user_id"],
            budget_limit_usd=100.0,
            period_days=30
        )
        
        assert not is_over_budget
        assert alert_info["current_cost_usd"] < alert_info["budget_limit_usd"]
        assert alert_info["remaining_budget_usd"] > 0
        assert alert_info["utilization_percent"] < 100
    
    def test_check_budget_alert_over_budget(
        self, db_session, sample_usage_data
    ):
        """Test budget alert when over budget."""
        CostTracker.track_usage(
            db=db_session,
            **sample_usage_data
        )
        
        # Set very low budget
        is_over_budget, alert_info = CostTracker.check_budget_alert(
            db=db_session,
            user_id=sample_usage_data["user_id"],
            budget_limit_usd=0.001,
            period_days=30
        )
        
        assert is_over_budget
        assert alert_info["current_cost_usd"] >= alert_info["budget_limit_usd"]
        assert alert_info["remaining_budget_usd"] == 0
        assert alert_info["utilization_percent"] >= 100


class TestTokenUsageModel:
    """Test TokenUsage model relationships."""
    
    def test_token_usage_task_relationship(self, db_session):
        """Test TokenUsage -> Task relationship."""
        from app.models.task import Task, TaskStatus, TaskType
        from app.models.token_usage import TokenUsage
        from app.models.user import User
        from uuid import uuid4
        
        # Create user
        user = User(
            id=uuid4(),
            email="test@example.com",
            google_id="test-google-id",
        )
        db_session.add(user)
        
        # Create task
        task = Task(
            id=uuid4(),
            user_id=user.id,
            prompt="Test prompt",
            task_type=TaskType.DOCS,
            status=TaskStatus.PENDING,
        )
        db_session.add(task)
        db_session.commit()
        
        # Create token usage
        usage = TokenUsage(
            id=str(uuid4()),
            task_id=str(task.id),
            user_id=str(user.id),
            model="claude-3-5-sonnet-20241022",
            provider="anthropic",
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500,
            cost_usd=0.0105,
            created_at=datetime.utcnow()
        )
        db_session.add(usage)
        db_session.commit()
        
        # Verify relationship
        assert usage.task_id == str(task.id)
        assert len(task.token_usages) == 1
        assert task.token_usages[0].id == usage.id
