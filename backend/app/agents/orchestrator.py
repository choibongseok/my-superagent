"""Multi-Agent Orchestrator for coordinating multiple agents."""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

from app.agents.research_agent import ResearchAgent
from app.agents.docs_agent import DocsAgent
from app.core.config import settings

logger = logging.getLogger(__name__)


class AgentTask:
    """Represents a task for a specific agent."""

    def __init__(
        self,
        task_id: str,
        agent_type: str,
        description: str,
        dependencies: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize agent task.

        Args:
            task_id: Unique task identifier
            agent_type: Type of agent (research, docs, sheets, slides)
            description: Task description
            dependencies: List of task IDs this task depends on
            metadata: Additional task metadata
        """
        self.task_id = task_id
        self.agent_type = agent_type
        self.description = description
        self.dependencies = dependencies or []
        self.metadata = metadata or {}
        self.status = "pending"  # pending, running, completed, failed
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None


class MultiAgentOrchestrator:
    """
    Orchestrate multiple agents for complex tasks.

    Features:
        - Task decomposition into agent-specific subtasks
        - Dependency management and parallel execution
        - Result aggregation and synthesis
        - Error handling and recovery
    """

    def __init__(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        google_credentials: Optional[Any] = None,
        llm_provider: str = "openai",
        model: str = "gpt-4-turbo-preview",
    ):
        """
        Initialize multi-agent orchestrator.

        Args:
            user_id: User identifier
            session_id: Session identifier
            google_credentials: Google OAuth credentials for Docs/Sheets/Slides
            llm_provider: LLM provider (openai or anthropic)
            model: Model name
        """
        self.user_id = user_id
        self.session_id = session_id or f"orchestrator_{user_id}_{uuid4().hex[:8]}"
        self.google_credentials = google_credentials

        # Initialize planning LLM (used for task decomposition and synthesis)
        if llm_provider == "openai":
            self.llm = ChatOpenAI(
                model=model,
                temperature=0.3,  # Lower temperature for planning
                max_tokens=4000,
            )
        else:
            self.llm = ChatAnthropic(
                model=model,
                temperature=0.3,
                max_tokens=4000,
            )

        # Agent cache (lazy initialization)
        self._agents: Dict[str, Any] = {}

        logger.info(
            f"MultiAgentOrchestrator initialized: user={user_id}, session={self.session_id}"
        )

    def _get_agent(self, agent_type: str) -> Any:
        """
        Get or create agent instance.

        Args:
            agent_type: Type of agent (research, docs, sheets, slides)

        Returns:
            Agent instance
        """
        if agent_type in self._agents:
            return self._agents[agent_type]

        # Create agent based on type
        if agent_type == "research":
            agent = ResearchAgent(
                user_id=self.user_id,
                session_id=self.session_id,
            )
        elif agent_type == "docs":
            agent = DocsAgent(
                user_id=self.user_id,
                session_id=self.session_id,
                credentials=self.google_credentials,
            )
        # TODO: Add sheets and slides agents
        else:
            raise ValueError(f"Unknown agent type: {agent_type}")

        # Cache agent
        self._agents[agent_type] = agent
        logger.debug(f"Created {agent_type} agent for session {self.session_id}")

        return agent

    async def decompose_task(self, task_description: str) -> List[AgentTask]:
        """
        Decompose complex task into agent-specific subtasks.

        Args:
            task_description: Complex task description

        Returns:
            List of AgentTask objects
        """
        system_prompt = """You are an intelligent task planner for a multi-agent system.

Available agents:
- research: Web research, information gathering, fact checking
- docs: Google Docs document generation
- sheets: Google Sheets spreadsheet generation (coming soon)
- slides: Google Slides presentation generation (coming soon)

Your job is to break down complex tasks into subtasks for specific agents.

For each subtask, identify:
1. The agent type that should handle it
2. A clear, specific task description
3. Dependencies on other subtasks (by task_id)

Output as JSON:
{
  "tasks": [
    {
      "task_id": "task_1",
      "agent_type": "research",
      "description": "Research renewable energy statistics",
      "dependencies": []
    },
    {
      "task_id": "task_2",
      "agent_type": "docs",
      "description": "Create comprehensive report on renewable energy",
      "dependencies": ["task_1"]
    }
  ]
}

Guidelines:
- Keep tasks focused and specific
- Ensure proper dependency ordering
- Minimize unnecessary dependencies
- Consider parallel execution when possible"""

        user_prompt = f"""Task: {task_description}

Break this down into subtasks for the available agents. Output JSON only."""

        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]

            response = await self.llm.ainvoke(messages)
            plan_text = response.content

            # Extract JSON from response
            if "```json" in plan_text:
                plan_text = plan_text.split("```json")[1].split("```")[0].strip()
            elif "```" in plan_text:
                plan_text = plan_text.split("```")[1].split("```")[0].strip()

            plan = json.loads(plan_text)

            # Create AgentTask objects
            tasks = [
                AgentTask(
                    task_id=t["task_id"],
                    agent_type=t["agent_type"],
                    description=t["description"],
                    dependencies=t.get("dependencies", []),
                )
                for t in plan["tasks"]
            ]

            logger.info(
                f"Task decomposition: {len(tasks)} subtasks created for '{task_description}'"
            )

            return tasks

        except Exception as e:
            logger.error(f"Task decomposition failed: {e}", exc_info=True)
            # Fallback: treat as single research task
            return [
                AgentTask(
                    task_id="task_1",
                    agent_type="research",
                    description=task_description,
                    dependencies=[],
                )
            ]

    async def execute_task(self, task: AgentTask) -> Dict[str, Any]:
        """
        Execute a single agent task.

        Args:
            task: AgentTask to execute

        Returns:
            Task result dictionary
        """
        try:
            task.status = "running"
            logger.info(f"Executing task {task.task_id}: {task.description}")

            # Get appropriate agent
            agent = self._get_agent(task.agent_type)

            # Execute task
            result = await agent.run(
                prompt=task.description,
                context=task.metadata,
            )

            if result.get("success"):
                task.status = "completed"
                task.result = result
                logger.info(f"Task {task.task_id} completed successfully")
            else:
                task.status = "failed"
                task.error = result.get("error", "Unknown error")
                logger.error(f"Task {task.task_id} failed: {task.error}")

            return result

        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            logger.error(f"Task {task.task_id} execution error: {e}", exc_info=True)

            return {
                "success": False,
                "error": str(e),
            }

    async def execute_tasks(self, tasks: List[AgentTask]) -> List[AgentTask]:
        """
        Execute tasks with dependency management and parallelization.

        Args:
            tasks: List of AgentTask objects

        Returns:
            List of completed tasks with results
        """
        task_map = {task.task_id: task for task in tasks}
        completed = set()

        while len(completed) < len(tasks):
            # Find tasks ready to execute (dependencies met)
            ready_tasks = [
                task
                for task in tasks
                if task.status == "pending"
                and all(dep in completed for dep in task.dependencies)
            ]

            if not ready_tasks:
                # Check for failed tasks blocking progress
                failed = [task for task in tasks if task.status == "failed"]
                if failed:
                    logger.warning(
                        f"{len(failed)} tasks failed, blocking {len(tasks) - len(completed)} remaining tasks"
                    )
                    break

                # No ready tasks but not all completed - circular dependency?
                logger.error("No ready tasks but execution incomplete - possible circular dependency")
                break

            # Execute ready tasks in parallel
            logger.info(f"Executing {len(ready_tasks)} tasks in parallel")
            await asyncio.gather(*[self.execute_task(task) for task in ready_tasks])

            # Mark completed tasks
            for task in ready_tasks:
                if task.status == "completed":
                    completed.add(task.task_id)

        logger.info(
            f"Task execution complete: {len(completed)}/{len(tasks)} successful"
        )

        return tasks

    async def synthesize_results(
        self, tasks: List[AgentTask], original_request: str
    ) -> str:
        """
        Synthesize results from multiple tasks into coherent response.

        Args:
            tasks: List of completed tasks
            original_request: Original user request

        Returns:
            Synthesized final response
        """
        system_prompt = """You are an intelligent result synthesizer.

Your job is to combine results from multiple specialized agents into a coherent, comprehensive response.

Guidelines:
- Provide a unified, well-structured response
- Preserve important details from each agent
- Ensure logical flow and coherence
- Cite sources when applicable
- Note any failures or limitations"""

        # Build task results summary
        results_summary = []
        for task in tasks:
            if task.status == "completed" and task.result:
                results_summary.append(
                    f"Task: {task.description}\n"
                    f"Agent: {task.agent_type}\n"
                    f"Result: {task.result.get('output', 'N/A')}\n"
                )
            elif task.status == "failed":
                results_summary.append(
                    f"Task: {task.description}\n"
                    f"Agent: {task.agent_type}\n"
                    f"Status: FAILED ({task.error})\n"
                )

        user_prompt = f"""Original Request: {original_request}

Task Results:
{'---'.join(results_summary)}

Synthesize these results into a comprehensive response to the original request."""

        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]

            response = await self.llm.ainvoke(messages)
            synthesis = response.content

            logger.info("Results synthesized successfully")

            return synthesis

        except Exception as e:
            logger.error(f"Result synthesis failed: {e}", exc_info=True)

            # Fallback: simple concatenation
            return "\n\n".join(
                task.result.get("output", "")
                for task in tasks
                if task.status == "completed" and task.result
            )

    async def execute_complex_task(self, task_description: str) -> Dict[str, Any]:
        """
        Execute complex task using multi-agent collaboration.

        Workflow:
        1. Decompose task into agent-specific subtasks
        2. Execute subtasks with dependency management
        3. Synthesize results into coherent response

        Args:
            task_description: Complex task description

        Returns:
            Result dictionary with synthesis, tasks, and metadata
        """
        try:
            logger.info(f"Starting complex task execution: {task_description}")

            # Step 1: Decompose task
            tasks = await self.decompose_task(task_description)

            # Step 2: Execute tasks
            completed_tasks = await self.execute_tasks(tasks)

            # Step 3: Synthesize results
            synthesis = await self.synthesize_results(completed_tasks, task_description)

            # Calculate statistics
            successful = sum(1 for t in completed_tasks if t.status == "completed")
            failed = sum(1 for t in completed_tasks if t.status == "failed")

            result = {
                "success": successful > 0,
                "synthesis": synthesis,
                "tasks": [
                    {
                        "task_id": t.task_id,
                        "agent_type": t.agent_type,
                        "description": t.description,
                        "status": t.status,
                        "result": t.result,
                        "error": t.error,
                    }
                    for t in completed_tasks
                ],
                "statistics": {
                    "total_tasks": len(completed_tasks),
                    "successful": successful,
                    "failed": failed,
                },
            }

            logger.info(
                f"Complex task completed: {successful}/{len(completed_tasks)} subtasks successful"
            )

            return result

        except Exception as e:
            logger.error(f"Complex task execution failed: {e}", exc_info=True)

            return {
                "success": False,
                "error": str(e),
                "synthesis": None,
                "tasks": [],
            }


__all__ = ["MultiAgentOrchestrator", "AgentTask"]
