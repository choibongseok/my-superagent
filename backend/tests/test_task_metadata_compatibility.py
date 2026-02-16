"""Task metadata and title resolution compatibility tests."""

from datetime import UTC, datetime
from uuid import uuid4

from app.api.v1 import tasks
from app.models.task import Task as TaskModel
from app.models.task import TaskStatus, TaskType
from app.schemas.task import Task


def test_build_task_kwargs_uses_task_metadata_field():
    kwargs = tasks._build_task_kwargs(
        user_id=uuid4(),
        prompt="Draft project kickoff",
        task_type=TaskType.DOCS,
        metadata={"template_id": "tpl-1"},
    )

    assert kwargs["task_metadata"] == {"template_id": "tpl-1"}
    assert "metadata" not in kwargs


def test_resolve_task_title_prefers_alias_keys_and_trims():
    title = tasks._resolve_task_title(
        "slides",
        {"title": "   ", "deck_title": "  Q1 Roadmap  "},
    )

    assert title == "Q1 Roadmap"


def test_resolve_task_title_falls_back_to_default():
    title = tasks._resolve_task_title("sheets", {"sheet_title": "   "})

    assert title == "Untitled Spreadsheet"


def test_task_schema_reads_task_metadata_instead_of_sqlalchemy_metadata_attr():
    now = datetime.now(UTC)
    task_model = TaskModel(
        id=uuid4(),
        user_id=uuid4(),
        prompt="Research multi-agent orchestration",
        task_type=TaskType.RESEARCH,
        status=TaskStatus.PENDING,
        task_metadata={"source": "template"},
    )

    # Simulate accidental instance-level metadata shadowing.
    task_model.metadata = {"source": "wrong"}
    task_model.created_at = now
    task_model.updated_at = now

    schema = Task.model_validate(task_model)

    assert schema.metadata == {"source": "template"}
