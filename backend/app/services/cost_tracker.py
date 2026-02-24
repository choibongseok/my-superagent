"""Cost tracking service for LLM token usage."""
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from app.models.token_usage import TokenUsage
from app.models.task import Task
from app.models.user import User


# Pricing per 1M tokens (USD)
# Source: https://www.anthropic.com/pricing, https://openai.com/api/pricing/
MODEL_PRICING = {
    # Anthropic Claude
    "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},
    "claude-3-5-sonnet-20240620": {"input": 3.0, "output": 15.0},
    "claude-3-opus-20240229": {"input": 15.0, "output": 75.0},
    "claude-3-sonnet-20240229": {"input": 3.0, "output": 15.0},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    
    # OpenAI GPT-4
    "gpt-4-turbo": {"input": 10.0, "output": 30.0},
    "gpt-4-0125-preview": {"input": 10.0, "output": 30.0},
    "gpt-4-1106-preview": {"input": 10.0, "output": 30.0},
    "gpt-4": {"input": 30.0, "output": 60.0},
    "gpt-4-32k": {"input": 60.0, "output": 120.0},
    
    # OpenAI GPT-3.5
    "gpt-3.5-turbo": {"input": 0.5, "output": 1.5},
    "gpt-3.5-turbo-16k": {"input": 3.0, "output": 4.0},
    
    # Default fallback (conservative estimate)
    "default": {"input": 3.0, "output": 15.0},
}


