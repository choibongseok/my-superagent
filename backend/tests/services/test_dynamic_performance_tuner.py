"""Tests for Dynamic Performance Tuner service."""

import pytest
from datetime import timedelta

from app.services.dynamic_performance_tuner import (
    DynamicPerformanceTuner,
    ModelProfile,
    ModelTier,
    TaskComplexity,
    UserPreference,
    PerformanceMetrics,
)


@pytest.fixture
def tuner():
    """Create a fresh performance tuner instance."""
    return DynamicPerformanceTuner()


class TestModelProfile:
    """Tests for ModelProfile scoring."""
    
    def test_model_profile_cost_calculation(self):
        """Test cost estimation for a model profile."""
        profile = ModelProfile(
            name="gpt-4",
            tier=ModelTier.PREMIUM,
            cost_per_1k_tokens=0.03,
            avg_latency_ms=3000,
            accuracy_score=0.95,
            max_tokens=8192,
        )
        
        # Test cost calculation
        assert profile.estimated_cost(1000) == 0.03
        assert profile.estimated_cost(2500) == 0.075
    
    def test_model_profile_cost_preference_scoring(self):
        """Test model scoring with cost preference."""
        expensive_model = ModelProfile(
            name="gpt-4",
            tier=ModelTier.PREMIUM,
            cost_per_1k_tokens=0.03,
            avg_latency_ms=3000,
            accuracy_score=0.95,
            max_tokens=8192,
        )
        
        cheap_model = ModelProfile(
            name="gpt-3.5-turbo",
            tier=ModelTier.FAST,
            cost_per_1k_tokens=0.0005,
            avg_latency_ms=800,
            accuracy_score=0.75,
            max_tokens=4096,
        )
        
        # With cost preference, cheap model should score higher
        expensive_score = expensive_model.score(UserPreference.COST, TaskComplexity.SIMPLE)
        cheap_score = cheap_model.score(UserPreference.COST, TaskComplexity.SIMPLE)
        
        assert cheap_score > expensive_score
    
    def test_model_profile_speed_preference_scoring(self):
        """Test model scoring with speed preference."""
        slow_model = ModelProfile(
            name="gpt-4",
            tier=ModelTier.PREMIUM,
            cost_per_1k_tokens=0.03,
            avg_latency_ms=3000,
            accuracy_score=0.95,
            max_tokens=8192,
        )
        
        fast_model = ModelProfile(
            name="gpt-3.5-turbo",
            tier=ModelTier.FAST,
            cost_per_1k_tokens=0.0005,
            avg_latency_ms=800,
            accuracy_score=0.75,
            max_tokens=4096,
        )
        
        # With speed preference, fast model should score higher
        slow_score = slow_model.score(UserPreference.SPEED, TaskComplexity.SIMPLE)
        fast_score = fast_model.score(UserPreference.SPEED, TaskComplexity.SIMPLE)
        
        assert fast_score > slow_score
    
    def test_model_profile_accuracy_preference_scoring(self):
        """Test model scoring with accuracy preference."""
        accurate_model = ModelProfile(
            name="claude-3-5-sonnet-20241022",
            tier=ModelTier.PREMIUM,
            cost_per_1k_tokens=0.003,
            avg_latency_ms=2500,
            accuracy_score=0.97,
            max_tokens=8192,
        )
        
        less_accurate_model = ModelProfile(
            name="gpt-3.5-turbo",
            tier=ModelTier.FAST,
            cost_per_1k_tokens=0.0005,
            avg_latency_ms=800,
            accuracy_score=0.75,
            max_tokens=4096,
        )
        
        # With accuracy preference, accurate model should score higher
        accurate_score = accurate_model.score(UserPreference.ACCURACY, TaskComplexity.COMPLEX)
        less_accurate_score = less_accurate_model.score(UserPreference.ACCURACY, TaskComplexity.COMPLEX)
        
        assert accurate_score > less_accurate_score


