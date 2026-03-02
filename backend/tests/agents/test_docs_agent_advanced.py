"""
Tests for advanced Docs Agent features.

Tests the enhanced formatting capabilities including:
- Text formatting (bold, italic, underline, font size)
- Named paragraph styles (HEADING_1, HEADING_2, TITLE, etc.)
- Table insertion
- Image insertion
- Page breaks
- Bullet lists
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from google.oauth2.credentials import Credentials

from app.agents.docs_agent import DocsAgent
from app.tools.google_apis import GoogleDocsAPI


@pytest.fixture
def mock_credentials():
    """Mock Google OAuth2 credentials."""
    return Mock(spec=Credentials)


@pytest.fixture
def mock_docs_api():
    """Mock GoogleDocsAPI."""
    api = Mock(spec=GoogleDocsAPI)
    api.create_document = Mock(return_value="doc123")
    api.insert_text = Mock(return_value={"success": True})
    api.get_document_url = Mock(return_value="https://docs.google.com/document/d/doc123/edit")
    api.apply_formatting = Mock(return_value={"success": True})
    api.apply_named_style = Mock(return_value={"success": True})
    api.insert_table = Mock(return_value={"success": True})
    api.insert_image = Mock(return_value={"success": True})
    api.insert_page_break = Mock(return_value={"success": True})
    api.create_bullet_list = Mock(return_value={"success": True})
    return api


@pytest.fixture
def docs_agent(mock_credentials, mock_docs_api):
    """Create a DocsAgent with mocked dependencies."""
    with patch('app.agents.docs_agent.GoogleDocsAPI', return_value=mock_docs_api):
        agent = DocsAgent(
            user_id="test_user",
            credentials=mock_credentials,
            session_id="test_session",
        )
        agent.docs_api = mock_docs_api
        return agent


class TestDocsAgentAdvancedFeatures:
    """Test suite for advanced Docs Agent features."""

    def test_agent_initialization_with_tools(self, docs_agent):
        """Test that agent initializes with advanced formatting tools."""
        assert docs_agent is not None
        assert docs_agent.docs_api is not None
        
        # Check that tools are created
        tools = docs_agent._create_tools()
        assert len(tools) == 6
        
        tool_names = [tool.name for tool in tools]
        assert "apply_text_formatting" in tool_names
        assert "apply_paragraph_style" in tool_names
        assert "insert_table" in tool_names
        assert "insert_image" in tool_names
        assert "insert_page_break" in tool_names
        assert "create_bullet_list" in tool_names

    def test_agent_metadata(self, docs_agent):
        """Test that agent metadata reflects new capabilities."""
        metadata = docs_agent._get_metadata()
        
        assert metadata["agent_type"] == "docs"
        assert metadata["version"] == "2.0"
        
        capabilities = metadata["capabilities"]
        assert "advanced_formatting" in capabilities
        assert "text_styling" in capabilities
        assert "table_insertion" in capabilities
        assert "image_insertion" in capabilities
        assert "bullet_lists" in capabilities
        assert "page_breaks" in capabilities
        assert "named_styles" in capabilities

    def test_apply_formatting_tool(self, docs_agent, mock_docs_api):
        """Test text formatting tool."""
        result = docs_agent._apply_formatting_tool(
            document_id="doc123",
            start_index=1,
            end_index=10,
            bold=True,
            italic=True,
            font_size=14,
        )
        
        assert "Applied formatting" in result
        mock_docs_api.apply_formatting.assert_called_once_with(
            document_id="doc123",
            start_index=1,
            end_index=10,
            bold=True,
            italic=True,
            underline=None,
            font_size=14,
        )

    def test_apply_style_tool(self, docs_agent, mock_docs_api):
        """Test named style application tool."""
        result = docs_agent._apply_style_tool(
            document_id="doc123",
            start_index=1,
            end_index=20,
            style_name="HEADING_1",
        )
        
        assert "Applied HEADING_1" in result
        mock_docs_api.apply_named_style.assert_called_once_with(
            document_id="doc123",
            start_index=1,
            end_index=20,
            style_name="HEADING_1",
        )

    def test_insert_table_tool(self, docs_agent, mock_docs_api):
        """Test table insertion tool."""
        table_data = [
            ["Header 1", "Header 2", "Header 3"],
            ["Row 1 Col 1", "Row 1 Col 2", "Row 1 Col 3"],
            ["Row 2 Col 1", "Row 2 Col 2", "Row 2 Col 3"],
        ]
        
        result = docs_agent._insert_table_tool(
            document_id="doc123",
            rows=3,
            columns=3,
            index=100,
            data=table_data,
        )
        
        assert "Inserted 3x3 table" in result
        mock_docs_api.insert_table.assert_called_once_with(
            document_id="doc123",
            rows=3,
            columns=3,
            index=100,
            data=table_data,
        )

    def test_insert_image_tool(self, docs_agent, mock_docs_api):
        """Test image insertion tool."""
        result = docs_agent._insert_image_tool(
            document_id="doc123",
            image_url="https://example.com/image.png",
            index=50,
            width=400,
            height=300,
        )
        
        assert "Inserted image" in result
        mock_docs_api.insert_image.assert_called_once_with(
            document_id="doc123",
            image_url="https://example.com/image.png",
            index=50,
            width=400,
            height=300,
        )

    def test_insert_page_break_tool(self, docs_agent, mock_docs_api):
        """Test page break insertion tool."""
        result = docs_agent._insert_page_break_tool(
            document_id="doc123",
            index=200,
        )
        
        assert "Inserted page break" in result
        mock_docs_api.insert_page_break.assert_called_once_with(
            document_id="doc123",
            index=200,
        )

    def test_create_bullet_list_tool(self, docs_agent, mock_docs_api):
        """Test bullet list creation tool."""
        result = docs_agent._create_bullet_list_tool(
            document_id="doc123",
            start_index=50,
            end_index=150,
            bullet_preset="BULLET_DISC_CIRCLE_SQUARE",
        )
        
        assert "Created bullet list" in result
        mock_docs_api.create_bullet_list.assert_called_once_with(
            document_id="doc123",
            start_index=50,
            end_index=150,
            bullet_preset="BULLET_DISC_CIRCLE_SQUARE",
        )

    def test_tool_error_handling(self, docs_agent, mock_docs_api):
        """Test that tools handle errors gracefully."""
        mock_docs_api.apply_formatting.side_effect = Exception("API Error")
        
        result = docs_agent._apply_formatting_tool(
            document_id="doc123",
            start_index=1,
            end_index=10,
            bold=True,
        )
        
        assert "Error applying formatting" in result
        assert "API Error" in result

    @pytest.mark.asyncio
    async def test_document_creation_with_formatting(self, docs_agent, mock_docs_api):
        """Test document creation uses new formatting capabilities."""
        with patch.object(docs_agent, 'run', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = {
                "success": True,
                "output": "# Main Title\n\nThis is content with **bold** text.",
            }
            
            with patch.object(docs_agent, 'research_agent') as mock_research:
                mock_research.research = AsyncMock(return_value={
                    "success": True,
                    "output": "Research findings",
                    "citations": [],
                })
                
                result = await docs_agent.create_document(
                    title="Advanced Report",
                    prompt="Create a report with tables and images",
                    include_research=True,
                )
        
        assert result["success"] is True
        assert result["document_id"] == "doc123"
        assert result["document_url"] == "https://docs.google.com/document/d/doc123/edit"
        
        # Verify document was created
        mock_docs_api.create_document.assert_called_once_with("Advanced Report")
        
        # Verify content was inserted
        mock_docs_api.insert_text.assert_called_once()


class TestGoogleDocsAPIAdvanced:
    """Test suite for advanced GoogleDocsAPI methods."""

    @pytest.fixture
    def docs_api(self, mock_credentials):
        """Create GoogleDocsAPI with mocked service."""
        with patch('app.tools.google_apis.build') as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            
            api = GoogleDocsAPI(mock_credentials)
            api.service = mock_service
            
            return api, mock_service

    def test_apply_formatting(self, docs_api):
        """Test apply_formatting method."""
        api, mock_service = docs_api
        
        # Create a fresh mock for the chain
        mock_batch_update = MagicMock()
        mock_batch_update.execute.return_value = {"success": True}
        mock_service.documents().batchUpdate.return_value = mock_batch_update
        
        result = api.apply_formatting(
            document_id="doc123",
            start_index=1,
            end_index=10,
            bold=True,
            italic=True,
            font_size=16,
        )
        
        assert result["success"] is True
        # Verify batchUpdate was called with correct parameters
        mock_service.documents().batchUpdate.assert_called_once()
        call_args = mock_service.documents().batchUpdate.call_args
        assert call_args[1]['documentId'] == 'doc123'
        assert 'requests' in call_args[1]['body']

    def test_apply_named_style(self, docs_api):
        """Test apply_named_style method."""
        api, mock_service = docs_api
        
        # Create a fresh mock for the chain
        mock_batch_update = MagicMock()
        mock_batch_update.execute.return_value = {"success": True}
        mock_service.documents().batchUpdate.return_value = mock_batch_update
        
        result = api.apply_named_style(
            document_id="doc123",
            start_index=1,
            end_index=20,
            style_name="HEADING_1",
        )
        
        assert result["success"] is True
        # Verify batchUpdate was called with correct parameters
        mock_service.documents().batchUpdate.assert_called_once()
        call_args = mock_service.documents().batchUpdate.call_args
        assert call_args[1]['documentId'] == 'doc123'

    def test_insert_table(self, docs_api):
        """Test insert_table method."""
        api, mock_service = docs_api
        
        mock_service.documents().batchUpdate().execute.return_value = {
            "replies": [{"insertTable": {"tableId": "table123"}}]
        }
        mock_service.documents().get().execute.return_value = {
            "body": {
                "content": [
                    {
                        "table": {
                            "tableRows": [
                                {
                                    "tableCells": [
                                        {"content": [{"startIndex": 10}]},
                                        {"content": [{"startIndex": 20}]},
                                    ]
                                }
                            ]
                        }
                    }
                ]
            }
        }
        
        result = api.insert_table(
            document_id="doc123",
            rows=2,
            columns=2,
            index=100,
            data=[["A", "B"], ["C", "D"]],
        )
        
        assert "replies" in result or "success" in result

    def test_insert_image(self, docs_api):
        """Test insert_image method."""
        api, mock_service = docs_api
        
        # Create a fresh mock for the chain
        mock_batch_update = MagicMock()
        mock_batch_update.execute.return_value = {"success": True}
        mock_service.documents().batchUpdate.return_value = mock_batch_update
        
        result = api.insert_image(
            document_id="doc123",
            image_url="https://example.com/image.png",
            index=50,
            width=400,
            height=300,
        )
        
        assert result["success"] is True
        mock_service.documents().batchUpdate.assert_called_once()
        call_args = mock_service.documents().batchUpdate.call_args
        assert call_args[1]['documentId'] == 'doc123'

    def test_insert_page_break(self, docs_api):
        """Test insert_page_break method."""
        api, mock_service = docs_api
        
        # Create a fresh mock for the chain
        mock_batch_update = MagicMock()
        mock_batch_update.execute.return_value = {"success": True}
        mock_service.documents().batchUpdate.return_value = mock_batch_update
        
        result = api.insert_page_break(
            document_id="doc123",
            index=200,
        )
        
        assert result["success"] is True
        mock_service.documents().batchUpdate.assert_called_once()
        call_args = mock_service.documents().batchUpdate.call_args
        assert call_args[1]['documentId'] == 'doc123'

    def test_create_bullet_list(self, docs_api):
        """Test create_bullet_list method."""
        api, mock_service = docs_api
        
        # Create a fresh mock for the chain
        mock_batch_update = MagicMock()
        mock_batch_update.execute.return_value = {"success": True}
        mock_service.documents().batchUpdate.return_value = mock_batch_update
        
        result = api.create_bullet_list(
            document_id="doc123",
            start_index=50,
            end_index=150,
            bullet_preset="BULLET_DISC_CIRCLE_SQUARE",
        )
        
        assert result["success"] is True
        mock_service.documents().batchUpdate.assert_called_once()
        call_args = mock_service.documents().batchUpdate.call_args
        assert call_args[1]['documentId'] == 'doc123'


@pytest.mark.integration
class TestDocsAgentE2E:
    """End-to-end tests for Docs Agent with advanced features."""

    @pytest.mark.asyncio
    async def test_create_formatted_report(self, mock_credentials):
        """Test creating a fully formatted report with all features."""
        with patch('app.tools.google_apis.build'):
            agent = DocsAgent(
                user_id="test_user",
                credentials=mock_credentials,
            )
            
            # Mock the agent's run method to simulate LLM response
            with patch.object(agent, 'run', new_callable=AsyncMock) as mock_run:
                mock_run.return_value = {
                    "success": True,
                    "output": """
