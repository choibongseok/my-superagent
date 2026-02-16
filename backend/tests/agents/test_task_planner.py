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


def test_get_agent_workload_breakdown_groups_resource_estimates(planner_stub):
    """Workload breakdown should aggregate execution estimates by agent type."""
    steps = [
        PlanStep("step_1", "Research market", "research", 30, 0.02, 2000),
        PlanStep("step_2", "Research users", "research", 30, 0.02, 2000),
        PlanStep("step_3", "Draft report", "docs", 20, 0.03, 3000),
        PlanStep("step_4", "Publish summary", "docs", 20, 0.03, 3000),
        PlanStep("step_5", "Build table", "sheets", 10, 0.01, 1000),
    ]

    breakdown = planner_stub.get_agent_workload_breakdown(_build_plan(steps))

    assert breakdown == {
        "docs": {
            "step_count": 2,
            "total_work_seconds": 40,
            "total_estimated_cost": 0.06,
            "total_estimated_tokens": 6000,
            "time_share": 0.3636,
            "cost_share": 0.5455,
            "token_share": 0.5455,
        },
        "research": {
            "step_count": 2,
            "total_work_seconds": 60,
            "total_estimated_cost": 0.04,
            "total_estimated_tokens": 4000,
            "time_share": 0.5455,
            "cost_share": 0.3636,
            "token_share": 0.3636,
        },
        "sheets": {
            "step_count": 1,
            "total_work_seconds": 10,
            "total_estimated_cost": 0.01,
            "total_estimated_tokens": 1000,
            "time_share": 0.0909,
            "cost_share": 0.0909,
            "token_share": 0.0909,
        },
    }


def test_get_execution_summary_can_include_agent_workload_breakdown(planner_stub):
    """Execution summary should optionally include per-agent workload metrics."""
    steps = [
        PlanStep("step_1", "Research", "research", 30, 0.02, 2000),
        PlanStep("step_2", "Draft", "docs", 20, 0.03, 3000, ["step_1"]),
    ]

    summary = planner_stub.get_execution_summary(
        _build_plan(steps),
        include_agent_workload=True,
    )

    assert "agent_workload" in summary
    assert summary["agent_workload"]["research"] == {
        "step_count": 1,
        "total_work_seconds": 30,
        "total_estimated_cost": 0.02,
        "total_estimated_tokens": 2000,
        "time_share": 0.6,
        "cost_share": 0.4,
        "token_share": 0.4,
    }


def test_get_execution_summary_validates_include_agent_workload_flag(planner_stub):
    """include_agent_workload should require a strict boolean value."""
    with pytest.raises(ValueError, match="include_agent_workload must be a boolean"):
        planner_stub.get_execution_summary(
            _build_plan(
                [
                    PlanStep("step_1", "Research", "research", 30, 0.02, 2000),
                ]
            ),
            include_agent_workload=1,  # type: ignore[arg-type]
        )


def test_get_execution_timeline_reports_dependency_aware_step_times(planner_stub):
    """Timeline helper should expose deterministic start/finish times per step."""
    steps = [
        PlanStep("step_1", "Research", "research", 30, 0.02, 2000),
        PlanStep("step_2", "Collect metrics", "research", 30, 0.02, 2000),
        PlanStep("step_3", "Draft summary", "docs", 20, 0.03, 3000, ["step_1"]),
        PlanStep("step_4", "Build table", "sheets", 15, 0.02, 1500, ["step_2"]),
        PlanStep(
            "step_5", "Finalize report", "docs", 20, 0.03, 3000, ["step_3", "step_4"]
        ),
    ]

    timeline = planner_stub.get_execution_timeline(_build_plan(steps))

    assert [entry["step_id"] for entry in timeline] == [
        "step_1",
        "step_2",
        "step_3",
        "step_4",
        "step_5",
    ]
    assert timeline[0]["start_time"] == 0
    assert timeline[0]["finish_time"] == 30
    assert timeline[2]["dependency_ready_time"] == 30
    assert timeline[2]["start_time"] == 30
    assert timeline[4]["dependency_ready_time"] == 50
    assert timeline[4]["finish_time"] == 70
    assert all(entry["queue_delay_seconds"] == 0 for entry in timeline)


def test_get_execution_timeline_accounts_for_parallelism_limits(planner_stub):
    """Timeline should report queue delay when worker capacity is constrained."""
    steps = [
        PlanStep("step_1", "Collect A", "research", 30, 0.02, 2000),
        PlanStep("step_2", "Collect B", "research", 20, 0.02, 2000),
        PlanStep("step_3", "Collect C", "research", 10, 0.02, 2000),
    ]

    timeline = planner_stub.get_execution_timeline(
        _build_plan(steps),
        max_parallel_steps=2,
    )

    assert [entry["step_id"] for entry in timeline] == ["step_1", "step_2", "step_3"]
    assert timeline[2]["dependency_ready_time"] == 0
    assert timeline[2]["start_time"] == 20
    assert timeline[2]["finish_time"] == 30
    assert timeline[2]["queue_delay_seconds"] == 20


