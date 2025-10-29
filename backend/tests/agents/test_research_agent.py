"""Tests for ResearchAgent with comprehensive mocking (zero network calls)."""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime

from app.agents.research_agent import ResearchAgent
from app.memory.conversation import ConversationMemory


class TestResearchAgentInitialization:
    """Test ResearchAgent initialization."""

    def test_init_basic(self):
        """Test basic initialization."""
        agent = ResearchAgent(user_id="test_user")
        
        assert agent.user_id == "test_user"
        assert agent.session_id.startswith("research_")
        assert agent.citations == []
        assert agent.memory is not None
        assert isinstance(agent.memory, ConversationMemory)

    def test_init_with_session(self):
        """Test initialization with custom session ID."""
        agent = ResearchAgent(
            user_id="test_user",
            session_id="custom_session",
        )
        
        assert agent.session_id == "custom_session"

    def test_metadata(self):
        """Test agent metadata."""
        agent = ResearchAgent(user_id="test_user")
        metadata = agent._get_metadata()
        
        assert metadata["agent_type"] == "research"
        assert "web_search" in metadata["capabilities"]
        assert "citation_tracking" in metadata["capabilities"]


class TestResearchAgentTools:
    """Test tool creation."""

    def test_create_tools(self):
        """Test tools are created correctly."""
        agent = ResearchAgent(user_id="test_user")
        tools = agent._create_tools()
        
        assert len(tools) > 0
        assert any(tool.name == "web_search" for tool in tools)

    def test_tool_initialization(self):
        """Test tool initialization doesn't fail."""
        agent = ResearchAgent(user_id="test_user")
        agent.initialize_agent()
        
        assert agent.agent_executor is not None
        assert len(agent.tools) > 0


class TestResearchAgentPrompt:
    """Test prompt template creation."""

    def test_create_prompt(self):
        """Test prompt template is created."""
        agent = ResearchAgent(user_id="test_user")
        prompt = agent._create_prompt()
        
        assert prompt is not None
        assert "research" in str(prompt).lower()


class TestResearchAgentMemory:
    """Test memory integration."""

    def test_memory_initialization(self):
        """Test ConversationMemory is initialized."""
        agent = ResearchAgent(user_id="test_user")
        
        assert agent.memory is not None
        assert isinstance(agent.memory, ConversationMemory)
        assert agent.memory.user_id == "test_user"

    def test_add_user_message(self):
        """Test adding user message to memory."""
        agent = ResearchAgent(user_id="test_user")
        
        agent.add_user_message("Test query")
        messages = agent.memory.get_messages()
        
        assert len(messages) == 1
        assert messages[0].content == "Test query"

    def test_add_ai_message(self):
        """Test adding AI message to memory."""
        agent = ResearchAgent(user_id="test_user")
        
        agent.add_ai_message("Test response")
        messages = agent.memory.get_messages()
        
        assert len(messages) == 1
        assert messages[0].content == "Test response"

    def test_conversation_flow(self):
        """Test full conversation flow in memory."""
        agent = ResearchAgent(user_id="test_user")
        
        agent.add_user_message("Query 1")
        agent.add_ai_message("Response 1")
        agent.add_user_message("Query 2")
        agent.add_ai_message("Response 2")
        
        messages = agent.memory.get_messages()
        assert len(messages) == 4


@pytest.mark.asyncio
class TestResearchAgentExecution:
    """Test agent execution with mocking."""

    @patch("app.agents.research_agent.DuckDuckGoSearchTool")
    async def test_run_basic(self, mock_search_tool):
        """Test basic agent execution with mocked search."""
        # Mock the search tool
        mock_tool_instance = Mock()
        mock_tool_instance.name = "web_search"
        mock_tool_instance.description = "Search tool"
        mock_tool_instance._run = Mock(return_value="Mocked search results")
        mock_search_tool.return_value = mock_tool_instance
        
        agent = ResearchAgent(user_id="test_user")
        
        # Mock the agent executor
        with patch.object(agent, 'agent_executor') as mock_executor:
            mock_executor.ainvoke = AsyncMock(return_value={
                "output": "Research findings here",
                "intermediate_steps": [],
            })
            
            result = await agent.run("Test query")
            
            assert result["success"] is True
            assert "output" in result

    @patch("app.agents.research_agent.DuckDuckGoSearchTool")
    async def test_research_method(self, mock_search_tool):
        """Test research method with citation extraction."""
        # Mock the search tool
        mock_tool_instance = Mock()
        mock_tool_instance.name = "web_search"
        mock_search_tool.return_value = mock_tool_instance
        
        agent = ResearchAgent(user_id="test_user")
        
        # Mock agent executor
        with patch.object(agent, 'agent_executor') as mock_executor:
            # Create mock action with tool attribute
            mock_action = Mock()
            mock_action.tool = "web_search"
            mock_action.tool_input = "test query"
            
            mock_executor.ainvoke = AsyncMock(return_value={
                "output": "Research output",
                "intermediate_steps": [
                    (mock_action, "Search results"),
                ],
            })
            
            result = await agent.research("Test research query")
            
            assert result["success"] is True
            assert "citations" in result
            assert "citation_count" in result

    async def test_error_handling(self):
        """Test error handling in agent execution."""
        agent = ResearchAgent(user_id="test_user")
        
        # Mock executor to raise exception
        with patch.object(agent, 'agent_executor') as mock_executor:
            mock_executor.ainvoke = AsyncMock(side_effect=Exception("Test error"))
            
            result = await agent.run("Test query")
            
            assert result["success"] is False
            assert "error" in result


