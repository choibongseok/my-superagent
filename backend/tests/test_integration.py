"""Integration tests for agent system."""

import pytest
from unittest.mock import patch
from app.agents.research_agent import ResearchAgent
from app.prompts.registry import prompt_registry


@pytest.mark.asyncio
async def test_research_agent_with_prompt_registry():
    """Test research agent with prompt from registry."""
    with patch.dict('os.environ', {
        'LANGFUSE_PUBLIC_KEY': 'test_public_key',
        'LANGFUSE_SECRET_KEY': 'test_secret_key',
        'OPENAI_API_KEY': 'test_openai_key',
    }):
        # Get prompt from registry
        prompt_version = prompt_registry.get("research_agent", version="v1")
        assert prompt_version is not None
        assert prompt_version.version == "v1"
        assert "topic" in prompt_version.variables
        assert "focus_areas" in prompt_version.variables

        # Create agent
        agent = ResearchAgent(
            user_id="test_user",
            session_id="integration_test",
        )

        # Verify agent is created successfully
        assert agent.user_id == "test_user"
        assert agent.llm is not None


@pytest.mark.asyncio
async def test_multiple_agents_creation():
    """Test creating multiple different agents."""
    with patch.dict('os.environ', {
        'LANGFUSE_PUBLIC_KEY': 'test_public_key',
        'LANGFUSE_SECRET_KEY': 'test_secret_key',
        'OPENAI_API_KEY': 'test_openai_key',
    }):
        from app.agents import ResearchAgent, DocsAgent, SheetsAgent, SlidesAgent

        agents = [
            ResearchAgent(user_id="user1", session_id="session1"),
            DocsAgent(user_id="user2", session_id="session2"),
            SheetsAgent(user_id="user3", session_id="session3"),
            SlidesAgent(user_id="user4", session_id="session4"),
        ]

        for agent in agents:
            assert agent.llm is not None
            assert agent.memory is not None


@pytest.mark.asyncio
async def test_prompt_registry_operations():
    """Test prompt registry CRUD operations."""
    from app.prompts.registry import PromptRegistry

    # Create temporary registry for testing
    registry = PromptRegistry(storage_path="/tmp/test_prompts")

    # Register new prompt
    prompt_v1 = registry.register(
        name="test_prompt",
        template="Test template with {variable1} and {variable2}",
        variables=["variable1", "variable2"],
        metadata={"test": True},
        version="v1",
    )

    assert prompt_v1.version == "v1"
    assert len(prompt_v1.variables) == 2

    # Get prompt
    retrieved = registry.get("test_prompt", version="v1")
    assert retrieved is not None
    assert retrieved.version == "v1"

    # Register new version
    prompt_v2 = registry.register(
        name="test_prompt",
        template="Updated template with {variable1}",
        variables=["variable1"],
        metadata={"test": True, "updated": True},
        version="v2",
    )

    assert prompt_v2.version == "v2"

    # List all versions
    versions = registry.list_versions("test_prompt")
    assert len(versions) == 2

    # Get latest version
    latest = registry.get("test_prompt")
    assert latest.version == "v2"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
