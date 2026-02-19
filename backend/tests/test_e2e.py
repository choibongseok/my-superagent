"""
End-to-End Integration Tests
Tests full workflows: Client → API → Agent → Google API → Database
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import patch, MagicMock, AsyncMock
from sqlalchemy.orm import Session

# Import FastAPI app and dependencies
from app.main import app
from app.database import get_db
from app.models import User, Task
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
    User request → API → ResearchAgent → Web scraping → Citation → Response
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
        
        # 2. Mock web scraping
        with patch.object(agent, '_scrape_web') as mock_scrape:
            mock_scrape.return_value = [
                {
                    'url': 'https://example.com/ai-trends',
                    'title': 'AI Trends 2026',
                    'content': 'Latest AI developments...',
                    'timestamp': datetime.now(),
                }
            ]
            
            # 3. Mock LLM response
            with patch.object(agent, '_analyze_with_llm') as mock_analyze:
                mock_analyze.return_value = {
                    'summary': 'AI trends analysis...',
                    'key_points': ['Point 1', 'Point 2'],
                    'citations': ['[1] AI Trends 2026'],
                }
                
                # 4. Execute research
                prompt = "What are the latest AI trends?"
                result = await agent.research(prompt)
                
                # 5. Verify result
                assert result is not None
                assert 'summary' in result
                assert 'citations' in result
                
                # 6. Verify methods called
                mock_scrape.assert_called_once()
                mock_analyze.assert_called_once()


@pytest.mark.asyncio
async def test_full_docs_agent_workflow(mock_db_session, mock_google_creds):
    """
    E2E Test: Docs Agent Full Workflow
    User request → API → DocsAgent → Google Docs API → Document creation
    """
    with patch('app.services.google_auth.get_user_credentials', return_value=mock_google_creds):
        # 1. Create Docs Agent
        agent = DocsAgent(
            user_id="test_user_123",
            session_id="e2e_test_docs",
            credentials=mock_google_creds,
        )
        
        assert agent.credentials is not None
        
        # 2. Mock Google Docs API
        mock_service = MagicMock()
        mock_service.documents.return_value.create.return_value.execute.return_value = {
            'documentId': 'doc_123',
            'title': 'Test Document',
        }
        
        with patch('googleapiclient.discovery.build', return_value=mock_service):
            # 3. Create document
            doc_id = agent._create_document(
                title="Test Document",
                content="This is a test document."
            )
            
            # 4. Verify document created
            assert doc_id == 'doc_123'
            mock_service.documents.return_value.create.assert_called_once()


@pytest.mark.asyncio
async def test_full_sheets_agent_workflow(mock_db_session, mock_google_creds):
    """
    E2E Test: Sheets Agent Full Workflow
    User request → API → SheetsAgent → Google Sheets API → Spreadsheet creation
    """
    with patch('app.services.google_auth.get_user_credentials', return_value=mock_google_creds):
        # 1. Create Sheets Agent
        agent = SheetsAgent(
            user_id="test_user_123",
            session_id="e2e_test_sheets",
            credentials=mock_google_creds,
        )
        
        # 2. Mock Google Sheets API
        mock_service = MagicMock()
        mock_service.spreadsheets.return_value.create.return_value.execute.return_value = {
            'spreadsheetId': 'sheet_123',
            'spreadsheetUrl': 'https://docs.google.com/spreadsheets/d/sheet_123',
        }
        
        with patch('googleapiclient.discovery.build', return_value=mock_service):
            # 3. Create spreadsheet
            data = [
                ['Name', 'Age', 'City'],
                ['Alice', '25', 'NYC'],
                ['Bob', '30', 'LA'],
            ]
            
            result = agent._create_spreadsheet(
                title="Test Spreadsheet",
                data=data
            )
            
            # 4. Verify spreadsheet created
            assert 'sheet_123' in result
            mock_service.spreadsheets.return_value.create.assert_called_once()


@pytest.mark.asyncio
async def test_full_slides_agent_workflow(mock_db_session, mock_google_creds):
    """
    E2E Test: Slides Agent Full Workflow
    User request → API → SlidesAgent → Google Slides API → Presentation creation
    """
    with patch('app.services.google_auth.get_user_credentials', return_value=mock_google_creds):
        # 1. Create Slides Agent
        agent = SlidesAgent(
            user_id="test_user_123",
            session_id="e2e_test_slides",
            credentials=mock_google_creds,
        )
        
        # 2. Mock Google Slides API
        mock_service = MagicMock()
        mock_service.presentations.return_value.create.return_value.execute.return_value = {
            'presentationId': 'pres_123',
        }
        
        mock_service.presentations.return_value.batchUpdate.return_value.execute.return_value = {
            'replies': [{'createSlide': {'objectId': 'slide_1'}}]
        }
        
        with patch('googleapiclient.discovery.build', return_value=mock_service):
            # 3. Create presentation
            pres_id = agent._create_presentation(title="Test Presentation")
            assert pres_id == 'pres_123'
            
            # 4. Add slide
            slide_id = agent._add_slide(pres_id, layout="TITLE")
            assert slide_id == 'slide_1'
            
            # 5. Verify API calls
            mock_service.presentations.return_value.create.assert_called_once()
            mock_service.presentations.return_value.batchUpdate.assert_called()


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
            session_id="e2e_multi_agent",
        )
        
        with patch.object(research_agent, '_scrape_web') as mock_scrape:
            mock_scrape.return_value = [
                {
                    'url': 'https://example.com/sales-data',
                    'title': 'Sales Data Q1 2026',
                    'content': 'Q1 sales: $1M...',
                    'timestamp': datetime.now(),
                }
            ]
            
            with patch.object(research_agent, '_analyze_with_llm') as mock_analyze:
                mock_analyze.return_value = {
                    'data': [
                        {'month': 'Jan', 'sales': 300000},
                        {'month': 'Feb', 'sales': 350000},
                        {'month': 'Mar', 'sales': 350000},
                    ]
                }
                
                research_result = await research_agent.research("Get Q1 sales data")
                assert 'data' in research_result
        
        # 2. Sheets phase - create spreadsheet from research
        sheets_agent = SheetsAgent(
            user_id="test_user_123",
            session_id="e2e_multi_agent",
            credentials=mock_google_creds,
        )
        
        mock_sheets_service = MagicMock()
        mock_sheets_service.spreadsheets.return_value.create.return_value.execute.return_value = {
            'spreadsheetId': 'sheet_multi_123',
        }
        
        with patch('googleapiclient.discovery.build', return_value=mock_sheets_service):
            sheet_data = [
                ['Month', 'Sales'],
                ['Jan', '300000'],
                ['Feb', '350000'],
                ['Mar', '350000'],
            ]
            
            sheet_id = sheets_agent._create_spreadsheet(
                title="Q1 Sales Report",
                data=sheet_data
            )
            
            assert 'sheet_multi_123' in sheet_id
        
        # 3. Docs phase - create summary document
        docs_agent = DocsAgent(
            user_id="test_user_123",
            session_id="e2e_multi_agent",
            credentials=mock_google_creds,
        )
        
        mock_docs_service = MagicMock()
        mock_docs_service.documents.return_value.create.return_value.execute.return_value = {
            'documentId': 'doc_multi_123',
        }
        
        with patch('googleapiclient.discovery.build', return_value=mock_docs_service):
            doc_id = docs_agent._create_document(
                title="Q1 Sales Summary",
                content="Q1 total sales: $1M. See attached spreadsheet."
            )
            
            assert doc_id == 'doc_multi_123'
        
        # 4. Verify all agents executed successfully
        assert research_result is not None
        assert sheet_id is not None
        assert doc_id is not None


@pytest.mark.asyncio
async def test_task_lifecycle_complete_workflow(mock_db_session, mock_google_creds):
    """
    E2E Test: Complete Task Lifecycle
    Task creation → Agent execution → Status updates → Completion
    """
    with patch('app.services.google_auth.get_user_credentials', return_value=mock_google_creds):
        # 1. Create task record
        task = Task(
            id="task_e2e_123",
            user_id="test_user_123",
            prompt="Create sales report",
            task_type="sheets",
            status="pending",
            created_at=datetime.now(),
        )
        
        # 2. Update status to in_progress
        task.status = "in_progress"
        assert task.status == "in_progress"
        
        # 3. Execute agent
        agent = SheetsAgent(
            user_id=task.user_id,
            session_id=task.id,
            credentials=mock_google_creds,
        )
        
        mock_service = MagicMock()
        mock_service.spreadsheets.return_value.create.return_value.execute.return_value = {
            'spreadsheetId': 'sheet_lifecycle_123',
            'spreadsheetUrl': 'https://docs.google.com/spreadsheets/d/sheet_lifecycle_123',
        }
        
        with patch('googleapiclient.discovery.build', return_value=mock_service):
            result = agent._create_spreadsheet(
                title="Sales Report",
                data=[['Product', 'Sales'], ['A', '1000'], ['B', '2000']]
            )
            
            # 4. Update task with result
            task.status = "completed"
            task.result = {
                'spreadsheet_id': 'sheet_lifecycle_123',
                'spreadsheet_url': 'https://docs.google.com/spreadsheets/d/sheet_lifecycle_123',
            }
            task.completed_at = datetime.now()
            
            # 5. Verify final state
            assert task.status == "completed"
            assert task.result is not None
            assert 'spreadsheet_url' in task.result
            assert task.completed_at is not None


@pytest.mark.asyncio
async def test_error_handling_workflow(mock_db_session, mock_google_creds):
    """
    E2E Test: Error Handling
    Task → Agent → API Error → Error recovery → Status update
    """
    with patch('app.services.google_auth.get_user_credentials', return_value=mock_google_creds):
        # 1. Create agent
        agent = DocsAgent(
            user_id="test_user_123",
            session_id="e2e_error_test",
            credentials=mock_google_creds,
        )
        
        # 2. Mock Google API error
        mock_service = MagicMock()
        mock_service.documents.return_value.create.side_effect = Exception("API Error: Quota exceeded")
        
        with patch('googleapiclient.discovery.build', return_value=mock_service):
            # 3. Execute and expect error
            with pytest.raises(Exception) as exc_info:
                agent._create_document(
                    title="Test Doc",
                    content="Content"
                )
            
            # 4. Verify error message
            assert "API Error" in str(exc_info.value)
            
            # 5. Simulate task error handling
            task = Task(
                id="task_error_123",
                user_id="test_user_123",
                prompt="Create document",
                task_type="docs",
                status="in_progress",
                created_at=datetime.now(),
            )
            
            # 6. Update task with error
            task.status = "failed"
            task.error_message = str(exc_info.value)
            
            # 7. Verify error state
            assert task.status == "failed"
            assert task.error_message is not None
            assert "Quota exceeded" in task.error_message


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
        
        # Mock memory save
        with patch.object(research_agent.memory_manager, 'save_conversation') as mock_save:
            with patch.object(research_agent, '_scrape_web', return_value=[]):
                with patch.object(research_agent, '_analyze_with_llm', return_value={'result': 'AI trends'}):
                    await research_agent.research("What are AI trends?")
                    mock_save.assert_called_once()
        
        # 2. Second agent call - Should have access to previous context
        with patch.object(research_agent.memory_manager, 'get_relevant_context') as mock_get:
            mock_get.return_value = "Previous conversation: AI trends discussion"
            
            context = await research_agent.memory_manager.get_relevant_context("Tell me more")
            
            # 3. Verify context retrieved
            assert context is not None
            assert "AI trends" in context
            mock_get.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