class TestTaskComplexityAnalysis:
    """Tests for task complexity analysis."""
    
    @pytest.mark.asyncio
    async def test_simple_task_detection(self, tuner):
        """Test detection of simple tasks."""
        simple_prompts = [
            "Summarize this email",
            "Extract the key points",
            "List the main topics",
            "Quick summary please",
        ]
        
        for prompt in simple_prompts:
            complexity = await tuner.analyze_task_complexity(prompt)
            assert complexity == TaskComplexity.SIMPLE, f"Failed for: {prompt}"
    
    @pytest.mark.asyncio
    async def test_complex_task_detection(self, tuner):
        """Test detection of complex tasks."""
        complex_prompts = [
            "Analyze the legal implications of this contract in detail",
            "Provide a comprehensive technical analysis of the system",
            "Perform a detailed medical diagnosis based on these symptoms",
        ]
        
        for prompt in complex_prompts:
            complexity = await tuner.analyze_task_complexity(prompt)
            assert complexity == TaskComplexity.COMPLEX, f"Failed for: {prompt}"
    
    @pytest.mark.asyncio
    async def test_creative_task_detection(self, tuner):
        """Test detection of creative tasks."""
        creative_prompts = [
            "Create a creative marketing campaign",
            "Design an innovative solution",
            "Brainstorm creative ideas for the project",
            "Imagine a futuristic scenario",
        ]
        
        for prompt in creative_prompts:
            complexity = await tuner.analyze_task_complexity(prompt)
            assert complexity == TaskComplexity.CREATIVE, f"Failed for: {prompt}"
    
    @pytest.mark.asyncio
    async def test_moderate_task_detection(self, tuner):
        """Test detection of moderate complexity tasks."""
        moderate_prompt = "Write a report on Q4 sales performance"
        complexity = await tuner.analyze_task_complexity(moderate_prompt)
        assert complexity == TaskComplexity.MODERATE


class TestModelSelection:
    """Tests for optimal model selection."""
    
    @pytest.mark.asyncio
    async def test_simple_task_model_selection(self, tuner):
        """Test model selection for simple tasks."""
        prompt = "Summarize this email"
        model, params = await tuner.select_optimal_model(
            prompt,
            UserPreference.COST,
        )
        
        # Should select a cheap, fast model
        assert model in ["gpt-3.5-turbo", "claude-3-haiku-20240307"]
        assert params["temperature"] == 0.1  # Low temperature for simple tasks
        assert params["max_tokens"] <= 512
    
    @pytest.mark.asyncio
    async def test_complex_task_model_selection(self, tuner):
        """Test model selection for complex tasks."""
        prompt = "Analyze the legal implications of this contract in detail"
        model, params = await tuner.select_optimal_model(
            prompt,
            UserPreference.ACCURACY,
        )
        
        # Should select a high-accuracy model
        assert model in ["gpt-4", "claude-3-5-sonnet-20241022"]
        assert params["temperature"] <= 0.3  # Low-moderate temperature for accuracy
        assert params["max_tokens"] >= 2048
    
    @pytest.mark.asyncio
    async def test_creative_task_model_selection(self, tuner):
        """Test model selection for creative tasks."""
        prompt = "Create a creative marketing campaign"
        model, params = await tuner.select_optimal_model(
            prompt,
            UserPreference.BALANCED,
        )
        
        # Should use high temperature for creativity
        assert params["temperature"] >= 0.7
        assert params["max_tokens"] >= 1024
    
    @pytest.mark.asyncio
    async def test_speed_preference_model_selection(self, tuner):
        """Test model selection with speed preference."""
        prompt = "Write a report"
        model, params = await tuner.select_optimal_model(
            prompt,
            UserPreference.SPEED,
        )
        
        # Should select a fast model
        assert model in ["gpt-3.5-turbo", "gpt-4o-mini", "claude-3-haiku-20240307"]
    
    @pytest.mark.asyncio
    async def test_available_models_filtering(self, tuner):
        """Test model selection with limited available models."""
        prompt = "Summarize this"
        available_models = ["gpt-4", "gpt-3.5-turbo"]  # Only OpenAI models
        
        model, params = await tuner.select_optimal_model(
            prompt,
            UserPreference.COST,
            available_models,
        )
        
        # Should only select from available models
        assert model in available_models


