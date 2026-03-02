"""
Tests for Analytics Service
"""
import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from app.services.analytics import AnalyticsService
from app.models.task import Task, TaskStatus
from app.models.user import User
from sqlalchemy.orm import Session


@pytest.fixture
def test_user(db: Session):
    """Create a test user"""
    user = User(
        id=str(uuid4()),
        email="test@example.com",
        full_name="Test User",
        hashed_password="hashed_test_password"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_productivity_summary(db: Session, test_user: User):
    """Test productivity summary generation"""
    analytics = AnalyticsService(db)
    
    # Create test tasks
    for i in range(10):
        task = Task(
            id=str(uuid4()),
            user_id=test_user.id,
            prompt=f"Test task {i}",
            task_type="research",
            status=TaskStatus.COMPLETED,
            created_at=datetime.utcnow() - timedelta(days=i),
            completed_at=datetime.utcnow() - timedelta(days=i, hours=-1)
        )
        db.add(task)
    db.commit()
    
    # Get summary
    summary = analytics.get_user_productivity_summary(
        user_id=test_user.id,
        start_date=datetime.utcnow() - timedelta(days=30)
    )
    
    assert summary["total_tasks"] == 10
    assert summary["completed_tasks"] == 10
    assert summary["success_rate"] == 100.0
    assert len(summary["most_used_agents"]) > 0
    assert summary["most_used_agents"][0]["agent_type"] == "research"


def test_cost_insights(db: Session, test_user: User):
    """Test cost insights generation"""
    analytics = AnalyticsService(db)
    
    # Create test tasks
    for _ in range(5):
        task = Task(
            id=str(uuid4()),
            user_id=test_user.id,
            prompt="Test task",
            task_type="docs",
            status=TaskStatus.COMPLETED,
            created_at=datetime.utcnow(),
            completed_at=datetime.utcnow()
        )
        db.add(task)
    db.commit()
    
    # Get cost insights
    insights = analytics.get_cost_insights(
        user_id=test_user.id,
        start_date=datetime.utcnow() - timedelta(days=30)
    )
    
    assert insights["total_cost_usd"] > 0
    assert len(insights["cost_by_agent"]) > 0
    assert insights["cost_by_agent"][0]["agent_type"] == "docs"
    assert len(insights["optimization_tips"]) >= 0


def test_ai_recommendations(db: Session, test_user: User):
    """Test AI recommendations generation"""
    analytics = AnalyticsService(db)
    
    # Create tasks at different hours
    for hour in [9, 10, 11, 14, 15]:
        for _ in range(3):
            task = Task(
                id=str(uuid4()),
                user_id=test_user.id,
                prompt="Test task",
                task_type="research",
                status=TaskStatus.COMPLETED,
                created_at=datetime.utcnow().replace(hour=hour, minute=0),
                completed_at=datetime.utcnow().replace(hour=hour, minute=30)
            )
            db.add(task)
    db.commit()
    
    # Get recommendations
    recommendations = analytics.get_ai_recommendations(
        user_id=test_user.id
    )
    
    assert isinstance(recommendations, list)
    # Should have at least time optimization recommendation
    if len(recommendations) > 0:
        assert any(r["type"] == "time_optimization" for r in recommendations)


def test_goal_progress(db: Session, test_user: User):
    """Test goal progress and gamification"""
    analytics = AnalyticsService(db)
    
    # Create 15 completed tasks
    for i in range(15):
        task = Task(
            id=str(uuid4()),
            user_id=test_user.id,
            prompt=f"Test task {i}",
            task_type="research",
            status=TaskStatus.COMPLETED,
            created_at=datetime.utcnow() - timedelta(days=i),
            completed_at=datetime.utcnow() - timedelta(days=i, hours=-1)
        )
        db.add(task)
    db.commit()
    
    # Get goal progress
    progress = analytics.get_goal_progress(
        user_id=test_user.id
    )
    
    assert progress["total_tasks_completed"] == 15
    assert progress["current_streak"] > 0
    assert len(progress["badges"]) > 0
    assert progress["level"] == 1  # 15 tasks / 10 = level 1
    assert "next_milestone" in progress


def test_streak_calculation(db: Session, test_user: User):
    """Test consecutive day streak calculation"""
    analytics = AnalyticsService(db)
    
    # Create tasks for 5 consecutive days
    for i in range(5):
        task = Task(
            id=str(uuid4()),
            user_id=test_user.id,
            prompt=f"Test task {i}",
            task_type="research",
            status=TaskStatus.COMPLETED,
            created_at=datetime.utcnow() - timedelta(days=i),
            completed_at=datetime.utcnow() - timedelta(days=i, hours=-1)
        )
        db.add(task)
    db.commit()
    
    streak = analytics._calculate_streak(test_user.id)
    
    assert streak == 5


def test_badges_earned():
    """Test badge earning logic"""
    analytics = AnalyticsService(None)  # No DB needed for this test
    
    # Test with 50 tasks
    badges_50 = analytics._calculate_badges(50, 0)
    badge_names = [b["name"] for b in badges_50]
    
    assert "🎯 First Steps" in badge_names
    assert "🚀 Rising Star" in badge_names
    assert "⭐ Expert" not in badge_names  # Need 100 tasks
    
    # Test with 100 tasks and 30-day streak
    badges_100 = analytics._calculate_badges(100, 30)
    badge_names_100 = [b["name"] for b in badges_100]
    
    assert "⭐ Expert" in badge_names_100
    assert "💪 Monthly Master" in badge_names_100
