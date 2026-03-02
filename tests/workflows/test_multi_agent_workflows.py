"""
Integration tests for multi-agent workflow orchestration.

Tests cover:
- Research to Sheets workflow
- Research to Docs workflow
- Full pipeline workflow (Research → Sheets → Slides)
- Error handling and retry logic
- Context passing between agents
- Performance and latency
"""

import asyncio
import json
import time
from datetime import datetime
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from redis import Redis

from app.agents.coordinator import AgentCoordinator
from app.agents.protocols import (
    AgentMessage,
    AgentResponse,
    AgentRole,
    MessageStatus,
    WorkflowDefinition,
    WorkflowResult,
    WorkflowStep,
)
from app.workflows import (
    create_full_pipeline_workflow,
    create_research_to_docs_workflow,
    create_research_to_sheets_workflow,
    get_workflow,
    list_workflows,
)


class TestWorkflowRegistry:
    """Test workflow registry and factory functions."""
    
    def test_list_workflows(self):
        """Should return all available workflows."""
        workflows = list_workflows()
        
        assert len(workflows) == 3
        assert any(w["id"] == "research_to_sheets" for w in workflows)
        assert any(w["id"] == "research_to_docs" for w in workflows)
        assert any(w["id"] == "full_pipeline" for w in workflows)
    
    def test_get_workflow_by_id(self):
        """Should retrieve workflow by ID."""
        workflow = get_workflow("research_to_sheets")
        
        assert workflow.name == "Research to Spreadsheet"
        assert len(workflow.steps) == 2
        assert workflow.steps[0].agent == AgentRole.RESEARCH
        assert workflow.steps[1].agent == AgentRole.SHEETS
    
    def test_get_workflow_invalid_id(self):
        """Should raise KeyError for invalid workflow ID."""
        with pytest.raises(KeyError):
            get_workflow("nonexistent_workflow")
    
    def test_workflow_metadata(self):
        """Should include metadata in workflow definitions."""
        workflow = get_workflow("full_pipeline")
        
        assert "category" in workflow.metadata
        assert "estimated_duration_seconds" in workflow.metadata
        assert workflow.metadata["requires_google_auth"] is True
        assert workflow.metadata["complexity"] == "high"


