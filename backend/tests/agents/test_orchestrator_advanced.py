"""Advanced tests for MultiAgentOrchestrator - parsing, validation, and execution logic."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
import json

from app.agents.orchestrator import MultiAgentOrchestrator, AgentTask


class TestLLMContentNormalization:
    """Test LLM content normalization helpers."""

    def test_normalize_string_content(self):
        """Test normalizing string content."""
        result = MultiAgentOrchestrator._normalize_llm_content("Hello world")
        assert result == "Hello world"

    def test_normalize_list_of_strings(self):
        """Test normalizing list of strings."""
        result = MultiAgentOrchestrator._normalize_llm_content(["Line 1", "Line 2"])
        assert result == "Line 1\nLine 2"

    def test_normalize_list_of_dicts_with_text(self):
        """Test normalizing list of dicts with 'text' key."""
        content = [
            {"text": "Part 1"},
            {"text": "Part 2"},
        ]
        result = MultiAgentOrchestrator._normalize_llm_content(content)
        assert result == "Part 1\nPart 2"

    def test_normalize_list_of_objects_with_text_attribute(self):
        """Test normalizing list of objects with text attribute."""
        obj1 = Mock()
        obj1.text = "Content 1"
        obj2 = Mock()
        obj2.text = "Content 2"
        result = MultiAgentOrchestrator._normalize_llm_content([obj1, obj2])
        assert result == "Content 1\nContent 2"

    def test_normalize_mixed_list(self):
        """Test normalizing mixed list of strings, dicts, and objects."""
        obj = Mock()
        obj.text = "Object text"
        content = [
            "String part",
            {"text": "Dict part"},
            obj,
        ]
        result = MultiAgentOrchestrator._normalize_llm_content(content)
        assert result == "String part\nDict part\nObject text"

    def test_normalize_non_string_content(self):
        """Test normalizing non-string content (fallback to str())."""
        result = MultiAgentOrchestrator._normalize_llm_content(12345)
        assert result == "12345"


class TestJSONPayloadExtraction:
    """Test JSON payload extraction from markdown/text."""

    def test_extract_from_plain_json(self):
        """Test extracting from plain JSON string."""
        plan_text = '{"tasks": []}'
        result = MultiAgentOrchestrator._extract_json_payload(plan_text)
        assert result == '{"tasks": []}'

    def test_extract_from_markdown_fenced_block(self):
        """Test extracting from ```json``` fenced block."""
        plan_text = '''Here is the plan:
```json
{"tasks": [{"task_id": "task_1"}]}
```
Done!'''
        result = MultiAgentOrchestrator._extract_json_payload(plan_text)
        assert result == '{"tasks": [{"task_id": "task_1"}]}'

    def test_extract_from_generic_fenced_block(self):
        """Test extracting from ``` fenced block without language."""
        plan_text = '''Plan:
```
{"tasks": []}
```'''
        result = MultiAgentOrchestrator._extract_json_payload(plan_text)
        assert result == '{"tasks": []}'

    def test_extract_with_whitespace(self):
        """Test extraction handles whitespace correctly."""
        plan_text = '''```json
    
    {"tasks": []}
    
    ```'''
        result = MultiAgentOrchestrator._extract_json_payload(plan_text)
        assert result == '{"tasks": []}'


class TestTaskNormalization:
    """Test task entry normalization and validation."""

    def test_normalize_valid_tasks(self):
        """Test normalizing valid task entries."""
        raw_tasks = [
            {
                "task_id": "task_1",
                "agent_type": "research",
                "description": "Research topic",
                "dependencies": [],
            },
            {
                "task_id": "task_2",
                "agent_type": "docs",
                "description": "Create document",
                "dependencies": ["task_1"],
            },
        ]
        result = MultiAgentOrchestrator._normalize_task_entries(raw_tasks)
        assert len(result) == 2
        assert result[0]["task_id"] == "task_1"
        assert result[1]["agent_type"] == "docs"
        assert result[1]["dependencies"] == ["task_1"]

    def test_normalize_task_with_auto_generated_id(self):
        """Test normalizing task without explicit ID (auto-generated)."""
        raw_tasks = [
            {
                "agent_type": "research",
                "description": "Research task",
            }
        ]
        result = MultiAgentOrchestrator._normalize_task_entries(raw_tasks)
        assert result[0]["task_id"] == "task_1"

    def test_normalize_task_with_string_dependency(self):
        """Test normalizing task with single string dependency."""
        raw_tasks = [
            {
                "task_id": "task_2",
                "agent_type": "docs",
                "description": "Write doc",
                "dependencies": "task_1",  # Single string
            }
        ]
        result = MultiAgentOrchestrator._normalize_task_entries(raw_tasks)
        assert result[0]["dependencies"] == ["task_1"]

    def test_normalize_task_with_metadata(self):
        """Test normalizing task with metadata."""
        raw_tasks = [
            {
                "task_id": "task_1",
                "agent_type": "research",
                "description": "Research",
                "metadata": {"priority": "high", "tags": ["urgent"]},
            }
        ]
        result = MultiAgentOrchestrator._normalize_task_entries(raw_tasks)
        assert result[0]["metadata"] == {"priority": "high", "tags": ["urgent"]}

    def test_normalize_task_lowercases_agent_type(self):
        """Test agent_type is normalized to lowercase."""
        raw_tasks = [
            {
                "task_id": "task_1",
                "agent_type": "RESEARCH",
                "description": "Research",
            }
        ]
        result = MultiAgentOrchestrator._normalize_task_entries(raw_tasks)
        assert result[0]["agent_type"] == "research"

    def test_normalize_task_removes_duplicate_dependencies(self):
        """Test duplicate dependencies are removed."""
        raw_tasks = [
            {
                "task_id": "task_2",
                "agent_type": "docs",
                "description": "Write",
                "dependencies": ["task_1", "task_1", "task_1"],
            }
        ]
        result = MultiAgentOrchestrator._normalize_task_entries(raw_tasks)
        assert result[0]["dependencies"] == ["task_1"]

    def test_normalize_rejects_non_dict_task(self):
        """Test normalizing rejects non-dictionary task entries."""
        raw_tasks = ["not a dict"]
        with pytest.raises(ValueError, match="expected object"):
            MultiAgentOrchestrator._normalize_task_entries(raw_tasks)

    def test_normalize_rejects_empty_task_id(self):
        """Test normalizing rejects empty task_id."""
        raw_tasks = [
            {
                "task_id": "   ",
                "agent_type": "research",
                "description": "Research",
            }
        ]
        with pytest.raises(ValueError, match="empty task_id"):
            MultiAgentOrchestrator._normalize_task_entries(raw_tasks)

    def test_normalize_rejects_missing_agent_type(self):
        """Test normalizing rejects missing agent_type."""
        raw_tasks = [
            {
                "task_id": "task_1",
                "description": "Research",
            }
        ]
        with pytest.raises(ValueError, match="missing agent_type"):
            MultiAgentOrchestrator._normalize_task_entries(raw_tasks)

    def test_normalize_rejects_unsupported_agent_type(self):
        """Test normalizing rejects unsupported agent type."""
        raw_tasks = [
            {
                "task_id": "task_1",
                "agent_type": "invalid_agent",
                "description": "Task",
            }
        ]
        with pytest.raises(ValueError, match="unsupported agent_type"):
            MultiAgentOrchestrator._normalize_task_entries(raw_tasks)

    def test_normalize_rejects_missing_description(self):
        """Test normalizing rejects missing description."""
        raw_tasks = [
            {
                "task_id": "task_1",
                "agent_type": "research",
            }
        ]
        with pytest.raises(ValueError, match="missing description"):
            MultiAgentOrchestrator._normalize_task_entries(raw_tasks)

    def test_normalize_rejects_non_list_dependencies(self):
        """Test normalizing rejects invalid dependency type."""
        raw_tasks = [
            {
                "task_id": "task_1",
                "agent_type": "research",
                "description": "Research",
                "dependencies": {"invalid": "type"},
            }
        ]
        with pytest.raises(ValueError, match="dependencies must be a list or string"):
            MultiAgentOrchestrator._normalize_task_entries(raw_tasks)

    def test_normalize_rejects_non_dict_metadata(self):
        """Test normalizing rejects invalid metadata type."""
        raw_tasks = [
            {
                "task_id": "task_1",
                "agent_type": "research",
                "description": "Research",
                "metadata": "invalid",
            }
        ]
        with pytest.raises(ValueError, match="metadata must be an object"):
            MultiAgentOrchestrator._normalize_task_entries(raw_tasks)


class TestDependencyValidation:
    """Test task dependency validation logic."""

    def test_validate_valid_dependencies(self):
        """Test validating valid task dependencies."""
        tasks = [
            {
                "task_id": "task_1",
                "agent_type": "research",
                "description": "Research",
                "dependencies": [],
            },
            {
                "task_id": "task_2",
                "agent_type": "docs",
                "description": "Write",
                "dependencies": ["task_1"],
            },
        ]
        # Should not raise
        MultiAgentOrchestrator._validate_task_dependencies(tasks)

    def test_validate_detects_duplicate_task_ids(self):
        """Test detecting duplicate task IDs."""
        tasks = [
            {
                "task_id": "task_1",
                "agent_type": "research",
                "description": "Research",
                "dependencies": [],
            },
            {
                "task_id": "task_1",  # Duplicate!
                "agent_type": "docs",
                "description": "Write",
                "dependencies": [],
            },
        ]
        with pytest.raises(ValueError, match="Duplicate task_id"):
            MultiAgentOrchestrator._validate_task_dependencies(tasks)

    def test_validate_detects_missing_dependencies(self):
        """Test detecting missing dependency references."""
        tasks = [
            {
                "task_id": "task_2",
                "agent_type": "docs",
                "description": "Write",
                "dependencies": ["task_1", "task_999"],  # task_999 doesn't exist
            },
        ]
        with pytest.raises(ValueError, match="Unknown task dependencies"):
            MultiAgentOrchestrator._validate_task_dependencies(tasks)

    def test_validate_detects_circular_dependency_simple(self):
        """Test detecting simple circular dependency (self-reference)."""
        tasks = [
            {
                "task_id": "task_1",
                "agent_type": "research",
                "description": "Research",
                "dependencies": ["task_1"],  # Self-reference
            },
        ]
        with pytest.raises(ValueError, match="Circular task dependency"):
            MultiAgentOrchestrator._validate_task_dependencies(tasks)

    def test_validate_detects_circular_dependency_complex(self):
        """Test detecting complex circular dependency (A -> B -> C -> A)."""
        tasks = [
            {
                "task_id": "task_1",
                "agent_type": "research",
                "description": "Research",
                "dependencies": ["task_3"],  # Depends on task_3
            },
            {
                "task_id": "task_2",
                "agent_type": "docs",
                "description": "Write",
                "dependencies": ["task_1"],
            },
            {
                "task_id": "task_3",
                "agent_type": "sheets",
                "description": "Analyze",
                "dependencies": ["task_2"],  # Circular: task_3 -> task_2 -> task_1 -> task_3
            },
        ]
        with pytest.raises(ValueError, match="Circular task dependency"):
            MultiAgentOrchestrator._validate_task_dependencies(tasks)

    def test_validate_allows_dag(self):
        """Test validating allows directed acyclic graph (DAG) dependencies."""
        tasks = [
            {
                "task_id": "task_1",
                "agent_type": "research",
                "description": "Research",
                "dependencies": [],
            },
            {
                "task_id": "task_2",
                "agent_type": "docs",
                "description": "Write",
                "dependencies": ["task_1"],
            },
            {
                "task_id": "task_3",
                "agent_type": "slides",
                "description": "Present",
                "dependencies": ["task_1", "task_2"],  # Multiple dependencies
            },
        ]
        # Should not raise
        MultiAgentOrchestrator._validate_task_dependencies(tasks)


class TestTaskPlanParsing:
    """Test task plan parsing from various formats."""

    def test_parse_task_list(self):
        """Test parsing direct task list."""
        raw_plan = [
            {
                "task_id": "task_1",
                "agent_type": "research",
                "description": "Research",
                "dependencies": [],
            }
        ]
        result = MultiAgentOrchestrator._parse_task_plan(raw_plan)
        assert len(result) == 1
        assert result[0]["task_id"] == "task_1"

    def test_parse_task_dict_with_tasks_key(self):
        """Test parsing dict with 'tasks' key."""
        raw_plan = {
            "tasks": [
                {
                    "task_id": "task_1",
                    "agent_type": "research",
                    "description": "Research",
                }
            ]
        }
        result = MultiAgentOrchestrator._parse_task_plan(raw_plan)
        assert len(result) == 1

    def test_parse_task_dict_with_plan_tasks_key(self):
        """Test parsing dict with nested 'plan.tasks' key."""
        raw_plan = {
            "plan": {
                "tasks": [
                    {
                        "task_id": "task_1",
                        "agent_type": "research",
                        "description": "Research",
                    }
                ]
            }
        }
        result = MultiAgentOrchestrator._parse_task_plan(raw_plan)
        assert len(result) == 1

    def test_parse_task_mapping(self):
        """Test parsing task mapping (task_id -> task object)."""
        raw_plan = {
            "task_1": {
                "agent_type": "research",
                "description": "Research",
            },
            "task_2": {
                "agent_type": "docs",
                "description": "Write",
            },
        }
        result = MultiAgentOrchestrator._parse_task_plan(raw_plan)
        assert len(result) == 2
        task_ids = [task["task_id"] for task in result]
        assert "task_1" in task_ids
        assert "task_2" in task_ids

    def test_parse_json_string(self):
        """Test parsing JSON string."""
        raw_plan = '{"tasks": [{"task_id": "task_1", "agent_type": "research", "description": "Research"}]}'
        result = MultiAgentOrchestrator._parse_task_plan(raw_plan)
        assert len(result) == 1

    def test_parse_markdown_fenced_json(self):
        """Test parsing JSON from markdown fenced block."""
        raw_plan = '''Here is the plan:
```json
{
  "tasks": [
    {
      "task_id": "task_1",
      "agent_type": "research",
      "description": "Research renewable energy"
    }
  ]
}
```'''
        result = MultiAgentOrchestrator._parse_task_plan(raw_plan)
        assert len(result) == 1
        assert result[0]["description"] == "Research renewable energy"

    def test_parse_rejects_empty_plan(self):
        """Test parsing rejects empty plan content."""
        with pytest.raises(ValueError, match="empty content"):
            MultiAgentOrchestrator._parse_task_plan("")

    def test_parse_rejects_no_tasks(self):
        """Test parsing rejects plan with no tasks."""
        raw_plan = {"tasks": []}
        with pytest.raises(ValueError, match="no tasks"):
            MultiAgentOrchestrator._parse_task_plan(raw_plan)

    def test_parse_rejects_invalid_structure(self):
        """Test parsing rejects invalid plan structure."""
        raw_plan = {"invalid_key": "value"}
        with pytest.raises(ValueError, match="must be a list of tasks or an object containing 'tasks'"):
            MultiAgentOrchestrator._parse_task_plan(raw_plan)


class TestAgentTaskClass:
    """Test AgentTask class."""

    def test_agent_task_initialization(self):
        """Test AgentTask initialization."""
        task = AgentTask(
            task_id="task_1",
            agent_type="research",
            description="Research topic",
            dependencies=["task_0"],
            metadata={"priority": "high"},
        )
        assert task.task_id == "task_1"
        assert task.agent_type == "research"
        assert task.description == "Research topic"
        assert task.dependencies == ["task_0"]
        assert task.metadata == {"priority": "high"}
        assert task.status == "pending"
        assert task.result is None
        assert task.error is None

    def test_agent_task_defaults(self):
        """Test AgentTask default values."""
        task = AgentTask(
            task_id="task_1",
            agent_type="research",
            description="Research",
        )
        assert task.dependencies == []
        assert task.metadata == {}


class TestOrchestratorHelpers:
    """Test orchestrator helper methods."""

    def test_looks_like_task_list_valid(self):
        """Test recognizing valid task list."""
        payload = [
            {"task_id": "task_1", "agent_type": "research", "description": "Research"},
            {"task_id": "task_2", "agent_type": "docs", "description": "Write"},
        ]
        assert MultiAgentOrchestrator._looks_like_task_list(payload) is True

    def test_looks_like_task_list_invalid(self):
        """Test rejecting invalid task list."""
        assert MultiAgentOrchestrator._looks_like_task_list([]) is False
        assert MultiAgentOrchestrator._looks_like_task_list(["string"]) is False
        assert MultiAgentOrchestrator._looks_like_task_list([{"no_task_keys": "value"}]) is False

    def test_looks_like_task_mapping_valid(self):
        """Test recognizing valid task mapping."""
        payload = {
            "task_1": {"task_id": "task_1", "agent_type": "research", "description": "Research"},
            "task_2": {"task_id": "task_2", "agent_type": "docs", "description": "Write"},
        }
        assert MultiAgentOrchestrator._looks_like_task_mapping(payload) is True

    def test_looks_like_task_mapping_invalid(self):
        """Test rejecting invalid task mapping."""
        assert MultiAgentOrchestrator._looks_like_task_mapping({}) is False
        assert MultiAgentOrchestrator._looks_like_task_mapping({"key": "value"}) is False

    def test_coerce_raw_tasks_from_list(self):
        """Test coercing tasks from list (passthrough)."""
        raw_tasks = [{"task_id": "task_1"}]
        result = MultiAgentOrchestrator._coerce_raw_tasks(raw_tasks, field_name="tasks")
        assert result == raw_tasks

    def test_coerce_raw_tasks_from_mapping(self):
        """Test coercing tasks from mapping to list."""
        raw_tasks = {
            "task_1": {"agent_type": "research", "description": "Research"},
            "task_2": {"agent_type": "docs", "description": "Write"},
        }
        result = MultiAgentOrchestrator._coerce_raw_tasks(raw_tasks, field_name="tasks")
        assert len(result) == 2
        assert result[0]["task_id"] == "task_1"
        assert result[1]["task_id"] == "task_2"

    def test_coerce_raw_tasks_rejects_invalid_type(self):
        """Test coercing rejects invalid task container type."""
        with pytest.raises(ValueError, match="must be a task list or task mapping"):
            MultiAgentOrchestrator._coerce_raw_tasks("invalid", field_name="tasks")


@pytest.mark.asyncio
class TestOrchestratorExecution:
    """Test orchestrator execution methods (with mocking)."""

    @pytest.fixture
    def mock_credentials(self):
        """Mock Google credentials."""
        credentials = Mock()
        credentials.token = "mock_token"
        credentials.refresh_token = "mock_refresh"
        credentials.expiry = None
        return credentials

    @pytest.fixture
    def orchestrator(self, mock_credentials):
        """Create orchestrator instance with mocked LLM."""
        with patch.dict('os.environ', {
            'OPENAI_API_KEY': 'test_key',
            'LANGFUSE_PUBLIC_KEY': 'test_public_key',
            'LANGFUSE_SECRET_KEY': 'test_secret_key',
        }):
            return MultiAgentOrchestrator(
                user_id="test_user",
                google_credentials=mock_credentials,
            )

    async def test_execute_task_success(self, orchestrator):
        """Test executing single task successfully."""
        task = AgentTask(
            task_id="task_1",
            agent_type="research",
            description="Research AI",
        )

        # Mock agent and its run method
        mock_agent = AsyncMock()
        mock_agent.run.return_value = {
            "success": True,
            "output": "AI research complete",
        }
        orchestrator._agents["research"] = mock_agent

        result = await orchestrator.execute_task(task)

        assert result["success"] is True
        assert task.status == "completed"
        assert task.result["output"] == "AI research complete"
        mock_agent.run.assert_called_once()

    async def test_execute_task_failure(self, orchestrator):
        """Test executing single task with failure."""
        task = AgentTask(
            task_id="task_1",
            agent_type="research",
            description="Research AI",
        )

        # Mock agent with failure
        mock_agent = AsyncMock()
        mock_agent.run.return_value = {
            "success": False,
            "error": "Connection timeout",
        }
        orchestrator._agents["research"] = mock_agent

        result = await orchestrator.execute_task(task)

        assert result["success"] is False
        assert task.status == "failed"
        assert task.error == "Connection timeout"

    async def test_execute_task_exception(self, orchestrator):
        """Test executing task with exception."""
        task = AgentTask(
            task_id="task_1",
            agent_type="research",
            description="Research AI",
        )

        # Mock agent that raises exception
        mock_agent = AsyncMock()
        mock_agent.run.side_effect = RuntimeError("Agent crashed")
        orchestrator._agents["research"] = mock_agent

        result = await orchestrator.execute_task(task)

        assert result["success"] is False
        assert task.status == "failed"
        assert "Agent crashed" in task.error

    async def test_execute_tasks_parallel_no_dependencies(self, orchestrator):
        """Test executing multiple tasks in parallel (no dependencies)."""
        tasks = [
            AgentTask(task_id="task_1", agent_type="research", description="Research AI"),
            AgentTask(task_id="task_2", agent_type="research", description="Research ML"),
        ]

        # Mock agents
        mock_agent = AsyncMock()
        mock_agent.run.return_value = {"success": True, "output": "Done"}
        orchestrator._agents["research"] = mock_agent

        completed = await orchestrator.execute_tasks(tasks)

        assert len(completed) == 2
        assert all(task.status == "completed" for task in completed)
        assert mock_agent.run.call_count == 2

    async def test_execute_tasks_with_dependencies(self, orchestrator):
        """Test executing tasks with dependencies in correct order."""
        task1 = AgentTask(task_id="task_1", agent_type="research", description="Research", dependencies=[])
        task2 = AgentTask(task_id="task_2", agent_type="docs", description="Write", dependencies=["task_1"])

        tasks = [task1, task2]

        # Mock agents
        mock_research = AsyncMock()
        mock_research.run.return_value = {"success": True, "output": "Research done"}
        mock_docs = AsyncMock()
        mock_docs.run.return_value = {"success": True, "output": "Document created"}

        orchestrator._agents["research"] = mock_research
        orchestrator._agents["docs"] = mock_docs

        completed = await orchestrator.execute_tasks(tasks)

        assert len(completed) == 2
        assert completed[0].status == "completed"
        assert completed[1].status == "completed"

    async def test_execute_tasks_stops_on_dependency_failure(self, orchestrator):
        """Test execution stops when dependency fails."""
        task1 = AgentTask(task_id="task_1", agent_type="research", description="Research", dependencies=[])
        task2 = AgentTask(task_id="task_2", agent_type="docs", description="Write", dependencies=["task_1"])

        tasks = [task1, task2]

        # Mock research agent to fail
        mock_research = AsyncMock()
        mock_research.run.return_value = {"success": False, "error": "Failed"}
        orchestrator._agents["research"] = mock_research

        completed = await orchestrator.execute_tasks(tasks)

        assert task1.status == "failed"
        assert task2.status == "pending"  # Should not execute


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
