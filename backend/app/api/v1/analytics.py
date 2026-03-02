"""
Analytics API Endpoints

Provides AI Insights Dashboard data
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional
from app.database import get_db
from app.models.user import User
from app.api.dependencies import get_current_user
from app.services.analytics import AnalyticsService

router = APIRouter()


@router.get("/productivity/summary")
async def get_productivity_summary(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get productivity summary for the current user
    
    Returns:
        - Total tasks completed
        - Average completion time
        - Success rate
        - Most used agents
        - Daily productivity breakdown
    """
    analytics = AnalyticsService(db)
    
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    summary = analytics.get_user_productivity_summary(
        user_id=current_user.id,
        start_date=start_date,
        end_date=end_date
    )
    
    return summary


@router.get("/cost/insights")
async def get_cost_insights(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get LLM cost insights and optimization recommendations
    
    Returns:
        - Total cost (USD)
        - Cost breakdown by agent type
        - Daily cost trend
        - Cost optimization tips
    """
    analytics = AnalyticsService(db)
    
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    insights = analytics.get_cost_insights(
        user_id=current_user.id,
        start_date=start_date,
        end_date=end_date
    )
    
    return insights


@router.get("/recommendations")
async def get_ai_recommendations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get AI-powered productivity recommendations
    
    Analyzes recent activity and suggests improvements:
        - Optimal working hours
        - Agent usage patterns
        - Workflow automation opportunities
    """
    analytics = AnalyticsService(db)
    
    recommendations = analytics.get_ai_recommendations(
        user_id=current_user.id
    )
    
    return {"recommendations": recommendations}


@router.get("/goals")
async def get_goal_progress(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get goal tracking and gamification stats
    
    Returns:
        - Current streak (consecutive days)
        - Total tasks completed
        - Earned badges/achievements
        - Next milestone
        - User level
    """
    analytics = AnalyticsService(db)
    
    progress = analytics.get_goal_progress(
        user_id=current_user.id
    )
    
    return progress


@router.get("/dashboard")
async def get_dashboard_data(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get complete dashboard data in a single request
    
    Combines:
        - Productivity summary
        - Cost insights
        - AI recommendations
        - Goal progress
    
    Optimized for dashboard page load
    """
    analytics = AnalyticsService(db)
    
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    # Fetch all data
    productivity = analytics.get_user_productivity_summary(
        user_id=current_user.id,
        start_date=start_date,
        end_date=end_date
    )
    
    cost = analytics.get_cost_insights(
        user_id=current_user.id,
        start_date=start_date,
        end_date=end_date
    )
    
    recommendations = analytics.get_ai_recommendations(
        user_id=current_user.id
    )
    
    goals = analytics.get_goal_progress(
        user_id=current_user.id
    )
    
    return {
        "productivity": productivity,
        "cost": cost,
        "recommendations": recommendations,
        "goals": goals,
        "generated_at": datetime.utcnow().isoformat()
    }
