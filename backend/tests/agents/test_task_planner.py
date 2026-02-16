"""Tests for TaskPlanner dependency validation and execution batching."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agents.task_planner import ExecutionPlan, PlanStep, TaskPlanner, TaskStatus


@pytest.fixture
def planner_stub() -> TaskPlanner:
    """Create a TaskPlanner instance without constructing real LLM clients."""
    planner = object.__new__(TaskPlanner)
    planner.llm = AsyncMock()
    planner.time_coefficients = {
        "research": 30,
        "docs": 20,
        "sheets": 15,
        "slides": 25,
    }
    planner.cost_coefficients = {
        "research": 0.02,
        "docs": 0.03,
        "sheets": 0.02,
        "slides": 0.03,
    }
    planner.token_coefficients = {
        "research": 2000,
        "docs": 3000,
        "sheets": 1500,
        "slides": 2500,
    }
    return planner


def _build_plan(steps: list[PlanStep]) -> ExecutionPlan:
    return ExecutionPlan(
        goal="Test goal",
        steps=steps,
        total_estimated_time=sum(step.estimated_time for step in steps),
        total_estimated_cost=sum(step.estimated_cost for step in steps),
        total_estimated_tokens=sum(step.estimated_tokens for step in steps),
        constraints={},
        created_at="2026-01-01T00:00:00",
    )


def test_get_execution_batches_groups_parallel_steps(planner_stub):
    """Planner should return deterministic parallel execution batches."""
    steps = [
        PlanStep("step_1", "Research", "research", 30, 0.02, 2000),
        PlanStep("step_2", "Gather requirements", "research", 30, 0.02, 2000),
        PlanStep("step_3", "Draft report", "docs", 20, 0.03, 3000, ["step_1"]),
        PlanStep("step_4", "Create table", "sheets", 15, 0.02, 1500, ["step_2"]),
        PlanStep(
            "step_5",
            "Final summary",
            "docs",
            20,
            0.03,
            3000,
            ["step_3", "step_4"],
        ),
    ]

    plan = _build_plan(steps)
    batches = planner_stub.get_execution_batches(plan)

    assert [[step.step_id for step in batch] for batch in batches] == [
        ["step_1", "step_2"],
        ["step_3", "step_4"],
        ["step_5"],
    ]


def test_get_execution_batches_rejects_unknown_dependencies(planner_stub):
    """Unknown dependencies should fail before batching starts."""
    steps = [
        PlanStep(
            "step_1",
            "Write summary",
            "docs",
            20,
            0.03,
            3000,
            ["step_missing"],
        )
    ]

    with pytest.raises(ValueError, match="Unknown step dependencies"):
        planner_stub.get_execution_batches(_build_plan(steps))


def test_get_execution_batches_rejects_cycles(planner_stub):
    """Circular dependencies should be detected and rejected."""
    steps = [
        PlanStep("step_1", "Research", "research", 30, 0.02, 2000, ["step_2"]),
        PlanStep("step_2", "Draft", "docs", 20, 0.03, 3000, ["step_1"]),
    ]

    with pytest.raises(ValueError, match="Circular step dependency"):
        planner_stub.get_execution_batches(_build_plan(steps))


def test_estimate_makespan_accounts_for_parallelism(planner_stub):
    """Makespan should track critical-chain duration instead of total work."""
    steps = [
        PlanStep("step_1", "Research", "research", 30, 0.02, 2000),
        PlanStep("step_2", "Collect metrics", "research", 30, 0.02, 2000),
        PlanStep("step_3", "Draft summary", "docs", 20, 0.03, 3000, ["step_1"]),
        PlanStep("step_4", "Build table", "sheets", 15, 0.02, 1500, ["step_2"]),
        PlanStep(
            "step_5", "Finalize report", "docs", 20, 0.03, 3000, ["step_3", "step_4"]
        ),
    ]

    plan = _build_plan(steps)

    assert planner_stub.estimate_makespan(plan) == 70


def test_estimate_makespan_supports_optional_parallelism_limits(planner_stub):
    """Makespan estimation should support explicit worker-capacity constraints."""
    steps = [
        PlanStep("step_1", "Collect market data", "research", 30, 0.02, 2000),
        PlanStep("step_2", "Collect user feedback", "research", 30, 0.02, 2000),
        PlanStep("step_3", "Collect competitor data", "research", 30, 0.02, 2000),
        PlanStep(
            "step_4",
            "Synthesize findings",
            "docs",
            10,
            0.03,
            3000,
            ["step_1", "step_2", "step_3"],
        ),
    ]

    plan = _build_plan(steps)

    assert planner_stub.estimate_makespan(plan) == 40
    assert planner_stub.estimate_makespan(plan, max_parallel_steps=2) == 70
    assert planner_stub.estimate_makespan(plan, max_parallel_steps=1) == 100


def test_estimate_makespan_rejects_invalid_parallelism_limits(planner_stub):
    """Parallelism limit should be validated before schedule simulation."""
    plan = _build_plan(
        [
            PlanStep("step_1", "Research", "research", 30, 0.02, 2000),
        ]
    )

    with pytest.raises(
        ValueError, match="max_parallel_steps must be a positive integer"
    ):
        planner_stub.estimate_makespan(plan, max_parallel_steps=0)

    with pytest.raises(
        ValueError, match="max_parallel_steps must be a positive integer"
    ):
        planner_stub.estimate_makespan(plan, max_parallel_steps=True)  # type: ignore[arg-type]


def test_get_execution_summary_includes_parallelism_limit_when_provided(planner_stub):
    """Execution summary should report the worker-capacity limit when set."""
    steps = [
        PlanStep("step_1", "Collect market data", "research", 30, 0.02, 2000),
        PlanStep("step_2", "Collect user feedback", "research", 30, 0.02, 2000),
        PlanStep("step_3", "Collect competitor data", "research", 30, 0.02, 2000),
        PlanStep(
            "step_4",
            "Synthesize findings",
            "docs",
            10,
            0.03,
            3000,
            ["step_1", "step_2", "step_3"],
        ),
    ]

    summary = planner_stub.get_execution_summary(
        _build_plan(steps),
        max_parallel_steps=2,
    )

    assert summary["makespan_seconds"] == 70
    assert summary["parallelism_gain"] == 1.43
    assert summary["max_parallel_steps"] == 2


def test_get_critical_path_prefers_longest_dependency_chain(planner_stub):
    """Critical path should follow dependencies that determine makespan."""
    steps = [
        PlanStep("step_1", "Research", "research", 30, 0.02, 2000),
        PlanStep("step_2", "Collect metrics", "research", 30, 0.02, 2000),
        PlanStep("step_3", "Draft summary", "docs", 20, 0.03, 3000, ["step_1"]),
        PlanStep("step_4", "Build table", "sheets", 15, 0.02, 1500, ["step_2"]),
        PlanStep(
            "step_5", "Finalize report", "docs", 20, 0.03, 3000, ["step_3", "step_4"]
        ),
    ]

    plan = _build_plan(steps)

    assert planner_stub.get_critical_path(plan) == ["step_1", "step_3", "step_5"]


def test_get_execution_summary_reports_schedule_metrics(planner_stub):
    """Execution summary should include batching, makespan, and critical-path data."""
    steps = [
        PlanStep("step_1", "Research", "research", 30, 0.02, 2000),
        PlanStep("step_2", "Collect metrics", "research", 30, 0.02, 2000),
        PlanStep("step_3", "Draft summary", "docs", 20, 0.03, 3000, ["step_1"]),
        PlanStep("step_4", "Build table", "sheets", 15, 0.02, 1500, ["step_2"]),
        PlanStep(
            "step_5", "Finalize report", "docs", 20, 0.03, 3000, ["step_3", "step_4"]
        ),
    ]

    plan = _build_plan(steps)
    summary = planner_stub.get_execution_summary(plan)

    assert summary == {
        "total_steps": 5,
        "batch_count": 3,
        "batch_sizes": [2, 2, 1],
        "total_work_seconds": 115,
        "makespan_seconds": 70,
        "parallelism_gain": 1.64,
        "critical_path_step_ids": ["step_1", "step_3", "step_5"],
    }


def test_get_ready_steps_returns_only_dependency_satisfied_planned_steps(planner_stub):
    """Ready-queue helper should skip steps with unmet or terminally failed dependencies."""
    steps = [
        PlanStep("step_1", "Research", "research", 30, 0.02, 2000),
        PlanStep("step_2", "Collect metrics", "research", 30, 0.02, 2000),
        PlanStep("step_3", "Draft summary", "docs", 20, 0.03, 3000, ["step_1"]),
        PlanStep("step_4", "Build table", "sheets", 15, 0.02, 1500, ["step_2"]),
        PlanStep(
            "step_5", "Finalize report", "docs", 20, 0.03, 3000, ["step_3", "step_4"]
        ),
    ]

    steps[0].status = TaskStatus.COMPLETED
    steps[1].status = TaskStatus.FAILED

    plan = _build_plan(steps)

    ready_steps = planner_stub.get_ready_steps(plan)

    assert [step.step_id for step in ready_steps] == ["step_3"]


def test_get_blocked_steps_reports_failed_and_incomplete_dependencies(planner_stub):
    """Blocked-step helper should separate terminal failures from pending blockers."""
    steps = [
        PlanStep("step_1", "Research", "research", 30, 0.02, 2000),
        PlanStep("step_2", "Collect metrics", "research", 30, 0.02, 2000),
        PlanStep("step_3", "Draft summary", "docs", 20, 0.03, 3000, ["step_1"]),
        PlanStep("step_4", "Build table", "sheets", 15, 0.02, 1500, ["step_2"]),
    ]

    steps[1].status = TaskStatus.CANCELLED

    plan = _build_plan(steps)
    blocked = planner_stub.get_blocked_steps(plan)

    assert blocked == {
        "failed_dependencies": {"step_4": ["step_2"]},
        "incomplete_dependencies": {"step_3": ["step_1"]},
    }


def test_get_progress_reports_ready_queue_and_failed_dependency_blockers(planner_stub):
    """Progress payload should expose runnable steps and failed-dependency blockers."""
    steps = [
        PlanStep("step_1", "Research", "research", 30, 0.02, 2000),
        PlanStep("step_2", "Collect metrics", "research", 30, 0.02, 2000),
        PlanStep("step_3", "Draft summary", "docs", 20, 0.03, 3000, ["step_1"]),
        PlanStep("step_4", "Build table", "sheets", 15, 0.02, 1500, ["step_2"]),
    ]

    steps[0].status = TaskStatus.COMPLETED
    steps[1].status = TaskStatus.CANCELLED

    plan = _build_plan(steps)

    progress = planner_stub.get_progress(plan)

    assert progress["ready"] == 1
    assert progress["ready_step_ids"] == ["step_3"]
    assert progress["blocked_by_failed_dependencies"] == {"step_4": ["step_2"]}
    assert progress["blocked_by_incomplete_dependencies"] == {}


def test_get_progress_reports_incomplete_dependency_blockers(planner_stub):
    """Progress payload should expose blockers waiting on unfinished dependencies."""
    steps = [
        PlanStep("step_1", "Research", "research", 30, 0.02, 2000),
        PlanStep("step_2", "Draft summary", "docs", 20, 0.03, 3000, ["step_1"]),
        PlanStep("step_3", "Finalize", "docs", 20, 0.03, 3000, ["step_2"]),
    ]

    steps[0].status = TaskStatus.IN_PROGRESS

    plan = _build_plan(steps)
    progress = planner_stub.get_progress(plan)

    assert progress["ready"] == 0
    assert progress["blocked_by_failed_dependencies"] == {}
    assert progress["blocked_by_incomplete_dependencies"] == {
        "step_2": ["step_1"],
        "step_3": ["step_2"],
    }


@pytest.mark.asyncio
async def test_plan_parses_structured_content_blocks(planner_stub):
    """Structured provider responses with fenced JSON should parse correctly."""
    planner_stub.llm.ainvoke.return_value = SimpleNamespace(
        content=[
            {
                "type": "text",
                "text": '```json\n{"steps": [{"step_id": "step_1", "description": "Collect facts", "agent_type": "research", "complexity": "low", "dependencies": []}]}\n```',
            }
        ]
    )

    plan = await planner_stub.plan(goal="Collect facts")

    assert len(plan.steps) == 1
    assert plan.steps[0].step_id == "step_1"
    assert plan.steps[0].estimated_time == 21  # 30 * 0.7
    assert plan.total_estimated_tokens == 1400


@pytest.mark.asyncio
async def test_plan_rejects_unknown_dependencies(planner_stub):
    """Plan creation should fail fast when a step references unknown dependencies."""
    planner_stub.llm.ainvoke.return_value = SimpleNamespace(
        content='{"steps": [{"step_id": "step_1", "description": "Draft", "agent_type": "docs", "dependencies": ["step_2"]}]}'
    )

    with pytest.raises(ValueError, match="Unknown step dependencies"):
        await planner_stub.plan(goal="Create draft")
