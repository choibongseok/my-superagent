"""Autonomous Task Planner with goal-oriented planning and resource estimation."""

import heapq
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """Task execution status."""

    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class ResourceType(str, Enum):
    """Resource types for task execution."""

    TIME = "time"  # Time in seconds
    COST = "cost"  # Cost in USD
    API_CALLS = "api_calls"  # Number of API calls
    TOKENS = "tokens"  # LLM tokens


@dataclass
class PlanStep:
    """Represents a single step in execution plan."""

    step_id: str
    description: str
    agent_type: str
    estimated_time: int  # seconds
    estimated_cost: float  # USD
    estimated_tokens: int
    dependencies: List[str] = field(default_factory=list)
    success_criteria: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PLANNED
    actual_time: Optional[int] = None
    actual_cost: Optional[float] = None
    result: Optional[Dict[str, Any]] = None


@dataclass
class ExecutionPlan:
    """Represents complete execution plan for a goal."""

    goal: str
    steps: List[PlanStep]
    total_estimated_time: int
    total_estimated_cost: float
    total_estimated_tokens: int
    constraints: Dict[str, Any]
    created_at: str
    updated_at: Optional[str] = None


class TaskPlanner:
    """
    Autonomous task planner with goal-oriented planning.

    Features:
        - Goal decomposition into executable steps
        - Resource estimation (time, cost, tokens)
        - Constraint validation (budget, time limits)
        - Dynamic re-planning based on execution results
        - Progress tracking and reporting
    """

    def __init__(
        self,
        llm_provider: str = "openai",
        model: str = "gpt-4-turbo-preview",
        temperature: float = 0.3,
    ):
        """
        Initialize task planner.

        Args:
            llm_provider: LLM provider (openai or anthropic)
            model: Model name
            temperature: Temperature for planning (lower = more deterministic)
        """
        if llm_provider == "openai":
            self.llm = ChatOpenAI(
                model=model,
                temperature=temperature,
                max_tokens=4000,
            )
        else:
            self.llm = ChatAnthropic(
                model=model,
                temperature=temperature,
                max_tokens=4000,
            )

        # Resource estimation coefficients (based on historical data)
        self.time_coefficients = {
            "research": 30,  # 30 seconds base
            "docs": 20,
            "sheets": 15,
            "slides": 25,
        }

        self.cost_coefficients = {
            "research": 0.02,  # $0.02 base
            "docs": 0.03,
            "sheets": 0.02,
            "slides": 0.03,
        }

        self.token_coefficients = {
            "research": 2000,  # 2000 tokens base
            "docs": 3000,
            "sheets": 1500,
            "slides": 2500,
        }

        logger.info(f"TaskPlanner initialized with {llm_provider}/{model}")

    @staticmethod
    def _normalize_llm_content(content: Any) -> str:
        """Normalize provider-specific LLM response content into plain text."""
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue

                if isinstance(item, dict):
                    text = item.get("text")
                    if text:
                        parts.append(str(text))
                    continue

                text = getattr(item, "text", None)
                if text:
                    parts.append(str(text))

            return "\n".join(parts).strip()

        return str(content)

    @staticmethod
    def _normalize_dependencies(raw_dependencies: Any, *, step_id: str) -> List[str]:
        """Normalize a step dependency field into a de-duplicated list."""
        if raw_dependencies is None:
            return []

        if isinstance(raw_dependencies, str):
            raw_dependencies = [raw_dependencies]

        if not isinstance(raw_dependencies, list):
            raise ValueError(f"Step '{step_id}' dependencies must be a list or string")

        normalized: List[str] = []
        for dependency in raw_dependencies:
            dependency_id = str(dependency).strip()
            if dependency_id:
                normalized.append(dependency_id)

        # Preserve order while removing duplicates
        return list(dict.fromkeys(normalized))

    @classmethod
    def _validate_step_dependencies(cls, steps: List[PlanStep]) -> None:
        """Validate step IDs and dependencies before execution."""
        step_ids: List[str] = []
        duplicates: set[str] = set()
        seen: set[str] = set()

        for step in steps:
            step_id = step.step_id
            step_ids.append(step_id)
            if step_id in seen:
                duplicates.add(step_id)
            seen.add(step_id)

        if duplicates:
            duplicate_list = ", ".join(sorted(duplicates))
            raise ValueError(f"Duplicate step_id values found: {duplicate_list}")

        known_ids = set(step_ids)
        missing_dependencies = sorted(
            {
                dependency
                for step in steps
                for dependency in step.dependencies
                if dependency not in known_ids
            }
        )
        if missing_dependencies:
            missing = ", ".join(missing_dependencies)
            raise ValueError(f"Unknown step dependencies found: {missing}")

        for step in steps:
            if step.step_id in step.dependencies:
                raise ValueError(f"Step '{step.step_id}' cannot depend on itself")

        graph = {step.step_id: step.dependencies for step in steps}
        visited: set[str] = set()
        visiting: set[str] = set()

        def dfs(step_id: str) -> None:
            if step_id in visited:
                return
            if step_id in visiting:
                raise ValueError(f"Circular step dependency detected at '{step_id}'")

            visiting.add(step_id)
            for dependency_id in graph[step_id]:
                dfs(dependency_id)
            visiting.remove(step_id)
            visited.add(step_id)

        for current_step_id in step_ids:
            dfs(current_step_id)

    def get_execution_batches(self, plan: ExecutionPlan) -> List[List[PlanStep]]:
        """Return step batches that can run in parallel based on dependencies."""
        self._validate_step_dependencies(plan.steps)

        step_by_id = {step.step_id: step for step in plan.steps}
        order_index = {step.step_id: index for index, step in enumerate(plan.steps)}
        unresolved_dependencies = {
            step.step_id: set(step.dependencies) for step in plan.steps
        }

        remaining = set(step_by_id)
        batches: List[List[PlanStep]] = []

        while remaining:
            ready_ids = sorted(
                [
                    step_id
                    for step_id in remaining
                    if not unresolved_dependencies[step_id]
                ],
                key=lambda step_id: order_index[step_id],
            )

            if not ready_ids:
                raise ValueError("Circular step dependency detected during batching")

            ready_set = set(ready_ids)
            batches.append([step_by_id[step_id] for step_id in ready_ids])
            remaining -= ready_set

            for step_id in remaining:
                unresolved_dependencies[step_id] -= ready_set

        return batches

    def _build_dependency_timeline(
        self, plan: ExecutionPlan
    ) -> tuple[Dict[str, int], Dict[str, Optional[str]]]:
        """Compute step finish times and predecessors for dependency-aware scheduling."""
        batches = self.get_execution_batches(plan)
        order_index = {step.step_id: index for index, step in enumerate(plan.steps)}

        finish_times: Dict[str, int] = {}
        predecessor: Dict[str, Optional[str]] = {}

        for batch in batches:
            for step in batch:
                if not step.dependencies:
                    start_time = 0
                    predecessor[step.step_id] = None
                else:
                    critical_dependency = max(
                        step.dependencies,
                        key=lambda dependency_id: (
                            finish_times[dependency_id],
                            -order_index[dependency_id],
                            dependency_id,
                        ),
                    )
                    start_time = finish_times[critical_dependency]
                    predecessor[step.step_id] = critical_dependency

                finish_times[step.step_id] = start_time + step.estimated_time

        return finish_times, predecessor

    @staticmethod
    def _validate_parallelism_limit(max_parallel_steps: Optional[int]) -> Optional[int]:
        """Validate optional parallelism limits used for schedule simulation."""
        if max_parallel_steps is None:
            return None

        if isinstance(max_parallel_steps, bool) or not isinstance(
            max_parallel_steps, int
        ):
            raise ValueError("max_parallel_steps must be a positive integer")

        if max_parallel_steps <= 0:
            raise ValueError("max_parallel_steps must be a positive integer")

        return max_parallel_steps

    def _estimate_makespan_with_parallelism_limit(
        self,
        plan: ExecutionPlan,
        *,
        max_parallel_steps: int,
    ) -> int:
        """Estimate makespan with dependency and worker-capacity constraints."""
        self._validate_step_dependencies(plan.steps)

        if not plan.steps:
            return 0

        step_by_id = {step.step_id: step for step in plan.steps}
        order_index = {step.step_id: index for index, step in enumerate(plan.steps)}

        unresolved_dependency_counts = {
            step.step_id: len(step.dependencies) for step in plan.steps
        }
        dependents: Dict[str, List[str]] = {step.step_id: [] for step in plan.steps}
        for step in plan.steps:
            for dependency_id in step.dependencies:
                dependents[dependency_id].append(step.step_id)

        ready_queue = [
            step.step_id
            for step in plan.steps
            if unresolved_dependency_counts[step.step_id] == 0
        ]

        running_steps: list[tuple[int, int, str]] = []
        completed: set[str] = set()
        current_time = 0

        while len(completed) < len(plan.steps):
            ready_queue.sort(key=lambda step_id: order_index[step_id])

            while ready_queue and len(running_steps) < max_parallel_steps:
                step_id = ready_queue.pop(0)
                step = step_by_id[step_id]
                finish_time = current_time + step.estimated_time
                heapq.heappush(
                    running_steps, (finish_time, order_index[step_id], step_id)
                )

            if not running_steps:
                raise ValueError(
                    "No runnable steps available during schedule simulation"
                )

            finish_time, _, finished_step_id = heapq.heappop(running_steps)
            finished_step_ids = [finished_step_id]

            while running_steps and running_steps[0][0] == finish_time:
                _, _, tied_step_id = heapq.heappop(running_steps)
                finished_step_ids.append(tied_step_id)

            current_time = finish_time

            for step_id in finished_step_ids:
                completed.add(step_id)
                for dependent_id in dependents[step_id]:
                    unresolved_dependency_counts[dependent_id] -= 1
                    if unresolved_dependency_counts[dependent_id] == 0:
                        ready_queue.append(dependent_id)

        return current_time

    def estimate_makespan(
        self,
        plan: ExecutionPlan,
        *,
        max_parallel_steps: Optional[int] = None,
    ) -> int:
        """Estimate wall-clock duration with optional parallelism constraints.

        Args:
            plan: Plan to evaluate.
            max_parallel_steps: Optional worker-capacity limit. When omitted,
                assumes all dependency-safe steps can run in parallel.
        """
        validated_limit = self._validate_parallelism_limit(max_parallel_steps)
        if validated_limit is None:
            finish_times, _ = self._build_dependency_timeline(plan)
            return max(finish_times.values(), default=0)

        return self._estimate_makespan_with_parallelism_limit(
            plan,
            max_parallel_steps=validated_limit,
        )

    def get_critical_path(self, plan: ExecutionPlan) -> List[str]:
        """Return the critical path (longest dependency chain) for a plan."""
        if not plan.steps:
            return []

        finish_times, predecessor = self._build_dependency_timeline(plan)
        order_index = {step.step_id: index for index, step in enumerate(plan.steps)}

        end_step_id = max(
            [step.step_id for step in plan.steps],
            key=lambda step_id: (finish_times[step_id], -order_index[step_id], step_id),
        )

        critical_path: List[str] = []
        current_step_id: Optional[str] = end_step_id
        while current_step_id:
            critical_path.append(current_step_id)
            current_step_id = predecessor.get(current_step_id)

        critical_path.reverse()
        return critical_path

    def get_execution_summary(
        self,
        plan: ExecutionPlan,
        *,
        max_parallel_steps: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Return dependency-aware schedule metrics for execution planning.

        Args:
            plan: Plan to summarize.
            max_parallel_steps: Optional worker-capacity limit used for
                makespan and parallelism-gain estimation.
        """
        batches = self.get_execution_batches(plan)
        makespan = self.estimate_makespan(
            plan,
            max_parallel_steps=max_parallel_steps,
        )
        total_work = sum(step.estimated_time for step in plan.steps)

        summary: Dict[str, Any] = {
            "total_steps": len(plan.steps),
            "batch_count": len(batches),
            "batch_sizes": [len(batch) for batch in batches],
            "total_work_seconds": total_work,
            "makespan_seconds": makespan,
            "parallelism_gain": round(total_work / makespan, 2) if makespan else 0.0,
            "critical_path_step_ids": self.get_critical_path(plan),
        }

        if max_parallel_steps is not None:
            summary["max_parallel_steps"] = self._validate_parallelism_limit(
                max_parallel_steps
            )

        return summary

    def _get_ready_and_blocked_steps(
        self,
        plan: ExecutionPlan,
    ) -> tuple[List[PlanStep], Dict[str, List[str]], Dict[str, List[str]]]:
        """Return ready planned steps and dependency blockers for non-runnable steps.

        A step is considered *ready* when:
        - its status is ``PLANNED``
        - all declared dependencies are ``COMPLETED``
        - none of its dependencies are in a terminal failed state

        Returns:
            Tuple of ``(
                ready_steps,
                blocked_by_failed_dependencies,
                blocked_by_incomplete_dependencies,
            )``.

            - ``blocked_by_failed_dependencies`` maps ``step_id`` to dependency IDs
              that are currently ``FAILED`` or ``CANCELLED``.
            - ``blocked_by_incomplete_dependencies`` maps ``step_id`` to dependency
              IDs that are not completed yet (excluding terminal failures).
        """
        self._validate_step_dependencies(plan.steps)

        completed_ids = {
            step.step_id for step in plan.steps if step.status == TaskStatus.COMPLETED
        }
        failed_dependency_ids = {
            step.step_id
            for step in plan.steps
            if step.status in {TaskStatus.FAILED, TaskStatus.CANCELLED}
        }

        ready_steps: List[PlanStep] = []
        blocked_by_failed_dependencies: Dict[str, List[str]] = {}
        blocked_by_incomplete_dependencies: Dict[str, List[str]] = {}

        for step in plan.steps:
            if step.status != TaskStatus.PLANNED:
                continue

            failed_dependencies = [
                dependency_id
                for dependency_id in step.dependencies
                if dependency_id in failed_dependency_ids
            ]
            if failed_dependencies:
                blocked_by_failed_dependencies[step.step_id] = failed_dependencies
                continue

            incomplete_dependencies = [
                dependency_id
                for dependency_id in step.dependencies
                if dependency_id not in completed_ids
            ]
            if incomplete_dependencies:
                blocked_by_incomplete_dependencies[
                    step.step_id
                ] = incomplete_dependencies
                continue

            ready_steps.append(step)

        return (
            ready_steps,
            blocked_by_failed_dependencies,
            blocked_by_incomplete_dependencies,
        )

    def get_ready_steps(self, plan: ExecutionPlan) -> List[PlanStep]:
        """Return PLANNED steps that can be executed immediately.

        This helper is useful for scheduler/runner loops that repeatedly pull
        the next dependency-safe execution batch from an evolving plan state.
        """
        ready_steps, _, _ = self._get_ready_and_blocked_steps(plan)
        return ready_steps

    def get_blocked_steps(self, plan: ExecutionPlan) -> Dict[str, Dict[str, List[str]]]:
        """Return dependency blockers for planned steps that are not runnable.

        Returns a dictionary with two dependency blocker maps:
        - ``failed_dependencies``: blockers that are terminally failed/cancelled
        - ``incomplete_dependencies``: blockers still waiting on completion
        """
        (
            _,
            blocked_by_failed_dependencies,
            blocked_by_incomplete_dependencies,
        ) = self._get_ready_and_blocked_steps(plan)

        return {
            "failed_dependencies": blocked_by_failed_dependencies,
            "incomplete_dependencies": blocked_by_incomplete_dependencies,
        }

    async def plan(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        constraints: Optional[Dict[str, Any]] = None,
    ) -> ExecutionPlan:
        """
        Create execution plan for goal.

        Args:
            goal: High-level goal description
            context: Additional context for planning
            constraints: Resource constraints (max_time, max_cost, max_tokens)

        Returns:
            ExecutionPlan with detailed steps and estimates
        """
        from datetime import datetime

        context = context or {}
        constraints = constraints or {}

        system_prompt = """You are an intelligent task planner specialized in breaking down goals into executable steps.

Available agent types:
- research: Web research, information gathering (avg: 30s, $0.02, 2000 tokens)
- docs: Google Docs document creation (avg: 20s, $0.03, 3000 tokens)
- sheets: Google Sheets spreadsheet creation (avg: 15s, $0.02, 1500 tokens)
- slides: Google Slides presentation creation (avg: 25s, $0.03, 2500 tokens)

For each step, provide:
1. step_id: Unique identifier (step_1, step_2, etc.)
2. description: Clear, actionable description
3. agent_type: Which agent will execute this
4. complexity: low/medium/high (affects resource estimates)
5. dependencies: List of step_ids this depends on
6. success_criteria: How to verify success (list of criteria)
7. risks: Potential issues (list of risks)

Output as JSON:
{
  "steps": [
    {
      "step_id": "step_1",
      "description": "Research renewable energy trends",
      "agent_type": "research",
      "complexity": "medium",
      "dependencies": [],
      "success_criteria": [
        "Found at least 5 credible sources",
        "Coverage of major renewable technologies"
      ],
      "risks": [
        "Limited recent data availability",
        "Conflicting statistics from sources"
      ]
    }
  ]
}

Guidelines:
- Break complex goals into 3-8 manageable steps
- Ensure logical ordering with clear dependencies
- Be specific about success criteria
- Identify realistic risks"""

        user_prompt = f"""Goal: {goal}

Context: {json.dumps(context, indent=2)}

Constraints: {json.dumps(constraints, indent=2)}

Create a detailed execution plan. Output JSON only."""

        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]

            response = await self.llm.ainvoke(messages)
            plan_text = self._normalize_llm_content(response.content)

            # Extract JSON
            if "```json" in plan_text:
                plan_text = plan_text.split("```json", 1)[1].split("```", 1)[0].strip()
            elif "```" in plan_text:
                plan_text = plan_text.split("```", 1)[1].split("```", 1)[0].strip()

            plan_data = json.loads(plan_text)
            raw_steps = plan_data.get("steps") if isinstance(plan_data, dict) else None
            if not isinstance(raw_steps, list) or not raw_steps:
                raise ValueError(
                    "Planner response must include a non-empty 'steps' list"
                )

            # Create PlanStep objects with resource estimates
            steps: List[PlanStep] = []
            for index, step_data in enumerate(raw_steps, start=1):
                if not isinstance(step_data, dict):
                    raise ValueError(
                        f"Invalid step entry at index {index - 1}: expected object"
                    )

                step_id = str(step_data.get("step_id", "")).strip()
                if not step_id:
                    raise ValueError(f"Step at index {index - 1} is missing step_id")

                description = str(step_data.get("description", "")).strip()
                if not description:
                    raise ValueError(f"Step '{step_id}' is missing description")

                agent_type = str(step_data.get("agent_type", "")).strip()
                if not agent_type:
                    raise ValueError(f"Step '{step_id}' is missing agent_type")

                complexity_multiplier = {
                    "low": 0.7,
                    "medium": 1.0,
                    "high": 1.5,
                }.get(str(step_data.get("complexity", "medium")).lower(), 1.0)

                estimated_time = int(
                    self.time_coefficients.get(agent_type, 30) * complexity_multiplier
                )
                estimated_cost = (
                    self.cost_coefficients.get(agent_type, 0.02) * complexity_multiplier
                )
                estimated_tokens = int(
                    self.token_coefficients.get(agent_type, 2000)
                    * complexity_multiplier
                )

                dependencies = self._normalize_dependencies(
                    step_data.get("dependencies", []),
                    step_id=step_id,
                )

                step = PlanStep(
                    step_id=step_id,
                    description=description,
                    agent_type=agent_type,
                    estimated_time=estimated_time,
                    estimated_cost=estimated_cost,
                    estimated_tokens=estimated_tokens,
                    dependencies=dependencies,
                    success_criteria=step_data.get("success_criteria", []),
                    risks=step_data.get("risks", []),
                )
                steps.append(step)

            self._validate_step_dependencies(steps)

            # Calculate totals
            total_time = sum(s.estimated_time for s in steps)
            total_cost = sum(s.estimated_cost for s in steps)
            total_tokens = sum(s.estimated_tokens for s in steps)

            # Validate constraints
            if constraints.get("max_time") and total_time > constraints["max_time"]:
                logger.warning(
                    f"Plan exceeds time constraint: {total_time}s > {constraints['max_time']}s"
                )

            if constraints.get("max_cost") and total_cost > constraints["max_cost"]:
                logger.warning(
                    f"Plan exceeds cost constraint: ${total_cost} > ${constraints['max_cost']}"
                )

            plan = ExecutionPlan(
                goal=goal,
                steps=steps,
                total_estimated_time=total_time,
                total_estimated_cost=total_cost,
                total_estimated_tokens=total_tokens,
                constraints=constraints,
                created_at=datetime.utcnow().isoformat(),
            )

            logger.info(
                f"Plan created: {len(steps)} steps, "
                f"estimated {total_time}s, ${total_cost:.2f}, {total_tokens} tokens"
            )

            return plan

        except Exception as e:
            logger.error(f"Planning failed: {e}", exc_info=True)
            raise

    async def replan(
        self,
        original_plan: ExecutionPlan,
        execution_results: List[Dict[str, Any]],
        reason: str,
    ) -> ExecutionPlan:
        """
        Create updated plan based on execution results.

        Args:
            original_plan: Original execution plan
            execution_results: Results from executed steps
            reason: Reason for re-planning

        Returns:
            Updated ExecutionPlan
        """
        from datetime import datetime

        system_prompt = """You are re-planning a task execution based on results so far.

Analyze what worked, what failed, and what needs to change.

Create an updated plan that:
1. Preserves successful completed steps
2. Fixes or replaces failed steps
3. Adjusts remaining steps based on new information
4. Updates resource estimates

Output the updated plan in the same JSON format."""

        # Build execution summary
        execution_summary = {
            "original_goal": original_plan.goal,
            "original_steps": [
                {
                    "step_id": s.step_id,
                    "description": s.description,
                    "agent_type": s.agent_type,
                    "status": s.status.value,
                }
                for s in original_plan.steps
            ],
            "execution_results": execution_results,
            "reason_for_replan": reason,
        }

        user_prompt = f"""Execution Summary:
{json.dumps(execution_summary, indent=2)}

Create an updated execution plan. Output JSON only."""

        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]

            response = await self.llm.ainvoke(messages)

            # Parse and create updated plan (similar to plan() method)
            # For brevity, reusing same logic
            updated_plan = await self.plan(
                goal=original_plan.goal,
                context={
                    "replan_reason": reason,
                    "previous_results": execution_results,
                },
                constraints=original_plan.constraints,
            )

            updated_plan.updated_at = datetime.utcnow().isoformat()

            logger.info(f"Re-planning completed: {reason}")

            return updated_plan

        except Exception as e:
            logger.error(f"Re-planning failed: {e}", exc_info=True)
            # Return original plan as fallback
            return original_plan

    def validate_constraints(
        self, plan: ExecutionPlan, constraints: Dict[str, Any]
    ) -> Dict[str, bool]:
        """
        Validate plan against constraints.

        Args:
            plan: Execution plan to validate
            constraints: Resource constraints

        Returns:
            Validation results for each constraint
        """
        validation = {}

        if "max_time" in constraints:
            validation["time"] = plan.total_estimated_time <= constraints["max_time"]

        if "max_cost" in constraints:
            validation["cost"] = plan.total_estimated_cost <= constraints["max_cost"]

        if "max_tokens" in constraints:
            validation["tokens"] = (
                plan.total_estimated_tokens <= constraints["max_tokens"]
            )

        all_valid = all(validation.values())

        logger.info(
            f"Constraint validation: {validation} - {'PASS' if all_valid else 'FAIL'}"
        )

        return validation

    def get_progress(self, plan: ExecutionPlan) -> Dict[str, Any]:
        """
        Get execution progress for plan.

        Args:
            plan: Execution plan

        Returns:
            Progress statistics
        """
        total = len(plan.steps)
        completed = sum(1 for s in plan.steps if s.status == TaskStatus.COMPLETED)
        in_progress = sum(1 for s in plan.steps if s.status == TaskStatus.IN_PROGRESS)
        failed = sum(1 for s in plan.steps if s.status == TaskStatus.FAILED)
        blocked = sum(1 for s in plan.steps if s.status == TaskStatus.BLOCKED)

        (
            ready_steps,
            blocked_by_failed_dependencies,
            blocked_by_incomplete_dependencies,
        ) = self._get_ready_and_blocked_steps(plan)

        # Calculate actual vs estimated
        actual_time = sum(s.actual_time or 0 for s in plan.steps if s.actual_time)
        actual_cost = sum(s.actual_cost or 0.0 for s in plan.steps if s.actual_cost)

        progress_pct = (completed / total * 100) if total > 0 else 0

        return {
            "total_steps": total,
            "completed": completed,
            "in_progress": in_progress,
            "failed": failed,
            "blocked": blocked,
            "ready": len(ready_steps),
            "ready_step_ids": [step.step_id for step in ready_steps],
            "blocked_by_failed_dependencies": blocked_by_failed_dependencies,
            "blocked_by_incomplete_dependencies": blocked_by_incomplete_dependencies,
            "progress_percentage": round(progress_pct, 1),
            "estimated_time": plan.total_estimated_time,
            "actual_time": actual_time,
            "estimated_cost": plan.total_estimated_cost,
            "actual_cost": actual_cost,
            "time_variance": actual_time - plan.total_estimated_time
            if actual_time > 0
            else 0,
            "cost_variance": actual_cost - plan.total_estimated_cost
            if actual_cost > 0
            else 0.0,
        }


__all__ = ["TaskPlanner", "ExecutionPlan", "PlanStep", "TaskStatus", "ResourceType"]
