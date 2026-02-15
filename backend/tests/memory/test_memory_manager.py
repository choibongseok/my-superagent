"""Tests for MemoryManager context retrieval behavior."""

from datetime import datetime, timezone

from app.memory.manager import MemoryManager


class DummyVectorMemory:
    """Simple test double for vector memory."""

    def get_relevant_context(self, query: str, k: int = 3) -> str:
        return f"vector match for: {query} (k={k})"


class RecordingVectorMemory(DummyVectorMemory):
    """Records scored-search arguments for delegation assertions."""

    def __init__(self):
        self.last_search_with_scores_kwargs = None

    def search_with_scores(self, **kwargs):
        self.last_search_with_scores_kwargs = kwargs
        return [{"content": "cached"}]


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

    def test_search_conversation_supports_multi_role_filters(self):
        manager = MemoryManager(
            user_id="test_user",
            session_id="test_session",
            use_vector_memory=False,
        )

        manager.add_system_message("project guardrails")
        manager.add_user_message("project kickoff")
        manager.add_ai_message("project summary")

        matches = manager.search_conversation("project", role=["system", "ai"])

        assert [message.content for message in matches] == [
            "project guardrails",
            "project summary",
        ]

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

    def test_search_conversation_supports_exact_match_mode(self):
        manager = MemoryManager(
            user_id="test_user",
            session_id="test_session",
            use_vector_memory=False,
        )

        manager.add_user_message("Project status")
        manager.add_ai_message("Project status update")
        manager.add_system_message("project status")

        default_matches = manager.search_conversation(
            "project status",
            match_mode="exact",
        )
        strict_matches = manager.search_conversation(
            "project status",
            match_mode="exact",
            case_sensitive=True,
        )

        assert [message.content for message in default_matches] == [
            "Project status",
            "project status",
        ]
        assert [message.content for message in strict_matches] == ["project status"]

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

    def test_search_conversation_supports_all_terms_match_mode(self):
        manager = MemoryManager(
            user_id="test_user",
            session_id="test_session",
            use_vector_memory=False,
        )

        manager.add_user_message("project alpha kickoff")
        manager.add_ai_message("project status")
        manager.add_system_message("alpha policy")

        matches = manager.search_conversation(
            "project alpha",
            match_mode="all_terms",
        )

        assert len(matches) == 1
        assert matches[0].content == "project alpha kickoff"

    def test_search_memory_passes_confidence_and_relevance_filters(self):
        manager = MemoryManager(
            user_id="test_user",
            session_id="test_session",
            use_vector_memory=False,
        )
        manager.vector_memory = RecordingVectorMemory()

        results = manager.search_memory(
            query="project status",
            k=4,
            score_threshold=0.65,
            min_confidence="moderate",
            min_relevance="medium",
        )

        assert results == [{"content": "cached"}]
        assert manager.vector_memory.last_search_with_scores_kwargs == {
            "query": "project status",
            "k": 4,
            "score_threshold": 0.65,
            "min_confidence": "moderate",
            "min_relevance": "medium",
            "filter_dict": None,
            "sort_by_score": False,
            "adaptive_threshold": True,
            "adaptive_std_multiplier": 1.5,
            "min_adaptive_threshold": 0.5,
            "max_score_gap": None,
            "min_score_margin": None,
            "min_relative_score": None,
            "include_score_context": False,
            "unique_content": False,
            "required_terms": None,
            "required_terms_mode": "all",
            "excluded_terms": None,
            "excluded_terms_mode": "any",
            "created_after": None,
            "created_before": None,
            "offset": None,
            "max_results_per_session": None,
        }

    def test_search_memory_supports_session_scoping_and_score_sorting(self):
        manager = MemoryManager(
            user_id="test_user",
            session_id="session-42",
            use_vector_memory=False,
        )
        manager.vector_memory = RecordingVectorMemory()

        results = manager.search_memory(
            query="roadmap",
            k=3,
            score_threshold=0.5,
            filter_dict={"topic": "planning"},
            session_only=True,
            sort_by_score=True,
        )

        assert results == [{"content": "cached"}]
        assert manager.vector_memory.last_search_with_scores_kwargs == {
            "query": "roadmap",
            "k": 3,
            "score_threshold": 0.5,
            "min_confidence": None,
            "min_relevance": None,
            "filter_dict": {
                "topic": "planning",
                "session_id": "session-42",
            },
            "sort_by_score": True,
            "adaptive_threshold": True,
            "adaptive_std_multiplier": 1.5,
            "min_adaptive_threshold": 0.5,
            "max_score_gap": None,
            "min_score_margin": None,
            "min_relative_score": None,
            "include_score_context": False,
            "unique_content": False,
            "required_terms": None,
            "required_terms_mode": "all",
            "excluded_terms": None,
            "excluded_terms_mode": "any",
            "created_after": None,
            "created_before": None,
            "offset": None,
            "max_results_per_session": None,
        }

    def test_search_memory_exposes_advanced_vector_scoring_controls(self):
        manager = MemoryManager(
            user_id="test_user",
            session_id="session-99",
            use_vector_memory=False,
        )
        manager.vector_memory = RecordingVectorMemory()

        results = manager.search_memory(
            query="release readiness",
            k=6,
            score_threshold=None,
            adaptive_threshold=True,
            adaptive_std_multiplier=2.0,
            min_adaptive_threshold=0.6,
            max_score_gap=0.08,
            min_score_margin=0.04,
            include_score_context=True,
            unique_content=True,
            offset=2,
        )

        assert results == [{"content": "cached"}]
        assert manager.vector_memory.last_search_with_scores_kwargs == {
            "query": "release readiness",
            "k": 6,
            "score_threshold": None,
            "min_confidence": None,
            "min_relevance": None,
            "filter_dict": None,
            "sort_by_score": False,
            "adaptive_threshold": True,
            "adaptive_std_multiplier": 2.0,
            "min_adaptive_threshold": 0.6,
            "max_score_gap": 0.08,
            "min_score_margin": 0.04,
            "min_relative_score": None,
            "include_score_context": True,
            "unique_content": True,
            "required_terms": None,
            "required_terms_mode": "all",
            "excluded_terms": None,
            "excluded_terms_mode": "any",
            "created_after": None,
            "created_before": None,
            "offset": 2,
            "max_results_per_session": None,
        }

    def test_search_memory_forwards_required_terms_controls(self):
        manager = MemoryManager(
            user_id="test_user",
            session_id="session-lexical",
            use_vector_memory=False,
        )
        manager.vector_memory = RecordingVectorMemory()

        manager.search_memory(
            query="launch prep",
            required_terms=["checklist", "launch"],
            required_terms_mode="any",
        )

        assert manager.vector_memory.last_search_with_scores_kwargs[
            "required_terms"
        ] == ["checklist", "launch"]
        assert (
            manager.vector_memory.last_search_with_scores_kwargs["required_terms_mode"]
            == "any"
        )

    def test_search_memory_supports_per_session_result_cap(self):
        manager = MemoryManager(
            user_id="test_user",
            session_id="session-99",
            use_vector_memory=False,
        )
        manager.vector_memory = RecordingVectorMemory()

        manager.search_memory(
            query="release readiness",
            max_results_per_session=1,
        )

        assert (
            manager.vector_memory.last_search_with_scores_kwargs[
                "max_results_per_session"
            ]
            == 1
        )

    def test_search_memory_forwards_negative_lexical_and_relative_controls(self):
        manager = MemoryManager(
            user_id="test_user",
            session_id="session-lexical",
            use_vector_memory=False,
        )
        manager.vector_memory = RecordingVectorMemory()

        manager.search_memory(
            query="launch prep",
            min_relative_score=0.9,
            excluded_terms=["deprecated", "archive"],
            excluded_terms_mode="all",
        )

        forwarded_kwargs = manager.vector_memory.last_search_with_scores_kwargs
        assert forwarded_kwargs["min_relative_score"] == 0.9
        assert forwarded_kwargs["excluded_terms"] == ["deprecated", "archive"]
        assert forwarded_kwargs["excluded_terms_mode"] == "all"

    def test_search_memory_forwards_timestamp_boundaries(self):
        manager = MemoryManager(
            user_id="test_user",
            session_id="session-time-window",
            use_vector_memory=False,
        )
        manager.vector_memory = RecordingVectorMemory()

        created_after = datetime(2026, 2, 15, 8, 0, tzinfo=timezone.utc)

        manager.search_memory(
            query="incident timeline",
            created_after=created_after,
            created_before="2026-02-15T12:00:00Z",
        )

        forwarded_kwargs = manager.vector_memory.last_search_with_scores_kwargs
        assert forwarded_kwargs["created_after"] == created_after
        assert forwarded_kwargs["created_before"] == "2026-02-15T12:00:00Z"