def test_get_execution_summary_can_include_execution_timeline(planner_stub):
    """Execution summary should optionally include per-step timing details."""
    steps = [
        PlanStep("step_1", "Research", "research", 30, 0.02, 2000),
        PlanStep("step_2", "Draft", "docs", 20, 0.03, 3000, ["step_1"]),
    ]

    summary = planner_stub.get_execution_summary(
        _build_plan(steps),
        include_execution_timeline=True,
    )

    assert "execution_timeline" in summary
    assert [entry["step_id"] for entry in summary["execution_timeline"]] == [
        "step_1",
        "step_2",
    ]
    assert summary["execution_timeline"][1]["dependency_ready_time"] == 30
    assert summary["execution_timeline"][1]["queue_delay_seconds"] == 0


def test_get_execution_summary_validates_include_execution_timeline_flag(planner_stub):
    """include_execution_timeline should require a strict boolean value."""
    with pytest.raises(
        ValueError,
        match="include_execution_timeline must be a boolean",
    ):
        planner_stub.get_execution_summary(
            _build_plan(
                [
                    PlanStep("step_1", "Research", "research", 30, 0.02, 2000),
                ]
            ),
            include_execution_timeline="yes",  # type: ignore[arg-type]
        )


def test_get_step_slack_reports_earliest_latest_and_float_metrics(planner_stub):
    """Step slack helper should report CPM timing windows per step."""
    steps = [
        PlanStep("step_1", "Primary research", "research", 30, 0.02, 2000),
        PlanStep("step_2", "Secondary research", "research", 10, 0.02, 2000),
        PlanStep("step_3", "Draft report", "docs", 20, 0.03, 3000, ["step_1"]),
        PlanStep("step_4", "Quick appendix", "docs", 5, 0.03, 3000, ["step_2"]),
    ]

    step_slack = planner_stub.get_step_slack(_build_plan(steps))

    assert step_slack == [
        {
            "step_id": "step_1",
            "description": "Primary research",
            "dependencies": [],
            "earliest_start": 0,
            "earliest_finish": 30,
            "latest_start": 0,
            "latest_finish": 30,
            "total_float_seconds": 0,
            "is_critical": True,
        },
        {
            "step_id": "step_2",
            "description": "Secondary research",
            "dependencies": [],
            "earliest_start": 0,
            "earliest_finish": 10,
            "latest_start": 35,
            "latest_finish": 45,
            "total_float_seconds": 35,
            "is_critical": False,
        },
        {
            "step_id": "step_3",
            "description": "Draft report",
            "dependencies": ["step_1"],
            "earliest_start": 30,
            "earliest_finish": 50,
            "latest_start": 30,
            "latest_finish": 50,
            "total_float_seconds": 0,
            "is_critical": True,
        },
        {
            "step_id": "step_4",
            "description": "Quick appendix",
            "dependencies": ["step_2"],
            "earliest_start": 10,
            "earliest_finish": 15,
            "latest_start": 45,
            "latest_finish": 50,
            "total_float_seconds": 35,
            "is_critical": False,
        },
    ]


def test_get_execution_summary_can_include_step_slack(planner_stub):
    """Execution summary should optionally expose step-slack diagnostics."""
    steps = [
        PlanStep("step_1", "Primary research", "research", 30, 0.02, 2000),
        PlanStep("step_2", "Secondary research", "research", 10, 0.02, 2000),
        PlanStep("step_3", "Draft report", "docs", 20, 0.03, 3000, ["step_1"]),
        PlanStep("step_4", "Quick appendix", "docs", 5, 0.03, 3000, ["step_2"]),
    ]

    summary = planner_stub.get_execution_summary(
        _build_plan(steps),
        include_step_slack=True,
    )

    assert summary["critical_step_ids"] == ["step_1", "step_3"]
    assert [item["step_id"] for item in summary["step_slack"]] == [
        "step_1",
        "step_2",
        "step_3",
        "step_4",
    ]
    assert summary["step_slack"][1]["total_float_seconds"] == 35


def test_get_execution_summary_validates_include_step_slack_flag(planner_stub):
    """include_step_slack should require a strict boolean value."""
    with pytest.raises(ValueError, match="include_step_slack must be a boolean"):
        planner_stub.get_execution_summary(
            _build_plan(
                [
                    PlanStep("step_1", "Research", "research", 30, 0.02, 2000),
                ]
            ),
            include_step_slack=1,  # type: ignore[arg-type]
        )


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
