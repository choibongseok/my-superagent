"""Tests for WebSocket ConnectionManager bug fixes.

Covers:
- Bug 1: disconnect() must not remove user from global chat rooms when other
  connections of the same user are still in that room.
- Bug 2: leave_chat() must update per-connection chat_rooms tracking.
- Bug 3: task_type enum is serialised to string before emitting WS events.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.core.websocket import ConnectionManager, ConnectionInfo, EventType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ws(*, accept: bool = True) -> MagicMock:
    """Return a mock WebSocket that records sent messages."""
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


# ---------------------------------------------------------------------------
# Bug 1 – disconnect with multiple connections
# ---------------------------------------------------------------------------

class TestDisconnectMultiConnection:
    """When a user has two connections in the same chat, disconnecting one
    must NOT remove the user from the global chat room."""

    @pytest.mark.asyncio
    async def test_user_stays_in_chat_when_other_conn_active(self):
        mgr = ConnectionManager()
        user_id = uuid4()
        chat_id = uuid4()

        ws1 = _make_ws()
        ws2 = _make_ws()

        # Connect both
        conn1 = await mgr.connect(ws1, user_id)
        conn2 = await mgr.connect(ws2, user_id)

        # Both join the same chat
        mgr.join_chat(chat_id, user_id, ws1)
        mgr.join_chat(chat_id, user_id, ws2)

        assert user_id in mgr.chat_rooms.get(chat_id, set())

        # Disconnect ws1 – user should STILL be in chat via ws2
        mgr.disconnect(ws1, user_id)

        assert user_id in mgr.active_connections
        assert user_id in mgr.chat_rooms.get(chat_id, set()), \
            "User removed from chat room despite having another connection in it"

    @pytest.mark.asyncio
    async def test_user_removed_from_chat_when_last_conn_drops(self):
        mgr = ConnectionManager()
        user_id = uuid4()
        chat_id = uuid4()

        ws1 = _make_ws()
        conn1 = await mgr.connect(ws1, user_id)
        mgr.join_chat(chat_id, user_id, ws1)

        assert user_id in mgr.chat_rooms.get(chat_id, set())

        mgr.disconnect(ws1, user_id)

        assert user_id not in mgr.active_connections
        assert chat_id not in mgr.chat_rooms or user_id not in mgr.chat_rooms[chat_id], \
            "User still in chat room after all connections closed"

    @pytest.mark.asyncio
    async def test_only_unshared_rooms_cleaned_on_partial_disconnect(self):
        """If ws1 is in chat A+B and ws2 is only in chat B,
        disconnecting ws1 should remove user from A but keep B."""
        mgr = ConnectionManager()
        user_id = uuid4()
        chat_a = uuid4()
        chat_b = uuid4()

        ws1 = _make_ws()
        ws2 = _make_ws()

        await mgr.connect(ws1, user_id)
        await mgr.connect(ws2, user_id)

        mgr.join_chat(chat_a, user_id, ws1)
        mgr.join_chat(chat_b, user_id, ws1)
        mgr.join_chat(chat_b, user_id, ws2)

        mgr.disconnect(ws1, user_id)

        assert user_id not in mgr.chat_rooms.get(chat_a, set()), \
            "User should be removed from chat_a (only ws1 was in it)"
        assert user_id in mgr.chat_rooms.get(chat_b, set()), \
            "User should stay in chat_b (ws2 is still in it)"


# ---------------------------------------------------------------------------
# Bug 2 – leave_chat per-connection tracking
# ---------------------------------------------------------------------------

class TestLeaveChatTracking:
    """leave_chat must update per-connection chat_rooms so that disconnect()
    doesn't try to remove the user from already-left rooms."""

    @pytest.mark.asyncio
    async def test_leave_chat_clears_conn_tracking(self):
        mgr = ConnectionManager()
        user_id = uuid4()
        chat_id = uuid4()

        ws = _make_ws()
        conn = await mgr.connect(ws, user_id)
        mgr.join_chat(chat_id, user_id, ws)

        assert chat_id in conn.chat_rooms

        mgr.leave_chat(chat_id, user_id, ws)

        assert chat_id not in conn.chat_rooms, \
            "Per-connection chat_rooms not cleaned up on leave_chat"
        assert user_id not in mgr.chat_rooms.get(chat_id, set())

    @pytest.mark.asyncio
    async def test_leave_then_disconnect_no_double_removal(self):
        """After leave_chat, disconnect shouldn't try to remove again."""
        mgr = ConnectionManager()
        user_id = uuid4()
        chat_id = uuid4()

        ws = _make_ws()
        conn = await mgr.connect(ws, user_id)
        mgr.join_chat(chat_id, user_id, ws)
        mgr.leave_chat(chat_id, user_id, ws)

        # disconnect should not error
        mgr.disconnect(ws, user_id)

        assert user_id not in mgr.active_connections


# ---------------------------------------------------------------------------
# Bug 3 – task_type enum serialisation
# ---------------------------------------------------------------------------

class TestTaskEventSerialisation:
    """task_created must accept string task_type values (not enum objects)."""

    @pytest.mark.asyncio
    async def test_task_created_with_string_type(self):
        mgr = ConnectionManager()
        user_id = uuid4()
        task_id = uuid4()

        ws = _make_ws()
        await mgr.connect(ws, user_id)

        # Should not raise
        await mgr.task_created(user_id, task_id, "research")

        ws.send_json.assert_called_once()
        payload = ws.send_json.call_args[0][0]
        assert payload["type"] == "task_created"
        assert payload["task_type"] == "research"
        assert payload["task_id"] == str(task_id)

    @pytest.mark.asyncio
    async def test_task_failed_includes_error(self):
        mgr = ConnectionManager()
        user_id = uuid4()
        task_id = uuid4()

        ws = _make_ws()
        await mgr.connect(ws, user_id)

        await mgr.task_failed(user_id, task_id, "something broke")

        payload = ws.send_json.call_args[0][0]
        assert payload["type"] == "task_failed"
        assert payload["error"] == "something broke"
        assert payload["status"] == "failed"


# ---------------------------------------------------------------------------
# Heartbeat record_pong
# ---------------------------------------------------------------------------

class TestRecordPong:
    @pytest.mark.asyncio
    async def test_record_pong_updates_timestamp(self):
        mgr = ConnectionManager()
        user_id = uuid4()
        ws = _make_ws()

        conn = await mgr.connect(ws, user_id)
        old_pong = conn.last_pong

        # Simulate small delay
        await asyncio.sleep(0.01)
        mgr.record_pong(ws, user_id)

        assert conn.last_pong > old_pong
