"""Tests for ResearchAgent with mocking."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage

from app.agents.research_agent import ResearchAgent


class TestResearchAgent:
    """Test ResearchAgent with mocked dependencies."""
    
    @pytest.fixture
    def mock_llm(self):
        """Create mock LLM."""
        llm = Mock()
        llm.invoke = Mock(return_value=Mock(content="Mocked LLM response"))
        return llm
    
    @pytest.fixture
    def mock_web_search(self):
        """Create mock web search results."""
        return """1. Test Result Title
   URL: https://example.com/1
   This is a test snippet about AI.

2. Another Result
   URL: https://example.com/2
   More information about machine learning."""
    
    @pytest.fixture
    def agent(self, mock_llm):
        """Create ResearchAgent with mocked LLM."""
        with patch("app.agents.research_agent.ChatOpenAI", return_value=mock_llm):
            agent = ResearchAgent(
                user_id="test_user",
                session_id="test_session",
                enable_langfuse=False,  # Disable LangFuse for testing
            )
            return agent
    
    def test_agent_initialization(self, agent):
        """Test agent initializes correctly."""
        assert agent.user_id == "test_user"
        assert agent.session_id == "test_session"
        assert agent.memory is not None
        assert len(agent.tools) > 0
    
    def test_memory_integration(self, agent):
        """Test memory integration."""
        # Add messages
        agent.add_user_message("Test question")
        agent.add_ai_message("Test response")
        
        # Check memory
        messages = agent.get_conversation_history()
        assert len(messages) >= 2
        
        # Verify message types
        user_msgs = [m for m in messages if isinstance(m, HumanMessage)]
        ai_msgs = [m for m in messages if isinstance(m, AIMessage)]
        assert len(user_msgs) >= 1
        assert len(ai_msgs) >= 1
    
    @patch("app.agents.research_agent.AgentExecutor")
    def test_research_with_mocked_executor(self, mock_executor_class, agent, mock_web_search):
        """Test research method with mocked executor."""
        # Mock executor response
        mock_executor = Mock()
        mock_executor.invoke = Mock(return_value={
            "output": "Research complete. Found relevant information about AI.",
            "intermediate_steps": [
                (Mock(tool="web_search"), mock_web_search)
            ]
        })
        mock_executor_class.return_value = mock_executor
        
        # Replace agent executor
        agent.agent_executor = mock_executor
        
        # Run research
        result = agent.research("What is AI?")
        
        # Verify result structure
        assert "output" in result
        assert "sources" in result
        assert isinstance(result["sources"], list)
        
        # Verify executor was called
        mock_executor.invoke.assert_called_once()
    
    def test_citation_extraction(self, agent, mock_web_search):
        """Test citation extraction from search results."""
        # Mock intermediate steps
        mock_action = Mock()
        mock_action.tool = "web_search"
        intermediate_steps = [(mock_action, mock_web_search)]
        
        # Extract sources
        sources = agent._extract_sources(intermediate_steps)
        
        # Verify sources extracted
        assert len(sources) > 0
        assert all("url" in s for s in sources)
        assert all("title" in s for s in sources)
    
    def test_clear_memory(self, agent):
        """Test memory clearing."""
        # Add some messages
        agent.add_user_message("Test 1")
        agent.add_ai_message("Response 1")
        
        # Clear memory
        agent.clear_memory()
        
        # Verify memory is empty
        messages = agent.get_conversation_history()
        assert len(messages) == 0
    
    def test_error_handling(self, agent):
        """Test error handling in research."""
        # Mock executor to raise exception
        agent.agent_executor.invoke = Mock(side_effect=Exception("Test error"))
        
        # Run research
        result = agent.research("This will fail")
        
        # Verify error handling
        assert "error" in result
        assert "output" in result
        assert "failed" in result["output"].lower()


class TestResearchAgentTools:
    """Test ResearchAgent tools without network calls."""
    
    @patch("app.tools.web_search.DuckDuckGoSearchAPIWrapper")
    def test_web_search_tool_creation(self, mock_ddg):
        """Test web search tool creation."""
        from app.tools.web_search import create_web_search_tool
        
        # Mock search results
        mock_ddg.return_value.results = Mock(return_value=[
            {
                "title": "Test Title",
                "link": "https://example.com",
                "snippet": "Test snippet"
            }
        ])
        
        # Create tool
        tool = create_web_search_tool(max_results=5)
        
        # Verify tool properties
        assert tool.name == "web_search"
        assert "search" in tool.description.lower()
    
    @patch("app.tools.web_search.DuckDuckGoSearchAPIWrapper")
    def test_web_search_tool_execution(self, mock_ddg):
        """Test web search tool execution with mocking."""
        from app.tools.web_search import create_web_search_tool
        
        # Mock search results
        mock_search = Mock()
        mock_search.results = Mock(return_value=[
            {
                "title": "AI Research",
                "link": "https://example.com/ai",
                "snippet": "Latest AI developments"
            }
        ])
        mock_ddg.return_value = mock_search
        
        # Create and run tool
        tool = create_web_search_tool(max_results=1)
        result = tool.run("AI trends")
        
        # Verify result
        assert isinstance(result, str)
        assert len(result) > 0
        
        # Verify search was called
        mock_search.results.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
