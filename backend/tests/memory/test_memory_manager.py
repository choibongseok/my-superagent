"""Tests for MemoryManager context retrieval behavior."""

from app.memory.manager import MemoryManager


class DummyVectorMemory:
    """Simple test double for vector memory."""

    def get_relevant_context(self, query: str, k: int = 3) -> str:
        return f"vector match for: {query} (k={k})"


class TestMemoryManagerContext:
    """Regression tests for get_context API compatibility."""

    def test_get_context_without_query_returns_conversation_context(self):
        manager = MemoryManager(
            user_id="test_user",
            session_id="test_session",
            use_vector_memory=False,
        )

        manager.add_user_message("Hello")
        manager.add_ai_message("Hi there")

        context = manager.get_context()

        assert "=== Recent Conversation ===" in context
        assert "Human: Hello" in context
        assert "AI: Hi there" in context

    def test_get_context_with_query_includes_vector_context(self):
        manager = MemoryManager(
            user_id="test_user",
            session_id="test_session",
            use_vector_memory=False,
        )
        manager.vector_memory = DummyVectorMemory()

        manager.add_user_message("Talk about weather")
        manager.add_ai_message("Sure, let's discuss weather")

        context = manager.get_context(query="weather", include_vector=True, vector_k=2)

        assert "=== Recent Conversation ===" in context
        assert "=== Relevant Past Memories ===" in context
        assert "vector match for: weather (k=2)" in context

    def test_search_conversation_delegates_to_conversation_memory(self):
        manager = MemoryManager(
            user_id="test_user",
            session_id="test_session",
            use_vector_memory=False,
        )

        manager.add_user_message("Need project timeline")
        manager.add_ai_message("Project timeline is in the docs")
        manager.add_user_message("Thanks")

        matches = manager.search_conversation("project", role="ai")

        assert len(matches) == 1
        assert matches[0].content == "Project timeline is in the docs"

    def test_add_system_message_is_included_in_context(self):
        manager = MemoryManager(
            user_id="test_user",
            session_id="test_session",
            use_vector_memory=False,
        )

        manager.add_system_message("Follow workspace policy")
        manager.add_user_message("Understood")

        context = manager.get_context()

        assert "System: Follow workspace policy" in context
        assert "Human: Understood" in context

    def test_search_conversation_supports_word_match_mode(self):
        manager = MemoryManager(
            user_id="test_user",
            session_id="test_session",
            use_vector_memory=False,
        )

        manager.add_user_message("python basics")
        manager.add_ai_message("pythonic style tips")

        matches = manager.search_conversation("python", match_mode="word")

        assert len(matches) == 1
        assert matches[0].content == "python basics"

    def test_search_conversation_supports_fuzzy_match_mode(self):
        manager = MemoryManager(
            user_id="test_user",
            session_id="test_session",
            use_vector_memory=False,
        )

        manager.add_user_message("I like pythonn")
        manager.add_ai_message("I like ruby")

        matches = manager.search_conversation(
            "python",
            match_mode="fuzzy",
            fuzzy_threshold=0.8,
        )

        assert len(matches) == 1
        assert matches[0].content == "I like pythonn"
