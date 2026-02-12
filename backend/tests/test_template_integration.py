"""Tests for Template-Task integration."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from app.models.task import TaskStatus


class TestTemplateTaskIntegration:
    """Test template usage creates tasks automatically."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @pytest.fixture
    def mock_user(self):
        """Create mock user."""
        user = MagicMock()
        user.id = uuid4()
        user.full_name = "Test User"
        return user

    @pytest.fixture
    def template_result(self):
        """Sample template use result."""
        return {
            "template_id": str(uuid4()),
            "prompt": "Research the benefits of AI in healthcare",
            "output_type": "research",
        }

    @pytest.mark.asyncio
    async def test_research_template_creates_research_task(
        self, mock_db, mock_user, template_result
    ):
        """Test that research template creates research task."""
        from app.api.v1.templates import use_template
        from app.schemas.template import TemplateUseRequest

        template_id = uuid4()
        use_request = TemplateUseRequest(inputs={"topic": "AI healthcare"})

        with patch("app.api.v1.templates.TemplateService") as MockService:
            mock_service = MockService.return_value
            mock_service.use_template = AsyncMock(return_value=template_result)

            with patch("app.api.v1.templates.process_research_task") as mock_celery:
                mock_celery.apply_async.return_value = MagicMock(id="celery-task-123")

                # Mock task creation
                with patch("app.api.v1.templates.TaskModel") as MockTask:
                    mock_task = MagicMock()
                    mock_task.id = uuid4()
                    mock_task.user_id = mock_user.id
                    mock_task.prompt = template_result["prompt"]
                    mock_task.task_type = "research"
                    mock_task.status = TaskStatus.IN_PROGRESS
                    mock_task.celery_task_id = "celery-task-123"
                    MockTask.return_value = mock_task

                    result = await use_template(
                        template_id, use_request, mock_user, mock_db
                    )

                    # Verify task was created
                    assert MockTask.called
                    task_kwargs = MockTask.call_args[1]
                    assert task_kwargs["user_id"] == mock_user.id
                    assert task_kwargs["prompt"] == template_result["prompt"]
                    assert task_kwargs["task_type"] == "research"
                    assert task_kwargs["status"] == TaskStatus.PENDING

                    # Verify Celery task was queued
                    assert mock_celery.apply_async.called

                    # Verify response
                    assert result.template_id == UUID(template_result["template_id"])
                    assert result.task_id == mock_task.id
                    assert result.prompt == template_result["prompt"]

    @pytest.mark.asyncio
    async def test_docs_template_creates_docs_task(
        self, mock_db, mock_user
    ):
        """Test that document template creates docs task."""
        from app.api.v1.templates import use_template
        from app.schemas.template import TemplateUseRequest

        template_id = uuid4()
        use_request = TemplateUseRequest(
            inputs={"title": "Project Report", "content": "Quarterly results"}
        )

        docs_result = {
            "template_id": str(uuid4()),
            "prompt": "Create a project report with quarterly results",
            "output_type": "document",
        }

        with patch("app.api.v1.templates.TemplateService") as MockService:
            mock_service = MockService.return_value
            mock_service.use_template = AsyncMock(return_value=docs_result)

            with patch("app.api.v1.templates.process_docs_task") as mock_celery:
                mock_celery.apply_async.return_value = MagicMock(id="celery-docs-456")

                with patch("app.api.v1.templates.TaskModel") as MockTask:
                    mock_task = MagicMock()
                    mock_task.id = uuid4()
                    mock_task.task_type = "docs"
                    MockTask.return_value = mock_task

                    result = await use_template(
                        template_id, use_request, mock_user, mock_db
                    )

                    # Verify docs task was created
                    task_kwargs = MockTask.call_args[1]
                    assert task_kwargs["task_type"] == "docs"

                    # Verify docs Celery task was called with title
                    celery_args = mock_celery.apply_async.call_args[1]["args"]
                    assert "Project Report" in celery_args

    @pytest.mark.asyncio
    async def test_sheets_template_creates_sheets_task(
        self, mock_db, mock_user
    ):
        """Test that spreadsheet template creates sheets task."""
        from app.api.v1.templates import use_template
        from app.schemas.template import TemplateUseRequest

        template_id = uuid4()
        use_request = TemplateUseRequest(
            inputs={"title": "Budget 2026", "data": "quarterly expenses"}
        )

        sheets_result = {
            "template_id": str(uuid4()),
            "prompt": "Create a budget spreadsheet for 2026",
            "output_type": "spreadsheet",
        }

        with patch("app.api.v1.templates.TemplateService") as MockService:
            mock_service = MockService.return_value
            mock_service.use_template = AsyncMock(return_value=sheets_result)

            with patch("app.api.v1.templates.process_sheets_task") as mock_celery:
                mock_celery.apply_async.return_value = MagicMock(id="celery-sheets-789")

                with patch("app.api.v1.templates.TaskModel") as MockTask:
                    mock_task = MagicMock()
                    mock_task.id = uuid4()
                    mock_task.task_type = "sheets"
                    MockTask.return_value = mock_task

                    result = await use_template(
                        template_id, use_request, mock_user, mock_db
                    )

                    # Verify sheets task was created
                    task_kwargs = MockTask.call_args[1]
                    assert task_kwargs["task_type"] == "sheets"

                    # Verify sheets Celery task was called
                    assert mock_celery.apply_async.called

    @pytest.mark.asyncio
    async def test_slides_template_creates_slides_task(
        self, mock_db, mock_user
    ):
        """Test that presentation template creates slides task."""
        from app.api.v1.templates import use_template
        from app.schemas.template import TemplateUseRequest

        template_id = uuid4()
        use_request = TemplateUseRequest(
            inputs={"title": "Q4 Review", "topics": "achievements, metrics"}
        )

        slides_result = {
            "template_id": str(uuid4()),
            "prompt": "Create a Q4 review presentation",
            "output_type": "presentation",
        }

        with patch("app.api.v1.templates.TemplateService") as MockService:
            mock_service = MockService.return_value
            mock_service.use_template = AsyncMock(return_value=slides_result)

            with patch("app.api.v1.templates.process_slides_task") as mock_celery:
                mock_celery.apply_async.return_value = MagicMock(id="celery-slides-101")

                with patch("app.api.v1.templates.TaskModel") as MockTask:
                    mock_task = MagicMock()
                    mock_task.id = uuid4()
                    mock_task.task_type = "slides"
                    MockTask.return_value = mock_task

                    result = await use_template(
                        template_id, use_request, mock_user, mock_db
                    )

                    # Verify slides task was created
                    task_kwargs = MockTask.call_args[1]
                    assert task_kwargs["task_type"] == "slides"

    @pytest.mark.asyncio
    async def test_template_metadata_stored_in_task(
        self, mock_db, mock_user, template_result
    ):
        """Test that template ID and inputs are stored in task metadata."""
        from app.api.v1.templates import use_template
        from app.schemas.template import TemplateUseRequest

        template_id = uuid4()
        inputs = {"topic": "blockchain", "depth": "comprehensive"}
        use_request = TemplateUseRequest(inputs=inputs)

        with patch("app.api.v1.templates.TemplateService") as MockService:
            mock_service = MockService.return_value
            mock_service.use_template = AsyncMock(return_value=template_result)

            with patch("app.api.v1.templates.process_research_task") as mock_celery:
                mock_celery.apply_async.return_value = MagicMock(id="celery-task-999")

                with patch("app.api.v1.templates.TaskModel") as MockTask:
                    mock_task = MagicMock()
                    mock_task.id = uuid4()
                    MockTask.return_value = mock_task

                    await use_template(template_id, use_request, mock_user, mock_db)

                    # Verify metadata contains template info
                    task_kwargs = MockTask.call_args[1]
                    metadata = task_kwargs["metadata"]
                    assert "template_id" in metadata
                    assert metadata["template_id"] == str(template_id)
                    assert "inputs" in metadata
                    assert metadata["inputs"] == inputs

    @pytest.mark.asyncio
    async def test_celery_failure_marks_task_failed(
        self, mock_db, mock_user, template_result
    ):
        """Test that Celery queueing failure marks task as failed."""
        from app.api.v1.templates import use_template
        from app.schemas.template import TemplateUseRequest

        template_id = uuid4()
        use_request = TemplateUseRequest(inputs={"topic": "test"})

        with patch("app.api.v1.templates.TemplateService") as MockService:
            mock_service = MockService.return_value
            mock_service.use_template = AsyncMock(return_value=template_result)

            with patch("app.api.v1.templates.process_research_task") as mock_celery:
                # Simulate Celery failure
                mock_celery.apply_async.side_effect = Exception("Celery connection failed")

                with patch("app.api.v1.templates.TaskModel") as MockTask:
                    mock_task = MagicMock()
                    mock_task.id = uuid4()
                    MockTask.return_value = mock_task

                    result = await use_template(
                        template_id, use_request, mock_user, mock_db
                    )

                    # Verify task status was set to FAILED
                    assert mock_task.status == TaskStatus.FAILED
                    assert mock_task.error_message is not None
                    assert "Failed to queue task" in mock_task.error_message

                    # Still returns response with task_id
                    assert result.task_id == mock_task.id

    @pytest.mark.asyncio
    async def test_unknown_output_type_defaults_to_research(
        self, mock_db, mock_user
    ):
        """Test that unknown output type defaults to research task."""
        from app.api.v1.templates import use_template
        from app.schemas.template import TemplateUseRequest

        template_id = uuid4()
        use_request = TemplateUseRequest(inputs={"data": "test"})

        unknown_result = {
            "template_id": str(uuid4()),
            "prompt": "Do something",
            "output_type": "unknown_category",
        }

        with patch("app.api.v1.templates.TemplateService") as MockService:
            mock_service = MockService.return_value
            mock_service.use_template = AsyncMock(return_value=unknown_result)

            with patch("app.api.v1.templates.process_research_task") as mock_celery:
                mock_celery.apply_async.return_value = MagicMock(id="celery-default-111")

                with patch("app.api.v1.templates.TaskModel") as MockTask:
                    mock_task = MagicMock()
                    mock_task.id = uuid4()
                    MockTask.return_value = mock_task

                    await use_template(template_id, use_request, mock_user, mock_db)

                    # Should default to research
                    task_kwargs = MockTask.call_args[1]
                    assert task_kwargs["task_type"] == "research"
                    assert mock_celery.apply_async.called