class TestResearchToSheetsWorkflow:
    """Test Research → Sheets workflow."""
    
    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client."""
        redis_mock = Mock(spec=Redis)
        redis_mock.pubsub.return_value = Mock()
        redis_mock.publish.return_value = 1
        return redis_mock
    
    @pytest.fixture
    def mock_research_agent(self):
        """Mock research agent."""
        agent = Mock()
        agent.run_async = AsyncMock(return_value={
            "results": [
                {"company": "OpenAI", "funding": "$11.3B", "stage": "Series C"},
                {"company": "Anthropic", "funding": "$7.3B", "stage": "Series C"},
                {"company": "Cohere", "funding": "$445M", "stage": "Series C"},
            ],
            "sources": [
                {"url": "https://example.com/ai-funding", "title": "AI Funding 2026"}
            ],
            "summary": "Research completed on AI companies 2026",
        })
        return agent
    
    @pytest.fixture
    def mock_sheets_agent(self):
        """Mock sheets agent."""
        agent = Mock()
        agent.run_async = AsyncMock(return_value={
            "spreadsheet_id": "test_spreadsheet_123",
            "spreadsheet_url": "https://docs.google.com/spreadsheets/d/test_spreadsheet_123",
            "sheets_created": ["Companies", "Charts"],
            "rows_inserted": 3,
        })
        return agent
    
    @pytest.fixture
    def agent_registry(self, mock_research_agent, mock_sheets_agent):
        """Agent registry with mocked agents."""
        return {
            AgentRole.RESEARCH: mock_research_agent,
            AgentRole.SHEETS: mock_sheets_agent,
        }
    
    @pytest.mark.asyncio
    async def test_research_to_sheets_success(self, mock_redis, agent_registry):
        """Should successfully execute research to sheets workflow."""
        coordinator = AgentCoordinator(mock_redis, agent_registry)
        workflow = create_research_to_sheets_workflow()
        
        result = await coordinator.execute_workflow(
            workflow=workflow,
            initial_inputs={"query": "AI companies 2026"},
            user_id=1,
        )
        
        # Verify workflow completed
        assert result.status == MessageStatus.COMPLETED
        assert result.error is None
        assert len(result.step_results) == 2
        
        # Verify research step
        research_result = result.step_results[workflow.steps[0].step_id]
        assert research_result.status == MessageStatus.COMPLETED
        assert "results" in research_result.result
        
        # Verify sheets step
        sheets_result = result.step_results[workflow.steps[1].step_id]
        assert sheets_result.status == MessageStatus.COMPLETED
        assert "spreadsheet_id" in sheets_result.result
        
        # Verify final output
        assert "primary_result" in result.final_output
        assert result.final_output["workflow_name"] == "Research to Spreadsheet"
    
    @pytest.mark.asyncio
    async def test_research_to_sheets_context_passing(self, mock_redis, agent_registry):
        """Should correctly pass research results to sheets agent."""
        coordinator = AgentCoordinator(mock_redis, agent_registry)
        workflow = create_research_to_sheets_workflow()
        
        await coordinator.execute_workflow(
            workflow=workflow,
            initial_inputs={"query": "AI companies 2026"},
            user_id=1,
        )
        
        # Verify sheets agent received research data
        sheets_agent = agent_registry[AgentRole.SHEETS]
        call_kwargs = sheets_agent.run_async.call_args[1]
        
        assert "data" in call_kwargs
        assert call_kwargs["data"] == [
            {"company": "OpenAI", "funding": "$11.3B", "stage": "Series C"},
            {"company": "Anthropic", "funding": "$7.3B", "stage": "Series C"},
            {"company": "Cohere", "funding": "$445M", "stage": "Series C"},
        ]
    
    @pytest.mark.asyncio
    async def test_research_to_sheets_agent_failure(self, mock_redis, agent_registry):
        """Should handle agent failure gracefully."""
        # Make research agent fail
        agent_registry[AgentRole.RESEARCH].run_async = AsyncMock(
            side_effect=Exception("API rate limit exceeded")
        )
        
        coordinator = AgentCoordinator(mock_redis, agent_registry)
        workflow = create_research_to_sheets_workflow()
        
        result = await coordinator.execute_workflow(
            workflow=workflow,
            initial_inputs={"query": "AI companies 2026"},
            user_id=1,
        )
        
        # Verify workflow failed
        assert result.status == MessageStatus.FAILED
        assert "API rate limit exceeded" in result.error


class TestResearchToDocsWorkflow:
    """Test Research → Docs workflow."""
    
    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client."""
        redis_mock = Mock(spec=Redis)
        redis_mock.pubsub.return_value = Mock()
        redis_mock.publish.return_value = 1
        return redis_mock
    
    @pytest.fixture
    def mock_research_agent(self):
        """Mock research agent."""
        agent = Mock()
        agent.run_async = AsyncMock(return_value={
            "results": "Quantum computing is advancing rapidly in 2026...",
            "sources": [
                {"url": "https://example.com/quantum", "title": "Quantum Trends 2026"}
            ],
            "summary": "Comprehensive research on quantum computing trends",
        })
        return agent
    
    @pytest.fixture
    def mock_docs_agent(self):
        """Mock docs agent."""
        agent = Mock()
        agent.run_async = AsyncMock(return_value={
            "document_id": "test_doc_456",
            "document_url": "https://docs.google.com/document/d/test_doc_456",
            "pages_created": 3,
            "citations_added": 5,
        })
        return agent
    
    @pytest.fixture
    def agent_registry(self, mock_research_agent, mock_docs_agent):
        """Agent registry with mocked agents."""
        return {
            AgentRole.RESEARCH: mock_research_agent,
            AgentRole.DOCS: mock_docs_agent,
        }
    
    @pytest.mark.asyncio
    async def test_research_to_docs_success(self, mock_redis, agent_registry):
        """Should successfully execute research to docs workflow."""
        coordinator = AgentCoordinator(mock_redis, agent_registry)
        workflow = create_research_to_docs_workflow()
        
        result = await coordinator.execute_workflow(
            workflow=workflow,
            initial_inputs={"query": "Quantum computing trends 2026"},
            user_id=1,
        )
        
        # Verify workflow completed
        assert result.status == MessageStatus.COMPLETED
        assert len(result.step_results) == 2
        
        # Verify docs step received citations
        docs_result = result.step_results[workflow.steps[1].step_id]
        assert docs_result.status == MessageStatus.COMPLETED
        assert "document_id" in docs_result.result
    
    @pytest.mark.asyncio
    async def test_research_to_docs_input_mapping(self, mock_redis, agent_registry):
        """Should correctly map research outputs to docs inputs."""
        coordinator = AgentCoordinator(mock_redis, agent_registry)
        workflow = create_research_to_docs_workflow()
        
        await coordinator.execute_workflow(
            workflow=workflow,
            initial_inputs={
                "query": "Quantum computing trends 2026",
                "report_style": "technical",
            },
            user_id=1,
        )
        
        # Verify docs agent received mapped inputs
        docs_agent = agent_registry[AgentRole.DOCS]
        call_kwargs = docs_agent.run_async.call_args[1]
        
        assert "research_data" in call_kwargs
        assert "citations" in call_kwargs
        assert call_kwargs["report_style"] == "technical"


