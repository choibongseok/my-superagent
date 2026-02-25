"""
Tests for Recovery Suggestion System (Idea #276: Reliability Landing Page)
"""
import pytest
from datetime import datetime, UTC
from uuid import uuid4

from app.models.task import Task, TaskStatus, TaskType
from app.models.recovery_suggestion import RecoverySuggestion, RecoverySuggestionType
from app.services.recovery_suggestion_service import RecoverySuggestionService


class TestRecoverySuggestionService:
    """Test recovery suggestion generation"""
    
    @pytest.mark.asyncio
    async def test_generate_suggestions_for_permission_error(self, db, test_user):
        """Test suggestions for permission denied errors"""
        # Create a failed task with permission error
        task = Task(
            id=uuid4(),
            user_id=test_user.id,
            task_type=TaskType.DOCUMENT_GENERATION,
            status=TaskStatus.FAILED,
            input_data={"prompt": "Create a document"},
            error_message="Permission denied: 403 Forbidden",
            created_at=datetime.now(UTC)
        )
        db.add(task)
        await db.commit()
        
        # Generate suggestions
        service = RecoverySuggestionService(db)
        suggestions = await service.generate_suggestions(task, test_user)
        
        # Should have at least one permission-related suggestion
        assert len(suggestions) > 0
        permission_suggestions = [
            s for s in suggestions 
            if s.suggestion_type == RecoverySuggestionType.FIX_PERMISSIONS
        ]
        assert len(permission_suggestions) > 0
        
        # Check suggestion content
        perm_suggestion = permission_suggestions[0]
        assert perm_suggestion.title == "Grant missing permissions"
        assert perm_suggestion.confidence_score >= 80
        assert "action" in perm_suggestion.action_payload
        assert perm_suggestion.error_category == "permission_denied"
    
    @pytest.mark.asyncio
    async def test_generate_suggestions_for_timeout(self, db, test_user):
        """Test suggestions for timeout errors"""
        task = Task(
            id=uuid4(),
            user_id=test_user.id,
            task_type=TaskType.RESEARCH,
            status=TaskStatus.FAILED,
            input_data={"prompt": "Research everything about AI"},
            error_message="Task timed out after 60 seconds",
            created_at=datetime.now(UTC)
        )
        db.add(task)
        await db.commit()
        
        service = RecoverySuggestionService(db)
        suggestions = await service.generate_suggestions(task, test_user)
        
        # Should suggest simplification
        simplify_suggestions = [
            s for s in suggestions 
            if s.suggestion_type == RecoverySuggestionType.SIMPLIFY_PROMPT
        ]
        assert len(simplify_suggestions) > 0
        assert "simplify" in simplify_suggestions[0].title.lower()
    
    @pytest.mark.asyncio
    async def test_generate_suggestions_for_rate_limit(self, db, test_user):
        """Test suggestions for rate limit errors"""
        task = Task(
            id=uuid4(),
            user_id=test_user.id,
            task_type=TaskType.SPREADSHEET_ANALYSIS,
            status=TaskStatus.FAILED,
            input_data={"prompt": "Analyze spreadsheet"},
            error_message="Rate limit exceeded: 429 Too Many Requests",
            created_at=datetime.now(UTC)
        )
        db.add(task)
        await db.commit()
        
        service = RecoverySuggestionService(db)
        suggestions = await service.generate_suggestions(task, test_user)
        
        # Should suggest retry with delay
        retry_suggestions = [
            s for s in suggestions 
            if s.suggestion_type == RecoverySuggestionType.RETRY
        ]
        assert len(retry_suggestions) > 0
        assert "retry" in retry_suggestions[0].title.lower()
        assert "delay_minutes" in retry_suggestions[0].action_payload
    
    @pytest.mark.asyncio
    async def test_suggestions_have_expiration(self, db, test_user):
        """Test that suggestions expire after 24 hours"""
        task = Task(
            id=uuid4(),
            user_id=test_user.id,
            task_type=TaskType.DOCUMENT_GENERATION,
            status=TaskStatus.FAILED,
            input_data={},
            error_message="Generic error",
            created_at=datetime.now(UTC)
        )
        db.add(task)
        await db.commit()
        
        service = RecoverySuggestionService(db)
        suggestions = await service.generate_suggestions(task, test_user)
        
        # All suggestions should have expiration
        for suggestion in suggestions:
            assert suggestion.expires_at is not None
            assert suggestion.expires_at > int(datetime.now(UTC).timestamp())
    
    @pytest.mark.asyncio
    async def test_mark_suggestion_selected(self, db, test_user):
        """Test marking a suggestion as selected"""
        task = Task(
            id=uuid4(),
            user_id=test_user.id,
            task_type=TaskType.DOCUMENT_GENERATION,
            status=TaskStatus.FAILED,
            input_data={},
            error_message="Error",
            created_at=datetime.now(UTC)
        )
        db.add(task)
        await db.commit()
        
        service = RecoverySuggestionService(db)
        suggestions = await service.generate_suggestions(task, test_user)
        suggestion = suggestions[0]
        
        # Mark as selected
        updated = await service.mark_suggestion_selected(
            suggestion.id,
            outcome_success=True
        )
        
        assert updated.was_selected == 1
        assert updated.selection_timestamp is not None
        assert updated.outcome_success == 1
    
    @pytest.mark.asyncio
    async def test_categorize_errors_correctly(self, db, test_user):
        """Test error categorization"""
        service = RecoverySuggestionService(db)
        
        assert service._categorize_error("403 Forbidden") == "permission_denied"
        assert service._categorize_error("timeout after 60s") == "timeout"
        assert service._categorize_error("Rate limit exceeded") == "rate_limit"
        assert service._categorize_error("404 Not Found") == "resource_not_found"
        assert service._categorize_error("500 Internal Server Error") == "internal_error"
        assert service._categorize_error("400 Bad Request") == "invalid_request"
        assert service._categorize_error("Unknown error") == "unknown"
    
    @pytest.mark.asyncio
    async def test_infer_required_scopes(self, db, test_user):
        """Test Google API scope inference"""
        service = RecoverySuggestionService(db)
        
        # Docs task
        docs_task = Task(
            id=uuid4(),
            user_id=test_user.id,
            task_type=TaskType.DOCUMENT_GENERATION,
            status=TaskStatus.FAILED,
            created_at=datetime.now(UTC)
        )
        scopes = service._infer_required_scopes(docs_task)
        assert "documents" in " ".join(scopes)
        
        # Sheets task
        sheets_task = Task(
            id=uuid4(),
            user_id=test_user.id,
            task_type=TaskType.SPREADSHEET_ANALYSIS,
            status=TaskStatus.FAILED,
            created_at=datetime.now(UTC)
        )
        scopes = service._infer_required_scopes(sheets_task)
        assert "spreadsheets" in " ".join(scopes)


