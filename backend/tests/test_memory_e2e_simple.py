"""Simplified Memory System E2E tests without DB dependencies.

Tests memory functionality in isolation without full DB fixture setup.
"""

import pytest
from datetime import datetime, timedelta

from app.memory.manager import MemoryManager


# ---------------------------------------------------------------------------
# Test 1: Basic Initialization
# ---------------------------------------------------------------------------

def test_memory_manager_without_vector():
    """Test MemoryManager with vector memory disabled."""
    manager = MemoryManager(
        user_id="test-user-001",
        session_id="session-001",
        use_vector_memory=False,
    )
    
    assert manager.user_id == "test-user-001"
    assert manager.session_id == "session-001"
    assert manager.use_vector_memory is False
    assert manager.conversation_memory is not None
    assert manager.vector_memory is None


def test_add_conversation_turn_no_vector():
    """Test adding conversation turns without vector storage."""
    manager = MemoryManager(
        user_id="test-user-002",
        session_id="session-002",
        use_vector_memory=False,
    )
    
    manager.add_turn(
        user_message="Hello, how are you?",
        ai_message="I'm doing great, thanks!",
        save_to_vector=False,
    )
    
    messages = manager.get_recent_messages(last_n=10)
    assert len(messages) >= 2
    assert any("Hello" in msg.content for msg in messages)


def test_get_conversation_context_no_vector():
    """Test retrieving conversation context without vector memory."""
    manager = MemoryManager(
        user_id="test-user-003",
        session_id="session-003",
        use_vector_memory=False,
    )
    
    manager.add_turn(
        user_message="What's the weather?",
        ai_message="It's sunny today.",
        save_to_vector=False,
    )
    
    context = manager.get_conversation_context()
    assert len(context) > 0
    assert ("weather" in context.lower() or "sunny" in context.lower())


def test_clear_conversation_no_vector():
    """Test clearing conversation memory."""
    manager = MemoryManager(
        user_id="test-user-004",
        session_id="session-004",
        use_vector_memory=False,
    )
    
    manager.add_turn(
        user_message="Test message",
        ai_message="Test response",
        save_to_vector=False,
    )
    
    messages_before = manager.get_recent_messages()
    assert len(messages_before) > 0
    
    manager.clear_conversation()
    
    messages_after = manager.get_recent_messages()
    assert len(messages_after) == 0


def test_get_metadata_no_vector():
    """Test retrieving memory manager metadata."""
    manager = MemoryManager(
        user_id="test-user-005",
        session_id="session-005",
        use_vector_memory=False,
    )
    
    manager.add_turn(
        user_message="Test",
        ai_message="Response",
        save_to_vector=False,
    )
    
    metadata = manager.get_metadata()
    assert "user_id" in metadata
    assert "session_id" in metadata
    assert "turn_count" in metadata
    assert metadata["user_id"] == "test-user-005"


def test_to_dict_export_no_vector():
    """Test exporting memory state to dictionary."""
    manager = MemoryManager(
        user_id="test-user-006",
        session_id="session-006",
        use_vector_memory=False,
    )
    
    manager.add_turn(
        user_message="Export test",
        ai_message="Export response",
        save_to_vector=False,
    )
    
    state = manager.to_dict()
    assert "user_id" in state
    assert "session_id" in state
    assert "conversation" in state
    assert "metadata" in state
    assert state["user_id"] == manager.user_id


def test_search_memory_disabled():
    """Test search_memory when vector memory is disabled."""
    manager = MemoryManager(
        user_id="test-user-007",
        session_id="session-007",
        use_vector_memory=False,
    )
    
    results = manager.search_memory("test query", k=5)
    assert results == []


def test_count_memories_disabled():
    """Test count_memories when vector memory is disabled."""
    manager = MemoryManager(
        user_id="test-user-008",
        session_id="session-008",
        use_vector_memory=False,
    )
    
    count = manager.count_memories()
    assert count == 0


# ---------------------------------------------------------------------------
# Test 2: Multiple Turns
# ---------------------------------------------------------------------------

def test_multiple_conversation_turns():
    """Test handling multiple conversation turns."""
    manager = MemoryManager(
        user_id="test-user-009",
        session_id="session-009",
        use_vector_memory=False,
    )
    
    conversations = [
        ("What's Python?", "Python is a programming language."),
        ("How do I install it?", "You can download from python.org"),
        ("What about packages?", "Use pip to install packages."),
    ]
    
    for user_msg, ai_msg in conversations:
        manager.add_turn(
            user_message=user_msg,
            ai_message=ai_msg,
            save_to_vector=False,
        )
    
    messages = manager.get_recent_messages()
    assert len(messages) >= 6  # 3 turns x 2 messages
    
    turn_count = manager.get_turn_count()
    assert turn_count >= 3


def test_get_recent_messages_limit():
    """Test retrieving limited number of recent messages."""
    manager = MemoryManager(
        user_id="test-user-010",
        session_id="session-010",
        use_vector_memory=False,
    )
    
    for i in range(5):
        manager.add_turn(
            user_message=f"User message {i}",
            ai_message=f"AI response {i}",
            save_to_vector=False,
        )
    
    # Get only last 4 messages
    recent_messages = manager.get_recent_messages(last_n=4)
    assert len(recent_messages) == 4


# ---------------------------------------------------------------------------
# Test 3: Context Retrieval
# ---------------------------------------------------------------------------

def test_get_context_with_no_query():
    """Test get_context without query (conversation only)."""
    manager = MemoryManager(
        user_id="test-user-011",
        session_id="session-011",
        use_vector_memory=False,
    )
    
    manager.add_turn(
        user_message="Tell me about AI",
        ai_message="AI stands for Artificial Intelligence.",
        save_to_vector=False,
    )
    
    # No query - should return conversation only
    context = manager.get_context()
    assert len(context) > 0
    assert "AI" in context or "ai" in context.lower()


def test_get_context_with_query_no_vector():
    """Test get_context with query when vector memory is disabled."""
    manager = MemoryManager(
        user_id="test-user-012",
        session_id="session-012",
        use_vector_memory=False,
    )
    
    manager.add_turn(
        user_message="Machine learning basics",
        ai_message="ML is a subset of AI.",
        save_to_vector=False,
    )
    
    # Query provided but vector disabled - should return conversation only
    context = manager.get_context(
        query="machine learning",
        include_conversation=True,
        include_vector=True,
    )
    
    assert len(context) > 0
    assert "Recent Conversation" in context


# ---------------------------------------------------------------------------
# Test 4: Edge Cases
# ---------------------------------------------------------------------------

def test_empty_conversation():
    """Test behavior with empty conversation."""
    manager = MemoryManager(
        user_id="test-user-013",
        session_id="session-013",
        use_vector_memory=False,
    )
    
    messages = manager.get_recent_messages()
    assert len(messages) == 0
    
    context = manager.get_conversation_context()
    assert context == "" or context is None


def test_add_system_message():
    """Test adding system messages."""
    manager = MemoryManager(
        user_id="test-user-014",
        session_id="session-014",
        use_vector_memory=False,
    )
    
    manager.add_system_message("System: New session started")
    
    messages = manager.get_recent_messages()
    assert len(messages) >= 1
    assert any("System" in msg.content for msg in messages)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

# Total: 15 tests
# All tests work without vector memory or DB dependencies
# Focused on core MemoryManager conversation handling
