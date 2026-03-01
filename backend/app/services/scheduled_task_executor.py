"""Scheduled Task Executor Service."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from croniter import croniter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_context
from app.models.scheduled_task import ScheduledTask, ScheduledTaskExecution
from app.models.task import Task
from app.agents.orchestrator import MultiAgentOrchestrator

logger = logging.getLogger(__name__)


class ScheduledTaskExecutor:
    """
    Executes scheduled tasks based on their configuration.
    
    Features:
    - Calculates next run time using cron expressions or simple schedules
    - Creates actual Task records for execution
    - Records execution history
    - Sends notifications on completion
    """

    @staticmethod
    def calculate_next_run(
        schedule_type: str,
        schedule_config: Dict[str, Any],
        cron_expression: Optional[str] = None,
        from_time: Optional[datetime] = None,
    ) -> datetime:
        """
        Calculate next run time for a scheduled task.
        
        Args:
            schedule_type: Type of schedule (daily, weekly, monthly, cron)
            schedule_config: Schedule configuration dict
            cron_expression: Cron expression for custom schedules
            from_time: Calculate from this time (default: now)
            
        Returns:
            Next run datetime (UTC)
        """
        base_time = from_time or datetime.utcnow()
        
        if schedule_type == "cron" and cron_expression:
            # Use croniter for cron expressions
            cron = croniter(cron_expression, base_time)
            return cron.get_next(datetime)
        
        # Simple schedule types
        hour = schedule_config.get("hour", 9)
        minute = schedule_config.get("minute", 0)
        
        if schedule_type == "daily":
            # Next occurrence of HH:MM today or tomorrow
            next_run = base_time.replace(
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0
            )
            if next_run <= base_time:
                next_run += timedelta(days=1)
            return next_run
        
        elif schedule_type == "weekly":
            # Next occurrence of weekday at HH:MM
            day_of_week = schedule_config.get("day_of_week", 1)  # 1 = Monday
            next_run = base_time.replace(
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0
            )
            
            # Calculate days until target weekday
            days_ahead = day_of_week - next_run.weekday()
            if days_ahead < 0 or (days_ahead == 0 and next_run <= base_time):
                days_ahead += 7
            
            next_run += timedelta(days=days_ahead)
            return next_run
        
        elif schedule_type == "monthly":
            # Next occurrence of day_of_month at HH:MM
            day_of_month = schedule_config.get("day_of_month", 1)
            
            # Try current month
            try:
                next_run = base_time.replace(
                    day=day_of_month,
                    hour=hour,
                    minute=minute,
                    second=0,
                    microsecond=0
                )
                if next_run > base_time:
                    return next_run
            except ValueError:
                pass  # Invalid day for current month
            
            # Next month
            next_month = base_time.month + 1
            next_year = base_time.year
            if next_month > 12:
                next_month = 1
                next_year += 1
            
            try:
                next_run = base_time.replace(
                    year=next_year,
                    month=next_month,
                    day=day_of_month,
                    hour=hour,
                    minute=minute,
                    second=0,
                    microsecond=0
                )
                return next_run
            except ValueError:
                # Day doesn't exist in next month, use last day
                if next_month == 2:
                    last_day = 28 if next_year % 4 != 0 else 29
                elif next_month in [4, 6, 9, 11]:
                    last_day = 30
                else:
                    last_day = 31
                
                next_run = base_time.replace(
                    year=next_year,
                    month=next_month,
                    day=min(day_of_month, last_day),
                    hour=hour,
                    minute=minute,
                    second=0,
                    microsecond=0
                )
                return next_run
        
        # Default: tomorrow at 9 AM
        return (base_time + timedelta(days=1)).replace(
            hour=9, minute=0, second=0, microsecond=0
        )

    @staticmethod
    async def get_due_tasks(db: AsyncSession) -> List[ScheduledTask]:
        """
        Get all scheduled tasks that are due for execution.
        
        Args:
            db: Database session
            
        Returns:
            List of scheduled tasks due for execution
        """
        now = datetime.utcnow()
        
        query = select(ScheduledTask).where(
            ScheduledTask.is_active == True,
            ScheduledTask.next_run_at <= now
        )
        
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    def render_prompt_template(
        template: str,
        execution_time: datetime
    ) -> str:
        """
        Render prompt template with time variables.
        
        Available variables:
        - {date}: YYYY-MM-DD
        - {datetime}: YYYY-MM-DD HH:MM:SS
        - {time}: HH:MM:SS
        - {year}: YYYY
        - {month}: MM
        - {day}: DD
        - {weekday}: Monday/Tuesday/etc.
        - {week}: Week number
        
        Args:
            template: Prompt template with variables
            execution_time: Time to use for variable substitution
            
        Returns:
            Rendered prompt string
        """
        return template.format(
            date=execution_time.strftime("%Y-%m-%d"),
            datetime=execution_time.strftime("%Y-%m-%d %H:%M:%S"),
            time=execution_time.strftime("%H:%M:%S"),
            year=execution_time.strftime("%Y"),
            month=execution_time.strftime("%m"),
            day=execution_time.strftime("%d"),
            weekday=execution_time.strftime("%A"),
            week=execution_time.strftime("%U"),
        )

    @staticmethod
    async def execute_scheduled_task(
        scheduled_task: ScheduledTask,
        db: AsyncSession
    ) -> ScheduledTaskExecution:
        """
        Execute a single scheduled task.
        
        Args:
            scheduled_task: ScheduledTask to execute
            db: Database session
            
        Returns:
            ScheduledTaskExecution record
        """
        logger.info(f"Executing scheduled task: {scheduled_task.name} ({scheduled_task.id})")
        
        execution_start = datetime.utcnow()
        
        # Create execution record
        execution = ScheduledTaskExecution(
            scheduled_task_id=scheduled_task.id,
            started_at=execution_start,
            status="running"
        )
        db.add(execution)
        await db.commit()
        await db.refresh(execution)
        
        try:
            # Render prompt
            prompt = ScheduledTaskExecutor.render_prompt_template(
                scheduled_task.prompt_template,
                execution_start
            )
            
            logger.debug(f"Rendered prompt: {prompt}")
            
            # Create task via orchestrator
            orchestrator = MultiAgentOrchestrator(
                user_id=str(scheduled_task.user_id),
                session_id=None
            )
            
            result = await orchestrator.run_task(
                prompt=prompt,
                task_type=scheduled_task.task_type
            )
            
            # Update execution record
            execution.completed_at = datetime.utcnow()
            execution.success = result.get("success", False)
            execution.status = "completed" if execution.success else "failed"
            execution.output_data = result
            
            if not execution.success:
                execution.error_message = result.get("error", "Unknown error")
            
            logger.info(
                f"Scheduled task completed: {scheduled_task.name} "
                f"(success={execution.success})"
            )
            
        except Exception as e:
            logger.error(f"Scheduled task execution failed: {e}", exc_info=True)
            
            execution.completed_at = datetime.utcnow()
            execution.success = False
            execution.status = "failed"
            execution.error_message = str(e)
        
        # Update scheduled task
        scheduled_task.last_run_at = execution_start
        scheduled_task.run_count += 1
        scheduled_task.next_run_at = ScheduledTaskExecutor.calculate_next_run(
            schedule_type=scheduled_task.schedule_type,
            schedule_config=scheduled_task.schedule_config,
            cron_expression=scheduled_task.cron_expression,
            from_time=execution_start
        )
        
        await db.commit()
        await db.refresh(execution)
        
        # TODO: Send notification if enabled
        # if scheduled_task.notify_on_completion:
        #     await send_completion_notification(scheduled_task, execution)
        
        return execution

    @staticmethod
    async def run_scheduler() -> Dict[str, Any]:
        """
        Main scheduler loop - checks for due tasks and executes them.
        
        This should be called by Celery Beat periodically (e.g., every 1 minute).
        
        Returns:
            Summary of execution results
        """
        logger.info("Running scheduled task checker...")
        
        async with get_db_context() as db:
            # Get due tasks
            due_tasks = await ScheduledTaskExecutor.get_due_tasks(db)
            
            if not due_tasks:
                logger.debug("No scheduled tasks due for execution")
                return {
                    "status": "success",
                    "tasks_executed": 0,
                    "tasks_succeeded": 0,
                    "tasks_failed": 0,
                    "timestamp": datetime.utcnow().isoformat()
                }
            
            logger.info(f"Found {len(due_tasks)} scheduled tasks due for execution")
            
            # Execute tasks
            succeeded = 0
            failed = 0
            
            for task in due_tasks:
                try:
                    execution = await ScheduledTaskExecutor.execute_scheduled_task(
                        task, db
                    )
                    if execution.success:
                        succeeded += 1
                    else:
                        failed += 1
                except Exception as e:
                    logger.error(f"Failed to execute scheduled task {task.id}: {e}")
                    failed += 1
            
            summary = {
                "status": "success",
                "tasks_executed": len(due_tasks),
                "tasks_succeeded": succeeded,
                "tasks_failed": failed,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            logger.info(
                f"Scheduled task execution complete: "
                f"{succeeded} succeeded, {failed} failed"
            )
            
            return summary


__all__ = ["ScheduledTaskExecutor"]