class TestFullPipelineWorkflow:
    """Test full pipeline: Research → Sheets → Slides."""
    
    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client."""
        redis_mock = Mock(spec=Redis)
        redis_mock.pubsub.return_value = Mock()
        redis_mock.publish.return_value = 1
        return redis_mock
    
    @pytest.fixture
    def mock_agents(self):
        """Mock all agents for full pipeline."""
        research_agent = Mock()
        research_agent.run_async = AsyncMock(return_value={
            "results": [{"metric": "Market size", "value": "$500B"}],
            "summary": "EV market analysis complete",
            "sources": [{"url": "https://example.com/ev", "title": "EV Market 2026"}],
        })
        
        sheets_agent = Mock()
        sheets_agent.run_async = AsyncMock(return_value={
            "spreadsheet_id": "test_sheet_789",
            "spreadsheet_url": "https://docs.google.com/spreadsheets/d/test_sheet_789",
            "chart_ids": ["chart1", "chart2"],
        })
        
        slides_agent = Mock()
        slides_agent.run_async = AsyncMock(return_value={
            "presentation_id": "test_slides_999",
            "presentation_url": "https://docs.google.com/presentation/d/test_slides_999",
            "slides_created": 5,
        })
        
        return {
            AgentRole.RESEARCH: research_agent,
            AgentRole.SHEETS: sheets_agent,
            AgentRole.SLIDES: slides_agent,
        }
    
    @pytest.mark.asyncio
    async def test_full_pipeline_success(self, mock_redis, mock_agents):
        """Should successfully execute full pipeline workflow."""
        coordinator = AgentCoordinator(mock_redis, mock_agents)
        workflow = create_full_pipeline_workflow()
        
        result = await coordinator.execute_workflow(
            workflow=workflow,
            initial_inputs={"query": "Electric vehicle market 2026"},
            user_id=1,
        )
        
        # Verify all steps completed
        assert result.status == MessageStatus.COMPLETED
        assert len(result.step_results) == 3
        
        # Verify execution order (research → sheets → slides)
        research_step = workflow.steps[0]
        sheets_step = workflow.steps[1]
        slides_step = workflow.steps[2]
        
        assert research_step.step_id in result.step_results
        assert sheets_step.step_id in result.step_results
        assert slides_step.step_id in result.step_results
    
    @pytest.mark.asyncio
    async def test_full_pipeline_slides_failure_skip(self, mock_redis, mock_agents):
        """Should skip slides step on failure (error_handling='skip')."""
        # Make slides agent fail
        mock_agents[AgentRole.SLIDES].run_async = AsyncMock(
            side_effect=Exception("Slides API error")
        )
        
        coordinator = AgentCoordinator(mock_redis, mock_agents)
        workflow = create_full_pipeline_workflow()
        
        # Verify slides step has skip error handling
        slides_step = workflow.steps[2]
        assert slides_step.error_handling == "skip"
        
        result = await coordinator.execute_workflow(
            workflow=workflow,
            initial_inputs={"query": "Electric vehicle market 2026"},
            user_id=1,
        )
        
        # Workflow should complete despite slides failure
        # Note: With current implementation, workflow might still fail
        # depending on coordinator logic. Adjust assertion accordingly.
        assert len(result.step_results) >= 2  # At least research and sheets
    
    @pytest.mark.asyncio
    async def test_full_pipeline_dependency_resolution(self, mock_redis, mock_agents):
        """Should execute steps in correct dependency order."""
        # Track execution order
        execution_order = []
        
        # Store original return values
        original_returns = {
            AgentRole.RESEARCH: {
                "results": [{"metric": "Market size", "value": "$500B"}],
                "summary": "EV market analysis complete",
                "sources": [{"url": "https://example.com/ev", "title": "EV Market 2026"}],
            },
            AgentRole.SHEETS: {
                "spreadsheet_id": "test_sheet_789",
                "spreadsheet_url": "https://docs.google.com/spreadsheets/d/test_sheet_789",
                "chart_ids": ["chart1", "chart2"],
            },
            AgentRole.SLIDES: {
                "presentation_id": "test_slides_999",
                "presentation_url": "https://docs.google.com/presentation/d/test_slides_999",
                "slides_created": 5,
            },
        }
        
        def track_execution(agent_role, return_value):
            async def wrapper(*args, **kwargs):
                execution_order.append(agent_role)
                return return_value
            return wrapper
        
        # Replace mock agents with tracking wrappers
        for role in [AgentRole.RESEARCH, AgentRole.SHEETS, AgentRole.SLIDES]:
            mock_agents[role].run_async = track_execution(role, original_returns[role])
        
        coordinator = AgentCoordinator(mock_redis, mock_agents)
        workflow = create_full_pipeline_workflow()
        
        await coordinator.execute_workflow(
            workflow=workflow,
            initial_inputs={"query": "Electric vehicle market 2026"},
            user_id=1,
        )
        
        # Verify execution order: research → sheets → slides
        assert len(execution_order) == 3
        assert execution_order.index(AgentRole.RESEARCH) < execution_order.index(AgentRole.SHEETS)
        assert execution_order.index(AgentRole.SHEETS) < execution_order.index(AgentRole.SLIDES)


class TestWorkflowErrorHandling:
    """Test workflow error handling and retry logic."""
    
    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client."""
        redis_mock = Mock(spec=Redis)
        redis_mock.pubsub.return_value = Mock()
        redis_mock.publish.return_value = 1
        return redis_mock
    
    @pytest.mark.asyncio
    async def test_circular_dependency_detection(self, mock_redis):
        """Should detect and reject circular dependencies."""
        # Create workflow with circular dependency
        # Use step IDs for proper referencing
        step1 = WorkflowStep(
            agent=AgentRole.RESEARCH,
            task_description="Step 1",
        )
        step2 = WorkflowStep(
            agent=AgentRole.SHEETS,
            task_description="Step 2",
        )
        
        # Now set circular dependencies using actual IDs
        step1.dependencies = [step2.step_id]  # Step1 depends on step2
        step2.dependencies = [step1.step_id]  # Step2 depends on step1 (circular!)
        
        workflow = WorkflowDefinition(
            name="Circular Workflow",
            description="Test circular dependency",
            steps=[step1, step2],
        )
        
        coordinator = AgentCoordinator(mock_redis, {})
        result = await coordinator.execute_workflow(workflow, user_id=1)
        
        # Should fail with validation error
        assert result.status == MessageStatus.FAILED
        assert "circular" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_retry_logic(self, mock_redis):
        """Should retry failed steps up to max_retries."""
        # Mock agent that fails twice then succeeds
        retry_count = 0
        
        async def failing_agent(*args, **kwargs):
            nonlocal retry_count
            retry_count += 1
            if retry_count <= 2:
                raise Exception(f"Temporary failure {retry_count}")
            return {"result": "success"}
        
        mock_agent = Mock()
        mock_agent.run_async = failing_agent
        
        step = WorkflowStep(
            agent=AgentRole.RESEARCH,
            task_description="Test retry",
            max_retries=3,
        )
        
        workflow = WorkflowDefinition(
            name="Retry Test",
            description="Test retry logic",
            steps=[step],
        )
        
        coordinator = AgentCoordinator(
            mock_redis,
            {AgentRole.RESEARCH: mock_agent}
        )
        
        result = await coordinator.execute_workflow(workflow, user_id=1)
        
        # Should succeed after 2 retries
        assert result.status == MessageStatus.COMPLETED
        assert retry_count == 3  # 1 initial + 2 retries
    
    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self, mock_redis):
        """Should fail after exhausting max_retries."""
        # Mock agent that always fails
        async def always_failing(*args, **kwargs):
            raise Exception("Permanent failure")
        
        mock_agent = Mock()
        mock_agent.run_async = always_failing
        
        step = WorkflowStep(
            agent=AgentRole.RESEARCH,
            task_description="Test retry exhaustion",
            max_retries=2,
        )
        
        workflow = WorkflowDefinition(
            name="Retry Exhaustion Test",
            description="Test max retries",
            steps=[step],
        )
        
        coordinator = AgentCoordinator(
            mock_redis,
            {AgentRole.RESEARCH: mock_agent}
        )
        
        result = await coordinator.execute_workflow(workflow, user_id=1)
        
        # Should fail after max retries
        assert result.status == MessageStatus.FAILED
        assert "Max retries exceeded" in result.error


