"""
Analytics Service for AI Insights Dashboard

Provides usage analytics, productivity insights, and cost optimization.
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, desc
from app.models.task import Task, TaskStatus
from app.models.user import User
import logging

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Service for generating analytics and insights"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_user_productivity_summary(
        self,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get productivity summary for a user
        
        Returns:
            - total_tasks: Total completed tasks
            - avg_completion_time: Average time to complete
            - success_rate: Percentage of successful tasks
            - most_used_agents: Top agent types
            - productivity_by_day: Daily breakdown
        """
        if not start_date:
            start_date = datetime.utcnow() - timedelta(days=30)
        if not end_date:
            end_date = datetime.utcnow()
        
        # Base query for user tasks in date range
        tasks_query = self.db.query(Task).filter(
            and_(
                Task.user_id == user_id,
                Task.created_at >= start_date,
                Task.created_at <= end_date
            )
        )
        
        # Total completed tasks
        completed_tasks = tasks_query.filter(
            Task.status == TaskStatus.COMPLETED
        ).count()
        
        # Success rate
        total_tasks = tasks_query.count()
        success_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        
        # Average completion time
        completed_with_time = tasks_query.filter(
            and_(
                Task.status == TaskStatus.COMPLETED,
                Task.completed_at.isnot(None)
            )
        ).all()
        
        avg_completion_seconds = 0
        if completed_with_time:
            completion_times = [
                (task.completed_at - task.created_at).total_seconds()
                for task in completed_with_time
                if task.completed_at
            ]
            avg_completion_seconds = sum(completion_times) / len(completion_times)
        
        # Most used agents
        agent_usage = self.db.query(
            Task.task_type,
            func.count(Task.id).label('count')
        ).filter(
            and_(
                Task.user_id == user_id,
                Task.created_at >= start_date,
                Task.created_at <= end_date
            )
        ).group_by(Task.task_type).order_by(desc('count')).limit(5).all()
        
        most_used_agents = [
            {"agent_type": agent_type, "count": count}
            for agent_type, count in agent_usage
        ]
        
        # Productivity by day
        daily_stats = self.db.query(
            func.date(Task.created_at).label('date'),
            func.count(Task.id).label('total'),
            func.sum(
                func.cast(Task.status == TaskStatus.COMPLETED, type_=func.Integer())
            ).label('completed')
        ).filter(
            and_(
                Task.user_id == user_id,
                Task.created_at >= start_date,
                Task.created_at <= end_date
            )
        ).group_by(func.date(Task.created_at)).order_by('date').all()
        
        productivity_by_day = [
            {
                "date": str(date),
                "total": total or 0,
                "completed": completed or 0
            }
            for date, total, completed in daily_stats
        ]
        
        return {
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "success_rate": round(success_rate, 2),
            "avg_completion_time_seconds": round(avg_completion_seconds, 2),
            "most_used_agents": most_used_agents,
            "productivity_by_day": productivity_by_day,
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            }
        }
    
    def get_cost_insights(
        self,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get LLM cost insights and optimization recommendations
        
        Returns:
            - total_cost_usd: Estimated total cost
            - cost_by_agent: Breakdown by agent type
            - cost_trend: Daily cost trend
            - optimization_tips: AI-generated cost saving recommendations
        """
        if not start_date:
            start_date = datetime.utcnow() - timedelta(days=30)
        if not end_date:
            end_date = datetime.utcnow()
        
        # TODO: Integrate with LangFuse for actual token usage
        # For now, estimate based on task count
        
        tasks = self.db.query(Task).filter(
            and_(
                Task.user_id == user_id,
                Task.created_at >= start_date,
                Task.created_at <= end_date,
                Task.status == TaskStatus.COMPLETED
            )
        ).all()
        
        # Rough cost estimates (GPT-4: $0.03/1K tokens input, $0.06/1K tokens output)
        # Average task: ~2K input + 1K output tokens
        avg_cost_per_task = 0.09  # $0.09 per task
        
        total_cost = len(tasks) * avg_cost_per_task
        
        # Cost by agent type
        agent_costs = {}
        for task in tasks:
            agent_type = task.task_type or "unknown"
            agent_costs[agent_type] = agent_costs.get(agent_type, 0) + avg_cost_per_task
        
        cost_by_agent = [
            {"agent_type": agent, "cost_usd": round(cost, 2)}
            for agent, cost in sorted(agent_costs.items(), key=lambda x: x[1], reverse=True)
        ]
        
        # Daily cost trend
        daily_tasks = {}
        for task in tasks:
            date_str = task.created_at.date().isoformat()
            daily_tasks[date_str] = daily_tasks.get(date_str, 0) + 1
        
        cost_trend = [
            {"date": date, "cost_usd": round(count * avg_cost_per_task, 2)}
            for date, count in sorted(daily_tasks.items())
        ]
        
        # Optimization tips
        optimization_tips = self._generate_cost_optimization_tips(
            tasks, total_cost, agent_costs
        )
        
        return {
            "total_cost_usd": round(total_cost, 2),
            "cost_by_agent": cost_by_agent,
            "cost_trend": cost_trend,
            "optimization_tips": optimization_tips,
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            }
        }
    
    def _generate_cost_optimization_tips(
        self,
        tasks: List[Task],
        total_cost: float,
        agent_costs: Dict[str, float]
    ) -> List[Dict[str, Any]]:
        """Generate AI-powered cost optimization recommendations"""
        tips = []
        
        # Tip 1: High-cost agent usage
        if agent_costs:
            most_expensive_agent = max(agent_costs.items(), key=lambda x: x[1])
            if most_expensive_agent[1] > total_cost * 0.4:  # >40% of total cost
                tips.append({
                    "type": "agent_optimization",
                    "priority": "high",
                    "title": f"Optimize {most_expensive_agent[0]} usage",
                    "description": f"This agent accounts for ${round(most_expensive_agent[1], 2)} "
                                   f"({round(most_expensive_agent[1]/total_cost*100, 1)}% of costs). "
                                   f"Consider using simpler prompts or batch processing.",
                    "potential_savings_usd": round(most_expensive_agent[1] * 0.3, 2),
                    "potential_savings_percent": 30
                })
        
        # Tip 2: Failed tasks
        failed_count = len([t for t in tasks if t.status == TaskStatus.FAILED])
        if failed_count > len(tasks) * 0.1:  # >10% failure rate
            wasted_cost = failed_count * 0.09
            tips.append({
                "type": "reduce_failures",
                "priority": "medium",
                "title": "Reduce failed task rate",
                "description": f"You have {failed_count} failed tasks, wasting ${round(wasted_cost, 2)}. "
                               f"Review error patterns and improve prompts.",
                "potential_savings_usd": round(wasted_cost, 2),
                "potential_savings_percent": 10
            })
        
        # Tip 3: Batch processing
        if len(tasks) > 50:
            tips.append({
                "type": "batch_processing",
                "priority": "low",
                "title": "Enable batch processing for repetitive tasks",
                "description": "You have many similar tasks. Batch processing could reduce costs by 20%.",
                "potential_savings_usd": round(total_cost * 0.2, 2),
                "potential_savings_percent": 20
            })
        
        return tips
    
    def get_ai_recommendations(
        self,
        user_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get AI-powered productivity recommendations
        
        Analyzes user patterns and suggests improvements
        """
        # Get recent task history
        recent_tasks = self.db.query(Task).filter(
            and_(
                Task.user_id == user_id,
                Task.created_at >= datetime.utcnow() - timedelta(days=14)
            )
        ).order_by(desc(Task.created_at)).limit(100).all()
        
        recommendations = []
        
        # Pattern analysis
        if recent_tasks:
            # Recommendation 1: Peak productivity time
            hour_distribution = {}
            for task in recent_tasks:
                hour = task.created_at.hour
                hour_distribution[hour] = hour_distribution.get(hour, 0) + 1
            
            if hour_distribution:
                peak_hour = max(hour_distribution.items(), key=lambda x: x[1])[0]
                recommendations.append({
                    "type": "time_optimization",
                    "priority": "medium",
                    "title": f"Your peak productivity is at {peak_hour}:00",
                    "description": f"Schedule important tasks around {peak_hour}:00 for best results.",
                    "action": "view_schedule"
                })
            
            # Recommendation 2: Task success patterns
            agent_success_rates = {}
            for task in recent_tasks:
                agent_type = task.task_type or "unknown"
                if agent_type not in agent_success_rates:
                    agent_success_rates[agent_type] = {"success": 0, "total": 0}
                
                agent_success_rates[agent_type]["total"] += 1
                if task.status == TaskStatus.COMPLETED:
                    agent_success_rates[agent_type]["success"] += 1
            
            for agent_type, stats in agent_success_rates.items():
                if stats["total"] >= 5:  # Enough data
                    success_rate = stats["success"] / stats["total"]
                    if success_rate < 0.7:  # <70% success
                        recommendations.append({
                            "type": "improve_prompts",
                            "priority": "high",
                            "title": f"Low success rate with {agent_type}",
                            "description": f"Only {round(success_rate*100)}% success. "
                                           f"Try more specific prompts or examples.",
                            "action": "view_examples"
                        })
        
        # Recommendation 3: Workflow automation
        if len(recent_tasks) > 20:
            recommendations.append({
                "type": "workflow_automation",
                "priority": "medium",
                "title": "Consider setting up workflow automation",
                "description": "You have recurring tasks that could be automated. "
                               "This could save 30% of your time.",
                "action": "setup_workflows"
            })
        
        return recommendations
    
    def get_goal_progress(
        self,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Get user goal tracking and gamification stats
        
        Returns:
            - current_streak: Days of consecutive usage
            - total_tasks_completed: Lifetime completed tasks
            - badges: Earned achievements
            - next_milestone: Next achievement target
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            return {}
        
        # Total completed tasks
        total_completed = self.db.query(Task).filter(
            and_(
                Task.user_id == user_id,
                Task.status == TaskStatus.COMPLETED
            )
        ).count()
        
        # Calculate streak (consecutive days with at least 1 completed task)
        current_streak = self._calculate_streak(user_id)
        
        # Badges (achievements)
        badges = self._calculate_badges(total_completed, current_streak)
        
        # Next milestone
        next_milestone = self._get_next_milestone(total_completed, current_streak)
        
        return {
            "current_streak": current_streak,
            "total_tasks_completed": total_completed,
            "badges": badges,
            "next_milestone": next_milestone,
            "level": self._calculate_level(total_completed)
        }
    
    def _calculate_streak(self, user_id: str) -> int:
        """Calculate consecutive days of activity"""
        # Get all days with completed tasks, ordered by date descending
        days_with_tasks = self.db.query(
            func.date(Task.completed_at).label('date')
        ).filter(
            and_(
                Task.user_id == user_id,
                Task.status == TaskStatus.COMPLETED,
                Task.completed_at.isnot(None)
            )
        ).distinct().order_by(desc('date')).all()
        
        if not days_with_tasks:
            return 0
        
        streak = 0
        expected_date = datetime.utcnow().date()
        
        for (task_date,) in days_with_tasks:
            if task_date == expected_date or task_date == expected_date - timedelta(days=1):
                streak += 1
                expected_date = task_date - timedelta(days=1)
            else:
                break
        
        return streak
    
    def _calculate_badges(
        self,
        total_completed: int,
        current_streak: int
    ) -> List[Dict[str, Any]]:
        """Calculate earned badges/achievements"""
        badges = []
        
        # Task completion badges
        task_milestones = [
            (10, "🎯 First Steps", "Completed 10 tasks"),
            (50, "🚀 Rising Star", "Completed 50 tasks"),
            (100, "⭐ Expert", "Completed 100 tasks"),
            (500, "🏆 Master", "Completed 500 tasks"),
            (1000, "👑 Legend", "Completed 1,000 tasks")
        ]
        
        for threshold, name, description in task_milestones:
            if total_completed >= threshold:
                badges.append({
                    "name": name,
                    "description": description,
                    "earned_at": threshold,
                    "rarity": "gold" if threshold >= 500 else "silver" if threshold >= 100 else "bronze"
                })
        
        # Streak badges
        streak_milestones = [
            (7, "🔥 Week Warrior", "7-day streak"),
            (30, "💪 Monthly Master", "30-day streak"),
            (100, "🌟 Century Streak", "100-day streak")
        ]
        
        for threshold, name, description in streak_milestones:
            if current_streak >= threshold:
                badges.append({
                    "name": name,
                    "description": description,
                    "earned_at": threshold,
                    "rarity": "legendary" if threshold >= 100 else "gold" if threshold >= 30 else "silver"
                })
        
        return badges
    
    def _get_next_milestone(
        self,
        total_completed: int,
        current_streak: int
    ) -> Dict[str, Any]:
        """Get the next achievement milestone"""
        # Find next task milestone
        task_milestones = [10, 50, 100, 500, 1000, 5000]
        next_task_milestone = next((m for m in task_milestones if m > total_completed), 5000)
        
        # Find next streak milestone
        streak_milestones = [7, 30, 100, 365]
        next_streak_milestone = next((m for m in streak_milestones if m > current_streak), 365)
        
        # Return the closest one
        tasks_until_next = next_task_milestone - total_completed
        days_until_next = next_streak_milestone - current_streak
        
        if tasks_until_next <= days_until_next * 2:  # Roughly prefer task milestones
            return {
                "type": "tasks",
                "target": next_task_milestone,
                "current": total_completed,
                "remaining": tasks_until_next,
                "description": f"Complete {tasks_until_next} more tasks to unlock the next badge!"
            }
        else:
            return {
                "type": "streak",
                "target": next_streak_milestone,
                "current": current_streak,
                "remaining": days_until_next,
                "description": f"Keep your streak going for {days_until_next} more days!"
            }
    
    def _calculate_level(self, total_completed: int) -> int:
        """Calculate user level based on completed tasks"""
        # 10 tasks per level, up to level 100
        return min(total_completed // 10, 100)
