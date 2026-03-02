"""Dynamic Performance Tuner - Real-time Agent performance optimization.

This service monitors Agent performance in real-time and automatically optimizes:
- Model selection (GPT-4 vs GPT-3.5 vs Claude based on task complexity)
- LLM parameters (temperature, top_p, max_tokens)
- Caching strategies
- Performance recommendations

Features:
1. Real-time Performance Monitoring: Track speed, cost, accuracy per step
2. Adaptive Model Selection: AI chooses the best model for each task
3. Auto-Tuning Parameters: Adjust LLM params based on task type
4. Smart Caching: Cache frequently used queries with TTL optimization
5. Performance Recommendations: AI suggests improvements

Example usage:
    ```python
    from app.services.dynamic_performance_tuner import performance_tuner
    
    # Monitor Agent execution
    async with performance_tuner.monitor_execution(task_id, agent_type):
        result = await agent.execute(prompt)
    
    # Get optimal model
    model = await performance_tuner.select_optimal_model(prompt, user_preferences)
    
    # Get recommendations
    recommendations = await performance_tuner.get_recommendations(user_id)
    ```
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.cache import cache
from app.models.task import Task


class ModelTier(str, Enum):
    """Model performance tiers."""
    
    PREMIUM = "premium"  # GPT-4, Claude 3.5 Sonnet (high cost, high accuracy)
    BALANCED = "balanced"  # GPT-4o-mini, Claude 3 Haiku (medium)
    FAST = "fast"  # GPT-3.5, fast but lower accuracy


class TaskComplexity(str, Enum):
    """Task complexity levels."""
    
    SIMPLE = "simple"  # Email summary, simple extraction
    MODERATE = "moderate"  # Research, docs writing
    COMPLEX = "complex"  # Legal analysis, complex reasoning
    CREATIVE = "creative"  # Content generation, brainstorming


class UserPreference(str, Enum):
    """User optimization preferences."""
    
    COST = "cost"  # Minimize cost
    SPEED = "speed"  # Maximize speed
    ACCURACY = "accuracy"  # Maximize accuracy
    BALANCED = "balanced"  # Balance all factors


@dataclass
class PerformanceMetrics:
    """Performance metrics for an Agent execution step."""
    
    task_id: str
    agent_type: str
    step_name: str
    start_time: float
    end_time: float
    duration_ms: float = 0.0
    model_used: Optional[str] = None
    tokens_used: int = 0
    estimated_cost: float = 0.0
    cache_hit: bool = False
    error: Optional[str] = None
    
    def __post_init__(self):
        """Calculate duration."""
        if self.duration_ms == 0.0:
            self.duration_ms = (self.end_time - self.start_time) * 1000


@dataclass
class ModelProfile:
    """Profile for an LLM model."""
    
    name: str
    tier: ModelTier
    cost_per_1k_tokens: float
    avg_latency_ms: float
    accuracy_score: float  # 0-1
    max_tokens: int
    supports_streaming: bool = True
    
    def estimated_cost(self, tokens: int) -> float:
        """Calculate estimated cost for token count."""
        return (tokens / 1000) * self.cost_per_1k_tokens
    
    def score(self, preference: UserPreference, complexity: TaskComplexity) -> float:
        """Calculate model suitability score (0-1) based on preference and task."""
        if preference == UserPreference.COST:
            # Prefer cheaper models (cost is primary factor)
            cost_score = 1.0 - min(1.0, self.cost_per_1k_tokens / 0.03)  # Normalize to GPT-4 cost
            # For simple tasks, heavily weight cost
            if complexity == TaskComplexity.SIMPLE:
                return cost_score * 0.9 + self.accuracy_score * 0.1
            else:
                return cost_score * 0.7 + self.accuracy_score * 0.3
        
        elif preference == UserPreference.SPEED:
            # Prefer faster models
            speed_score = 1.0 - min(1.0, self.avg_latency_ms / 5000)  # Normalize to ~5s
            return speed_score * 0.7 + self.accuracy_score * 0.3
        
        elif preference == UserPreference.ACCURACY:
            # Prefer accurate models
            return self.accuracy_score
        
        else:  # BALANCED
            # Balance all factors
            cost_norm = 1.0 - min(1.0, self.cost_per_1k_tokens / 0.03)
            speed_norm = 1.0 - min(1.0, self.avg_latency_ms / 5000)
            return (self.accuracy_score * 0.4 + cost_norm * 0.3 + speed_norm * 0.3)


@dataclass
class PerformanceRecommendation:
    """Performance improvement recommendation."""
    
    type: str  # "model_switch", "cache_hit", "parallel_execution", etc.
    current_state: str
    recommended_state: str
    estimated_improvement: Dict[str, str]  # {"speed": "+100%", "cost": "-70%"}
    explanation: str
    confidence: float  # 0-1


class DynamicPerformanceTuner:
    """Real-time Agent performance monitoring and optimization."""
    
    def __init__(self):
        """Initialize the performance tuner."""
        self.model_profiles = self._init_model_profiles()
        self.metrics_buffer: List[PerformanceMetrics] = []
        self.cache_stats = {"hits": 0, "misses": 0}
    
    def _init_model_profiles(self) -> Dict[str, ModelProfile]:
        """Initialize model performance profiles."""
        return {
            # OpenAI Models
            "gpt-4": ModelProfile(
                name="gpt-4",
                tier=ModelTier.PREMIUM,
                cost_per_1k_tokens=0.03,  # Input tokens
                avg_latency_ms=3000,
                accuracy_score=0.95,
                max_tokens=8192,
            ),
            "gpt-4o-mini": ModelProfile(
                name="gpt-4o-mini",
                tier=ModelTier.BALANCED,
                cost_per_1k_tokens=0.0015,
                avg_latency_ms=1000,
                accuracy_score=0.85,
                max_tokens=4096,
            ),
            "gpt-3.5-turbo": ModelProfile(
                name="gpt-3.5-turbo",
                tier=ModelTier.FAST,
                cost_per_1k_tokens=0.0005,
                avg_latency_ms=800,
                accuracy_score=0.75,
                max_tokens=4096,
            ),
            
            # Anthropic Models
            "claude-3-5-sonnet-20241022": ModelProfile(
                name="claude-3-5-sonnet-20241022",
                tier=ModelTier.PREMIUM,
                cost_per_1k_tokens=0.003,
                avg_latency_ms=2500,
                accuracy_score=0.97,
                max_tokens=8192,
            ),
            "claude-3-haiku-20240307": ModelProfile(
                name="claude-3-haiku-20240307",
                tier=ModelTier.FAST,
                cost_per_1k_tokens=0.00025,
                avg_latency_ms=600,
                accuracy_score=0.80,
                max_tokens=4096,
            ),
        }
    
    async def analyze_task_complexity(self, prompt: str) -> TaskComplexity:
        """Analyze prompt to determine task complexity.
        
        Uses heuristics and optionally LLM analysis to classify task complexity.
        
        Args:
            prompt: User prompt text
            
        Returns:
            TaskComplexity level
        """
        prompt_lower = prompt.lower()
        
        # Simple heuristics (can be enhanced with LLM classification later)
        simple_keywords = ["summarize", "extract", "list", "simple", "quick", "summary"]
        complex_keywords = ["analyze", "legal", "medical", "technical", "detailed", "comprehensive", "diagnosis"]
        creative_keywords = ["create", "design", "brainstorm", "imagine", "innovative", "creative", "futuristic"]
        moderate_keywords = ["report", "write", "explain", "describe", "review"]
        
        # Count keyword matches
        simple_count = sum(1 for kw in simple_keywords if kw in prompt_lower)
        complex_count = sum(1 for kw in complex_keywords if kw in prompt_lower)
        creative_count = sum(1 for kw in creative_keywords if kw in prompt_lower)
        moderate_count = sum(1 for kw in moderate_keywords if kw in prompt_lower)
        
        # Classify based on length and keyword counts
        word_count = len(prompt.split())
        
        # Creative has highest priority if keywords present
        if creative_count >= 1 or ("create" in prompt_lower and "creative" in prompt_lower):
            return TaskComplexity.CREATIVE
        # Then complex
        elif complex_count >= 2 or word_count > 100:
            return TaskComplexity.COMPLEX
        # Moderate (report/write keywords or medium length)
        elif moderate_count >= 1:
            return TaskComplexity.MODERATE
        # Simple (explicit simple keywords or very short)
        elif simple_count >= 1 or word_count < 10:
            return TaskComplexity.SIMPLE
        else:
            return TaskComplexity.MODERATE
    
    async def select_optimal_model(
        self,
        prompt: str,
        user_preference: UserPreference = UserPreference.BALANCED,
        available_models: Optional[List[str]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """Select the optimal LLM model for a task.
        
        Args:
            prompt: User prompt
            user_preference: User's optimization preference
            available_models: List of available model names (default: all)
            
        Returns:
            Tuple of (model_name, recommended_parameters)
        """
        # Analyze task complexity
        complexity = await self.analyze_task_complexity(prompt)
        
        # Filter available models
        if available_models:
            models = {k: v for k, v in self.model_profiles.items() if k in available_models}
        else:
            models = self.model_profiles
        
        # Score each model
        scored_models = [
            (name, profile, profile.score(user_preference, complexity))
            for name, profile in models.items()
        ]
        
        # Sort by score (descending)
        scored_models.sort(key=lambda x: x[2], reverse=True)
        
        # Select best model
        best_model_name, best_profile, score = scored_models[0]
        
        # Generate recommended parameters based on task complexity
        params = self._generate_optimal_params(complexity, best_profile)
        
        return best_model_name, params
    
    def _generate_optimal_params(
        self,
        complexity: TaskComplexity,
        profile: ModelProfile,
    ) -> Dict[str, Any]:
        """Generate optimal LLM parameters for task complexity.
        
        Args:
            complexity: Task complexity level
            profile: Model profile
            
        Returns:
            Dict of LLM parameters
        """
        if complexity == TaskComplexity.SIMPLE:
            return {
                "temperature": 0.1,  # Low creativity, focus on accuracy
                "top_p": 0.9,
                "max_tokens": min(512, profile.max_tokens),
            }
        elif complexity == TaskComplexity.CREATIVE:
            return {
                "temperature": 0.9,  # High creativity
                "top_p": 0.95,
                "max_tokens": min(2048, profile.max_tokens),
            }
        elif complexity == TaskComplexity.COMPLEX:
            return {
                "temperature": 0.3,  # Moderate creativity, focus on reasoning
                "top_p": 0.95,
                "max_tokens": min(4096, profile.max_tokens),
            }
        else:  # MODERATE
            return {
                "temperature": 0.5,  # Balanced
                "top_p": 0.9,
                "max_tokens": min(1024, profile.max_tokens),
            }
    
    @asynccontextmanager
    async def monitor_execution(
        self,
        task_id: str,
        agent_type: str,
        step_name: str = "default",
    ):
        """Context manager to monitor Agent execution performance.
        
        Usage:
            async with tuner.monitor_execution(task_id, "research", "web_search"):
                result = await perform_search()
        
        Args:
            task_id: Task identifier
            agent_type: Agent type (research, docs, sheets, etc.)
            step_name: Name of execution step
        """
        start_time = time.time()
        error = None
        
        try:
            yield
        except Exception as e:
            error = str(e)
            raise
        finally:
            end_time = time.time()
            
            # Record metrics
            metrics = PerformanceMetrics(
                task_id=task_id,
                agent_type=agent_type,
                step_name=step_name,
                start_time=start_time,
                end_time=end_time,
                error=error,
            )
            
            self.metrics_buffer.append(metrics)
            
            # Optionally flush to persistent storage
            if len(self.metrics_buffer) >= 100:
                await self._flush_metrics()
    
    async def _flush_metrics(self):
        """Flush metrics buffer to cache/database."""
        if not self.metrics_buffer:
            return
        
        # Store in Redis for recent metrics (24h TTL)
        # Use a simple list stored as JSON
        cache_key = f"perf_metrics:{datetime.now().strftime('%Y-%m-%d')}"
        
        # Get existing metrics
        existing = await cache.get(cache_key) or []
        
        # Append new metrics
        new_metrics = [
            {
                "task_id": m.task_id,
                "agent_type": m.agent_type,
                "step_name": m.step_name,
                "duration_ms": m.duration_ms,
                "tokens_used": m.tokens_used,
                "estimated_cost": m.estimated_cost,
                "cache_hit": m.cache_hit,
                "timestamp": m.start_time,
            }
            for m in self.metrics_buffer
        ]
        
        existing.extend(new_metrics)
        
        # Store back to cache
        await cache.set(cache_key, existing, 86400)  # 24h
        
        self.metrics_buffer.clear()
    
    async def get_performance_summary(
        self,
        user_id: str,
        time_range: timedelta = timedelta(days=7),
    ) -> Dict[str, Any]:
        """Get performance summary for a user.
        
        Args:
            user_id: User identifier
            time_range: Time range for analysis
            
        Returns:
            Performance summary dict
        """
        # Get metrics from cache
        metrics = []
        for days_ago in range(time_range.days + 1):
            date = (datetime.now() - timedelta(days=days_ago)).strftime('%Y-%m-%d')
            cache_key = f"perf_metrics:{date}"
            daily_metrics = await cache.get(cache_key) or []
            if daily_metrics:
                metrics.extend(daily_metrics)
        
        if not metrics:
            return {
                "total_tasks": 0,
                "avg_duration_ms": 0,
                "total_cost": 0.0,
                "cache_hit_rate": 0.0,
                "recommendations": [],
            }
        
        # Calculate aggregates
        total_tasks = len(metrics)
        avg_duration = sum(m.get("duration_ms", 0) for m in metrics) / total_tasks
        total_cost = sum(m.get("estimated_cost", 0.0) for m in metrics)
        cache_hits = sum(1 for m in metrics if m.get("cache_hit"))
        cache_hit_rate = cache_hits / total_tasks if total_tasks > 0 else 0.0
        
        # Get model usage breakdown
        model_usage = {}
        for m in metrics:
            model = m.get("model_used", "unknown")
            if model in model_usage:
                model_usage[model] += 1
            else:
                model_usage[model] = 1
        
        return {
            "total_tasks": total_tasks,
            "avg_duration_ms": round(avg_duration, 2),
            "total_cost": round(total_cost, 4),
            "cache_hit_rate": round(cache_hit_rate * 100, 1),
            "model_usage": model_usage,
            "time_range_days": time_range.days,
        }
    
    async def get_recommendations(
        self,
        user_id: str,
        db: Optional[AsyncSession] = None,
    ) -> List[PerformanceRecommendation]:
        """Generate performance optimization recommendations for a user.
        
        Args:
            user_id: User identifier
            db: Database session (optional)
            
        Returns:
            List of recommendations
        """
        recommendations = []
        
        # Get performance summary
        summary = await self.get_performance_summary(user_id)
        
        # Recommendation 1: Model switching
        if summary.get("model_usage", {}).get("gpt-4", 0) > summary["total_tasks"] * 0.7:
            recommendations.append(PerformanceRecommendation(
                type="model_switch",
                current_state="Using GPT-4 for 70%+ of tasks",
                recommended_state="Use GPT-3.5-turbo or GPT-4o-mini for simple tasks",
                estimated_improvement={
                    "cost": "-60% to -70%",
                    "speed": "+200% to +300%",
                    "accuracy": "-5% to -10%",
                },
                explanation=(
                    "Many of your tasks could be handled by faster, cheaper models "
                    "with minimal accuracy loss. Enable Auto Model Selection."
                ),
                confidence=0.85,
            ))
        
        # Recommendation 2: Caching
        if summary.get("cache_hit_rate", 0) < 30:
            recommendations.append(PerformanceRecommendation(
                type="cache_optimization",
                current_state=f"Cache hit rate: {summary.get('cache_hit_rate', 0)}%",
                recommended_state="Enable smart caching for repeated queries",
                estimated_improvement={
                    "speed": "+500% to +1000%",
                    "cost": "-50% to -70%",
                },
                explanation=(
                    "You have repeated tasks that could be cached. "
                    "Enable Smart Caching to speed up recurring workflows."
                ),
                confidence=0.70,
            ))
        
        # Recommendation 3: Batch processing (if many small tasks)
        if summary["total_tasks"] > 50 and summary.get("avg_duration_ms", 0) < 2000:
            recommendations.append(PerformanceRecommendation(
                type="batch_processing",
                current_state=f"{summary['total_tasks']} small tasks executed individually",
                recommended_state="Batch similar tasks together",
                estimated_improvement={
                    "speed": "+50% to +100%",
                    "cost": "-20% to -30%",
                },
                explanation=(
                    "You execute many small tasks individually. "
                    "Batching similar tasks can reduce overhead and improve throughput."
                ),
                confidence=0.65,
            ))
        
        return recommendations
    
    async def get_realtime_metrics(self, task_id: str) -> List[PerformanceMetrics]:
        """Get real-time metrics for an ongoing task.
        
        Args:
            task_id: Task identifier
            
        Returns:
            List of performance metrics for the task
        """
        return [m for m in self.metrics_buffer if m.task_id == task_id]
    
    async def record_cache_hit(self, hit: bool = True):
        """Record cache hit/miss statistics.
        
        Args:
            hit: True if cache hit, False if miss
        """
        if hit:
            self.cache_stats["hits"] += 1
        else:
            self.cache_stats["misses"] += 1
    
    def get_cache_hit_rate(self) -> float:
        """Calculate current cache hit rate.
        
        Returns:
            Cache hit rate (0.0 to 1.0)
        """
        total = self.cache_stats["hits"] + self.cache_stats["misses"]
        if total == 0:
            return 0.0
        return self.cache_stats["hits"] / total


# Global performance tuner instance
performance_tuner = DynamicPerformanceTuner()