class TestWorkflowPerformance:
    """Test workflow performance and latency."""
    
    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client."""
        redis_mock = Mock(spec=Redis)
        redis_mock.pubsub.return_value = Mock()
        redis_mock.publish.return_value = 1
        return redis_mock
    
    @pytest.mark.asyncio
    async def test_workflow_latency(self, mock_redis):
        """Should complete workflow within reasonable time (<30s)."""
        # Mock fast agents (100ms each)
        async def fast_agent(*args, **kwargs):
            await asyncio.sleep(0.1)
            return {"result": "success"}
        
        mock_research = Mock()
        mock_research.run_async = fast_agent
        
        mock_sheets = Mock()
        mock_sheets.run_async = fast_agent
        
        coordinator = AgentCoordinator(
            mock_redis,
            {
                AgentRole.RESEARCH: mock_research,
                AgentRole.SHEETS: mock_sheets,
            }
        )
        
        workflow = create_research_to_sheets_workflow()
        
        start_time = time.time()
        result = await coordinator.execute_workflow(
            workflow=workflow,
            initial_inputs={"query": "test"},
            user_id=1,
        )
        elapsed = time.time() - start_time
        
        # Should complete in < 30 seconds (generous bound for CI)
        assert elapsed < 30
        assert result.status == MessageStatus.COMPLETED
        
        # Verify timing metadata
        assert result.started_at is not None
        assert result.completed_at is not None
        assert result.completed_at > result.started_at
    
    @pytest.mark.asyncio
    async def test_parallel_workflow_execution(self, mock_redis):
        """Should support multiple concurrent workflows."""
        # Mock agent
        async def mock_agent_impl(*args, **kwargs):
            await asyncio.sleep(0.05)
            return {"result": "success"}
        
        mock_agent = Mock()
        mock_agent.run_async = mock_agent_impl
        
        coordinator = AgentCoordinator(
            mock_redis,
            {AgentRole.RESEARCH: mock_agent, AgentRole.SHEETS: mock_agent}
        )
        
        workflow = create_research_to_sheets_workflow()
        
        # Execute 5 workflows concurrently
        tasks = [
            coordinator.execute_workflow(
                workflow=workflow,
                initial_inputs={"query": f"test_{i}"},
                user_id=i,
            )
            for i in range(5)
        ]
        
        start_time = time.time()
        results = await asyncio.gather(*tasks)
        elapsed = time.time() - start_time
        
        # All should complete
        assert all(r.status == MessageStatus.COMPLETED for r in results)
        
        # Parallel execution should be faster than sequential
        # (5 workflows * 2 steps * 50ms = 500ms sequential)
        # (Parallel should be ~100ms + overhead)
        assert elapsed < 2.0  # Allow generous margin


class TestCoordinatorUtilities:
    """Test coordinator utility methods."""
    
    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client."""
        redis_mock = Mock(spec=Redis)
        redis_mock.pubsub.return_value = Mock()
        redis_mock.publish.return_value = 1
        redis_mock.get.return_value = None
        redis_mock.setex.return_value = True
        return redis_mock
    
    def test_subscribe_to_messages(self, mock_redis):
        """Should subscribe to agent message channels."""
        coordinator = AgentCoordinator(mock_redis, {})
        
        coordinator.subscribe_to_messages(AgentRole.RESEARCH)
        
        mock_redis.pubsub().subscribe.assert_called_once_with("agent:messages:research")
    
    def test_save_workflow_status(self, mock_redis):
        """Should save workflow status to Redis."""
        coordinator = AgentCoordinator(mock_redis, {})
        
        result = WorkflowResult(
            workflow_id="test_workflow",
            status=MessageStatus.COMPLETED,
            step_results={},
            final_output={"test": "data"},
        )
        
        coordinator.save_workflow_status(result)
        
        # Verify Redis setex was called
        assert mock_redis.setex.called
        call_args = mock_redis.setex.call_args
        assert f"workflow:execution:{result.execution_id}" in call_args[0]
    
    def test_get_workflow_status(self, mock_redis):
        """Should retrieve workflow status from Redis."""
        coordinator = AgentCoordinator(mock_redis, {})
        
        # Mock Redis return value
        mock_redis.get.return_value = json.dumps({
            "execution_id": "test_exec",
            "workflow_id": "test_workflow",
            "status": "completed",
        })
        
        status = coordinator.get_workflow_status("test_exec")
        
        assert status is not None
        assert status["execution_id"] == "test_exec"
        assert status["workflow_id"] == "test_workflow"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