# AI Industry Report 2024

## Executive Summary
The AI industry has seen unprecedented growth in 2024.

## Key Findings
- Market size: $50B
- Growth rate: 35% YoY
- Major players: OpenAI, Anthropic, Google

## Data Analysis
[Table of market data would be inserted here]

## Conclusion
The future looks promising for AI development.
                    """.strip(),
                }
                
                with patch.object(agent, 'research_agent') as mock_research:
                    mock_research.research = AsyncMock(return_value={
                        "success": True,
                        "output": "Research data about AI industry",
                        "citations": [
                            {"title": "AI Report", "url": "https://example.com/ai-report"}
                        ],
                    })
                    
                    # Mock docs_api methods
                    agent.docs_api = Mock()
                    agent.docs_api.create_document = Mock(return_value="doc_final_123")
                    agent.docs_api.insert_text = Mock(return_value={"success": True})
                    agent.docs_api.get_document_url = Mock(
                        return_value="https://docs.google.com/document/d/doc_final_123/edit"
                    )
                    
                    result = await agent.create_document(
                        title="AI Industry Report 2024",
                        prompt="Create a comprehensive report on the AI industry in 2024 with data tables and insights",
                        include_research=True,
                    )
            
            assert result["success"] is True
            assert result["document_id"] == "doc_final_123"
            assert "AI Industry Report" in result["content"]
            assert len(result["citations"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
