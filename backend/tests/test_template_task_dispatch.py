"""Unit tests for template task dispatch helpers."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.api.v1 import templates


def test_resolve_task_type_defaults_to_research_for_unknown_values():
    assert templates._resolve_task_type("unknown") == "research"
    assert templates._resolve_task_type(None) == "research"


def test_resolve_task_type_trims_and_normalizes_case():
    assert templates._resolve_task_type("  DoCuMeNt  ") == "docs"


def test_resolve_task_type_supports_workspace_aliases_and_separators():
    assert templates._resolve_task_type("Google-Docs") == "docs"
    assert templates._resolve_task_type("google_sheets") == "sheets"
    assert templates._resolve_task_type("Slide Deck") == "slides"
    assert templates._resolve_task_type("analysis") == "research"


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


def test_queue_task_docs_uses_trimmed_title_when_provided():
    with patch.object(templates.process_docs_task, "apply_async") as mock_apply:
        mock_apply.return_value = MagicMock(id="celery-2")

        templates._queue_task(
            task_type="docs",
            task_id="task-2",
            prompt="write report",
            user_id="user-1",
            inputs={"title": "  Quarterly Plan  "},
        )

        assert mock_apply.call_args.kwargs["args"][-1] == "Quarterly Plan"


def test_queue_task_docs_uses_document_title_alias_when_title_missing():
    with patch.object(templates.process_docs_task, "apply_async") as mock_apply:
        mock_apply.return_value = MagicMock(id="celery-3")

        templates._queue_task(
            task_type="docs",
            task_id="task-3",
            prompt="write report",
            user_id="user-1",
            inputs={"document_title": "Project Kickoff"},
        )

        assert mock_apply.call_args.kwargs["args"][-1] == "Project Kickoff"


def test_queue_task_docs_falls_back_for_blank_title_values():
    with patch.object(templates.process_docs_task, "apply_async") as mock_apply:
        mock_apply.return_value = MagicMock(id="celery-4")

        templates._queue_task(
            task_type="docs",
            task_id="task-4",
            prompt="write report",
            user_id="user-1",
            inputs={"title": "   ", "document_title": ""},
        )

        assert mock_apply.call_args.kwargs["args"][-1] == "Template Document"


def test_queue_task_docs_uses_nested_document_title_alias():
    with patch.object(templates.process_docs_task, "apply_async") as mock_apply:
        mock_apply.return_value = MagicMock(id="celery-5")

        templates._queue_task(
            task_type="docs",
            task_id="task-5",
            prompt="write report",
            user_id="user-1",
            inputs={"document": {"title": "Architecture Overview"}},
        )

        assert mock_apply.call_args.kwargs["args"][-1] == "Architecture Overview"


def test_queue_task_slides_uses_deck_title_alias():
    with patch.object(templates.process_slides_task, "apply_async") as mock_apply:
        mock_apply.return_value = MagicMock(id="celery-6")

        templates._queue_task(
            task_type="slides",
            task_id="task-6",
            prompt="build deck",
            user_id="user-1",
            inputs={"deck_title": "Roadmap Review"},
        )

        assert mock_apply.call_args.kwargs["args"][-1] == "Roadmap Review"
