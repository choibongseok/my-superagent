"""Budget tracking and alerting service for LLM cost management."""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID
import logging

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.budget import (
    UserBudget,
    BudgetAlert,
    CostRecord,
    BudgetPeriod,
    BudgetAlertLevel,
)
from app.models.user import User
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)


class BudgetService:
    """Service for budget management and cost tracking."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.email_service = EmailService()
    
    async def get_or_create_budget(
        self,
        user_id: UUID,
        period: BudgetPeriod = BudgetPeriod.MONTHLY,
        limit_usd: float = 50.0,
    ) -> UserBudget:
        """
        Get existing budget or create a new one with default limits.
        
        Args:
            user_id: User ID
            period: Budget period (daily, weekly, monthly, yearly)
            limit_usd: Budget limit in USD
            
        Returns:
            UserBudget instance
        """
        # Check for existing active budget
        now = datetime.utcnow()
        query = select(UserBudget).where(
            and_(
                UserBudget.user_id == user_id,
                UserBudget.period == period,
                UserBudget.period_end > now,
            )
        )
        result = await self.db.execute(query)
        budget = result.scalar_one_or_none()
        
        if budget:
            return budget
        
        # Create new budget
        period_start, period_end = self._calculate_period_dates(period)
        
        budget = UserBudget(
            user_id=user_id,
            period=period,
            limit_usd=limit_usd,
            current_spend_usd=0.0,
            period_start=period_start,
            period_end=period_end,
        )
        
        self.db.add(budget)
        await self.db.commit()
        await self.db.refresh(budget)
        
        logger.info(f"Created new budget for user {user_id}: ${limit_usd} {period}")
        return budget
    
    async def record_cost(
        self,
        user_id: UUID,
        cost_usd: float,
        model: str,
        agent_type: str,
        task_id: Optional[UUID] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        langfuse_trace_id: Optional[str] = None,
        langfuse_span_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CostRecord:
        """
        Record an LLM API call cost.
        
        Args:
            user_id: User ID
            cost_usd: Cost in USD
            model: Model name (e.g., "gpt-4")
            agent_type: Agent type (research, docs, sheets, slides)
            task_id: Associated task ID
            input_tokens: Input token count
            output_tokens: Output token count
            langfuse_trace_id: LangFuse trace ID
            langfuse_span_id: LangFuse span ID
            metadata: Additional metadata
            
        Returns:
            CostRecord instance
        """
        # Create cost record
        cost_record = CostRecord(
            user_id=user_id,
            task_id=task_id,
            cost_usd=cost_usd,
            model=model,
            agent_type=agent_type,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            langfuse_trace_id=langfuse_trace_id,
            langfuse_span_id=langfuse_span_id,
            metadata=metadata,
        )
        
        self.db.add(cost_record)
        
        # Update user budget
        await self._update_budget_spend(user_id, cost_usd)
        
        await self.db.commit()
        await self.db.refresh(cost_record)
        
        logger.info(
            f"Recorded cost for user {user_id}: ${cost_usd} "
            f"(model={model}, agent={agent_type})"
        )
        
        # Check budget alerts
        await self._check_and_send_alerts(user_id)
        
        return cost_record
    
    async def _update_budget_spend(self, user_id: UUID, cost_usd: float):
        """Update user budget with new spend."""
        # Get active budgets
        now = datetime.utcnow()
        query = select(UserBudget).where(
            and_(
                UserBudget.user_id == user_id,
                UserBudget.period_end > now,
            )
        )
        result = await self.db.execute(query)
        budgets = result.scalars().all()
        
        for budget in budgets:
            budget.current_spend_usd += cost_usd
            budget.updated_at = now
            
            if budget.current_spend_usd >= budget.limit_usd and not budget.budget_exceeded:
                budget.budget_exceeded = True
                logger.warning(
                    f"Budget exceeded for user {user_id}: "
                    f"${budget.current_spend_usd} / ${budget.limit_usd}"
                )
    
    async def _check_and_send_alerts(self, user_id: UUID):
        """Check budget thresholds and send alerts."""
        now = datetime.utcnow()
        
        # Get active budgets
        query = select(UserBudget).where(
            and_(
                UserBudget.user_id == user_id,
                UserBudget.period_end > now,
                UserBudget.enable_alerts == True,  # noqa: E712
            )
        )
        result = await self.db.execute(query)
        budgets = result.scalars().all()
        
        for budget in budgets:
            usage_pct = budget.usage_percentage
            
            # Check EXCEEDED threshold (100%)
            if usage_pct >= 100 and budget.budget_exceeded:
                await self._send_alert(budget, BudgetAlertLevel.EXCEEDED)
            
            # Check CRITICAL threshold (90% or custom)
            elif usage_pct >= budget.critical_threshold_pct:
                # Only send if not sent in last 12 hours
                if not budget.last_critical_sent or \
                   (now - budget.last_critical_sent) > timedelta(hours=12):
                    await self._send_alert(budget, BudgetAlertLevel.CRITICAL)
                    budget.last_critical_sent = now
            
            # Check WARNING threshold (75% or custom)
            elif usage_pct >= budget.warning_threshold_pct:
                # Only send if not sent in last 24 hours
                if not budget.last_warning_sent or \
                   (now - budget.last_warning_sent) > timedelta(hours=24):
                    await self._send_alert(budget, BudgetAlertLevel.WARNING)
                    budget.last_warning_sent = now
        
        await self.db.commit()
    
    async def _send_alert(self, budget: UserBudget, level: BudgetAlertLevel):
        """Send budget alert email."""
        try:
            # Get user
            user = await self.db.get(User, budget.user_id)
            if not user:
                logger.error(f"User not found for budget {budget.id}")
                return
            
            email_to = budget.alert_email or user.email
            
            # Create alert message
            usage_pct = budget.usage_percentage
            spend = budget.current_spend_usd
            limit = budget.limit_usd
            remaining = budget.remaining_usd
            
            if level == BudgetAlertLevel.WARNING:
                subject = f"⚠️ Budget Alert: {usage_pct:.1f}% Used"
                message = (
                    f"You've used {usage_pct:.1f}% of your {budget.period.value} budget.\n\n"
                    f"Current spend: ${spend:.2f} / ${limit:.2f}\n"
                    f"Remaining: ${remaining:.2f}\n\n"
                    f"Consider monitoring your usage to avoid exceeding your budget."
                )
            elif level == BudgetAlertLevel.CRITICAL:
                subject = f"🚨 Critical Budget Alert: {usage_pct:.1f}% Used"
                message = (
                    f"CRITICAL: You've used {usage_pct:.1f}% of your {budget.period.value} budget!\n\n"
                    f"Current spend: ${spend:.2f} / ${limit:.2f}\n"
                    f"Remaining: ${remaining:.2f}\n\n"
                    f"Please review your usage immediately to avoid service interruption."
                )
            else:  # EXCEEDED
                subject = f"🛑 Budget Exceeded: ${spend:.2f} / ${limit:.2f}"
                message = (
                    f"Your {budget.period.value} budget has been exceeded!\n\n"
                    f"Current spend: ${spend:.2f}\n"
                    f"Budget limit: ${limit:.2f}\n"
                    f"Overage: ${spend - limit:.2f}\n\n"
                    f"Further usage may be restricted. Please update your budget or reduce usage."
                )
            
            # Create alert record
            alert = BudgetAlert(
                budget_id=budget.id,
                user_id=budget.user_id,
                level=level,
                spend_usd=spend,
                limit_usd=limit,
                usage_percentage=usage_pct,
                message=message,
            )
            
            self.db.add(alert)
            await self.db.commit()
            await self.db.refresh(alert)
            
            # Send email
            await self.email_service.send_email(
                to_email=email_to,
                subject=subject,
                body=message,
            )
            
            alert.email_sent = True
            alert.email_sent_at = datetime.utcnow()
            await self.db.commit()
            
            logger.info(
                f"Sent {level} alert to {email_to} for budget {budget.id}"
            )
            
        except Exception as e:
            logger.error(f"Failed to send budget alert: {e}", exc_info=True)
    
    async def get_cost_summary(
        self,
        user_id: UUID,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Get cost summary for a user.
        
        Args:
            user_id: User ID
            start_date: Start date (default: 30 days ago)
            end_date: End date (default: now)
            
        Returns:
            Cost summary dictionary
        """
        if not start_date:
            start_date = datetime.utcnow() - timedelta(days=30)
        if not end_date:
            end_date = datetime.utcnow()
        
        # Get total cost
        query = select(func.sum(CostRecord.cost_usd)).where(
            and_(
                CostRecord.user_id == user_id,
                CostRecord.created_at >= start_date,
                CostRecord.created_at <= end_date,
            )
        )
        result = await self.db.execute(query)
        total_cost = result.scalar() or 0.0
        
        # Get cost by agent type
        query = select(
            CostRecord.agent_type,
            func.sum(CostRecord.cost_usd).label("cost"),
        ).where(
            and_(
                CostRecord.user_id == user_id,
                CostRecord.created_at >= start_date,
                CostRecord.created_at <= end_date,
            )
        ).group_by(CostRecord.agent_type)
        
        result = await self.db.execute(query)
        by_agent = {row.agent_type: float(row.cost) for row in result}
        
        # Get cost by model
        query = select(
            CostRecord.model,
            func.sum(CostRecord.cost_usd).label("cost"),
        ).where(
            and_(
                CostRecord.user_id == user_id,
                CostRecord.created_at >= start_date,
                CostRecord.created_at <= end_date,
            )
        ).group_by(CostRecord.model)
        
        result = await self.db.execute(query)
        by_model = {row.model: float(row.cost) for row in result}
        
        # Get current budget
        now = datetime.utcnow()
        query = select(UserBudget).where(
            and_(
                UserBudget.user_id == user_id,
                UserBudget.period_end > now,
            )
        )
        result = await self.db.execute(query)
        budget = result.scalar_one_or_none()
        
        return {
            "total_cost_usd": float(total_cost),
            "by_agent": by_agent,
            "by_model": by_model,
            "budget": {
                "limit_usd": budget.limit_usd if budget else None,
                "current_spend_usd": budget.current_spend_usd if budget else None,
                "usage_percentage": budget.usage_percentage if budget else None,
                "remaining_usd": budget.remaining_usd if budget else None,
                "period": budget.period.value if budget else None,
            } if budget else None,
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
        }
    
    def _calculate_period_dates(self, period: BudgetPeriod) -> tuple[datetime, datetime]:
        """Calculate period start and end dates."""
        now = datetime.utcnow()
        
        if period == BudgetPeriod.DAILY:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
        elif period == BudgetPeriod.WEEKLY:
            # Start on Monday
            days_since_monday = now.weekday()
            start = (now - timedelta(days=days_since_monday)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            end = start + timedelta(days=7)
        elif period == BudgetPeriod.MONTHLY:
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            # Next month
            if start.month == 12:
                end = start.replace(year=start.year + 1, month=1)
            else:
                end = start.replace(month=start.month + 1)
        else:  # YEARLY
            start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            end = start.replace(year=start.year + 1)
        
        return start, end
