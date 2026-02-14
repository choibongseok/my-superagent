"""Tests for VectorStoreMemory collection-management operations."""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from app.memory.vector_store import VectorStoreMemory


@contextmanager
def _session_context(session):
    """Yield a mocked SQLAlchemy session."""
    yield session


def _build_memory(
    embeddings,
    *,
    count=None,
    collection_exists=True,
    available=True,
):
    """Create a VectorStoreMemory instance without running __init__."""
    memory = object.__new__(VectorStoreMemory)
    memory.user_id = "test_user"
    memory.session_id = "active_session"
    memory.collection_name = "conversation_memory_test_user"
    memory.available = available

    session = MagicMock()
    query = MagicMock()
    session.query.return_value = query
    query.filter.return_value = query
    query.all.return_value = embeddings
    query.count.return_value = len(embeddings) if count is None else count

    vector_store = Mock()
    vector_store._make_session = Mock(side_effect=lambda: _session_context(session))
    vector_store.get_collection = Mock(
        return_value=(SimpleNamespace(uuid="collection-uuid") if collection_exists else None)
    )

    embedding_store = Mock()
    embedding_store.collection_id = Mock(name="collection_id")
    vector_store.EmbeddingStore = embedding_store

    memory.vector_store = vector_store

    return memory, session, vector_store, query


class TestVectorStoreManagement:
    """Tests for memory maintenance helpers."""

    def test_delete_session_memories_deletes_only_matching_session(self):
        target = SimpleNamespace(
            cmetadata={"user_id": "test_user", "session_id": "target_session"}
        )
        different_session = SimpleNamespace(
            cmetadata={"user_id": "test_user", "session_id": "other_session"}
        )
        different_user = SimpleNamespace(
            cmetadata={"user_id": "another_user", "session_id": "target_session"}
        )

        memory, session, _, _ = _build_memory(
            [target, different_session, different_user]
        )

        deleted_count = memory.delete_session_memories("target_session")

        assert deleted_count == 1
        session.delete.assert_called_once_with(target)
        session.commit.assert_called_once()

    def test_delete_session_memories_requires_session_id(self):
        memory, _, _, _ = _build_memory([])

        with pytest.raises(ValueError, match="session_id is required"):
            memory.delete_session_memories("")

    def test_clear_user_memories_deletes_all_user_records(self):
        owned_memory = SimpleNamespace(cmetadata={"user_id": "test_user"})
        cross_tenant_memory = SimpleNamespace(cmetadata={"user_id": "other"})
        missing_user_memory = SimpleNamespace(cmetadata={})

        memory, session, _, _ = _build_memory(
            [owned_memory, cross_tenant_memory, missing_user_memory]
        )

        deleted_count = memory.clear_user_memories()

        assert deleted_count == 2
        assert session.delete.call_count == 2
        session.delete.assert_any_call(owned_memory)
        session.delete.assert_any_call(missing_user_memory)
        session.commit.assert_called_once()

    def test_get_memory_count_returns_collection_count(self):
        memory, _, _, query = _build_memory([], count=7)

        result = memory.get_memory_count()

        assert result == 7
        query.count.assert_called_once()

    def test_collection_missing_returns_zero_without_deletion(self):
        memory, session, _, _ = _build_memory([], collection_exists=False)

        assert memory.delete_session_memories("missing_session") == 0
        assert memory.clear_user_memories() == 0
        assert memory.get_memory_count() == 0

        session.delete.assert_not_called()
        session.commit.assert_not_called()

    def test_unavailable_backend_returns_zero_gracefully(self):
        memory = object.__new__(VectorStoreMemory)
        memory.user_id = "test_user"
        memory.session_id = "active_session"
        memory.collection_name = "conversation_memory_test_user"
        memory.available = False
        memory.vector_store = Mock()

        assert memory.delete_session_memories("target_session") == 0
        assert memory.clear_user_memories() == 0
        assert memory.get_memory_count() == 0