class TestCitationManagement:
    """Test citation tracking and formatting."""

    def test_extract_citations(self):
        """Test citation extraction from intermediate steps."""
        agent = ResearchAgent(user_id="test_user")
        
        # Create mock action with tool attribute
        mock_action = Mock()
        mock_action.tool = "web_search"
        mock_action.tool_input = "AI developments"
        
        intermediate_steps = [
            (mock_action, "Search results about AI"),
        ]
        
        citations = agent._extract_citations(intermediate_steps)
        
        assert len(citations) > 0
        assert citations[0]["query"] == "AI developments"
        assert citations[0]["source"] == "duckduckgo"

    def test_get_citations_apa(self):
        """Test APA citation formatting."""
        agent = ResearchAgent(user_id="test_user")
        
        # Add mock citation
        agent.citations.append({
            "query": "Test query",
            "timestamp": "2024-01-01T00:00:00",
            "source": "duckduckgo",
        })
        
        formatted = agent.get_citations(format="apa")
        
        assert len(formatted) == 1
        assert "Test query" in formatted[0]

    def test_get_citations_mla(self):
        """Test MLA citation formatting."""
        agent = ResearchAgent(user_id="test_user")
        
        agent.citations.append({
            "query": "Test query",
            "timestamp": "2024-01-01T00:00:00",
            "source": "duckduckgo",
        })
        
        formatted = agent.get_citations(format="mla")
        
        assert len(formatted) == 1
        assert "Test query" in formatted[0]

    def test_clear_citations(self):
        """Test clearing citations."""
        agent = ResearchAgent(user_id="test_user")
        
        agent.citations.append({"query": "test"})
        assert len(agent.citations) == 1
        
        agent.clear_citations()
        assert len(agent.citations) == 0


class TestIntegrationScenarios:
    """Test realistic usage scenarios."""

    @patch("app.agents.research_agent.DuckDuckGoSearchTool")
    @pytest.mark.asyncio
    async def test_full_research_workflow(self, mock_search_tool):
        """Test complete research workflow."""
        # Setup mocks
        mock_tool_instance = Mock()
        mock_tool_instance.name = "web_search"
        mock_search_tool.return_value = mock_tool_instance
        
        agent = ResearchAgent(user_id="test_user")
        
        with patch.object(agent, 'agent_executor') as mock_executor:
            mock_action = Mock()
            mock_action.tool = "web_search"
            mock_action.tool_input = "AI news"
            
            mock_executor.ainvoke = AsyncMock(return_value={
                "output": "Latest AI developments include...",
                "intermediate_steps": [
                    (mock_action, "Mocked search results"),
                ],
            })
            
            # Execute research
            result = await agent.research("Research latest AI news")
            
            # Verify results
            assert result["success"] is True
            assert "output" in result
            assert len(result["citations"]) > 0
            
            # Verify memory
            messages = agent.memory.get_messages()
            assert len(messages) == 2  # User query + AI response

    def test_memory_persistence(self):
        """Test memory persists across multiple queries."""
        agent = ResearchAgent(user_id="test_user")
        
        # Simulate multiple interactions
        agent.add_user_message("Query 1")
        agent.add_ai_message("Response 1")
        agent.add_user_message("Query 2")
        agent.add_ai_message("Response 2")
        
        # Verify history
        history = agent.get_conversation_history()
        assert "Query 1" in history
        assert "Response 1" in history
        assert "Query 2" in history
        assert "Response 2" in history
