"""Budget tracking API endpoints for LLM cost management."""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from typing import List, Optional
from datetime import datetime, timedelta
from uuid import UUID
import logging

from app.core.database import get_db
from app.models.budget import UserBudget, BudgetAlert, CostRecord, BudgetPeriod
from app.models.user import User
from app.api.v1.auth import get_current_user
from app.services.budget_service import BudgetService
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/budget", tags=["budget"])


# Pydantic schemas
class BudgetCreate(BaseModel):
    """Request schema for creating a budget."""
    period: BudgetPeriod = Field(..., description="Budget period (daily, weekly, monthly, yearly)")
    limit_usd: float = Field(..., gt=0, description="Budget limit in USD")
    warning_threshold_pct: int = Field(75, ge=0, le=100, description="Warning threshold percentage")
    critical_threshold_pct: int = Field(90, ge=0, le=100, description="Critical threshold percentage")
    enable_alerts: bool = Field(True, description="Enable email alerts")
    alert_email: Optional[str] = Field(None, description="Override alert email")


class BudgetUpdate(BaseModel):
    """Request schema for updating a budget."""
    limit_usd: Optional[float] = Field(None, gt=0)
    warning_threshold_pct: Optional[int] = Field(None, ge=0, le=100)
    critical_threshold_pct: Optional[int] = Field(None, ge=0, le=100)
    enable_alerts: Optional[bool] = None
    alert_email: Optional[str] = None


class BudgetResponse(BaseModel):
    """Response schema for budget details."""
    id: UUID
    user_id: UUID
    period: str
    limit_usd: float
    current_spend_usd: float
    usage_percentage: float
    remaining_usd: float
    period_start: datetime
    period_end: datetime
    enable_alerts: bool
    budget_exceeded: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class AlertResponse(BaseModel):
    """Response schema for budget alerts."""
    id: UUID
    level: str
    spend_usd: float
    limit_usd: float
    usage_percentage: float
    message: Optional[str]
    email_sent: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class CostSummaryResponse(BaseModel):
    """Response schema for cost summary."""
    total_cost_usd: float
    by_agent: dict
    by_model: dict
    budget: Optional[dict]
    date_range: dict


