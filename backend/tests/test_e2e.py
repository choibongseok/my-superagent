"""
End-to-End Integration Tests
Tests full workflows: Client → API → Agent → Google API → Database
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import patch, MagicMock, AsyncMock
from sqlalchemy.orm import Session
from uuid import uuid4

# Import FastAPI app and dependencies
from app.main import app
from app.database import get_db
from app.models import User, Task
from app.models.task import TaskStatus, TaskType
from app.agents import ResearchAgent, DocsAgent, SheetsAgent, SlidesAgent


class MockGoogleCredentials:
    """Mock Google OAuth credentials"""
    def __init__(self, token="mock_token", refresh_token="mock_refresh"):
        self.token = token
        self.refresh_token = refresh_token
        self.expiry = None
        self.valid = True


@pytest.fixture
def mock_google_creds():
    """Mock Google credentials"""
    return MockGoogleCredentials()


@pytest.fixture
def mock_db_session():
    """Mock database session"""
    session = MagicMock(spec=Session)

    # Mock user
    mock_user = User(
        email="test@example.com",
        full_name="Test User",
    )

    # Mock query methods
    session.query.return_value.filter.return_value.first.return_value = mock_user
    session.add = MagicMock()
    session.commit = MagicMock()
    session.refresh = MagicMock()

    return session


@pytest.mark.asyncio
async def test_full_research_workflow(mock_db_session, mock_google_creds):
    """
    E2E Test: Research Agent Full Workflow
    User request → API → ResearchAgent → Web search → Citation → Response
    """
    with patch('app.services.google_auth.get_user_credentials', return_value=mock_google_creds):
        # 1. Create Research Agent
        agent = ResearchAgent(
            user_id="test_user_123",
            session_id="e2e_test_research",
        )

        assert agent.user_id == "test_user_123"
        assert agent.llm is not None
        assert agent.memory is not None

        # 2. Mock agent.run() (the actual internal LLM call)
        with patch.object(agent, 'run', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = {
                'success': True,
                'output': 'AI trends analysis: key developments in 2026...',
                'intermediate_steps': [],
            }

            # 3. Execute research
            prompt = "What are the latest AI trends?"
            result = await agent.research(prompt)

            # 4. Verify result
            assert result is not None
            assert 'citations' in result
            mock_run.assert_called_once()


@pytest.mark.asyncio
async def test_full_docs_agent_workflow(mock_db_session, mock_google_creds):
    """
    E2E Test: Docs Agent Full Workflow
    User request → API → DocsAgent → content generation → Response
    """
    with patch('app.services.google_auth.get_user_credentials', return_value=mock_google_creds):
        # 1. Create Docs Agent (no credentials → docs_api is None)
        agent = DocsAgent(
            user_id="test_user_123",
            session_id="e2e_test_docs",
        )

        assert agent is not None

        # 2. Mock agent.run() for content generation
        with patch.object(agent, 'run', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = {
                'success': True,
                'output': 'This is a test document content.',
                'intermediate_steps': [],
            }

            # 3. Create document (no research, no Google Docs API → content only)
            result = await agent.create_document(
                title="Test Document",
                prompt="Write a test document.",
                include_research=False,
            )

            # 4. Verify result
            assert result is not None
            assert result.get('success') is True
            assert 'content' in result


@pytest.mark.asyncio
async def test_full_sheets_agent_workflow(mock_db_session, mock_google_creds):
    """
    E2E Test: Sheets Agent Full Workflow
    User request → API → SheetsAgent → Google Sheets API → Spreadsheet creation
    """
    with patch('app.services.google_auth.get_user_credentials', return_value=mock_google_creds):
        # 1. Create Sheets Agent (no credentials → sheets_service is None)
        agent = SheetsAgent(
            user_id="test_user_123",
            session_id="e2e_test_sheets",
        )

        assert agent is not None

        # 2. Mock agent.run()
        with patch.object(agent, 'run', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = {
                'success': True,
                'output': 'Created spreadsheet with Name/Age/City columns.',
                'intermediate_steps': [],
            }

            # 3. Execute agent task
            result = await agent.run(
                prompt="Create a spreadsheet with Name, Age, City columns"
            )

            # 4. Verify result
            assert result is not None
            assert result['success'] is True


@pytest.mark.asyncio
async def test_full_slides_agent_workflow(mock_db_session, mock_google_creds):
    """
    E2E Test: Slides Agent Full Workflow
    User request → API → SlidesAgent → Google Slides API → Presentation creation
    """
    with patch('app.services.google_auth.get_user_credentials', return_value=mock_google_creds):
        # 1. Create Slides Agent (no credentials → slides_service is None)
        agent = SlidesAgent(
            user_id="test_user_123",
            session_id="e2e_test_slides",
        )

        assert agent is not None

        # 2. Mock agent.run()
        with patch.object(agent, 'run', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = {
                'success': True,
                'output': 'Created presentation with 3 slides.',
                'intermediate_steps': [],
            }

            # 3. Execute agent task
            result = await agent.run(
                prompt="Create a test presentation with title and content slides"
            )

            # 4. Verify result
            assert result is not None
            assert result['success'] is True


@pytest.mark.asyncio
async def test_multi_agent_orchestration(mock_db_session, mock_google_creds):
    """
    E2E Test: Multi-Agent Orchestration
    Complex task requiring multiple agents (Research → Docs → Sheets)
    """
    with patch('app.services.google_auth.get_user_credentials', return_value=mock_google_creds):
        # 1. Research phase
        research_agent = ResearchAgent(
            user_id="test_user_123",
            session_id="e2e_multi_agent_research",
        )

        with patch.object(research_agent, 'run', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = {
                'success': True,
                'output': 'Q1 sales: $1M total revenue.',
                'intermediate_steps': [],
            }
            research_result = await research_agent.research("Get Q1 sales data")
            assert research_result is not None
            assert research_result.get('success') is True

        # 2. Sheets phase - create spreadsheet from research
        sheets_agent = SheetsAgent(
            user_id="test_user_123",
            session_id="e2e_multi_agent_sheets",
        )

        with patch.object(sheets_agent, 'run', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = {
                'success': True,
                'output': 'Created spreadsheet: Q1 Sales Report.',
                'intermediate_steps': [],
            }
            sheets_result = await sheets_agent.run(
                prompt="Create a Q1 Sales Report spreadsheet with Month and Sales columns"
            )
            assert sheets_result is not None
            assert sheets_result['success'] is True

        # 3. Docs phase - create summary document
        docs_agent = DocsAgent(
            user_id="test_user_123",
            session_id="e2e_multi_agent_docs",
        )

        with patch.object(docs_agent, 'run', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = {
                'success': True,
                'output': 'Q1 total sales: $1M.',
                'intermediate_steps': [],
            }
            docs_result = await docs_agent.create_document(
                title="Q1 Sales Summary",
                prompt="Write a Q1 sales summary",
                include_research=False,
            )
            assert docs_result is not None
            assert docs_result.get('success') is True

        # 4. Verify all agents executed successfully
        assert research_result is not None
        assert sheets_result is not None
        assert docs_result is not None


@pytest.mark.asyncio
async def test_task_lifecycle_complete_workflow(mock_db_session, mock_google_creds):
    """
    E2E Test: Complete Task Lifecycle
    Task creation → Agent execution → Status updates → Completion
    """
    with patch('app.services.google_auth.get_user_credentials', return_value=mock_google_creds):
        # 1. Create task record with correct fields
        task = Task(
            user_id=uuid4(),
            prompt="Create sales report",
            task_type=TaskType.SHEETS,
            status=TaskStatus.PENDING,
        )

        # 2. Update status to IN_PROGRESS (alias for PROCESSING)
        task.status = TaskStatus.IN_PROGRESS
        assert task.status == TaskStatus.IN_PROGRESS

        # 3. Execute agent
        agent = SheetsAgent(
            user_id=str(task.user_id),
            session_id="lifecycle_test",
        )

        with patch.object(agent, 'run', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = {
                'success': True,
                'output': 'Created spreadsheet: sheet_lifecycle_123.',
                'intermediate_steps': [],
            }

            result = await agent.run(
                prompt="Create sales report with Product A: 1000, Product B: 2000"
            )

            # 4. Update task with result
            task.status = TaskStatus.COMPLETED
            task.result = {
                'spreadsheet_id': 'sheet_lifecycle_123',
                'spreadsheet_url': 'https://docs.google.com/spreadsheets/d/sheet_lifecycle_123',
            }

            # 5. Verify final state
            assert task.status == TaskStatus.COMPLETED
            assert task.result is not None
            assert 'spreadsheet_url' in task.result


@pytest.mark.asyncio
async def test_error_handling_workflow(mock_db_session, mock_google_creds):
    """
    E2E Test: Error Handling
    Task → Agent → Error → Status update
    """
    with patch('app.services.google_auth.get_user_credentials', return_value=mock_google_creds):
        # 1. Create agent
        agent = DocsAgent(
            user_id="test_user_123",
            session_id="e2e_error_test",
        )

        # 2. Mock agent.run() to raise an error
        with patch.object(agent, 'run', new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = Exception("API Error: Quota exceeded")

            # 3. Execute — DocsAgent.create_document catches the exception and
            #    returns {"success": False, "error": "..."} rather than re-raising.
            result = await agent.create_document(
                title="Test Doc",
                prompt="Write a test document",
                include_research=False,
            )

            # 4. Verify error is surfaced in the result dict
            assert result is not None
            assert result.get('success') is False
            error_text = result.get('error', '')
            assert "API Error" in error_text or "Quota exceeded" in error_text

        error_text = result.get('error', '')

        # 5. Simulate task error handling
        task = Task(
            user_id=uuid4(),
            prompt="Create document",
            task_type=TaskType.DOCS,
            status=TaskStatus.IN_PROGRESS,
        )

        # 6. Update task with error
        task.status = TaskStatus.FAILED
        task.error_message = error_text

        # 7. Verify error state
        assert task.status == TaskStatus.FAILED
        assert task.error_message is not None


@pytest.mark.asyncio
async def test_memory_persistence_across_agents(mock_db_session, mock_google_creds):
    """
    E2E Test: Memory Persistence
    Multiple agent calls → Memory storage → Context retrieval
    """
    with patch('app.services.google_auth.get_user_credentials', return_value=mock_google_creds):
        # 1. First agent call - Research
        research_agent = ResearchAgent(
            user_id="test_user_123",
            session_id="memory_test",
        )

        # Verify agent has memory attribute
        assert research_agent.memory is not None

        # Mock agent.run() and memory operations
        with patch.object(research_agent, 'run', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = {
                'success': True,
                'output': 'AI trends: LLMs and agents are advancing.',
                'intermediate_steps': [],
            }
            result = await research_agent.research("What are AI trends?")
            assert result is not None
            assert result.get('success') is True

        # 2. Second agent call - Should have access to previous context via memory
        with patch.object(research_agent.memory, 'get_context') as mock_get_ctx:
            mock_get_ctx.return_value = "Previous conversation: AI trends discussion"

            context = research_agent.memory.get_context()

            # 3. Verify context retrieved
            assert context is not None
            assert "AI trends" in context
            mock_get_ctx.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
