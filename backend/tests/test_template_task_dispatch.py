"""Unit tests for template task dispatch helpers."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.api.v1 import templates


def test_resolve_task_type_defaults_to_research_for_unknown_values():
    assert templates._resolve_task_type("unknown") == "research"
    assert templates._resolve_task_type(None) == "research"


def test_build_task_kwargs_uses_task_metadata_for_real_task_model():
    kwargs = templates._build_task_kwargs(
        user_id=uuid4(),
        prompt="hello",
        task_type="research",
        template_id=uuid4(),
        inputs={"topic": "ai"},
    )

    assert "task_metadata" in kwargs
    assert "metadata" not in kwargs
    assert kwargs["task_metadata"]["inputs"] == {"topic": "ai"}


def test_queue_task_docs_uses_default_title_when_missing():
    with patch.object(templates.process_docs_task, "apply_async") as mock_apply:
        mock_apply.return_value = MagicMock(id="celery-1")

        result = templates._queue_task(
            task_type="docs",
            task_id="task-1",
            prompt="write report",
            user_id="user-1",
            inputs={},
        )

        assert result.id == "celery-1"
        assert mock_apply.call_args.kwargs["args"][-1] == "Template Document"
