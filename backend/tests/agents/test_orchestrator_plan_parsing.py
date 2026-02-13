"""Tests for robust orchestrator task-plan parsing and validation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agents.orchestrator import MultiAgentOrchestrator


@pytest.fixture
def orchestrator_stub() -> MultiAgentOrchestrator:
    """Create an orchestrator instance without running heavy __init__ setup."""
    orchestrator = object.__new__(MultiAgentOrchestrator)
    orchestrator.llm = AsyncMock()
    return orchestrator


@pytest.mark.asyncio
async def test_decompose_task_accepts_tasks_object_payload(orchestrator_stub):
    """Planner payloads with a top-level tasks object should parse successfully."""
    orchestrator_stub.llm.ainvoke.return_value = SimpleNamespace(
        content='{"tasks": [{"task_id": "task_1", "agent_type": "research", "description": "Find market data", "dependencies": []}, {"task_id": "task_2", "agent_type": "docs", "description": "Write brief", "dependencies": ["task_1"]}]}'
    )

    tasks = await orchestrator_stub.decompose_task("Create a short market brief")

    assert len(tasks) == 2
    assert tasks[0].task_id == "task_1"
    assert tasks[0].agent_type == "research"
    assert tasks[1].task_id == "task_2"
    assert tasks[1].dependencies == ["task_1"]


@pytest.mark.asyncio
async def test_decompose_task_accepts_top_level_list_payload(orchestrator_stub):
    """Planner payloads emitted as a raw task list should also be supported."""
    orchestrator_stub.llm.ainvoke.return_value = SimpleNamespace(
        content='[{"task_id": "task_1", "agent_type": "research", "description": "Gather facts", "dependencies": []}]'
    )

    tasks = await orchestrator_stub.decompose_task("Research a topic")

    assert len(tasks) == 1
    assert tasks[0].task_id == "task_1"
    assert tasks[0].agent_type == "research"


@pytest.mark.asyncio
async def test_decompose_task_handles_fenced_json_from_structured_content(
    orchestrator_stub,
):
    """Anthropic-style structured content with fenced JSON should parse."""
    orchestrator_stub.llm.ainvoke.return_value = SimpleNamespace(
        content=[
            {
                "type": "text",
                "text": '```json\n{"tasks": [{"agent_type": "research", "description": "Collect competitor intel", "dependencies": []}]}\n```',
            }
        ]
    )

    tasks = await orchestrator_stub.decompose_task("Analyze competitors")

    assert len(tasks) == 1
    # task_id is auto-generated when missing
    assert tasks[0].task_id == "task_1"
    assert tasks[0].description == "Collect competitor intel"


def test_parse_task_plan_rejects_unknown_dependencies():
    """Dependency validation should fail fast on unknown task references."""
    raw_plan = {
        "tasks": [
            {
                "task_id": "task_1",
                "agent_type": "research",
                "description": "Collect metrics",
                "dependencies": ["task_9"],
            }
        ]
    }

    with pytest.raises(ValueError, match="Unknown task dependencies"):
        MultiAgentOrchestrator._parse_task_plan(raw_plan)


@pytest.mark.asyncio
async def test_decompose_task_falls_back_on_circular_dependency(orchestrator_stub):
    """Invalid dependency cycles should trigger safe single-task fallback."""
    orchestrator_stub.llm.ainvoke.return_value = SimpleNamespace(
        content={
            "tasks": [
                {
                    "task_id": "task_1",
                    "agent_type": "research",
                    "description": "Collect findings",
                    "dependencies": ["task_2"],
                },
                {
                    "task_id": "task_2",
                    "agent_type": "docs",
                    "description": "Draft report",
                    "dependencies": ["task_1"],
                },
            ]
        }
    )

    tasks = await orchestrator_stub.decompose_task("Create findings report")

    assert len(tasks) == 1
    assert tasks[0].task_id == "task_1"
    assert tasks[0].agent_type == "research"
    assert tasks[0].description == "Create findings report"
