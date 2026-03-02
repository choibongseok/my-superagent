"""Performance tuning API endpoints."""

from datetime import timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user, get_db
from app.models.user import User
from app.services.dynamic_performance_tuner import (
    performance_tuner,
    UserPreference,
    TaskComplexity,
    PerformanceRecommendation,
)


router = APIRouter(prefix="/performance", tags=["performance"])


class ModelSelectionRequest(BaseModel):
    """Request for optimal model selection."""
    
    prompt: str = Field(..., description="Task prompt to analyze")
    preference: UserPreference = Field(
        default=UserPreference.BALANCED,
        description="Optimization preference"
    )
    available_models: Optional[List[str]] = Field(
        default=None,
        description="List of available model names"
    )


class ModelSelectionResponse(BaseModel):
    """Response with optimal model and parameters."""
    
    model: str
    parameters: dict
    task_complexity: str
    rationale: str


class PerformanceSummaryResponse(BaseModel):
    """Performance summary statistics."""
    
    total_tasks: int
    avg_duration_ms: float
    total_cost: float
    cache_hit_rate: float
    model_usage: dict
    time_range_days: int


class RecommendationResponse(BaseModel):
    """Performance recommendation."""
    
    type: str
    current_state: str
    recommended_state: str
    estimated_improvement: dict
    explanation: str
    confidence: float


@router.post("/select-model", response_model=ModelSelectionResponse)
async def select_optimal_model(
    request: ModelSelectionRequest,
    current_user: User = Depends(get_current_user),
):
    """Select the optimal LLM model for a task.
    
    Analyzes the prompt and user preferences to recommend:
    - Best model (GPT-4, GPT-3.5, Claude, etc.)
    - Optimal parameters (temperature, top_p, max_tokens)
    - Task complexity level
    
    Example request:
        ```json
        {
            "prompt": "Summarize this email",
            "preference": "speed"
        }
        ```
    
    Example response:
        ```json
        {
            "model": "gpt-3.5-turbo",
            "parameters": {"temperature": 0.1, "top_p": 0.9, "max_tokens": 512},
            "task_complexity": "simple",
            "rationale": "Simple task → fast, cheap model sufficient"
        }
        ```
    """
    # Analyze complexity
    complexity = await performance_tuner.analyze_task_complexity(request.prompt)
    
    # Select model
    model, params = await performance_tuner.select_optimal_model(
        request.prompt,
        request.preference,
        request.available_models,
    )
    
    # Generate rationale
    rationale = _generate_model_rationale(complexity, model, request.preference)
    
    return ModelSelectionResponse(
        model=model,
        parameters=params,
        task_complexity=complexity.value,
        rationale=rationale,
    )


@router.get("/summary", response_model=PerformanceSummaryResponse)
async def get_performance_summary(
    days: int = Query(default=7, ge=1, le=90, description="Days to analyze"),
    current_user: User = Depends(get_current_user),
):
    """Get performance summary for the current user.
    
    Returns metrics for the specified time range:
    - Total tasks executed
    - Average duration
    - Total LLM cost
    - Cache hit rate
    - Model usage breakdown
    
    Example response:
        ```json
        {
            "total_tasks": 150,
            "avg_duration_ms": 2345.67,
            "total_cost": 1.23,
            "cache_hit_rate": 45.5,
            "model_usage": {"gpt-4": 100, "gpt-3.5-turbo": 50},
            "time_range_days": 7
        }
        ```
    """
    summary = await performance_tuner.get_performance_summary(
        str(current_user.id),
        timedelta(days=days),
    )
    
    return PerformanceSummaryResponse(**summary)