@router.post("/", response_model=BudgetResponse)
async def create_budget(
    budget_data: BudgetCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new budget for the current user.
    
    **Parameters:**
    - `period`: Budget period (daily, weekly, monthly, yearly)
    - `limit_usd`: Budget limit in USD
    - `warning_threshold_pct`: Warning threshold (default: 75%)
    - `critical_threshold_pct`: Critical threshold (default: 90%)
    - `enable_alerts`: Enable email alerts (default: true)
    - `alert_email`: Override alert email (optional)
    """
    try:
        budget_service = BudgetService(db)
        
        # Check for existing budget with same period
        now = datetime.utcnow()
        query = select(UserBudget).where(
            and_(
                UserBudget.user_id == current_user.id,
                UserBudget.period == budget_data.period,
                UserBudget.period_end > now,
            )
        )
        result = await db.execute(query)
        existing_budget = result.scalar_one_or_none()
        
        if existing_budget:
            raise HTTPException(
                status_code=400,
                detail=f"Active {budget_data.period.value} budget already exists"
            )
        
        # Create budget
        budget = await budget_service.get_or_create_budget(
            user_id=current_user.id,
            period=budget_data.period,
            limit_usd=budget_data.limit_usd,
        )
        
        # Update settings
        budget.warning_threshold_pct = budget_data.warning_threshold_pct
        budget.critical_threshold_pct = budget_data.critical_threshold_pct
        budget.enable_alerts = budget_data.enable_alerts
        budget.alert_email = budget_data.alert_email
        
        await db.commit()
        await db.refresh(budget)
        
        return BudgetResponse(
            id=budget.id,
            user_id=budget.user_id,
            period=budget.period.value,
            limit_usd=budget.limit_usd,
            current_spend_usd=budget.current_spend_usd,
            usage_percentage=budget.usage_percentage,
            remaining_usd=budget.remaining_usd,
            period_start=budget.period_start,
            period_end=budget.period_end,
            enable_alerts=budget.enable_alerts,
            budget_exceeded=budget.budget_exceeded,
            created_at=budget.created_at,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create budget: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create budget: {str(e)}")


@router.get("/", response_model=List[BudgetResponse])
async def list_budgets(
    current_user: User = Depends(get_current_user),
    active_only: bool = Query(True, description="Show only active budgets"),
    db: AsyncSession = Depends(get_db),
):
    """
    List all budgets for the current user.
    
    **Parameters:**
    - `active_only`: Show only active budgets (default: true)
    """
    try:
        now = datetime.utcnow()
        
        query = select(UserBudget).where(UserBudget.user_id == current_user.id)
        
        if active_only:
            query = query.where(UserBudget.period_end > now)
        
        query = query.order_by(desc(UserBudget.created_at))
        
        result = await db.execute(query)
        budgets = result.scalars().all()
        
        return [
            BudgetResponse(
                id=b.id,
                user_id=b.user_id,
                period=b.period.value,
                limit_usd=b.limit_usd,
                current_spend_usd=b.current_spend_usd,
                usage_percentage=b.usage_percentage,
                remaining_usd=b.remaining_usd,
                period_start=b.period_start,
                period_end=b.period_end,
                enable_alerts=b.enable_alerts,
                budget_exceeded=b.budget_exceeded,
                created_at=b.created_at,
            )
            for b in budgets
        ]
        
    except Exception as e:
        logger.error(f"Failed to list budgets: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list budgets: {str(e)}")


@router.get("/{budget_id}", response_model=BudgetResponse)
async def get_budget(
    budget_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific budget by ID."""
    try:
        budget = await db.get(UserBudget, budget_id)
        
        if not budget or budget.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Budget not found")
        
        return BudgetResponse(
            id=budget.id,
            user_id=budget.user_id,
            period=budget.period.value,
            limit_usd=budget.limit_usd,
            current_spend_usd=budget.current_spend_usd,
            usage_percentage=budget.usage_percentage,
            remaining_usd=budget.remaining_usd,
            period_start=budget.period_start,
            period_end=budget.period_end,
            enable_alerts=budget.enable_alerts,
            budget_exceeded=budget.budget_exceeded,
            created_at=budget.created_at,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get budget: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get budget: {str(e)}")


@router.patch("/{budget_id}", response_model=BudgetResponse)
async def update_budget(
    budget_id: UUID,
    budget_data: BudgetUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing budget."""
    try:
        budget = await db.get(UserBudget, budget_id)
        
        if not budget or budget.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Budget not found")
        
        # Update fields
        if budget_data.limit_usd is not None:
            budget.limit_usd = budget_data.limit_usd
        if budget_data.warning_threshold_pct is not None:
            budget.warning_threshold_pct = budget_data.warning_threshold_pct
        if budget_data.critical_threshold_pct is not None:
            budget.critical_threshold_pct = budget_data.critical_threshold_pct
        if budget_data.enable_alerts is not None:
            budget.enable_alerts = budget_data.enable_alerts
        if budget_data.alert_email is not None:
            budget.alert_email = budget_data.alert_email
        
        budget.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(budget)
        
        return BudgetResponse(
            id=budget.id,
            user_id=budget.user_id,
            period=budget.period.value,
            limit_usd=budget.limit_usd,
            current_spend_usd=budget.current_spend_usd,
            usage_percentage=budget.usage_percentage,
            remaining_usd=budget.remaining_usd,
            period_start=budget.period_start,
            period_end=budget.period_end,
            enable_alerts=budget.enable_alerts,
            budget_exceeded=budget.budget_exceeded,
            created_at=budget.created_at,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update budget: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update budget: {str(e)}")


@router.delete("/{budget_id}")
async def delete_budget(
    budget_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a budget."""
    try:
        budget = await db.get(UserBudget, budget_id)
        
        if not budget or budget.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Budget not found")
        
        await db.delete(budget)
        await db.commit()
        
        return {"success": True, "message": "Budget deleted"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete budget: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete budget: {str(e)}")


@router.get("/{budget_id}/alerts", response_model=List[AlertResponse])
async def get_budget_alerts(
    budget_id: UUID,
    current_user: User = Depends(get_current_user),
    limit: int = Query(50, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get alert history for a budget."""
    try:
        # Verify budget ownership
        budget = await db.get(UserBudget, budget_id)
        if not budget or budget.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Budget not found")
        
        # Get alerts
        query = select(BudgetAlert).where(
            BudgetAlert.budget_id == budget_id
        ).order_by(desc(BudgetAlert.created_at)).limit(limit)
        
        result = await db.execute(query)
        alerts = result.scalars().all()
        
        return [
            AlertResponse(
                id=a.id,
                level=a.level.value,
                spend_usd=a.spend_usd,
                limit_usd=a.limit_usd,
                usage_percentage=a.usage_percentage,
                message=a.message,
                email_sent=a.email_sent,
                created_at=a.created_at,
            )
            for a in alerts
        ]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get alerts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get alerts: {str(e)}")


@router.get("/costs/summary", response_model=CostSummaryResponse)
async def get_cost_summary(
    current_user: User = Depends(get_current_user),
    days: int = Query(30, ge=1, le=365, description="Number of days to include"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get cost summary for the current user.
    
    **Parameters:**
    - `days`: Number of days to include (1-365, default: 30)
    """
    try:
        budget_service = BudgetService(db)
        
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        summary = await budget_service.get_cost_summary(
            user_id=current_user.id,
            start_date=start_date,
            end_date=end_date,
        )
        
        return CostSummaryResponse(**summary)
        
    except Exception as e:
        logger.error(f"Failed to get cost summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get cost summary: {str(e)}")
