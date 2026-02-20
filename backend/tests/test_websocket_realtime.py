"""Tests for Phase 5 WebSocket Real-Time Updates.

Covers:
- ConnectionManager event helpers (task events, typing, presence)
- WebSocket endpoint message handling (join/leave/typing/ping/pong/presence)
- Server heartbeat loop
- Task API WebSocket emission integration
- WS stats health endpoint
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.core.websocket import ConnectionInfo, ConnectionManager, EventType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ws_mock() -> MagicMock:
    """Create a mock WebSocket that records sent messages."""
    ws = MagicMock()
    ws.send_json = AsyncMock()
    ws.accept = AsyncMock()
    ws.receive_json = AsyncMock()
    return ws


# ---------------------------------------------------------------------------
# ConnectionManager unit tests
# ---------------------------------------------------------------------------

class TestConnectionManager:
    """Unit tests for the enhanced ConnectionManager."""

    @pytest.fixture(autouse=True)
    def fresh_manager(self):
        self.mgr = ConnectionManager()

    # -- connect / disconnect -----------------------------------------------

    @pytest.mark.asyncio
    async def test_connect_and_disconnect(self):
        ws = _make_ws_mock()
        uid = uuid4()

        conn = await self.mgr.connect(ws, uid)

        assert isinstance(conn, ConnectionInfo)
        assert conn.user_id == uid
        assert self.mgr.is_user_online(uid)
        assert self.mgr.total_connections == 1
        assert self.mgr.total_users == 1

        self.mgr.disconnect(ws, uid)

        assert not self.mgr.is_user_online(uid)
        assert self.mgr.total_connections == 0

    @pytest.mark.asyncio
    async def test_multiple_connections_per_user(self):
        ws1, ws2 = _make_ws_mock(), _make_ws_mock()
        uid = uuid4()

        await self.mgr.connect(ws1, uid)
        await self.mgr.connect(ws2, uid)

        assert self.mgr.total_connections == 2
        assert self.mgr.total_users == 1

        self.mgr.disconnect(ws1, uid)
        assert self.mgr.is_user_online(uid)
        assert self.mgr.total_connections == 1

        self.mgr.disconnect(ws2, uid)
        assert not self.mgr.is_user_online(uid)

    @pytest.mark.asyncio
    async def test_disconnect_cleans_chat_rooms(self):
        ws = _make_ws_mock()
        uid = uuid4()
        chat = uuid4()

        await self.mgr.connect(ws, uid)
        self.mgr.join_chat(chat, uid, ws)

        assert uid in self.mgr.get_chat_users(chat)

        self.mgr.disconnect(ws, uid)
        assert uid not in self.mgr.get_chat_users(chat)

    # -- chat rooms ---------------------------------------------------------

    @pytest.mark.asyncio
    async def test_join_and_leave_chat(self):
        ws = _make_ws_mock()
        uid = uuid4()
        chat = uuid4()

        await self.mgr.connect(ws, uid)
        self.mgr.join_chat(chat, uid, ws)

        assert uid in self.mgr.get_chat_users(chat)

        self.mgr.leave_chat(chat, uid)
        assert uid not in self.mgr.get_chat_users(chat)
        # Empty room should be cleaned up
        assert chat not in self.mgr.chat_rooms

    # -- send helpers -------------------------------------------------------

    @pytest.mark.asyncio
    async def test_send_personal_message(self):
        ws = _make_ws_mock()
        uid = uuid4()
        await self.mgr.connect(ws, uid)

        msg = {"type": "test", "data": 42}
        await self.mgr.send_personal_message(msg, uid)

        ws.send_json.assert_called_once_with(msg)

    @pytest.mark.asyncio
    async def test_send_personal_removes_failed_connection(self):
        ws = _make_ws_mock()
        ws.send_json.side_effect = RuntimeError("broken pipe")
        uid = uuid4()
        await self.mgr.connect(ws, uid)

        await self.mgr.send_personal_message({"type": "x"}, uid)

        # Connection should be cleaned up
        assert not self.mgr.is_user_online(uid)

    @pytest.mark.asyncio
    async def test_send_to_chat_excludes_user(self):
        ws1, ws2 = _make_ws_mock(), _make_ws_mock()
        uid1, uid2 = uuid4(), uuid4()
        chat = uuid4()

        await self.mgr.connect(ws1, uid1)
        await self.mgr.connect(ws2, uid2)
        self.mgr.join_chat(chat, uid1)
        self.mgr.join_chat(chat, uid2)

        # Reset mocks after connect (which sends presence broadcasts)
        ws1.send_json.reset_mock()
        ws2.send_json.reset_mock()

        msg = {"type": "test"}
        await self.mgr.send_to_chat(msg, chat, exclude_user=uid1)

        ws1.send_json.assert_not_called()
        ws2.send_json.assert_called()

    @pytest.mark.asyncio
    async def test_broadcast(self):
        ws1, ws2 = _make_ws_mock(), _make_ws_mock()
        uid1, uid2 = uuid4(), uuid4()

        await self.mgr.connect(ws1, uid1)
        await self.mgr.connect(ws2, uid2)

        # Reset mocks after connect (which sends presence broadcasts)
        ws1.send_json.reset_mock()
        ws2.send_json.reset_mock()

        msg = {"type": "broadcast"}
        await self.mgr.broadcast(msg)

        ws1.send_json.assert_called_once_with(msg)
        ws2.send_json.assert_called_once_with(msg)

    # -- task events --------------------------------------------------------

    @pytest.mark.asyncio
    async def test_task_created_event(self):
        ws = _make_ws_mock()
        uid = uuid4()
        task_id = uuid4()
        await self.mgr.connect(ws, uid)

        await self.mgr.task_created(uid, task_id, "research")

        ws.send_json.assert_called()
        payload = ws.send_json.call_args_list[-1][0][0]
        assert payload["type"] == "task_created"
        assert payload["task_id"] == str(task_id)
        assert payload["task_type"] == "research"
        assert payload["status"] == "pending"

    @pytest.mark.asyncio
    async def test_task_progress_event(self):
        ws = _make_ws_mock()
        uid = uuid4()
        task_id = uuid4()
        await self.mgr.connect(ws, uid)

        await self.mgr.task_progress(uid, task_id, 50, "Halfway done")

        payload = ws.send_json.call_args_list[-1][0][0]
        assert payload["type"] == "task_progress"
        assert payload["progress"] == 50
        assert payload["message"] == "Halfway done"
        assert payload["status"] == "processing"

    @pytest.mark.asyncio
    async def test_task_completed_event(self):
        ws = _make_ws_mock()
        uid = uuid4()
        task_id = uuid4()
        await self.mgr.connect(ws, uid)

        await self.mgr.task_completed(
            uid, task_id, result={"summary": "done"}, document_url="https://docs.google.com/d/123"
        )

        payload = ws.send_json.call_args_list[-1][0][0]
        assert payload["type"] == "task_completed"
        assert payload["progress"] == 100
        assert payload["status"] == "completed"
        assert payload["result"] == {"summary": "done"}
        assert payload["document_url"] == "https://docs.google.com/d/123"

    @pytest.mark.asyncio
    async def test_task_failed_event(self):
        ws = _make_ws_mock()
        uid = uuid4()
        task_id = uuid4()
        await self.mgr.connect(ws, uid)

        await self.mgr.task_failed(uid, task_id, "out of memory")

        payload = ws.send_json.call_args_list[-1][0][0]
        assert payload["type"] == "task_failed"
        assert payload["status"] == "failed"
        assert payload["error"] == "out of memory"

    @pytest.mark.asyncio
    async def test_task_cancelled_event(self):
        ws = _make_ws_mock()
        uid = uuid4()
        task_id = uuid4()
        await self.mgr.connect(ws, uid)

        await self.mgr.task_cancelled(uid, task_id)

        payload = ws.send_json.call_args_list[-1][0][0]
        assert payload["type"] == "task_cancelled"
        assert payload["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_emit_task_event_skips_optional_none_fields(self):
        ws = _make_ws_mock()
        uid = uuid4()
        task_id = uuid4()
        await self.mgr.connect(ws, uid)

        await self.mgr.emit_task_event(uid, EventType.TASK_CREATED, task_id)

        payload = ws.send_json.call_args_list[-1][0][0]
        assert "error" not in payload
        assert "result" not in payload
        assert "document_url" not in payload

    # -- typing indicators --------------------------------------------------

    @pytest.mark.asyncio
    async def test_typing_start_broadcasts_to_chat(self):
        ws1, ws2 = _make_ws_mock(), _make_ws_mock()
        uid1, uid2 = uuid4(), uuid4()
        chat = uuid4()

        await self.mgr.connect(ws1, uid1)
        await self.mgr.connect(ws2, uid2)
        self.mgr.join_chat(chat, uid1)
        self.mgr.join_chat(chat, uid2)

        await self.mgr.typing_start(chat, uid1)

        # uid1 should NOT receive the typing indicator (exclude_user)
        assert not any(
            call[0][0].get("type") == "typing_start"
            for call in ws1.send_json.call_args_list
        )
        # uid2 should receive it
        typing_msgs = [
            call[0][0]
            for call in ws2.send_json.call_args_list
            if call[0][0].get("type") == "typing_start"
        ]
        assert len(typing_msgs) == 1
        assert typing_msgs[0]["user_id"] == str(uid1)

    @pytest.mark.asyncio
    async def test_typing_stop_broadcasts_to_chat(self):
        ws1, ws2 = _make_ws_mock(), _make_ws_mock()
        uid1, uid2 = uuid4(), uuid4()
        chat = uuid4()

        await self.mgr.connect(ws1, uid1)
        await self.mgr.connect(ws2, uid2)
        self.mgr.join_chat(chat, uid1)
        self.mgr.join_chat(chat, uid2)

        await self.mgr.typing_stop(chat, uid1)

        typing_msgs = [
            call[0][0]
            for call in ws2.send_json.call_args_list
            if call[0][0].get("type") == "typing_stop"
        ]
        assert len(typing_msgs) == 1

    # -- presence -----------------------------------------------------------

    @pytest.mark.asyncio
    async def test_presence_broadcast_on_connect(self):
        ws1 = _make_ws_mock()
        ws2 = _make_ws_mock()
        uid1, uid2 = uuid4(), uuid4()

        await self.mgr.connect(ws1, uid1)
        # When uid2 connects, uid1 should get a user_online event
        await self.mgr.connect(ws2, uid2)

        online_msgs = [
            call[0][0]
            for call in ws1.send_json.call_args_list
            if call[0][0].get("type") == "user_online"
        ]
        assert len(online_msgs) >= 1
        assert online_msgs[-1]["user_id"] == str(uid2)

    @pytest.mark.asyncio
    async def test_send_presence_list(self):
        ws1, ws2 = _make_ws_mock(), _make_ws_mock()
        uid1, uid2 = uuid4(), uuid4()

        await self.mgr.connect(ws1, uid1)
        await self.mgr.connect(ws2, uid2)

        await self.mgr.send_presence_list(uid1)

        presence_msgs = [
            call[0][0]
            for call in ws1.send_json.call_args_list
            if call[0][0].get("type") == "presence_list"
        ]
        assert len(presence_msgs) >= 1
        assert str(uid1) in presence_msgs[-1]["users"]
        assert str(uid2) in presence_msgs[-1]["users"]

    # -- heartbeat ----------------------------------------------------------

    @pytest.mark.asyncio
    async def test_record_pong(self):
        ws = _make_ws_mock()
        uid = uuid4()
        conn = await self.mgr.connect(ws, uid)

        old_pong = conn.last_pong
        # Small sleep to ensure monotonic time advances
        await asyncio.sleep(0.01)
        self.mgr.record_pong(ws, uid)

        assert conn.last_pong > old_pong

    @pytest.mark.asyncio
    async def test_start_and_stop_heartbeat(self):
        self.mgr.start_heartbeat()
        assert self.mgr._heartbeat_task is not None
        assert not self.mgr._heartbeat_task.done()

        self.mgr.stop_heartbeat()
        # Allow event loop to process the cancellation
        await asyncio.sleep(0.05)
        assert self.mgr._heartbeat_task.cancelled() or self.mgr._heartbeat_task.done()

    # -- properties ---------------------------------------------------------

    @pytest.mark.asyncio
    async def test_total_connections_and_users(self):
        assert self.mgr.total_connections == 0
        assert self.mgr.total_users == 0

        ws1, ws2 = _make_ws_mock(), _make_ws_mock()
        uid = uuid4()
        await self.mgr.connect(ws1, uid)
        await self.mgr.connect(ws2, uid)

        assert self.mgr.total_connections == 2
        assert self.mgr.total_users == 1

    # -- EventType enum ----------------------------------------------------

    def test_event_type_values(self):
        assert EventType.TASK_CREATED.value == "task_created"
        assert EventType.TASK_PROGRESS.value == "task_progress"
        assert EventType.TASK_COMPLETED.value == "task_completed"
        assert EventType.TASK_FAILED.value == "task_failed"
        assert EventType.TASK_CANCELLED.value == "task_cancelled"
        assert EventType.TYPING_START.value == "typing_start"
        assert EventType.TYPING_STOP.value == "typing_stop"
        assert EventType.USER_ONLINE.value == "user_online"
        assert EventType.USER_OFFLINE.value == "user_offline"
        assert EventType.SERVER_HEARTBEAT.value == "server_heartbeat"


# ---------------------------------------------------------------------------
# WebSocket endpoint integration tests (via TestClient)
# ---------------------------------------------------------------------------

class TestWebSocketEndpoint:
    """Integration tests for the /ws endpoint."""

    @pytest.fixture(autouse=True)
    def setup_client(self, client):
        """Use the shared test client."""
        self.client = client

    def _auth_token(self):
        """Get a valid JWT token for WebSocket auth."""
        from datetime import timedelta
        from app.core.security import create_access_token
        return create_access_token(
            data={"sub": str(uuid4())},
            expires_delta=timedelta(minutes=30),
        )

    def test_ws_rejects_invalid_token(self):
        """WebSocket should close with policy violation on bad token."""
        with pytest.raises(Exception):
            with self.client.websocket_connect("/api/v1/messages/ws?token=invalid"):
                pass

    def test_ws_ping_pong(self):
        """Client sends ping, server replies pong."""
        token = self._auth_token()
        with self.client.websocket_connect(f"/api/v1/messages/ws?token={token}") as ws:
            # First message is presence_list (sent on connect)
            data = ws.receive_json()
            assert data["type"] == "presence_list"

            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"

    def test_ws_join_and_leave_chat(self):
        """Join/leave chat rooms via WebSocket."""
        token = self._auth_token()
        chat_id = str(uuid4())
        with self.client.websocket_connect(f"/api/v1/messages/ws?token={token}") as ws:
            # Skip presence list
            ws.receive_json()

            ws.send_json({"type": "join_chat", "chat_id": chat_id})
            data = ws.receive_json()
            assert data["type"] == "joined_chat"
            assert data["chat_id"] == chat_id

            ws.send_json({"type": "leave_chat", "chat_id": chat_id})
            data = ws.receive_json()
            assert data["type"] == "left_chat"
            assert data["chat_id"] == chat_id

    def test_ws_get_presence(self):
        """Client requests presence list."""
        token = self._auth_token()
        with self.client.websocket_connect(f"/api/v1/messages/ws?token={token}") as ws:
            # Skip initial presence list
            ws.receive_json()

            ws.send_json({"type": "get_presence"})
            data = ws.receive_json()
            assert data["type"] == "presence_list"
            assert isinstance(data["users"], list)

    def test_ws_subscribe_tasks(self):
        """Client subscribes to task events."""
        token = self._auth_token()
        with self.client.websocket_connect(f"/api/v1/messages/ws?token={token}") as ws:
            ws.receive_json()  # skip presence

            ws.send_json({"type": "subscribe_tasks"})
            data = ws.receive_json()
            assert data["type"] == "subscribed"
            assert data["channel"] == "tasks"

    def test_ws_unknown_type_returns_error(self):
        """Unknown message types get an error reply."""
        token = self._auth_token()
        with self.client.websocket_connect(f"/api/v1/messages/ws?token={token}") as ws:
            ws.receive_json()  # skip presence

            ws.send_json({"type": "bogus_type"})
            data = ws.receive_json()
            assert data["type"] == "error"
            assert "bogus_type" in data["message"]

    def test_ws_typing_indicator(self):
        """Typing events are handled without error."""
        token = self._auth_token()
        chat_id = str(uuid4())
        with self.client.websocket_connect(f"/api/v1/messages/ws?token={token}") as ws:
            ws.receive_json()  # skip presence

            # Join a chat first
            ws.send_json({"type": "join_chat", "chat_id": chat_id})
            ws.receive_json()  # joined_chat ack

            # Send typing start (no error = success)
            ws.send_json({"type": "typing", "chat_id": chat_id, "active": True})
            # Send typing stop
            ws.send_json({"type": "typing", "chat_id": chat_id, "active": False})

            # Verify no error came back (send ping to flush)
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"

    def test_ws_pong_response(self):
        """Client sends pong (heartbeat ack) — no crash."""
        token = self._auth_token()
        with self.client.websocket_connect(f"/api/v1/messages/ws?token={token}") as ws:
            ws.receive_json()  # skip presence

            ws.send_json({"type": "pong"})
            # Should not crash. Verify with a ping.
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"


# ---------------------------------------------------------------------------
# Health endpoint: /ws/stats
# ---------------------------------------------------------------------------

class TestWSStatsEndpoint:
    """Test the WebSocket stats health endpoint."""

    @pytest.fixture(autouse=True)
    def setup_client(self, client):
        self.client = client

    def test_ws_stats_returns_structure(self):
        resp = self.client.get("/api/v1/ws/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_connections" in data
        assert "total_users" in data
        assert "online_users" in data
        assert "active_chat_rooms" in data
        assert isinstance(data["total_connections"], int)
        assert isinstance(data["online_users"], list)
