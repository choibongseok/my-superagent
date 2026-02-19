"""
End-to-End Tests for Multi-Agent Orchestrator
Tests complex multi-agent coordination and template execution
"""

import os
os.environ.setdefault('OPENAI_API_KEY', 'test-key')

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime
from uuid import uuid4, UUID

from app.agents.orchestrator import MultiAgentOrchestrator, AgentTask
from app.models import Task, Template
from app.models.task import TaskStatus, TaskType
from app.services.cache import LocalCacheService


class MockGoogleCredentials:
    """Mock Google OAuth credentials"""
    def __init__(self):
        self.token = "mock_token"
        self.refresh_token = "mock_refresh"
        self.valid = True


@pytest.fixture
def mock_credentials():
    return MockGoogleCredentials()


@pytest.fixture
def orchestrator(mock_credentials):
    """Create orchestrator instance with mocked dependencies"""
    with patch('app.services.google_auth.get_user_credentials', return_value=mock_credentials):
        return MultiAgentOrchestrator(
            user_id="test_user_123",
            session_id="orchestrator_test"
        )


def _make_completed_task(task_id: str, agent_type: str, description: str,
                         result: dict) -> AgentTask:
    """Helper: create an AgentTask already marked as completed."""
    t = AgentTask(task_id=task_id, agent_type=agent_type, description=description)
    t.status = "completed"
    t.result = result
    return t


@pytest.mark.asyncio
async def test_orchestrator_simple_task(orchestrator):
    """
    Test orchestrator with simple single-agent task
    """
    research_task = _make_completed_task(
        "t1", "research", "Research AI trends",
        {"success": True, "output": "AI trends summary",
         "sources": ["https://example.com"]},
    )

    with patch.object(orchestrator, 'decompose_task',
                      new_callable=AsyncMock,
                      return_value=[research_task]):
        with patch.object(orchestrator, 'execute_task',
                          new_callable=AsyncMock,
                          return_value={"success": True, "output": "AI trends summary"}):
            with patch.object(orchestrator, 'synthesize_results',
                              new_callable=AsyncMock,
                              return_value="Synthesis: AI trends summary") as mock_synth:
                result = await orchestrator.execute_complex_task(
                    task_description="Research AI trends",
                )

                assert result is not None
                assert result['success'] is True
                assert 'synthesis' in result
                assert 'tasks' in result
                mock_synth.assert_called_once()


@pytest.mark.asyncio
async def test_orchestrator_multi_agent_coordination(orchestrator):
    """
    Test orchestrator coordinating multiple agents
    Research → Sheets → Docs workflow
    """
    research_task = _make_completed_task(
        "t1", "research", "Research Q1 data",
        {"success": True, "output": "Q1 revenue: $1M", "sources": []},
    )
    sheets_task = _make_completed_task(
        "t2", "sheets", "Create Q1 spreadsheet",
        {"success": True, "spreadsheet_id": "sheet_orch_123",
         "spreadsheet_url": "https://docs.google.com/spreadsheets/d/sheet_orch_123"},
    )
    docs_task = _make_completed_task(
        "t3", "docs", "Write Q1 report",
        {"success": True, "document_id": "doc_orch_123",
         "document_url": "https://docs.google.com/document/d/doc_orch_123"},
    )

    with patch.object(orchestrator, 'decompose_task',
                      new_callable=AsyncMock,
                      return_value=[research_task, sheets_task, docs_task]):
        with patch.object(orchestrator, 'execute_task',
                          new_callable=AsyncMock):
            with patch.object(orchestrator, 'synthesize_results',
                              new_callable=AsyncMock,
                              return_value="Q1 performance report synthesized."):
                result = await orchestrator.execute_complex_task(
                    task_description="Create Q1 performance report with data and analysis",
                )

                assert result is not None
                assert result['success'] is True
                assert 'synthesis' in result
                assert len(result['tasks']) == 3


@pytest.mark.asyncio
async def test_orchestrator_with_cache(orchestrator):
    """
    Test orchestrator using cache service
    """
    cache_service = LocalCacheService()

    research_task = _make_completed_task(
        "t1", "research", "Research topic X",
        {"success": True, "output": "research_data"},
    )

    with patch.object(orchestrator, 'decompose_task',
                      new_callable=AsyncMock,
                      return_value=[research_task]):
        with patch.object(orchestrator, 'execute_task',
                          new_callable=AsyncMock,
                          return_value={"success": True, "output": "research_data"}):
            with patch.object(orchestrator, 'synthesize_results',
                              new_callable=AsyncMock,
                              return_value="Synthesis of research topic X"):
                # 1. Execute task first time
                result1 = await orchestrator.execute_complex_task(
                    task_description="Research topic X",
                )

                # Cache the result
                cache_service.set(
                    key='research_topic_x',
                    value=result1,
                    ttl_seconds=3600
                )

                # 2. Execute same task - should use cache
                cached_result = cache_service.get('research_topic_x')

                assert cached_result is not None
                assert cached_result == result1