class CostTracker:
    """Service for tracking and calculating LLM costs."""
    
    @staticmethod
    def calculate_cost(
        model: str,
        prompt_tokens: int,
        completion_tokens: int
    ) -> float:
        """
        Calculate cost in USD for given token usage.
        
        Args:
            model: Model identifier (e.g., "claude-3-5-sonnet-20241022")
            prompt_tokens: Number of input tokens
            completion_tokens: Number of output tokens
            
        Returns:
            Cost in USD
        """
        pricing = MODEL_PRICING.get(model, MODEL_PRICING["default"])
        
        input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
        output_cost = (completion_tokens / 1_000_000) * pricing["output"]
        
        return input_cost + output_cost
    
    @staticmethod
    def track_usage(
        db: Session,
        task_id: str,
        user_id: str,
        model: str,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int
    ) -> TokenUsage:
        """
        Record token usage for a task.
        
        Args:
            db: Database session
            task_id: Task ID
            user_id: User ID
            model: Model identifier
            provider: Provider name (anthropic, openai)
            prompt_tokens: Input tokens
            completion_tokens: Output tokens
            
        Returns:
            TokenUsage record
        """
        total_tokens = prompt_tokens + completion_tokens
        cost_usd = CostTracker.calculate_cost(model, prompt_tokens, completion_tokens)
        
        usage = TokenUsage(
            id=str(uuid.uuid4()),
            task_id=task_id,
            user_id=user_id,
            model=model,
            provider=provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            created_at=datetime.utcnow()
        )
        
        db.add(usage)
        db.commit()
        db.refresh(usage)
        
        return usage
    
    @staticmethod
    def get_user_usage(
        db: Session,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        model_filter: Optional[str] = None
    ) -> Dict:
        """
        Get aggregated usage statistics for a user.
        
        Args:
            db: Database session
            user_id: User ID
            start_date: Start of date range (default: 30 days ago)
            end_date: End of date range (default: now)
            model_filter: Filter by model (optional)
            
        Returns:
            Dictionary with usage statistics
        """
        if start_date is None:
            start_date = datetime.utcnow() - timedelta(days=30)
        if end_date is None:
            end_date = datetime.utcnow()
        
        # Build query
        query = db.query(
            func.count(TokenUsage.id).label("request_count"),
            func.sum(TokenUsage.prompt_tokens).label("total_prompt_tokens"),
            func.sum(TokenUsage.completion_tokens).label("total_completion_tokens"),
            func.sum(TokenUsage.total_tokens).label("total_tokens"),
            func.sum(TokenUsage.cost_usd).label("total_cost")
        ).filter(
            and_(
                TokenUsage.user_id == user_id,
                TokenUsage.created_at >= start_date,
                TokenUsage.created_at <= end_date
            )
        )
        
        if model_filter:
            query = query.filter(TokenUsage.model == model_filter)
        
        result = query.one()
        
        return {
            "user_id": user_id,
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
            "model_filter": model_filter,
            "statistics": {
                "request_count": result.request_count or 0,
                "prompt_tokens": int(result.total_prompt_tokens or 0),
                "completion_tokens": int(result.total_completion_tokens or 0),
                "total_tokens": int(result.total_tokens or 0),
                "total_cost_usd": float(result.total_cost or 0.0),
            }
        }
    
    @staticmethod
    def get_cost_breakdown(
        db: Session,
        user_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        group_by: str = "model"
    ) -> List[Dict]:
        """
        Get cost breakdown grouped by model or date.
        
        Args:
            db: Database session
            user_id: User ID (optional, for admin queries)
            start_date: Start of date range
            end_date: End of date range
            group_by: "model" or "date"
            
        Returns:
            List of breakdown records
        """
        if start_date is None:
            start_date = datetime.utcnow() - timedelta(days=30)
        if end_date is None:
            end_date = datetime.utcnow()
        
        if group_by == "model":
            query = db.query(
                TokenUsage.model,
                TokenUsage.provider,
                func.count(TokenUsage.id).label("request_count"),
                func.sum(TokenUsage.total_tokens).label("total_tokens"),
                func.sum(TokenUsage.cost_usd).label("total_cost")
            ).filter(
                and_(
                    TokenUsage.created_at >= start_date,
                    TokenUsage.created_at <= end_date
                )
            )
            
            if user_id:
                query = query.filter(TokenUsage.user_id == user_id)
            
            query = query.group_by(TokenUsage.model, TokenUsage.provider)
            results = query.all()
            
            return [
                {
                    "model": r.model,
                    "provider": r.provider,
                    "request_count": r.request_count,
                    "total_tokens": int(r.total_tokens or 0),
                    "total_cost_usd": float(r.total_cost or 0.0),
                }
                for r in results
            ]
        
        elif group_by == "date":
            # Group by date (day)
            query = db.query(
                func.date(TokenUsage.created_at).label("date"),
                func.count(TokenUsage.id).label("request_count"),
                func.sum(TokenUsage.total_tokens).label("total_tokens"),
                func.sum(TokenUsage.cost_usd).label("total_cost")
            ).filter(
                and_(
                    TokenUsage.created_at >= start_date,
                    TokenUsage.created_at <= end_date
                )
            )
            
            if user_id:
                query = query.filter(TokenUsage.user_id == user_id)
            
            query = query.group_by(func.date(TokenUsage.created_at))
            query = query.order_by(func.date(TokenUsage.created_at))
            results = query.all()
            
            return [
                {
                    "date": str(r.date),
                    "request_count": r.request_count,
                    "total_tokens": int(r.total_tokens or 0),
                    "total_cost_usd": float(r.total_cost or 0.0),
                }
                for r in results
            ]
        
        else:
            raise ValueError(f"Invalid group_by parameter: {group_by}")
    
    @staticmethod
    def check_budget_alert(
        db: Session,
        user_id: str,
        budget_limit_usd: float,
        period_days: int = 30
    ) -> Tuple[bool, Dict]:
        """
        Check if user has exceeded budget limit.
        
        Args:
            db: Database session
            user_id: User ID
            budget_limit_usd: Budget limit in USD
            period_days: Period in days (default: 30)
            
        Returns:
            Tuple of (is_over_budget, statistics_dict)
        """
        start_date = datetime.utcnow() - timedelta(days=period_days)
        stats = CostTracker.get_user_usage(db, user_id, start_date)
        
        total_cost = stats["statistics"]["total_cost_usd"]
        is_over_budget = total_cost >= budget_limit_usd
        
        return is_over_budget, {
            "user_id": user_id,
            "budget_limit_usd": budget_limit_usd,
            "period_days": period_days,
            "current_cost_usd": total_cost,
            "remaining_budget_usd": max(0, budget_limit_usd - total_cost),
            "utilization_percent": (total_cost / budget_limit_usd * 100) if budget_limit_usd > 0 else 0,
            "is_over_budget": is_over_budget,
        }
