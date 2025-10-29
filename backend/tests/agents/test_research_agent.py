"""Tests for Research Agent."""

import pytest
from unittest.mock import Mock, patch
from app.agents.research_agent import ResearchAgent


@pytest.mark.asyncio
async def test_research_agent_creation():
    """Test research agent initialization."""
    with patch.dict('os.environ', {
        'LANGFUSE_PUBLIC_KEY': 'test_public_key',
        'LANGFUSE_SECRET_KEY': 'test_secret_key',
        'OPENAI_API_KEY': 'test_openai_key',
    }):
        agent = ResearchAgent(
            user_id="test_user",
            session_id="test_session",
        )

        assert agent.user_id == "test_user"
        assert agent.session_id == "test_session"
        assert agent.llm is not None


@pytest.mark.asyncio
async def test_research_agent_metadata():
    """Test research agent metadata."""
    with patch.dict('os.environ', {
        'LANGFUSE_PUBLIC_KEY': 'test_public_key',
        'LANGFUSE_SECRET_KEY': 'test_secret_key',
        'OPENAI_API_KEY': 'test_openai_key',
    }):
        agent = ResearchAgent(
            user_id="test_user",
            session_id="test_session",
        )

        metadata = agent._get_metadata()
        assert metadata["agent_type"] == "research"
        assert metadata["version"] == "1.0"
        assert "web_search" in metadata["capabilities"]


@pytest.mark.asyncio
async def test_research_agent_tools():
    """Test research agent tools creation."""
    with patch.dict('os.environ', {
        'LANGFUSE_PUBLIC_KEY': 'test_public_key',
        'LANGFUSE_SECRET_KEY': 'test_secret_key',
        'OPENAI_API_KEY': 'test_openai_key',
    }):
        agent = ResearchAgent(
            user_id="test_user",
            session_id="test_session",
        )

        tools = agent._create_tools()
        assert len(tools) > 0
        assert tools[0].name == "web_search"


@pytest.mark.asyncio
async def test_research_agent_prompt():
    """Test research agent prompt creation."""
    with patch.dict('os.environ', {
        'LANGFUSE_PUBLIC_KEY': 'test_public_key',
        'LANGFUSE_SECRET_KEY': 'test_secret_key',
        'OPENAI_API_KEY': 'test_openai_key',
    }):
        agent = ResearchAgent(
            user_id="test_user",
            session_id="test_session",
        )

        prompt = agent._create_prompt()
        assert prompt is not None


@pytest.mark.asyncio
@pytest.mark.skipif(
    True,
    reason="Skipping live API test - requires real API keys and can be slow"
)
async def test_research_agent_run():
    """Test research agent execution (integration test - requires real API keys)."""
    agent = ResearchAgent(
        user_id="test_user",
        session_id="test_session",
    )

    result = await agent.run(
        prompt="What are the latest trends in AI in 2024?",
    )

    assert result["success"] is True
    assert result["output"] is not None
    assert len(result["output"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