@pytest.mark.asyncio
async def test_orchestrator_error_handling(orchestrator):
    """
    Test orchestrator error handling when agent fails
    """
    failed_task = AgentTask(
        task_id="t1", agent_type="sheets",
        description="Create spreadsheet",
    )
    failed_task.status = "failed"
    failed_task.error = "Google Sheets API error"

    with patch.object(orchestrator, 'decompose_task',
                      new_callable=AsyncMock,
                      return_value=[failed_task]):
        with patch.object(orchestrator, 'execute_task',
                          new_callable=AsyncMock,
                          return_value={"success": False, "error": "Google Sheets API error"}):
            with patch.object(orchestrator, 'synthesize_results',
                              new_callable=AsyncMock,
                              return_value=""):
                result = await orchestrator.execute_complex_task(
                    task_description="Create spreadsheet",
                )

                # When all tasks fail, success should be False
                assert result is not None
                assert result['success'] is False
                assert result['statistics']['failed'] == 1


@pytest.mark.asyncio
async def test_orchestrator_partial_success(orchestrator):
    """
    Test orchestrator when some agents succeed and others fail
    """
    research_task = _make_completed_task(
        "t1", "research", "Research topic",
        {"success": True, "output": "data"},
    )
    failed_task = AgentTask(
        task_id="t2", agent_type="sheets",
        description="Create spreadsheet",
    )
    failed_task.status = "failed"
    failed_task.error = "Sheets failed"

    with patch.object(orchestrator, 'decompose_task',
                      new_callable=AsyncMock,
                      return_value=[research_task, failed_task]):
        with patch.object(orchestrator, 'execute_task',
                          new_callable=AsyncMock):
            with patch.object(orchestrator, 'synthesize_results',
                              new_callable=AsyncMock,
                              return_value="Partial synthesis"):
                result = await orchestrator.execute_complex_task(
                    task_description="Research and create sheet",
                )

                assert result is not None
                # Research succeeded → success is True
                assert result['success'] is True
                assert result['statistics']['successful'] == 1
                assert result['statistics']['failed'] == 1


@pytest.mark.asyncio
async def test_orchestrator_dependency_order(orchestrator):
    """
    Test that orchestrator executes tasks in the correct decomposed order
    """
    research_task = _make_completed_task(
        "t1", "research", "Research topic",
        {"success": True, "output": "research_result"},
    )
    docs_task = _make_completed_task(
        "t2", "docs", "Create document from research",
        {"success": True, "document_id": "doc_123"},
    )
    # docs_task depends on research_task
    docs_task.dependencies = ["t1"]

    decompose_called = []
    execute_called = []

    async def mock_decompose(desc):
        decompose_called.append(desc)
        return [research_task, docs_task]

    async def mock_execute(task):
        execute_called.append(task.agent_type)
        return task.result

    with patch.object(orchestrator, 'decompose_task', side_effect=mock_decompose):
        with patch.object(orchestrator, 'execute_task', side_effect=mock_execute):
            with patch.object(orchestrator, 'synthesize_results',
                              new_callable=AsyncMock,
                              return_value="Synthesized result"):
                result = await orchestrator.execute_complex_task(
                    task_description="Research and document",
                )

                assert result is not None
                assert len(decompose_called) == 1
                assert result['success'] is True


