"""
Recovery Suggestion Service - Generate AI-powered recovery recommendations
"""
from datetime import datetime, UTC, timedelta
from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.task import Task, TaskStatus
from app.models.recovery_suggestion import RecoverySuggestion, RecoverySuggestionType
from app.models.user import User


class RecoverySuggestionService:
    """Generate and manage recovery suggestions for failed tasks"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def generate_suggestions(
        self,
        task: Task,
        user: User
    ) -> List[RecoverySuggestion]:
        """
        Generate recovery suggestions based on task failure.
        
        Analyzes:
        - Error message/category
        - Task type
        - User permissions
        - Historical success patterns
        
        Returns 1-3 actionable suggestions ranked by confidence.
        """
        suggestions = []
        error_msg = task.error_message or ""
        error_category = self._categorize_error(error_msg)
        
        # Strategy 1: Permission errors
        if "permission" in error_msg.lower() or "403" in error_msg:
            suggestions.append(
                RecoverySuggestion(
                    task_id=task.id,
                    user_id=user.id,
                    suggestion_type=RecoverySuggestionType.FIX_PERMISSIONS,
                    title="Grant missing permissions",
                    description="This task failed because it couldn't access Google Workspace resources. "
                                "Review and grant the required permissions in your Google account.",
                    confidence_score=85,
                    action_payload={
                        "action": "redirect_to_permissions",
                        "required_scopes": self._infer_required_scopes(task)
                    },
                    error_category=error_category,
                    estimated_success_rate=90,
                    priority=1
                )
            )
        
        # Strategy 2: Timeout errors
        if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
            suggestions.append(
                RecoverySuggestion(
                    task_id=task.id,
                    user_id=user.id,
                    suggestion_type=RecoverySuggestionType.SIMPLIFY_PROMPT,
                    title="Simplify and retry",
                    description="This task took too long to complete. Try breaking it into smaller steps "
                                "or reducing the scope of work.",
                    confidence_score=75,
                    action_payload={
                        "action": "suggest_simplified_prompt",
                        "original_prompt": task.input_data.get("prompt", ""),
                        "suggested_simplification": self._simplify_prompt(task)
                    },
                    error_category=error_category,
                    estimated_success_rate=70,
                    priority=2
                )
            )
        
        # Strategy 3: API/Rate limit errors
        if "rate limit" in error_msg.lower() or "429" in error_msg or "quota" in error_msg.lower():
            suggestions.append(
                RecoverySuggestion(
                    task_id=task.id,
                    user_id=user.id,
                    suggestion_type=RecoverySuggestionType.RETRY,
                    title="Retry in a few minutes",
                    description="Google API rate limit reached. Retry this task in 5-10 minutes.",
                    confidence_score=90,
                    action_payload={
                        "action": "retry_with_delay",
                        "delay_minutes": 10,
                        "task_id": str(task.id)
                    },
                    error_category=error_category,
                    estimated_success_rate=95,
                    priority=1
                )
            )
        
        # Strategy 4: Generic retry (always include as fallback)
        if not suggestions:
            suggestions.append(
                RecoverySuggestion(
                    task_id=task.id,
                    user_id=user.id,
                    suggestion_type=RecoverySuggestionType.RETRY,
                    title="Retry this task",
                    description="Retry with the same settings. Sometimes temporary issues resolve on their own.",
                    confidence_score=60,
                    action_payload={
                        "action": "retry",
                        "task_id": str(task.id)
                    },
                    error_category=error_category,
                    estimated_success_rate=50,
                    priority=2
                )
            )
        
        # Strategy 5: Contact support for critical failures
        if "internal" in error_msg.lower() or "500" in error_msg:
            suggestions.append(
                RecoverySuggestion(
                    task_id=task.id,
                    user_id=user.id,
                    suggestion_type=RecoverySuggestionType.CONTACT_SUPPORT,
                    title="Contact support",
                    description="This looks like a system error. Our team can investigate and help you resolve it.",
                    confidence_score=80,
                    action_payload={
                        "action": "contact_support",
                        "task_id": str(task.id),
                        "error_summary": error_msg[:500]
                    },
                    error_category=error_category,
                    estimated_success_rate=None,
                    priority=3
                )
            )
        
        # Set expiration (24 hours from now)
        expires_at = int((datetime.now(UTC) + timedelta(hours=24)).timestamp())
        for suggestion in suggestions:
            suggestion.expires_at = expires_at
        
        # Save to database
        for suggestion in suggestions:
            self.db.add(suggestion)
        await self.db.commit()
        
        # Sort by priority and return top 3
        suggestions.sort(key=lambda s: (s.priority, -s.confidence_score))
        return suggestions[:3]
    
    async def get_suggestions_for_task(self, task_id: UUID) -> List[RecoverySuggestion]:
        """Get all suggestions for a specific task"""
        result = await self.db.execute(
            select(RecoverySuggestion)
            .where(RecoverySuggestion.task_id == task_id)
            .order_by(RecoverySuggestion.priority, RecoverySuggestion.confidence_score.desc())
        )
        return list(result.scalars().all())
    
    async def mark_suggestion_selected(
        self,
        suggestion_id: UUID,
        outcome_success: Optional[bool] = None
    ) -> RecoverySuggestion:
        """Mark a suggestion as selected by the user"""
        result = await self.db.execute(
            select(RecoverySuggestion).where(RecoverySuggestion.id == suggestion_id)
        )
        suggestion = result.scalar_one_or_none()
        
        if not suggestion:
            raise ValueError(f"Suggestion {suggestion_id} not found")
        
        suggestion.was_selected = 1
        suggestion.selection_timestamp = int(datetime.now(UTC).timestamp())
        if outcome_success is not None:
            suggestion.outcome_success = 1 if outcome_success else 0
        
        await self.db.commit()
        await self.db.refresh(suggestion)
        return suggestion
    
    def _categorize_error(self, error_msg: str) -> str:
        """Categorize error into high-level buckets"""
        error_msg_lower = error_msg.lower()
        
        if "permission" in error_msg_lower or "403" in error_msg:
            return "permission_denied"
        elif "timeout" in error_msg_lower or "timed out" in error_msg_lower:
            return "timeout"
        elif "rate limit" in error_msg_lower or "429" in error_msg or "quota" in error_msg_lower:
            return "rate_limit"
        elif "not found" in error_msg_lower or "404" in error_msg:
            return "resource_not_found"
        elif "internal" in error_msg_lower or "500" in error_msg:
            return "internal_error"
        elif "invalid" in error_msg_lower or "400" in error_msg:
            return "invalid_request"
        else:
            return "unknown"
    
    def _infer_required_scopes(self, task: Task) -> List[str]:
        """Infer Google API scopes needed for this task"""
        scopes = []
        task_type = task.task_type.lower() if task.task_type else ""
        
        if "docs" in task_type or "document" in task_type:
            scopes.extend([
                "https://www.googleapis.com/auth/documents",
                "https://www.googleapis.com/auth/drive.file"
            ])
        elif "sheets" in task_type or "spreadsheet" in task_type:
            scopes.extend([
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive.file"
            ])
        elif "slides" in task_type or "presentation" in task_type:
            scopes.extend([
                "https://www.googleapis.com/auth/presentations",
                "https://www.googleapis.com/auth/drive.file"
            ])
        else:
            scopes.append("https://www.googleapis.com/auth/drive.readonly")
        
        return scopes
    
    def _simplify_prompt(self, task: Task) -> str:
        """Generate a simplified version of the prompt"""
        original_prompt = task.input_data.get("prompt", "") if task.input_data else ""
        
        if not original_prompt:
            return "Try describing your request more clearly"
        
        # Simple heuristic: if prompt is long, suggest shorter version
        if len(original_prompt) > 200:
            return f"Try a shorter, more focused version: '{original_prompt[:100]}...'"
        
        return f"Try rephrasing: '{original_prompt}'"