class TestPerformanceMonitoring:
    """Tests for performance monitoring."""
    
    @pytest.mark.asyncio
    async def test_monitor_execution_success(self, tuner):
        """Test successful execution monitoring."""
        task_id = "test-task-123"
        agent_type = "research"
        
        # Simulate execution
        async with tuner.monitor_execution(task_id, agent_type, "web_search"):
            # Simulate work
            import asyncio
            await asyncio.sleep(0.1)
        
        # Check metrics were recorded
        metrics = tuner.metrics_buffer
        assert len(metrics) == 1
        assert metrics[0].task_id == task_id
        assert metrics[0].agent_type == agent_type
        assert metrics[0].step_name == "web_search"
        assert metrics[0].duration_ms >= 100  # At least 100ms
        assert metrics[0].error is None
    
    @pytest.mark.asyncio
    async def test_monitor_execution_error(self, tuner):
        """Test execution monitoring with error."""
        task_id = "test-task-456"
        agent_type = "docs"
        
        # Simulate execution with error
        try:
            async with tuner.monitor_execution(task_id, agent_type, "create_doc"):
                raise ValueError("Test error")
        except ValueError:
            pass
        
        # Check metrics were recorded with error
        metrics = tuner.metrics_buffer
        assert len(metrics) > 0
        last_metric = metrics[-1]
        assert last_metric.error == "Test error"
    
    @pytest.mark.asyncio
    async def test_get_realtime_metrics(self, tuner):
        """Test retrieving realtime metrics for a task."""
        task_id = "test-task-789"
        
        # Record multiple steps
        async with tuner.monitor_execution(task_id, "research", "step1"):
            pass
        
        async with tuner.monitor_execution(task_id, "research", "step2"):
            pass
        
        # Get metrics
        metrics = await tuner.get_realtime_metrics(task_id)
        assert len(metrics) == 2
        assert all(m.task_id == task_id for m in metrics)


class TestCacheStatistics:
    """Tests for cache statistics tracking."""
    
    @pytest.mark.asyncio
    async def test_cache_hit_tracking(self, tuner):
        """Test cache hit/miss tracking."""
        # Reset stats
        tuner.cache_stats = {"hits": 0, "misses": 0}
        
        # Record hits and misses
        await tuner.record_cache_hit(True)
        await tuner.record_cache_hit(True)
        await tuner.record_cache_hit(False)
        
        # Check stats
        assert tuner.cache_stats["hits"] == 2
        assert tuner.cache_stats["misses"] == 1
        assert tuner.get_cache_hit_rate() == 2/3
    
    def test_cache_hit_rate_with_no_data(self, tuner):
        """Test cache hit rate calculation with no data."""
        tuner.cache_stats = {"hits": 0, "misses": 0}
        assert tuner.get_cache_hit_rate() == 0.0


class TestPerformanceRecommendations:
    """Tests for performance recommendations."""
    
    @pytest.mark.asyncio
    async def test_model_switch_recommendation(self, tuner):
        """Test recommendation for model switching."""
        # Mock heavy GPT-4 usage
        user_id = "test-user-123"
        
        # Note: In a real test, we'd mock the performance summary
        # For now, test the recommendation structure
        recommendations = await tuner.get_recommendations(user_id)
        
        # Should return a list (may be empty without real data)
        assert isinstance(recommendations, list)
    
    @pytest.mark.asyncio
    async def test_recommendations_structure(self, tuner):
        """Test that recommendations have the correct structure."""
        user_id = "test-user-456"
        recommendations = await tuner.get_recommendations(user_id)
        
        # Check structure (if any recommendations exist)
        for rec in recommendations:
            assert hasattr(rec, 'type')
            assert hasattr(rec, 'current_state')
            assert hasattr(rec, 'recommended_state')
            assert hasattr(rec, 'estimated_improvement')
            assert hasattr(rec, 'explanation')
            assert hasattr(rec, 'confidence')
            assert 0.0 <= rec.confidence <= 1.0


class TestParameterOptimization:
    """Tests for parameter optimization."""
    
    def test_simple_task_parameters(self, tuner):
        """Test parameter generation for simple tasks."""
        params = tuner._generate_optimal_params(
            TaskComplexity.SIMPLE,
            tuner.model_profiles["gpt-3.5-turbo"],
        )
        
        assert params["temperature"] == 0.1  # Low creativity
        assert params["top_p"] == 0.9
        assert params["max_tokens"] <= 512
    
    def test_creative_task_parameters(self, tuner):
        """Test parameter generation for creative tasks."""
        params = tuner._generate_optimal_params(
            TaskComplexity.CREATIVE,
            tuner.model_profiles["gpt-4"],
        )
        
        assert params["temperature"] == 0.9  # High creativity
        assert params["top_p"] == 0.95
        assert params["max_tokens"] >= 2048
    
    def test_complex_task_parameters(self, tuner):
        """Test parameter generation for complex tasks."""
        params = tuner._generate_optimal_params(
            TaskComplexity.COMPLEX,
            tuner.model_profiles["claude-3-5-sonnet-20241022"],
        )
        
        assert params["temperature"] == 0.3  # Moderate creativity
        assert params["max_tokens"] >= 4096


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
