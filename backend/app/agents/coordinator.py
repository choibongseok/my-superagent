"""
Agent Coordinator Service for multi-agent workflow orchestration.

This module provides the AgentCoordinator class which manages the execution
of multi-agent workflows, handling message passing, dependency resolution,
and error handling.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from redis import Redis

from backend.app.agents.protocols import (
    AgentMessage,
    AgentResponse,
    AgentRole,
    MessageStatus,
    WorkflowDefinition,
    WorkflowResult,
    WorkflowStep,
)
from backend.app.core.config import settings

logger = logging.getLogger(__name__)


class AgentCoordinator:
    """
    Orchestrates multi-agent workflows with dependency resolution and error handling.
    
    Example:
        >>> coordinator = AgentCoordinator(redis_client, agent_registry)
        >>> workflow = WorkflowDefinition(...)
        >>> result = await coordinator.execute_workflow(workflow, {"topic": "AI"})
    """
    
    def __init__(self, redis_client: Redis, agent_registry: Dict[AgentRole, Any]):
        """
        Initialize coordinator.
        
        Args:
            redis_client: Redis client for message passing
            agent_registry: Mapping of AgentRole to agent instances
        """
        self.redis = redis_client
        self.agent_registry = agent_registry
        self.pubsub = redis_client.pubsub()
        
    async def execute_workflow(
        self,
        workflow: WorkflowDefinition,
        initial_inputs: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
    ) -> WorkflowResult:
        """
        Execute a multi-agent workflow.
        
        Args:
            workflow: Workflow definition
            initial_inputs: Override workflow.initial_inputs
            user_id: User executing the workflow
            
        Returns:
            WorkflowResult with status and outputs from all steps
            
        Raises:
            ValueError: If workflow has circular dependencies
            RuntimeError: If workflow execution fails
        """
        logger.info(f"Starting workflow: {workflow.name} ({workflow.workflow_id})")
        
        result = WorkflowResult(
            workflow_id=workflow.workflow_id,
            status=MessageStatus.PROCESSING,
            step_results={},
            final_output={},
            started_at=datetime.utcnow(),
        )
        
        # Use provided inputs or workflow defaults
        inputs = initial_inputs or workflow.initial_inputs
        
        # Validate workflow (check for cycles)
        if not self._validate_workflow(workflow):
            result.status = MessageStatus.FAILED
            result.error = "Workflow validation failed: circular dependencies detected"
            result.completed_at = datetime.utcnow()
            return result
        
        # Execute steps in dependency order
        execution_order = self._resolve_execution_order(workflow.steps)
        step_outputs: Dict[str, Dict[str, Any]] = {}
        
        try:
            for step in execution_order:
                logger.info(f"Executing step: {step.step_id} (agent={step.agent.value})")
                
                # Prepare step inputs from dependencies
                step_inputs = self._prepare_step_inputs(step, step_outputs, inputs)
                
                # Execute step with retry logic
                response = await self._execute_step_with_retry(
                    step=step,
                    inputs=step_inputs,
                    user_id=user_id,
                )
                
                # Store result
                result.step_results[step.step_id] = response
                step_outputs[step.step_id] = response.result
                
                # Handle step failure
                if response.status == MessageStatus.FAILED:
                    if step.error_handling == "stop":
                        result.status = MessageStatus.FAILED
                        result.error = f"Step {step.step_id} failed: {response.error}"
                        result.completed_at = datetime.utcnow()
                        return result
                    elif step.error_handling == "skip":
                        logger.warning(f"Step {step.step_id} failed, skipping...")
                        continue
            
            # Workflow completed successfully
            result.status = MessageStatus.COMPLETED
            result.final_output = self._compile_final_output(workflow, step_outputs)
            result.completed_at = datetime.utcnow()
            
            logger.info(f"Workflow completed: {workflow.workflow_id}")
            return result
            
        except Exception as e:
            logger.error(f"Workflow execution failed: {e}", exc_info=True)
            result.status = MessageStatus.FAILED
            result.error = str(e)
            result.completed_at = datetime.utcnow()
            return result
    
    async def _execute_step_with_retry(
        self,
        step: WorkflowStep,
        inputs: Dict[str, Any],
        user_id: Optional[int],
    ) -> AgentResponse:
        """Execute a step with retry logic."""
        last_error = None
        
        for attempt in range(step.max_retries + 1):
            try:
                if attempt > 0:
                    logger.info(f"Retry attempt {attempt} for step {step.step_id}")
                
                response = await self._execute_step(step, inputs, user_id)
                
                if response.status == MessageStatus.COMPLETED:
                    return response
                
                last_error = response.error
                
            except Exception as e:
                logger.error(f"Step execution error (attempt {attempt}): {e}")
                last_error = str(e)
        
        # All retries exhausted
        return AgentResponse(
            message_id=step.step_id,
            status=MessageStatus.FAILED,
            result={},
            agent=step.agent,
            error=f"Max retries exceeded. Last error: {last_error}",
        )
    
    async def _execute_step(
        self,
        step: WorkflowStep,
        inputs: Dict[str, Any],
        user_id: Optional[int],
    ) -> AgentResponse:
        """Execute a single workflow step."""
        # Get agent instance
        agent = self.agent_registry.get(step.agent)
        if not agent:
            return AgentResponse(
                message_id=step.step_id,
                status=MessageStatus.FAILED,
                result={},
                agent=step.agent,
                error=f"Agent not found: {step.agent.value}",
            )
        
        # Create message
        message = AgentMessage(
            sender=AgentRole.COORDINATOR,
            receiver=step.agent,
            payload=inputs,
            task_description=step.task_description,
        )
        
        # Publish message to Redis (for observability)
        self._publish_message(message)
        
        try:
            # Execute agent task
            result = await self._invoke_agent(
                agent=agent,
                message=message,
                user_id=user_id,
            )
            
            response = AgentResponse(
                message_id=message.message_id,
                status=MessageStatus.COMPLETED,
                result=result,
                agent=step.agent,
            )
            
        except Exception as e:
            logger.error(f"Agent invocation failed: {e}", exc_info=True)
            response = AgentResponse(
                message_id=message.message_id,
                status=MessageStatus.FAILED,
                result={},
                agent=step.agent,
                error=str(e),
            )
        
        # Publish response
        self._publish_response(response)
        
        return response
    
    async def _invoke_agent(
        self,
        agent: Any,
        message: AgentMessage,
        user_id: Optional[int],
    ) -> Dict[str, Any]:
        """
        Invoke an agent with a message.
        
        This is where we adapt the message to the agent's expected interface.
        Each agent has different methods (execute, run_async, etc.)
        """
        # TODO: Implement agent-specific invocation logic
        # For now, assume all agents have a run_async method
        
        if message.receiver == AgentRole.RESEARCH:
            # Research agent expects: query, user_id
            return await agent.run_async(
                query=message.task_description,
                user_id=user_id,
                **message.payload,
            )
        
        elif message.receiver == AgentRole.SHEETS:
            # Sheets agent expects: spreadsheet_id, data, user_id
            return await agent.run_async(
                instruction=message.task_description,
                user_id=user_id,
                **message.payload,
            )
        
        elif message.receiver == AgentRole.DOCS:
            # Docs agent expects: document_id, content, user_id
            return await agent.run_async(
                instruction=message.task_description,
                user_id=user_id,
                **message.payload,
            )
        
        elif message.receiver == AgentRole.SLIDES:
            # Slides agent expects: presentation_id, content, user_id
            return await agent.run_async(
                instruction=message.task_description,
                user_id=user_id,
                **message.payload,
            )
        
        else:
            raise NotImplementedError(f"Agent {message.receiver.value} not supported")
    
    def _prepare_step_inputs(
        self,
        step: WorkflowStep,
        step_outputs: Dict[str, Dict[str, Any]],
        initial_inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Prepare inputs for a step from dependencies and initial inputs.
        
        Args:
            step: Current step
            step_outputs: Outputs from completed steps
            initial_inputs: Workflow initial inputs
            
        Returns:
            Merged inputs for this step
        """
        inputs = dict(initial_inputs)
        
        # Apply input mapping from dependencies
        for dep_step_id in step.dependencies:
            if dep_step_id in step_outputs:
                dep_output = step_outputs[dep_step_id]
                
                # Use input_mapping if specified
                if step.input_mapping:
                    for target_key, source_key in step.input_mapping.items():
                        if source_key in dep_output:
                            inputs[target_key] = dep_output[source_key]
                else:
                    # Default: merge all outputs
                    inputs.update(dep_output)
        
        return inputs
    
    def _validate_workflow(self, workflow: WorkflowDefinition) -> bool:
        """Check for circular dependencies using DFS."""
        graph: Dict[str, List[str]] = {step.step_id: step.dependencies for step in workflow.steps}
        
        visited = set()
        rec_stack = set()
        
        def has_cycle(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if has_cycle(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            
            rec_stack.remove(node)
            return False
        
        for step in workflow.steps:
            if step.step_id not in visited:
                if has_cycle(step.step_id):
                    logger.error(f"Circular dependency detected in workflow {workflow.workflow_id}")
                    return False
        
        return True
    
    def _resolve_execution_order(self, steps: List[WorkflowStep]) -> List[WorkflowStep]:
        """
        Topological sort to determine execution order.
        
        Returns steps in dependency order (no step before its dependencies).
        """
        # Build graph
        graph: Dict[str, WorkflowStep] = {step.step_id: step for step in steps}
        in_degree: Dict[str, int] = {step.step_id: len(step.dependencies) for step in steps}
        
        # Find steps with no dependencies
        queue = [step for step in steps if len(step.dependencies) == 0]
        result: List[WorkflowStep] = []
        
        while queue:
            current = queue.pop(0)
            result.append(current)
            
            # Reduce in-degree for dependent steps
            for step in steps:
                if current.step_id in step.dependencies:
                    in_degree[step.step_id] -= 1
                    if in_degree[step.step_id] == 0:
                        queue.append(step)
        
        return result
    
    def _compile_final_output(
        self,
        workflow: WorkflowDefinition,
        step_outputs: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Compile final workflow output from all step outputs.
        
        Default: return output from last step + summary of all steps.
        """
        # Get last step (assuming topological order)
        last_step = workflow.steps[-1] if workflow.steps else None
        
        final_output = {
            "workflow_id": workflow.workflow_id,
            "workflow_name": workflow.name,
            "steps_completed": len(step_outputs),
            "all_outputs": step_outputs,
        }
        
        if last_step and last_step.step_id in step_outputs:
            final_output["primary_result"] = step_outputs[last_step.step_id]
        
        return final_output
    
    def _publish_message(self, message: AgentMessage):
        """Publish message to Redis for observability."""
        try:
            channel = f"agent:messages:{message.receiver.value}"
            self.redis.publish(channel, json.dumps(message.to_dict()))
        except Exception as e:
            logger.warning(f"Failed to publish message: {e}")
    
    def _publish_response(self, response: AgentResponse):
        """Publish response to Redis for observability."""
        try:
            channel = f"agent:responses:{response.agent.value}"
            self.redis.publish(channel, json.dumps(response.to_dict()))
        except Exception as e:
            logger.warning(f"Failed to publish response: {e}")
    
    def subscribe_to_messages(self, agent_role: AgentRole) -> None:
        """Subscribe to messages for a specific agent (for monitoring)."""
        channel = f"agent:messages:{agent_role.value}"
        self.pubsub.subscribe(channel)
        logger.info(f"Subscribed to {channel}")
    
    def get_workflow_status(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """
        Get real-time status of a running workflow.
        
        Args:
            execution_id: Workflow execution ID
            
        Returns:
            Status dict or None if not found
        """
        key = f"workflow:execution:{execution_id}"
        data = self.redis.get(key)
        
        if data:
            return json.loads(data)
        return None
    
    def save_workflow_status(self, result: WorkflowResult) -> None:
        """Save workflow execution status to Redis."""
        key = f"workflow:execution:{result.execution_id}"
        self.redis.setex(
            key,
            3600 * 24,  # 24 hours TTL
            json.dumps(result.to_dict()),
        )
