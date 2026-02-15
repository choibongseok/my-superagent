"""Tests for Conversation Memory."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.memory.conversation import ConversationMemory


class TestConversationMemory:
    """Test suite for ConversationMemory."""

    def test_initialization(self):
        """Test conversation memory initialization."""
        memory = ConversationMemory(
            user_id="test_user",
            session_id="test_session",
        )

        assert memory.user_id == "test_user"
        assert memory.session_id == "test_session"
        assert memory.get_turn_count() == 0

    def test_add_user_message(self):
        """Test adding user message."""
        memory = ConversationMemory(
            user_id="test_user",
            session_id="test_session",
        )

        memory.add_user_message("Hello, how are you?")

        messages = memory.get_messages()
        assert len(messages) == 1
        assert isinstance(messages[0], HumanMessage)
        assert messages[0].content == "Hello, how are you?"
        assert memory.get_turn_count() == 1

    def test_add_ai_message(self):
        """Test adding AI message."""
        memory = ConversationMemory(
            user_id="test_user",
            session_id="test_session",
        )

        memory.add_user_message("Hello!")
        memory.add_ai_message("Hi there!")

        messages = memory.get_messages()
        assert len(messages) == 2
        assert isinstance(messages[1], AIMessage)
        assert messages[1].content == "Hi there!"

    def test_add_system_message(self):
        """Test adding system message."""
        memory = ConversationMemory(
            user_id="test_user",
            session_id="test_session",
        )

        memory.add_system_message("System guidance")

        messages = memory.get_messages()
        assert len(messages) == 1
        assert isinstance(messages[0], SystemMessage)
        assert messages[0].content == "System guidance"

    def test_multi_turn_conversation(self):
        """Test multi-turn conversation."""
        memory = ConversationMemory(
            user_id="test_user",
            session_id="test_session",
        )

        # Turn 1
        memory.add_user_message("What's the weather?")
        memory.add_ai_message("It's sunny today.")

        # Turn 2
        memory.add_user_message("Should I bring an umbrella?")
        memory.add_ai_message("No, you won't need one.")

        messages = memory.get_messages()
        assert len(messages) == 4
        assert memory.get_turn_count() == 2

    def test_get_context(self):
        """Test getting conversation context."""
        memory = ConversationMemory(
            user_id="test_user",
            session_id="test_session",
        )

        memory.add_user_message("Hello")
        memory.add_ai_message("Hi")

        context = memory.get_context()
        assert "Human: Hello" in context
        assert "AI: Hi" in context

    def test_get_context_includes_system_messages(self):
        """Context rendering should include system role labels."""
        memory = ConversationMemory(
            user_id="test_user",
            session_id="test_session",
        )

        memory.add_system_message("Follow policy")
        memory.add_user_message("Hello")

        context = memory.get_context()
        assert "System: Follow policy" in context
        assert "Human: Hello" in context

    def test_get_last_n_messages(self):
        """Test getting last N messages."""
        memory = ConversationMemory(
            user_id="test_user",
            session_id="test_session",
        )

        # Add 5 messages
        for i in range(3):
            memory.add_user_message(f"User message {i}")
            memory.add_ai_message(f"AI message {i}")

        # Get last 2 messages
        last_messages = memory.get_messages(last_n=2)
        assert len(last_messages) == 2
        assert last_messages[-1].content == "AI message 2"

    def test_search_messages_filters_by_keyword_case_insensitive(self):
        """Test keyword search with default case-insensitive matching."""
        memory = ConversationMemory(
            user_id="test_user",
            session_id="test_session",
        )

        memory.add_user_message("Tell me about Python")
        memory.add_ai_message("PYTHON is great for automation")
        memory.add_user_message("Let's switch topics")

        matches = memory.search_messages("python")

        assert len(matches) == 2
        assert matches[0].content == "Tell me about Python"
        assert matches[1].content == "PYTHON is great for automation"

    def test_search_messages_can_filter_by_role_and_limit(self):
        """Test role filtering and result limiting in search."""
        memory = ConversationMemory(
            user_id="test_user",
            session_id="test_session",
        )

        memory.add_user_message("weather today")
        memory.add_ai_message("weather forecast: sunny")
        memory.add_user_message("weather this weekend")

        ai_matches = memory.search_messages("weather", role="ai")
        limited_matches = memory.search_messages("weather", role="human", limit=1)

        assert len(ai_matches) == 1
        assert isinstance(ai_matches[0], AIMessage)
        assert ai_matches[0].content == "weather forecast: sunny"

        assert len(limited_matches) == 1
        assert isinstance(limited_matches[0], HumanMessage)
        assert limited_matches[0].content == "weather today"

    def test_search_messages_supports_exact_matching(self):
        """exact mode should require full-message equality, not containment."""
        memory = ConversationMemory(
            user_id="test_user",
            session_id="test_session",
        )

        memory.add_user_message("project update")
        memory.add_ai_message("project update ready")
        memory.add_system_message("PROJECT UPDATE")

        default_matches = memory.search_messages("project update", match_mode="exact")
        case_sensitive_matches = memory.search_messages(
            "project update",
            match_mode="exact",
            case_sensitive=True,
        )

        assert [message.content for message in default_matches] == [
            "project update",
            "PROJECT UPDATE",
        ]
        assert [message.content for message in case_sensitive_matches] == [
            "project update",
        ]

    def test_search_messages_supports_system_role_filtering(self):
        """System role filter should return only system-authored messages."""
        memory = ConversationMemory(
            user_id="test_user",
            session_id="test_session",
        )

        memory.add_system_message("Use concise responses")
        memory.add_user_message("Tell me about Python")
        memory.add_ai_message("Python is great")

        matches = memory.search_messages("use", role="system")

        assert len(matches) == 1
        assert isinstance(matches[0], SystemMessage)
        assert matches[0].content == "Use concise responses"

    def test_search_messages_supports_starts_with_matching(self):
        """starts_with mode should match only leading query text."""
        memory = ConversationMemory(
            user_id="test_user",
            session_id="test_session",
        )

        memory.add_user_message("Release status: green")
        memory.add_ai_message("Status update: release on track")
        memory.add_system_message("release cadence policy")

        matches = memory.search_messages("release", match_mode="starts_with")

        assert [message.content for message in matches] == [
            "Release status: green",
            "release cadence policy",
        ]

    def test_search_messages_supports_ends_with_matching_case_sensitive(self):
        """ends_with mode should honor case_sensitive for trailing text checks."""
        memory = ConversationMemory(
            user_id="test_user",
            session_id="test_session",
        )

        memory.add_user_message("Checklist DONE")
        memory.add_ai_message("Checklist done")

        case_insensitive_matches = memory.search_messages(
            "done",
            match_mode="ends_with",
        )
        case_sensitive_matches = memory.search_messages(
            "done",
            match_mode="ends_with",
            case_sensitive=True,
        )

        assert [message.content for message in case_insensitive_matches] == [
            "Checklist DONE",
            "Checklist done",
        ]
        assert [message.content for message in case_sensitive_matches] == [
            "Checklist done",
        ]

    def test_search_messages_supports_multiple_role_filters(self):
        """Search role filters should accept iterables and comma-separated strings."""
        memory = ConversationMemory(
            user_id="test_user",
            session_id="test_session",
        )

        memory.add_system_message("project kickoff checklist")
        memory.add_user_message("project status update")
        memory.add_ai_message("project plan delivered")

        iterable_matches = memory.search_messages(
            "project",
            role=["system", "ai"],
        )
        comma_matches = memory.search_messages("project", role="human,ai")

        assert [message.content for message in iterable_matches] == [
            "project kickoff checklist",
            "project plan delivered",
        ]
        assert [message.content for message in comma_matches] == [
            "project status update",
            "project plan delivered",
        ]

    def test_search_messages_role_filter_any_in_iterable_matches_all_roles(self):
        """Including 'any' in role filters should include all message roles."""
        memory = ConversationMemory(
            user_id="test_user",
            session_id="test_session",
        )

        memory.add_system_message("project policy")
        memory.add_user_message("project question")
        memory.add_ai_message("project answer")

        matches = memory.search_messages("project", role=["system", "any"])

        assert len(matches) == 3

    def test_search_messages_respects_last_n_window(self):
        """Test restricting search scope with last_n."""
        memory = ConversationMemory(
            user_id="test_user",
            session_id="test_session",
        )

        memory.add_user_message("alpha target")
        memory.add_ai_message("middle")
        memory.add_user_message("omega target")

        matches = memory.search_messages("target", last_n=1)

        assert len(matches) == 1
        assert matches[0].content == "omega target"

    def test_search_messages_supports_whole_word_matching(self):
        """Whole-word mode should not match partial words."""
        memory = ConversationMemory(
            user_id="test_user",
            session_id="test_session",
        )

        memory.add_user_message("I like Python")
        memory.add_ai_message("Py-thon is hyphenated")
        memory.add_user_message("pythonic idioms are useful")

        matches = memory.search_messages("python", match_mode="word")

        assert len(matches) == 1
        assert matches[0].content == "I like Python"

    def test_search_messages_supports_regex_matching(self):
        """Regex mode should allow flexible pattern searches."""
        memory = ConversationMemory(
            user_id="test_user",
            session_id="test_session",
        )

        memory.add_user_message("Ticket ABC-123 is open")
        memory.add_ai_message("Ticket XYZ-999 is closed")

        matches = memory.search_messages(r"[A-Z]{3}-\d{3}", match_mode="regex")

        assert len(matches) == 2

    def test_search_messages_supports_fuzzy_matching(self):
        """Fuzzy mode should tolerate minor typos."""
        memory = ConversationMemory(
            user_id="test_user",
            session_id="test_session",
        )

        memory.add_user_message("I use pythonn for scripts")
        memory.add_ai_message("JavaScript is also nice")

        matches = memory.search_messages(
            "python",
            match_mode="fuzzy",
            fuzzy_threshold=0.8,
        )

        assert len(matches) == 1
        assert matches[0].content == "I use pythonn for scripts"

    def test_search_messages_supports_all_terms_matching(self):
        """all_terms mode should require all query terms in each message."""
        memory = ConversationMemory(
            user_id="test_user",
            session_id="test_session",
        )

        memory.add_user_message("project alpha kickoff notes")
        memory.add_ai_message("project timeline drafted")
        memory.add_system_message("alpha compliance checklist")

        matches = memory.search_messages("project alpha", match_mode="all_terms")

        assert [message.content for message in matches] == [
            "project alpha kickoff notes",
        ]

    def test_search_messages_supports_any_terms_matching(self):
        """any_terms mode should match when at least one query term appears."""
        memory = ConversationMemory(
            user_id="test_user",
            session_id="test_session",
        )

        memory.add_user_message("project alpha kickoff notes")
        memory.add_ai_message("project timeline drafted")
        memory.add_system_message("alpha compliance checklist")
        memory.add_ai_message("release retrospective")

        matches = memory.search_messages("project alpha", match_mode="any_terms")

        assert [message.content for message in matches] == [
            "project alpha kickoff notes",
            "project timeline drafted",
            "alpha compliance checklist",
        ]

    def test_search_messages_supports_phrase_matching(self):
        """phrase mode should match contiguous terms while ignoring punctuation."""
        memory = ConversationMemory(
            user_id="test_user",
            session_id="test_session",
        )

        memory.add_user_message("project kickoff checklist")
        memory.add_ai_message("project-kickoff timeline")
        memory.add_system_message("project final kickoff")

        matches = memory.search_messages("project kickoff", match_mode="phrase")

        assert [message.content for message in matches] == [
            "project kickoff checklist",
            "project-kickoff timeline",
        ]

    def test_search_messages_phrase_mode_respects_case_sensitive_option(self):
        """phrase mode should honor case sensitivity for term comparison."""
        memory = ConversationMemory(
            user_id="test_user",
            session_id="test_session",
        )

        memory.add_user_message("Project Kickoff checklist")
        memory.add_ai_message("project kickoff checklist")

        case_insensitive_matches = memory.search_messages(
            "Project Kickoff",
            match_mode="phrase",
        )
        case_sensitive_matches = memory.search_messages(
            "Project Kickoff",
            match_mode="phrase",
            case_sensitive=True,
        )

        assert [message.content for message in case_insensitive_matches] == [
            "Project Kickoff checklist",
            "project kickoff checklist",
        ]
        assert [message.content for message in case_sensitive_matches] == [
            "Project Kickoff checklist",
        ]

    def test_search_messages_rejects_invalid_inputs(self):
        """Test validation errors for invalid search parameters."""
        memory = ConversationMemory(
            user_id="test_user",
            session_id="test_session",
        )

        with pytest.raises(ValueError, match="query must be a non-empty string"):
            memory.search_messages("   ")

        with pytest.raises(ValueError, match="role must be one of"):
            memory.search_messages("hello", role="manager")

        with pytest.raises(ValueError, match="role must be one of"):
            memory.search_messages("hello", role=["human", "manager"])

        with pytest.raises(ValueError, match="role must be one of"):
            memory.search_messages("hello", role=[])

        with pytest.raises(ValueError, match="limit must be greater than 0"):
            memory.search_messages("hello", limit=0)

        with pytest.raises(ValueError, match="match_mode must be one of"):
            memory.search_messages("hello", match_mode="semantic")

        with pytest.raises(ValueError, match="fuzzy_threshold must be in"):
            memory.search_messages(
                "hello",
                match_mode="fuzzy",
                fuzzy_threshold=1.2,
            )

        with pytest.raises(ValueError, match="invalid regular expression"):
            memory.search_messages("(", match_mode="regex")

        with pytest.raises(ValueError, match="query must include at least one"):
            memory.search_messages("!!!", match_mode="phrase")

        with pytest.raises(ValueError, match="query must include at least one"):
            memory.search_messages("!!!", match_mode="all_terms")

    def test_clear_memory(self):
        """Test clearing conversation memory."""
        memory = ConversationMemory(
            user_id="test_user",
            session_id="test_session",
        )

        memory.add_user_message("Hello")
        memory.add_ai_message("Hi")

        assert len(memory.get_messages()) == 2

        memory.clear()

        assert len(memory.get_messages()) == 0
        assert memory.get_turn_count() == 0

    def test_to_dict(self):
        """Test exporting to dictionary."""
        memory = ConversationMemory(
            user_id="test_user",
            session_id="test_session",
        )

        memory.add_system_message("Stay brief")
        memory.add_user_message("Hello")
        memory.add_ai_message("Hi")

        data = memory.to_dict()

        assert data["user_id"] == "test_user"
        assert data["session_id"] == "test_session"
        assert len(data["messages"]) == 3
        assert data["messages"][0]["role"] == "system"
        assert data["messages"][1]["role"] == "human"
        assert data["messages"][2]["role"] == "ai"

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "user_id": "test_user",
            "session_id": "test_session",
            "messages": [
                {"role": "system", "content": "Stay brief"},
                {"role": "human", "content": "Hello"},
                {"role": "ai", "content": "Hi"},
            ],
            "metadata": {"turn_count": 1},
        }

        memory = ConversationMemory.from_dict(data)

        assert memory.user_id == "test_user"
        assert memory.session_id == "test_session"
        assert len(memory.get_messages()) == 3
        assert isinstance(memory.get_messages()[0], SystemMessage)
        assert memory.get_turn_count() == 1

    def test_metadata(self):
        """Test metadata tracking."""
        memory = ConversationMemory(
            user_id="test_user",
            session_id="test_session",
        )

        memory.add_user_message("Test")
        memory.add_ai_message("Response")

        metadata = memory.get_metadata()

        assert metadata["user_id"] == "test_user"
        assert metadata["session_id"] == "test_session"
        assert metadata["turn_count"] == 1
        assert "created_at" in metadata
        assert "last_updated" in metadata


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