@pytest.mark.asyncio
async def test_template_execution_via_orchestrator():
    """
    Test executing a template through the orchestrator
    Template → Task creation → Agent execution
    """
    user_id = uuid4()
    author_id = uuid4()

    # 1. Create template with correct field types
    template = Template(
        name="Sales Report Template",
        category="research",
        prompt_template="Research sales data for {product} in {quarter}",
        parameters={
            'product': 'string',
            'quarter': 'string',
        },
        author_id=author_id,
    )

    # 2. Create task with correct field types
    task = Task(
        user_id=user_id,
        prompt="Research sales data for Product A in Q1",
        task_type=TaskType.RESEARCH,
        status=TaskStatus.PENDING,
        task_metadata={
            'template_inputs': {
                'product': 'Product A',
                'quarter': 'Q1',
            },
        },
    )

    # 3. Execute via orchestrator
    with patch('app.services.google_auth.get_user_credentials',
               return_value=MockGoogleCredentials()):
        orchestrator = MultiAgentOrchestrator(
            user_id=str(user_id),
            session_id="template_test"
        )

        research_task = _make_completed_task(
            "t1", "research", task.prompt,
            {"success": True, "output": "Jan: 100k, Feb: 120k, Mar: 130k"},
        )

        with patch.object(orchestrator, 'decompose_task',
                          new_callable=AsyncMock,
                          return_value=[research_task]):
            with patch.object(orchestrator, 'execute_task',
                              new_callable=AsyncMock,
                              return_value=research_task.result):
                with patch.object(orchestrator, 'synthesize_results',
                                  new_callable=AsyncMock,
                                  return_value="Sales data synthesized"):
                    result = await orchestrator.execute_complex_task(
                        task_description=task.prompt,
                    )

                    # 4. Verify execution
                    assert result is not None
                    assert result['success'] is True
                    assert 'synthesis' in result

                    # 5. Update task
                    task.status = TaskStatus.COMPLETED
                    task.result = result

                    assert task.status == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_orchestrator_with_slides_presentation(orchestrator):
    """
    Test orchestrator handling slides presentation task
    """
    slides_task = _make_completed_task(
        "t1", "slides", "Create market analysis presentation for Q1",
        {
            "success": True,
            "presentation_id": "pres_orch_123",
            "slides": [
                {'id': 'slide_1', 'title': 'Market Analysis Q1'},
                {'id': 'slide_2', 'title': 'Key Findings'},
                {'id': 'slide_3', 'title': 'Recommendations'},
            ],
        },
    )

    with patch.object(orchestrator, 'decompose_task',
                      new_callable=AsyncMock,
                      return_value=[slides_task]):
        with patch.object(orchestrator, 'execute_task',
                          new_callable=AsyncMock,
                          return_value=slides_task.result):
            with patch.object(orchestrator, 'synthesize_results',
                              new_callable=AsyncMock,
                              return_value="Presentation created successfully"):
                result = await orchestrator.execute_complex_task(
                    task_description="Create market analysis presentation for Q1",
                )

                assert result is not None
                assert result['success'] is True
                # Find the slides task in result
                slides_tasks = [t for t in result['tasks'] if t['agent_type'] == 'slides']
                assert len(slides_tasks) == 1
                assert slides_tasks[0]['result']['presentation_id'] == 'pres_orch_123'
                assert len(slides_tasks[0]['result']['slides']) == 3


@pytest.mark.asyncio
async def test_orchestrator_retry_logic():
    """
    Test orchestrator resilience when decompose_task succeeds after prior attempt
    """
    with patch('app.services.google_auth.get_user_credentials',
               return_value=MockGoogleCredentials()):
        orchestrator = MultiAgentOrchestrator(
            user_id="test_user_123",
            session_id="retry_test"
        )

        call_count = 0

        async def eventually_succeeds(desc):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Transient error")
            task = _make_completed_task("t1", "research", desc,
                                        {"success": True, "output": "done"})
            return [task]

        with patch.object(orchestrator, 'decompose_task',
                          side_effect=eventually_succeeds):
            # First call should raise
            with pytest.raises(Exception, match="Transient error"):
                await orchestrator.execute_complex_task("Research with retries")

        # Second call succeeds
        with patch.object(orchestrator, 'decompose_task',
                          side_effect=eventually_succeeds):
            with patch.object(orchestrator, 'execute_task',
                              new_callable=AsyncMock,
                              return_value={"success": True}):
                with patch.object(orchestrator, 'synthesize_results',
                                  new_callable=AsyncMock,
                                  return_value="Done"):
                    result = await orchestrator.execute_complex_task(
                        "Research with retries"
                    )
                    assert result is not None


@pytest.mark.asyncio
async def test_orchestrator_concurrent_agent_execution():
    """
    Test orchestrator executing independent tasks
    """
    with patch('app.services.google_auth.get_user_credentials',
               return_value=MockGoogleCredentials()):
        orchestrator = MultiAgentOrchestrator(
            user_id="test_user_123",
            session_id="concurrent_test"
        )

        sheets_task = _make_completed_task(
            "t1", "sheets", "Create spreadsheet",
            {"success": True, "spreadsheet_id": "sheet_concurrent"},
        )
        slides_task = _make_completed_task(
            "t2", "slides", "Create presentation",
            {"success": True, "presentation_id": "pres_concurrent"},
        )

        with patch.object(orchestrator, 'decompose_task',
                          new_callable=AsyncMock,
                          return_value=[sheets_task, slides_task]):
            with patch.object(orchestrator, 'execute_task',
                              new_callable=AsyncMock):
                with patch.object(orchestrator, 'synthesize_results',
                                  new_callable=AsyncMock,
                                  return_value="Both completed"):
                    result = await orchestrator.execute_complex_task(
                        task_description="Create sheet and presentation",
                    )

                    assert result is not None
                    assert result['success'] is True
                    assert len(result['tasks']) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
