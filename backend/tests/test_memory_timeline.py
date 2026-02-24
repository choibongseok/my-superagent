"""Tests for Agent Memory Timeline API (#243).

Tests cover:
  - GET /memory/timeline — paginated memory feed
  - GET /memory/search — semantic search
  - POST /memory — user-defined memories
  - DELETE /memory/{id} — removal
  - GET /memory/stats — usage statistics
  - Auth enforcement on all endpoints
  - _memory_to_entry helper
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.memory import _memory_to_entry, MemoryEntry
from app.core.security import create_access_token
from app.models.user import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _user(db: AsyncSession, email: str | None = None) -> User:
    u = User(id=uuid4(), email=email or f"mem-{uuid4().hex[:6]}@test.com", is_active=True)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


def _headers(user: User) -> dict:
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


def _make_mock_manager():
    """Create a mock MemoryManager."""
    mock_memories = [
        {
            "content": "User prefers Korean for reports",
            "score": 0.95,
            "metadata": {
                "created_at": "2026-02-20T10:00:00+00:00",
                "source": "user",
                "agent_type": "docs",
            },
        },
        {
            "content": "Q4 sales data in spreadsheet 'Sales-2026'",
            "score": 0.88,
            "metadata": {
                "created_at": "2026-02-18T14:30:00+00:00",
                "source": "research",
                "agent_type": "research",
            },
        },
        {
            "content": "Preferred chart type: bar chart",
            "score": 0.82,
            "metadata": {
                "created_at": "2026-02-15T09:00:00+00:00",
                "source": "conversation",
                "agent_type": "sheets",
            },
        },
    ]

    manager = MagicMock()
    manager.vector_memory = MagicMock()
    manager.get_turn_count.return_value = 42
    manager.search_memory.side_effect = lambda *args, **kwargs: mock_memories[
        kwargs.get("offset", 0): kwargs.get("offset", 0) + kwargs.get("k", len(mock_memories))
    ]
    manager.count_memories.return_value = len(mock_memories)
    manager.add_memory.return_value = "mem-abc-123"
    return manager


# ---------------------------------------------------------------------------
# Unit tests for _memory_to_entry helper
# ---------------------------------------------------------------------------

class TestMemoryToEntry:
    def test_basic_conversion(self):
        raw = {
            "content": "User likes dark mode",
            "score": 0.91,
            "metadata": {
                "created_at": "2026-02-20T10:00:00+00:00",
                "source": "user",
                "agent_type": "docs",
            },
        }
        entry = _memory_to_entry(raw)
        assert entry.content == "User likes dark mode"
        assert entry.score == 0.91
        assert entry.source == "user"
        assert entry.agent_type == "docs"
        assert entry.created_at == "2026-02-20T10:00:00+00:00"

    def test_handles_page_content_key(self):
        raw = {"page_content": "Some memory text", "metadata": {}}
        entry = _memory_to_entry(raw)
        assert entry.content == "Some memory text"

    def test_handles_empty_metadata(self):
        raw = {"content": "Hello", "metadata": {}}
        entry = _memory_to_entry(raw)
        assert entry.source is None
        assert entry.agent_type is None
        assert entry.created_at is None

    def test_handles_missing_metadata(self):
        raw = {"content": "No metadata"}
        entry = _memory_to_entry(raw)
        assert entry.metadata == {}

    def test_type_fallback_for_source(self):
        raw = {"content": "Hello", "metadata": {"type": "preference"}}
        entry = _memory_to_entry(raw)
        assert entry.source == "preference"


# ---------------------------------------------------------------------------
# GET /memory/timeline
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestMemoryTimeline:

    @patch("app.api.v1.memory._get_memory_manager")
    async def test_timeline_returns_memories(self, mock_get_mgr, async_client: AsyncClient, db: AsyncSession):
        user = await _user(db)
        mock_get_mgr.return_value = _make_mock_manager()

        resp = await async_client.get("/api/v1/memory/timeline", headers=_headers(user))
        assert resp.status_code == 200
        data = resp.json()
        assert "memories" in data
        assert "total" in data
        assert "has_more" in data
        assert data["total"] == 3
        assert len(data["memories"]) == 3

    @patch("app.api.v1.memory._get_memory_manager")
    async def test_timeline_pagination(self, mock_get_mgr, async_client: AsyncClient, db: AsyncSession):
        user = await _user(db)
        mock_get_mgr.return_value = _make_mock_manager()

        resp = await async_client.get(
            "/api/v1/memory/timeline?page=1&page_size=2", headers=_headers(user)
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["memories"]) == 2
        assert data["has_more"] is True

    @patch("app.api.v1.memory._get_memory_manager")
    async def test_timeline_page_2(self, mock_get_mgr, async_client: AsyncClient, db: AsyncSession):
        user = await _user(db)
        mock_get_mgr.return_value = _make_mock_manager()

        resp = await async_client.get(
            "/api/v1/memory/timeline?page=2&page_size=2", headers=_headers(user)
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["memories"]) == 1
        assert data["has_more"] is False

    @patch("app.api.v1.memory._get_memory_manager")
    async def test_timeline_page_reports_full_total(self, mock_get_mgr, async_client: AsyncClient, db: AsyncSession):
        user = await _user(db)
        manager = _make_mock_manager()

        all_memories = [
            {"content": f"Memory {i}", "metadata": {"created_at": f"2026-02-22T0{i:02d}:00:00+00:00", "agent_type": "docs"}} for i in range(1, 6)
        ]
        manager.search_memory.side_effect = lambda *args, **kwargs: all_memories[
            kwargs.get("offset", 0): kwargs.get("offset", 0) + kwargs.get("k", len(all_memories))
        ]
        manager.count_memories.return_value = len(all_memories)
        mock_get_mgr.return_value = manager

        resp = await async_client.get(
            "/api/v1/memory/timeline?page=1&page_size=2", headers=_headers(user)
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["memories"]) == 2
        assert data["has_more"] is True

    @patch("app.api.v1.memory._get_memory_manager")
    async def test_timeline_filter_by_agent_type(self, mock_get_mgr, async_client: AsyncClient, db: AsyncSession):
        user = await _user(db)
        mgr = _make_mock_manager()
        mock_get_mgr.return_value = mgr

        resp = await async_client.get(
            "/api/v1/memory/timeline?agent_type=docs", headers=_headers(user)
        )
        assert resp.status_code == 200
        call_kwargs = mgr.search_memory.call_args[1]
        assert call_kwargs["filter_dict"] == {"agent_type": "docs"}

    @patch("app.api.v1.memory._get_memory_manager")
    async def test_timeline_date_filters(self, mock_get_mgr, async_client: AsyncClient, db: AsyncSession):
        user = await _user(db)
        mgr = _make_mock_manager()
        mock_get_mgr.return_value = mgr

        resp = await async_client.get(
            "/api/v1/memory/timeline?after=2026-02-19T00:00:00Z&before=2026-02-21T00:00:00Z",
            headers=_headers(user),
        )
        assert resp.status_code == 200
        call_kwargs = mgr.search_memory.call_args[1]
        assert call_kwargs["created_after"] == "2026-02-19T00:00:00Z"
        assert call_kwargs["created_before"] == "2026-02-21T00:00:00Z"

    @patch("app.api.v1.memory._get_memory_manager")
    async def test_timeline_empty(self, mock_get_mgr, async_client: AsyncClient, db: AsyncSession):
        user = await _user(db)
        mgr = _make_mock_manager()
        mgr.search_memory.side_effect = None
        mgr.search_memory.return_value = []
        mgr.count_memories.return_value = 0
        mock_get_mgr.return_value = mgr

        resp = await async_client.get("/api/v1/memory/timeline", headers=_headers(user))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["memories"] == []
        assert data["has_more"] is False

    @patch("app.api.v1.memory._get_memory_manager")
    async def test_timeline_handles_exception(self, mock_get_mgr, async_client: AsyncClient, db: AsyncSession):
        user = await _user(db)
        mgr = _make_mock_manager()
        mgr.search_memory.side_effect = Exception("Vector store down")
        mgr.count_memories.side_effect = Exception("Vector store down")
        mock_get_mgr.return_value = mgr

        resp = await async_client.get("/api/v1/memory/timeline", headers=_headers(user))
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    async def test_timeline_requires_auth(self, async_client: AsyncClient):
        resp = await async_client.get("/api/v1/memory/timeline")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# GET /memory/search
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestMemorySearch:

    @patch("app.api.v1.memory._get_memory_manager")
    async def test_search_returns_results(self, mock_get_mgr, async_client: AsyncClient, db: AsyncSession):
        user = await _user(db)
        mock_get_mgr.return_value = _make_mock_manager()

        resp = await async_client.get(
            "/api/v1/memory/search?q=Korean+reports", headers=_headers(user)
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "Korean reports"
        assert data["total"] == 3
        assert len(data["results"]) == 3

    @patch("app.api.v1.memory._get_memory_manager")
    async def test_search_respects_limit(self, mock_get_mgr, async_client: AsyncClient, db: AsyncSession):
        user = await _user(db)
        mgr = _make_mock_manager()
        mock_get_mgr.return_value = mgr

        resp = await async_client.get("/api/v1/memory/search?q=test&limit=2", headers=_headers(user))
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 2

        mock_get_mgr.return_value.search_memory.assert_called()

    @patch("app.api.v1.memory._get_memory_manager")
    async def test_search_filter_by_agent_type(self, mock_get_mgr, async_client: AsyncClient, db: AsyncSession):
        user = await _user(db)
        mgr = _make_mock_manager()
        mock_get_mgr.return_value = mgr

        resp = await async_client.get("/api/v1/memory/search?agent_type=docs&q=Korean", headers=_headers(user))
        assert resp.status_code == 200
        call_kwargs = mgr.search_memory.call_args[1]
        assert call_kwargs["filter_dict"] == {"agent_type": "docs"}

    @patch("app.api.v1.memory._get_memory_manager")
    async def test_search_handles_exception(self, mock_get_mgr, async_client: AsyncClient, db: AsyncSession):
        user = await _user(db)
        mgr = _make_mock_manager()
        mgr.search_memory.side_effect = Exception("Vector store down")
        mock_get_mgr.return_value = mgr

        resp = await async_client.get("/api/v1/memory/search?q=Korean", headers=_headers(user))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["results"] == []


# ---------------------------------------------------------------------------
# POST /memory
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestMemoryCreate:

    @patch("app.api.v1.memory._get_memory_manager")
    async def test_create_memory_success(self, mock_get_mgr, async_client: AsyncClient, db: AsyncSession):
        user = await _user(db)
        mock_get_mgr.return_value = _make_mock_manager()

        resp = await async_client.post(
            "/api/v1/memory",
            json={"content": "Save this preference"},
            headers=_headers(user),
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["memory_id"] == "mem-abc-123"
        assert data["content"] == "Save this preference"
        assert "created_at" in data

    @patch("app.api.v1.memory._get_memory_manager")
    async def test_create_memory_empty_content_rejected(self, mock_get_mgr, async_client: AsyncClient, db: AsyncSession):
        user = await _user(db)
        mock_get_mgr.return_value = _make_mock_manager()

        resp = await async_client.post(
            "/api/v1/memory",
            json={"content": ""},
            headers=_headers(user),
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /memory/{memory_id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestMemoryDelete:

    @patch("app.api.v1.memory._get_memory_manager")
    async def test_delete_memory_success(self, mock_get_mgr, async_client: AsyncClient, db: AsyncSession):
        user = await _user(db)
        mgr = _make_mock_manager()
        mgr.vector_memory.delete_memory.return_value = True
        mock_get_mgr.return_value = mgr

        resp = await async_client.delete("/api/v1/memory/mem-abc-123", headers=_headers(user))

        assert resp.status_code == 204
        mgr.vector_memory.delete_memory.assert_called_once_with("mem-abc-123")

    @patch("app.api.v1.memory._get_memory_manager")
    async def test_delete_memory_not_found(self, mock_get_mgr, async_client: AsyncClient, db: AsyncSession):
        user = await _user(db)
        mgr = _make_mock_manager()
        mgr.vector_memory.delete_memory.return_value = False
        mock_get_mgr.return_value = mgr

        resp = await async_client.delete("/api/v1/memory/nope", headers=_headers(user))
        assert resp.status_code == 404

    @patch("app.api.v1.memory._get_memory_manager")
    async def test_delete_memory_store_error(self, mock_get_mgr, async_client: AsyncClient, db: AsyncSession):
        user = await _user(db)
        mgr = _make_mock_manager()
        mgr.vector_memory.delete_memory.side_effect = RuntimeError("db fail")
        mock_get_mgr.return_value = mgr

        resp = await async_client.delete("/api/v1/memory/fail", headers=_headers(user))
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /memory/stats
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestMemoryStats:

    @patch("app.api.v1.memory._get_memory_manager")
    async def test_memory_stats_success(self, mock_get_mgr, async_client: AsyncClient, db: AsyncSession):
        user = await _user(db)
        mgr = _make_mock_manager()
        mgr.vector_memory.get_memory_count.return_value = 12
        mock_get_mgr.return_value = mgr

        resp = await async_client.get("/api/v1/memory/stats", headers=_headers(user))

        assert resp.status_code == 200
        data = resp.json()
        assert data["conversation_turns"] == 42
        assert data["long_term_memories"] == 12

    @patch("app.api.v1.memory._get_memory_manager")
    async def test_memory_stats_fallback_if_vector_unavailable(self, mock_get_mgr, async_client: AsyncClient, db: AsyncSession):
        user = await _user(db)
        mgr = _make_mock_manager()
        mgr.vector_memory = None
        mgr.count_memories.return_value = 0
        mock_get_mgr.return_value = mgr

        resp = await async_client.get("/api/v1/memory/stats", headers=_headers(user))

        assert resp.status_code == 200
        data = resp.json()
        assert data["conversation_turns"] == 42
        assert data["long_term_memories"] == 0


# ---------------------------------------------------------------------------
# Endpoint auth checks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestMemoryAuth:

    async def test_search_requires_auth(self, async_client: AsyncClient):
        resp = await async_client.get("/api/v1/memory/search?q=test")
        assert resp.status_code in (401, 403)

    async def test_create_requires_auth(self, async_client: AsyncClient):
        resp = await async_client.post("/api/v1/memory", json={"content": "x"})
        assert resp.status_code in (401, 403)

    async def test_delete_requires_auth(self, async_client: AsyncClient):
        resp = await async_client.delete("/api/v1/memory/mem-abc")
        assert resp.status_code in (401, 403)

    async def test_stats_requires_auth(self, async_client: AsyncClient):
        resp = await async_client.get("/api/v1/memory/stats")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------

class TestMemoryTimestamp:
    def test_memory_entry_created_at_default(self):
        entry = MemoryEntry(content="x")
        assert entry.created_at is None

    def test_to_dict_conversion(self):
        now = datetime.now(tz=timezone.utc).isoformat()
        response = {
            "content": "x",
            "metadata": {
                "created_at": now,
                "agent_type": "docs",
            },
        }
        entry = _memory_to_entry(response)
        assert entry.created_at == now


