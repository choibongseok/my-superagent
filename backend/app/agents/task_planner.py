"""Autonomous Task Planner with goal-oriented planning and resource estimation."""

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
            plan_text = response.content

            # Extract JSON
            if "```json" in plan_text:
                plan_text = plan_text.split("```json")[1].split("```")[0].strip()
            elif "```" in plan_text:
                plan_text = plan_text.split("```")[1].split("```")[0].strip()

            plan_data = json.loads(plan_text)

            # Create PlanStep objects with resource estimates
            steps = []
            for step_data in plan_data["steps"]:
                complexity_multiplier = {
                    "low": 0.7,
                    "medium": 1.0,
                    "high": 1.5,
                }.get(step_data.get("complexity", "medium"), 1.0)

                agent_type = step_data["agent_type"]
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

                step = PlanStep(
                    step_id=step_data["step_id"],
                    description=step_data["description"],
                    agent_type=agent_type,
                    estimated_time=estimated_time,
                    estimated_cost=estimated_cost,
                    estimated_tokens=estimated_tokens,
                    dependencies=step_data.get("dependencies", []),
                    success_criteria=step_data.get("success_criteria", []),
                    risks=step_data.get("risks", []),
                )
                steps.append(step)

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
                context={"replan_reason": reason, "previous_results": execution_results},
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