@pytest.mark.asyncio
async def test_recovery_api_get_suggestions(client, test_user, test_db):
    """Test GET /recovery/tasks/{task_id}/suggestions endpoint"""
    # Create failed task
    task = Task(
        id=uuid4(),
        user_id=test_user.id,
        task_type=TaskType.DOCUMENT_GENERATION,
        status=TaskStatus.FAILED,
        input_data={"prompt": "Create doc"},
        error_message="Permission denied",
        created_at=datetime.now(UTC)
    )
    test_db.add(task)
    await test_db.commit()
    
    # Request suggestions
    response = await client.get(
        f"/api/v1/recovery/tasks/{task.id}/suggestions",
        headers={"Authorization": f"Bearer {test_user.token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "suggestions" in data
    assert len(data["suggestions"]) > 0
    assert data["task_id"] == str(task.id)
    assert data["task_status"] == "failed"


@pytest.mark.asyncio
async def test_recovery_api_select_suggestion(client, test_user, test_db):
    """Test POST /recovery/suggestions/{suggestion_id}/select endpoint"""
    # Create task and suggestion
    task = Task(
        id=uuid4(),
        user_id=test_user.id,
        task_type=TaskType.DOCUMENT_GENERATION,
        status=TaskStatus.FAILED,
        created_at=datetime.now(UTC)
    )
    test_db.add(task)
    await test_db.commit()
    
    suggestion = RecoverySuggestion(
        task_id=task.id,
        user_id=test_user.id,
        suggestion_type=RecoverySuggestionType.RETRY,
        title="Retry",
        description="Try again",
        confidence_score=80,
        action_payload={"action": "retry"}
    )
    test_db.add(suggestion)
    await test_db.commit()
    
    # Select suggestion
    response = await client.post(
        f"/api/v1/recovery/suggestions/{suggestion.id}/select",
        headers={"Authorization": f"Bearer {test_user.token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["suggestion"]["was_selected"] is True


@pytest.mark.asyncio
async def test_recovery_status_endpoint(client, test_user, test_db):
    """Test GET /recovery/tasks/{task_id}/recovery-status endpoint"""
    task = Task(
        id=uuid4(),
        user_id=test_user.id,
        task_type=TaskType.DOCUMENT_GENERATION,
        status=TaskStatus.FAILED,
        error_message="Error",
        created_at=datetime.now(UTC)
    )
    test_db.add(task)
    await test_db.commit()
    
    response = await client.get(
        f"/api/v1/recovery/tasks/{task.id}/recovery-status",
        headers={"Authorization": f"Bearer {test_user.token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "task" in data
    assert "recovery" in data
    assert "analytics" in data
    assert data["task"]["id"] == str(task.id)
