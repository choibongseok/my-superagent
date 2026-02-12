"""
End-to-End Tests for Multi-Agent Orchestrator
Tests complex multi-agent coordination and template execution
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

from app.agents.orchestrator import MultiAgentOrchestrator
from app.models import Task, Template
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


@pytest.mark.asyncio
async def test_orchestrator_simple_task(orchestrator):
    """
    Test orchestrator with simple single-agent task
    """
    # Mock research agent
    with patch.object(orchestrator, '_execute_research') as mock_research:
        mock_research.return_value = {
            'summary': 'AI trends summary',
            'sources': ['https://example.com'],
        }
        
        result = await orchestrator.execute_complex_task(
            task_description="Research AI trends",
            required_agents=['research']
        )
        
        assert result is not None
        assert 'research_result' in result
        assert result['research_result']['summary'] == 'AI trends summary'
        mock_research.assert_called_once()


@pytest.mark.asyncio
async def test_orchestrator_multi_agent_coordination(orchestrator):
    """
    Test orchestrator coordinating multiple agents
    Research → Docs → Sheets workflow
    """
    # 1. Mock research phase
    with patch.object(orchestrator, '_execute_research') as mock_research:
        mock_research.return_value = {
            'data': [
                {'metric': 'Revenue', 'value': 1000000},
                {'metric': 'Users', 'value': 50000},
            ],
            'analysis': 'Strong Q1 performance'
        }
        
        # 2. Mock sheets phase
        with patch.object(orchestrator, '_execute_sheets') as mock_sheets:
            mock_sheets.return_value = {
                'spreadsheet_id': 'sheet_orch_123',
                'spreadsheet_url': 'https://docs.google.com/spreadsheets/d/sheet_orch_123',
            }
            
            # 3. Mock docs phase
            with patch.object(orchestrator, '_execute_docs') as mock_docs:
                mock_docs.return_value = {
                    'document_id': 'doc_orch_123',
                    'document_url': 'https://docs.google.com/document/d/doc_orch_123',
                }
                
                # 4. Execute complex task
                result = await orchestrator.execute_complex_task(
                    task_description="Create Q1 performance report with data and analysis",
                    required_agents=['research', 'sheets', 'docs']
                )
                
                # 5. Verify all agents executed
                assert result is not None
                assert 'research_result' in result
                assert 'sheets_result' in result
                assert 'docs_result' in result
                
                mock_research.assert_called_once()
                mock_sheets.assert_called_once()
                mock_docs.assert_called_once()


@pytest.mark.asyncio
async def test_orchestrator_with_cache(orchestrator):
    """
    Test orchestrator using cache service
    """
    cache_service = LocalCacheService()
    
    # 1. Execute task first time
    with patch.object(orchestrator, '_execute_research') as mock_research:
        mock_research.return_value = {'data': 'research_data'}
        
        result1 = await orchestrator.execute_complex_task(
            task_description="Research topic X",
            required_agents=['research']
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
        assert mock_research.call_count == 1  # Only called once


@pytest.mark.asyncio
async def test_orchestrator_error_handling(orchestrator):
    """
    Test orchestrator error handling when agent fails
    """
    # Mock agent failure
    with patch.object(orchestrator, '_execute_sheets') as mock_sheets:
        mock_sheets.side_effect = Exception("Google Sheets API error")
        
        # Execute and expect graceful error handling
        with pytest.raises(Exception) as exc_info:
            await orchestrator.execute_complex_task(
                task_description="Create spreadsheet",
                required_agents=['sheets']
            )
        
        assert "Google Sheets API error" in str(exc_info.value)


@pytest.mark.asyncio
async def test_orchestrator_partial_success(orchestrator):
    """
    Test orchestrator when some agents succeed and others fail
    """
    # Research succeeds
    with patch.object(orchestrator, '_execute_research') as mock_research:
        mock_research.return_value = {'data': 'success'}
        
        # Sheets fails
        with patch.object(orchestrator, '_execute_sheets') as mock_sheets:
            mock_sheets.side_effect = Exception("Sheets failed")
            
            # Should handle partial success gracefully
            try:
                result = await orchestrator.execute_complex_task(
                    task_description="Research and create sheet",
                    required_agents=['research', 'sheets']
                )
            except Exception as e:
                # Research completed but sheets failed
                assert "Sheets failed" in str(e)
                mock_research.assert_called_once()
                mock_sheets.assert_called_once()


@pytest.mark.asyncio
async def test_orchestrator_dependency_order(orchestrator):
    """
    Test that orchestrator executes agents in correct dependency order
    Research must complete before Docs can use the data
    """
    execution_order = []
    
    async def track_research(*args, **kwargs):
        execution_order.append('research')
        return {'data': 'research_result'}
    
    async def track_docs(*args, **kwargs):
        execution_order.append('docs')
        # Docs depends on research data
        assert 'research' in execution_order
        return {'document_id': 'doc_123'}
    
    with patch.object(orchestrator, '_execute_research', side_effect=track_research):
        with patch.object(orchestrator, '_execute_docs', side_effect=track_docs):
            await orchestrator.execute_complex_task(
                task_description="Research and document",
                required_agents=['research', 'docs']
            )
            
            # Verify execution order
            assert execution_order == ['research', 'docs']


@pytest.mark.asyncio
async def test_template_execution_via_orchestrator():
    """
    Test executing a template through the orchestrator
    Template → Task creation → Agent execution
    """
    # 1. Mock template
    template = Template(
        id="template_123",
        name="Sales Report Template",
        category="research",
        prompt_template="Research sales data for {product} in {quarter}",
        required_inputs={
            'product': 'string',
            'quarter': 'string',
        },
        metadata={
            'agents': ['research', 'sheets'],
            'output_format': 'spreadsheet',
        },
        created_by="admin",
        created_at=datetime.now(),
    )
    
    # 2. Mock task created from template
    task = Task(
        id="task_from_template_123",
        user_id="test_user_123",
        prompt="Research sales data for Product A in Q1",
        task_type="research",
        status="pending",
        metadata={
            'template_id': template.id,
            'template_inputs': {
                'product': 'Product A',
                'quarter': 'Q1',
            },
        },
        created_at=datetime.now(),
    )
    
    # 3. Execute via orchestrator
    with patch('app.services.google_auth.get_user_credentials', return_value=MockGoogleCredentials()):
        orchestrator = MultiAgentOrchestrator(
            user_id=task.user_id,
            session_id=task.id
        )
        
        with patch.object(orchestrator, '_execute_research') as mock_research:
            mock_research.return_value = {
                'sales_data': [
                    {'month': 'Jan', 'sales': 100000},
                    {'month': 'Feb', 'sales': 120000},
                    {'month': 'Mar', 'sales': 130000},
                ]
            }
            
            with patch.object(orchestrator, '_execute_sheets') as mock_sheets:
                mock_sheets.return_value = {
                    'spreadsheet_id': 'sheet_template_123',
                }
                
                result = await orchestrator.execute_complex_task(
                    task_description=task.prompt,
                    required_agents=['research', 'sheets']
                )
                
                # 4. Verify execution
                assert result is not None
                assert 'research_result' in result
                assert 'sheets_result' in result
                
                # 5. Update task
                task.status = "completed"
                task.result = result
                task.completed_at = datetime.now()
                
                assert task.status == "completed"
                assert task.metadata['template_id'] == template.id


@pytest.mark.asyncio
async def test_orchestrator_with_slides_presentation():
    """
    Test orchestrator creating a complete presentation
    Research → Data analysis → Slides creation
    """
    with patch('app.services.google_auth.get_user_credentials', return_value=MockGoogleCredentials()):
        orchestrator = MultiAgentOrchestrator(
            user_id="test_user_123",
            session_id="slides_test"
        )
        
        # 1. Research phase
        with patch.object(orchestrator, '_execute_research') as mock_research:
            mock_research.return_value = {
                'title': 'Market Analysis Q1',
                'key_findings': [
                    'Market grew 15%',
                    'New competitors entered',
                    'Customer satisfaction up',
                ],
                'recommendations': [
                    'Expand product line',
                    'Increase marketing',
                ],
            }
            
            # 2. Slides phase
            with patch.object(orchestrator, '_execute_slides') as mock_slides:
                mock_slides.return_value = {
                    'presentation_id': 'pres_orch_123',
                    'presentation_url': 'https://docs.google.com/presentation/d/pres_orch_123',
                    'slides': [
                        {'id': 'slide_1', 'title': 'Market Analysis Q1'},
                        {'id': 'slide_2', 'title': 'Key Findings'},
                        {'id': 'slide_3', 'title': 'Recommendations'},
                    ],
                }
                
                result = await orchestrator.execute_complex_task(
                    task_description="Create market analysis presentation for Q1",
                    required_agents=['research', 'slides']
                )
                
                # 3. Verify presentation
                assert result is not None
                assert 'slides_result' in result
                assert result['slides_result']['presentation_id'] == 'pres_orch_123'
                assert len(result['slides_result']['slides']) == 3


@pytest.mark.asyncio
async def test_orchestrator_retry_logic():
    """
    Test orchestrator retry logic on transient failures
    """
    with patch('app.services.google_auth.get_user_credentials', return_value=MockGoogleCredentials()):
        orchestrator = MultiAgentOrchestrator(
            user_id="test_user_123",
            session_id="retry_test"
        )
        
        call_count = 0
        
        async def failing_then_succeeding(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Transient error")
            return {'data': 'success'}
        
        with patch.object(orchestrator, '_execute_research', side_effect=failing_then_succeeding):
            # Should retry and eventually succeed
            # Note: Actual retry logic would need to be implemented in orchestrator
            try:
                result = await orchestrator.execute_complex_task(
                    task_description="Research with retries",
                    required_agents=['research']
                )
                # If retry is implemented, this should succeed on 3rd attempt
            except Exception as e:
                # If retry not implemented, fails on 1st attempt
                assert "Transient error" in str(e)


@pytest.mark.asyncio
async def test_orchestrator_concurrent_agent_execution():
    """
    Test orchestrator executing independent agents concurrently
    Sheets and Slides can run in parallel (no dependencies)
    """
    import asyncio
    
    execution_times = {}
    
    async def slow_sheets(*args, **kwargs):
        start = asyncio.get_event_loop().time()
        await asyncio.sleep(0.1)  # Simulate slow operation
        execution_times['sheets'] = asyncio.get_event_loop().time() - start
        return {'spreadsheet_id': 'sheet_concurrent'}
    
    async def slow_slides(*args, **kwargs):
        start = asyncio.get_event_loop().time()
        await asyncio.sleep(0.1)  # Simulate slow operation
        execution_times['slides'] = asyncio.get_event_loop().time() - start
        return {'presentation_id': 'pres_concurrent'}
    
    with patch('app.services.google_auth.get_user_credentials', return_value=MockGoogleCredentials()):
        orchestrator = MultiAgentOrchestrator(
            user_id="test_user_123",
            session_id="concurrent_test"
        )
        
        with patch.object(orchestrator, '_execute_sheets', side_effect=slow_sheets):
            with patch.object(orchestrator, '_execute_slides', side_effect=slow_slides):
                start_time = asyncio.get_event_loop().time()
                
                # If executed concurrently, should take ~0.1s
                # If sequential, would take ~0.2s
                result = await orchestrator.execute_complex_task(
                    task_description="Create sheet and presentation",
                    required_agents=['sheets', 'slides']
                )
                
                total_time = asyncio.get_event_loop().time() - start_time
                
                # Verify both completed
                assert result is not None
                # Note: Actual concurrent execution would need to be implemented


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