@router.get("/recommendations", response_model=List[RecommendationResponse])
async def get_recommendations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get performance optimization recommendations.
    
    AI analyzes your usage patterns and suggests improvements:
    - Switch to cheaper models for simple tasks
    - Enable caching for repeated queries
    - Batch similar tasks together
    - Adjust parameters for better results
    
    Each recommendation includes:
    - Type (model_switch, cache_optimization, etc.)
    - Current vs recommended state
    - Estimated improvement (speed, cost, accuracy)
    - Explanation
    - Confidence score
    
    Example response:
        ```json
        [
            {
                "type": "model_switch",
                "current_state": "Using GPT-4 for 70%+ of tasks",
                "recommended_state": "Use GPT-3.5-turbo for simple tasks",
                "estimated_improvement": {"cost": "-70%", "speed": "+200%"},
                "explanation": "Many tasks could use cheaper models...",
                "confidence": 0.85
            }
        ]
        ```
    """
    recommendations = await performance_tuner.get_recommendations(
        str(current_user.id),
        db,
    )
    
    return [
        RecommendationResponse(
            type=r.type,
            current_state=r.current_state,
            recommended_state=r.recommended_state,
            estimated_improvement=r.estimated_improvement,
            explanation=r.explanation,
            confidence=r.confidence,
        )
        for r in recommendations
    ]


@router.get("/realtime/{task_id}")
async def get_realtime_metrics(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get real-time performance metrics for an ongoing task.
    
    Returns:
    - Per-step execution times
    - Token usage
    - Cost estimates
    - Cache hits
    - Bottleneck detection
    
    Example response:
        ```json
        {
            "task_id": "abc123",
            "steps": [
                {
                    "step_name": "web_search",
                    "duration_ms": 2834.5,
                    "tokens_used": 1234,
                    "estimated_cost": 0.037,
                    "cache_hit": false,
                    "is_bottleneck": true
                },
                {
                    "step_name": "llm_analysis",
                    "duration_ms": 1245.2,
                    "tokens_used": 2456,
                    "estimated_cost": 0.074,
                    "cache_hit": false,
                    "is_bottleneck": false
                }
            ],
            "total_duration_ms": 4079.7,
            "total_cost": 0.111
        }
        ```
    """
    metrics = await performance_tuner.get_realtime_metrics(task_id)
    
    if not metrics:
        raise HTTPException(status_code=404, detail="No metrics found for this task")
    
    # Calculate totals
    total_duration = sum(m.duration_ms for m in metrics)
    total_cost = sum(m.estimated_cost for m in metrics)
    
    # Identify bottlenecks (steps taking >40% of total time)
    bottleneck_threshold = total_duration * 0.4
    
    steps = [
        {
            "step_name": m.step_name,
            "duration_ms": round(m.duration_ms, 2),
            "tokens_used": m.tokens_used,
            "estimated_cost": round(m.estimated_cost, 4),
            "cache_hit": m.cache_hit,
            "is_bottleneck": m.duration_ms >= bottleneck_threshold,
            "error": m.error,
        }
        for m in metrics
    ]
    
    return {
        "task_id": task_id,
        "steps": steps,
        "total_duration_ms": round(total_duration, 2),
        "total_cost": round(total_cost, 4),
        "cache_hit_rate": round(performance_tuner.get_cache_hit_rate() * 100, 1),
    }


@router.get("/cache-stats")
async def get_cache_stats(
    current_user: User = Depends(get_current_user),
):
    """Get current cache statistics.
    
    Returns:
        Current cache hit rate and stats
    """
    return {
        "cache_hit_rate": round(performance_tuner.get_cache_hit_rate() * 100, 1),
        "stats": performance_tuner.cache_stats,
    }


def _generate_model_rationale(
    complexity: TaskComplexity,
    model: str,
    preference: UserPreference,
) -> str:
    """Generate human-readable rationale for model selection.
    
    Args:
        complexity: Task complexity level
        model: Selected model
        preference: User preference
        
    Returns:
        Rationale string
    """
    complexity_desc = {
        TaskComplexity.SIMPLE: "simple task",
        TaskComplexity.MODERATE: "moderate complexity task",
        TaskComplexity.COMPLEX: "complex task requiring advanced reasoning",
        TaskComplexity.CREATIVE: "creative task",
    }
    
    preference_desc = {
        UserPreference.COST: "cost optimization",
        UserPreference.SPEED: "speed optimization",
        UserPreference.ACCURACY: "accuracy optimization",
        UserPreference.BALANCED: "balanced optimization",
    }
    
    model_tier = "premium" if "gpt-4" in model or "sonnet" in model else (
        "fast" if "3.5" in model or "haiku" in model else "balanced"
    )
    
    return (
        f"Selected {model} ({model_tier} tier) for {complexity_desc.get(complexity, 'unknown')} "
        f"with {preference_desc.get(preference, 'unknown')} preference. "
        f"This provides the best trade-off between speed, cost, and accuracy."
    )
