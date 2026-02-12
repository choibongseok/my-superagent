"""Tests for MultiAgentOrchestrator."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from app.agents.orchestrator import MultiAgentOrchestrator, AgentTask


@pytest.fixture
def mock_credentials():
    """Mock Google credentials."""
    credentials = Mock()
    credentials.token = "mock_token"
    credentials.refresh_token = "mock_refresh"
    credentials.expiry = None
    return credentials


@pytest.fixture
def orchestrator(mock_credentials):
    """Create orchestrator instance."""
    with patch.dict('os.environ', {
        'LANGFUSE_PUBLIC_KEY': 'test_public_key',
        'LANGFUSE_SECRET_KEY': 'test_secret_key',
        'OPENAI_API_KEY': 'test_openai_key',
    }):
        return MultiAgentOrchestrator(
            user_id="test_user",
            google_credentials=mock_credentials,
        )


def test_orchestrator_initialization(orchestrator):
    """Test orchestrator is initialized correctly."""
    assert orchestrator.user_id == "test_user"
    assert orchestrator.google_credentials is not None
    assert orchestrator.session_id is not None
    assert orchestrator._agents == {}


def test_get_research_agent(orchestrator):
    """Test creating research agent."""
    agent = orchestrator._get_agent("research")
    assert agent is not None
    assert agent.user_id == "test_user"
    # Agent should be cached
    agent2 = orchestrator._get_agent("research")
    assert agent is agent2


def test_get_docs_agent(orchestrator):
    """Test creating docs agent."""
    agent = orchestrator._get_agent("docs")
    assert agent is not None
    assert agent.user_id == "test_user"
    # Agent should be cached
    agent2 = orchestrator._get_agent("docs")
    assert agent is agent2


def test_get_sheets_agent(orchestrator):
    """Test creating sheets agent."""
    agent = orchestrator._get_agent("sheets")
    assert agent is not None
    assert agent.user_id == "test_user"
    # Agent should be cached
    agent2 = orchestrator._get_agent("sheets")
    assert agent is agent2


def test_get_slides_agent(orchestrator):
    """Test creating slides agent."""
    agent = orchestrator._get_agent("slides")
    assert agent is not None
    assert agent.user_id == "test_user"
    # Agent should be cached
    agent2 = orchestrator._get_agent("slides")
    assert agent is agent2


def test_get_invalid_agent(orchestrator):
    """Test error when requesting invalid agent type."""
    with pytest.raises(ValueError, match="Unknown agent type"):
        orchestrator._get_agent("invalid_agent")


def test_multiple_agents_cached(orchestrator):
    """Test multiple agents are created and cached correctly."""
    research = orchestrator._get_agent("research")
    docs = orchestrator._get_agent("docs")
    sheets = orchestrator._get_agent("sheets")
    slides = orchestrator._get_agent("slides")

    assert len(orchestrator._agents) == 4
    assert "research" in orchestrator._agents
    assert "docs" in orchestrator._agents
    assert "sheets" in orchestrator._agents
    assert "slides" in orchestrator._agents

    # All should be different instances
    assert research is not docs
    assert docs is not sheets
    assert sheets is not slides


@pytest.mark.asyncio
async def test_decompose_task_basic(orchestrator):
    """Test task decomposition."""
    with patch.object(orchestrator.llm, 'ainvoke', new_callable=AsyncMock) as mock_llm:
        # Mock LLM response
        mock_response = Mock()
        mock_response.content = """
        [
            {
                "task_id": "1",
                "agent_type": "research",
                "description": "Research the topic",
                "dependencies": []
            },
            {
                "task_id": "2",
                "agent_type": "docs",
                "description": "Write document",
                "dependencies": ["1"]
            }
        ]
        """
        mock_llm.return_value = mock_response

        tasks = await orchestrator.decompose_task("Create a research document")

        assert len(tasks) == 2
        assert tasks[0].agent_type == "research"
        assert tasks[1].agent_type == "docs"
        assert tasks[1].dependencies == ["1"]


@pytest.mark.asyncio
async def test_orchestrator_google_agents_have_credentials(orchestrator):
    """Test that Google-dependent agents receive credentials."""
    docs_agent = orchestrator._get_agent("docs")
    sheets_agent = orchestrator._get_agent("sheets")
    slides_agent = orchestrator._get_agent("slides")

    # These agents should have credentials
    assert hasattr(docs_agent, 'credentials')
    assert hasattr(sheets_agent, 'credentials')
    assert hasattr(slides_agent, 'credentials')

    # Research agent should not have credentials parameter
    research_agent = orchestrator._get_agent("research")
    # Research agent doesn't use credentials


def test_agent_task_creation():
    """Test AgentTask model creation."""
    task = AgentTask(
        task_id="test_1",
        agent_type="research",
        description="Test task",
        dependencies=["dep_1"],
        metadata={"key": "value"}
    )

    assert task.task_id == "test_1"
    assert task.agent_type == "research"
    assert task.description == "Test task"
    assert task.dependencies == ["dep_1"]
    assert task.metadata == {"key": "value"}


@pytest.mark.asyncio
async def test_orchestrator_session_isolation():
    """Test that different sessions create different orchestrators."""
    with patch.dict('os.environ', {
        'LANGFUSE_PUBLIC_KEY': 'test_public_key',
        'LANGFUSE_SECRET_KEY': 'test_secret_key',
        'OPENAI_API_KEY': 'test_openai_key',
    }):
        orch1 = MultiAgentOrchestrator(user_id="user1")
        orch2 = MultiAgentOrchestrator(user_id="user2")

        assert orch1.session_id != orch2.session_id
        assert orch1.user_id != orch2.user_id

        # Agents should be separate
        agent1 = orch1._get_agent("research")
        agent2 = orch2._get_agent("research")

        assert agent1 is not agent2
        assert agent1.user_id != agent2.user_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
