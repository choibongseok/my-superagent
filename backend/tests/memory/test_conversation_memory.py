"""Tests for Conversation Memory."""

import pytest
from langchain_core.messages import HumanMessage, AIMessage

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

        memory.add_user_message("Hello")
        memory.add_ai_message("Hi")

        data = memory.to_dict()

        assert data["user_id"] == "test_user"
        assert data["session_id"] == "test_session"
        assert len(data["messages"]) == 2
        assert data["messages"][0]["role"] == "human"
        assert data["messages"][1]["role"] == "ai"

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "user_id": "test_user",
            "session_id": "test_session",
            "messages": [
                {"role": "human", "content": "Hello"},
                {"role": "ai", "content": "Hi"},
            ],
            "metadata": {"turn_count": 1},
        }

        memory = ConversationMemory.from_dict(data)

        assert memory.user_id == "test_user"
        assert memory.session_id == "test_session"
        assert len(memory.get_messages()) == 2
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
