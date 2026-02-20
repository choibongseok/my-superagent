"""WebSocket connection manager with real-time event broadcasting.

Phase 5 Feature: WebSocket Real-Time Updates
- Task lifecycle events (created, progress, completed, failed, cancelled)
- Typing indicators
- User presence (online/offline)
- Server-side heartbeat for stale-connection detection
- Auto-rejoin chat rooms on reconnect
"""

import asyncio
import json
import logging
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from uuid import UUID

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# Server heartbeat interval in seconds
HEARTBEAT_INTERVAL = 30
# If a client doesn't respond to a ping within this time, consider it dead
HEARTBEAT_TIMEOUT = 10


class EventType(str, Enum):
    """WebSocket event types."""

    # Chat events
    NEW_MESSAGE = "new_message"
    JOINED_CHAT = "joined_chat"
    LEFT_CHAT = "left_chat"

    # Task lifecycle events
    TASK_CREATED = "task_created"
    TASK_PROGRESS = "task_progress"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_CANCELLED = "task_cancelled"

    # Presence events
    USER_ONLINE = "user_online"
    USER_OFFLINE = "user_offline"
    PRESENCE_LIST = "presence_list"

    # Typing indicators
    TYPING_START = "typing_start"
    TYPING_STOP = "typing_stop"

    # System events
    PONG = "pong"
    SERVER_HEARTBEAT = "server_heartbeat"
    ERROR = "error"
    RECONNECTED = "reconnected"


class ConnectionInfo:
    """Metadata about an active WebSocket connection."""

    __slots__ = ("websocket", "user_id", "connected_at", "last_pong", "chat_rooms")

    def __init__(self, websocket: WebSocket, user_id: UUID):
        self.websocket = websocket
        self.user_id = user_id
        self.connected_at = time.monotonic()
        self.last_pong = time.monotonic()
        # Track which chats this specific connection is in (for reconnect)
        self.chat_rooms: Set[UUID] = set()


class ConnectionManager:
    """Manages WebSocket connections with real-time event support."""

    def __init__(self):
        # user_id -> list of ConnectionInfo
        self.active_connections: Dict[UUID, List[ConnectionInfo]] = {}
        # chat_id -> set of user_ids
        self.chat_rooms: Dict[UUID, Set[UUID]] = {}
        # Background heartbeat task
        self._heartbeat_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self, websocket: WebSocket, user_id: UUID) -> ConnectionInfo:
        """Accept a new WebSocket connection."""
        await websocket.accept()

        conn = ConnectionInfo(websocket, user_id)

        if user_id not in self.active_connections:
            self.active_connections[user_id] = []

        self.active_connections[user_id].append(conn)

        logger.info(
            "User %s connected. Total connections: %d",
            user_id,
            len(self.active_connections[user_id]),
        )

        # Broadcast presence to other users
        await self._broadcast_presence(user_id, online=True)

        return conn

    def disconnect(self, websocket: WebSocket, user_id: UUID):
        """Remove a WebSocket connection."""
        if user_id not in self.active_connections:
            return

        conns = self.active_connections[user_id]
        to_remove = [c for c in conns if c.websocket is websocket]
        for c in to_remove:
            conns.remove(c)

        logger.info(
            "User %s disconnected. Remaining connections: %d",
            user_id,
            len(conns),
        )

        if not conns:
            # No more connections — remove user from ALL chat rooms
            del self.active_connections[user_id]
            for chat_id in list(self.chat_rooms.keys()):
                self._remove_user_from_chat(chat_id, user_id)
            # Schedule presence broadcast (sync-safe: fire-and-forget)
            asyncio.ensure_future(self._broadcast_presence(user_id, online=False))
        else:
            # Other connections still active — only remove from chats that
            # no remaining connection is tracking.
            disconnected_chats: Set[UUID] = set()
            for c in to_remove:
                disconnected_chats.update(c.chat_rooms)
            # Keep chat membership if another connection is still in that room
            still_active_chats: Set[UUID] = set()
            for c in conns:
                still_active_chats.update(c.chat_rooms)
            for chat_id in disconnected_chats - still_active_chats:
                self._remove_user_from_chat(chat_id, user_id)

    # ------------------------------------------------------------------
    # Sending helpers
    # ------------------------------------------------------------------

    async def _safe_send(self, conn: ConnectionInfo, message: dict) -> bool:
        """Send JSON to a single connection. Returns False if it failed."""
        try:
            await conn.websocket.send_json(message)
            return True
        except Exception as e:
            logger.error("Error sending to user %s: %s", conn.user_id, e)
            return False

    async def send_personal_message(self, message: dict, user_id: UUID):
        """Send a message to all connections of a specific user."""
        if user_id not in self.active_connections:
            return

        disconnected: List[ConnectionInfo] = []
        for conn in self.active_connections[user_id]:
            ok = await self._safe_send(conn, message)
            if not ok:
                disconnected.append(conn)

        for conn in disconnected:
            self.disconnect(conn.websocket, user_id)

    async def send_to_chat(
        self,
        message: dict,
        chat_id: UUID,
        exclude_user: Optional[UUID] = None,
    ):
        """Send a message to all users in a chat room."""
        if chat_id not in self.chat_rooms:
            return
        for user_id in list(self.chat_rooms[chat_id]):
            if exclude_user and user_id == exclude_user:
                continue
            await self.send_personal_message(message, user_id)

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected users."""
        for user_id in list(self.active_connections.keys()):
            await self.send_personal_message(message, user_id)

    # ------------------------------------------------------------------
    # Chat rooms
    # ------------------------------------------------------------------

    def join_chat(self, chat_id: UUID, user_id: UUID, websocket: Optional[WebSocket] = None):
        """Add a user to a chat room."""
        if chat_id not in self.chat_rooms:
            self.chat_rooms[chat_id] = set()
        self.chat_rooms[chat_id].add(user_id)

        # Track on the specific connection (for reconnect restore)
        if websocket and user_id in self.active_connections:
            for conn in self.active_connections[user_id]:
                if conn.websocket is websocket:
                    conn.chat_rooms.add(chat_id)
                    break

        logger.info(
            "User %s joined chat %s. Room size: %d",
            user_id,
            chat_id,
            len(self.chat_rooms[chat_id]),
        )

    def leave_chat(self, chat_id: UUID, user_id: UUID, websocket: Optional[WebSocket] = None):
        """Remove a user from a chat room."""
        # Update per-connection tracking so disconnect() stays consistent
        if websocket and user_id in self.active_connections:
            for conn in self.active_connections[user_id]:
                if conn.websocket is websocket:
                    conn.chat_rooms.discard(chat_id)
                    break
        else:
            # No specific websocket — remove from all connections
            if user_id in self.active_connections:
                for conn in self.active_connections[user_id]:
                    conn.chat_rooms.discard(chat_id)
        self._remove_user_from_chat(chat_id, user_id)

    def _remove_user_from_chat(self, chat_id: UUID, user_id: UUID):
        if chat_id in self.chat_rooms and user_id in self.chat_rooms[chat_id]:
            self.chat_rooms[chat_id].discard(user_id)
            logger.info(
                "User %s left chat %s. Room size: %d",
                user_id,
                chat_id,
                len(self.chat_rooms[chat_id]),
            )
            if not self.chat_rooms[chat_id]:
                del self.chat_rooms[chat_id]

    # ------------------------------------------------------------------
    # Presence
    # ------------------------------------------------------------------

    def get_online_users(self) -> List[UUID]:
        """Get list of all online user IDs."""
        return list(self.active_connections.keys())

    def is_user_online(self, user_id: UUID) -> bool:
        """Check if a user has at least one active connection."""
        return user_id in self.active_connections

    def get_chat_users(self, chat_id: UUID) -> Set[UUID]:
        """Get all users in a chat room."""
        return self.chat_rooms.get(chat_id, set())

    async def _broadcast_presence(self, user_id: UUID, *, online: bool):
        """Notify all other connected users about a presence change."""
        event = EventType.USER_ONLINE if online else EventType.USER_OFFLINE
        payload = {"type": event.value, "user_id": str(user_id)}
        for uid in list(self.active_connections.keys()):
            if uid != user_id:
                await self.send_personal_message(payload, uid)

    async def send_presence_list(self, user_id: UUID):
        """Send the current online-users list to a specific user."""
        online = [str(uid) for uid in self.get_online_users()]
        await self.send_personal_message(
            {"type": EventType.PRESENCE_LIST.value, "users": online},
            user_id,
        )

    # ------------------------------------------------------------------
    # Task events  (called from API / Celery callbacks)
    # ------------------------------------------------------------------

    async def emit_task_event(
        self,
        user_id: UUID,
        event_type: EventType,
        task_id: UUID | str,
        *,
        task_type: Optional[str] = None,
        status: Optional[str] = None,
        progress: Optional[int] = None,
        message: Optional[str] = None,
        result: Optional[dict] = None,
        error: Optional[str] = None,
        document_url: Optional[str] = None,
    ):
        """Emit a task lifecycle event to the owning user.

        This is the central method that should be called whenever a task
        transitions state so connected clients can update their UI in real time.
        """
        payload: Dict[str, Any] = {
            "type": event_type.value,
            "task_id": str(task_id),
        }
        if task_type is not None:
            payload["task_type"] = task_type
        if status is not None:
            payload["status"] = status
        if progress is not None:
            payload["progress"] = progress
        if message is not None:
            payload["message"] = message
        if result is not None:
            payload["result"] = result
        if error is not None:
            payload["error"] = error
        if document_url is not None:
            payload["document_url"] = document_url

        await self.send_personal_message(payload, user_id)

    # Convenience wrappers for common task events

    async def task_created(self, user_id: UUID, task_id: UUID | str, task_type: str):
        await self.emit_task_event(
            user_id,
            EventType.TASK_CREATED,
            task_id,
            task_type=task_type,
            status="pending",
        )

    async def task_progress(
        self,
        user_id: UUID,
        task_id: UUID | str,
        progress: int,
        message: str = "",
    ):
        await self.emit_task_event(
            user_id,
            EventType.TASK_PROGRESS,
            task_id,
            progress=progress,
            message=message,
            status="processing",
        )

    async def task_completed(
        self,
        user_id: UUID,
        task_id: UUID | str,
        *,
        result: Optional[dict] = None,
        document_url: Optional[str] = None,
    ):
        await self.emit_task_event(
            user_id,
            EventType.TASK_COMPLETED,
            task_id,
            status="completed",
            progress=100,
            result=result,
            document_url=document_url,
        )

    async def task_failed(
        self,
        user_id: UUID,
        task_id: UUID | str,
        error: str = "",
    ):
        await self.emit_task_event(
            user_id,
            EventType.TASK_FAILED,
            task_id,
            status="failed",
            error=error,
        )

    async def task_cancelled(self, user_id: UUID, task_id: UUID | str):
        await self.emit_task_event(
            user_id,
            EventType.TASK_CANCELLED,
            task_id,
            status="cancelled",
        )

    # ------------------------------------------------------------------
    # Typing indicators
    # ------------------------------------------------------------------

    async def typing_start(self, chat_id: UUID, user_id: UUID):
        """Broadcast that a user started typing in a chat."""
        await self.send_to_chat(
            {"type": EventType.TYPING_START.value, "user_id": str(user_id), "chat_id": str(chat_id)},
            chat_id,
            exclude_user=user_id,
        )

    async def typing_stop(self, chat_id: UUID, user_id: UUID):
        """Broadcast that a user stopped typing in a chat."""
        await self.send_to_chat(
            {"type": EventType.TYPING_STOP.value, "user_id": str(user_id), "chat_id": str(chat_id)},
            chat_id,
            exclude_user=user_id,
        )

    # ------------------------------------------------------------------
    # Server-side heartbeat
    # ------------------------------------------------------------------

    def start_heartbeat(self):
        """Start background heartbeat loop. Call once from app lifespan."""
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.ensure_future(self._heartbeat_loop())
            logger.info("WebSocket heartbeat loop started (interval=%ds)", HEARTBEAT_INTERVAL)

    def stop_heartbeat(self):
        """Stop background heartbeat loop."""
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            logger.info("WebSocket heartbeat loop stopped")

    async def _heartbeat_loop(self):
        """Periodically ping all connections and prune stale ones."""
        while True:
            try:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                now = time.monotonic()

                stale: List[tuple] = []  # (websocket, user_id)

                for user_id, conns in list(self.active_connections.items()):
                    for conn in conns:
                        # Check if the last pong is too old
                        if now - conn.last_pong > HEARTBEAT_INTERVAL + HEARTBEAT_TIMEOUT:
                            stale.append((conn.websocket, user_id))
                        else:
                            # Send server heartbeat
                            ok = await self._safe_send(
                                conn,
                                {
                                    "type": EventType.SERVER_HEARTBEAT.value,
                                    "timestamp": int(time.time()),
                                },
                            )
                            if not ok:
                                stale.append((conn.websocket, user_id))

                for ws, uid in stale:
                    logger.info("Pruning stale connection for user %s", uid)
                    self.disconnect(ws, uid)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in heartbeat loop")

    def record_pong(self, websocket: WebSocket, user_id: UUID):
        """Record that a client responded to a heartbeat."""
        if user_id in self.active_connections:
            for conn in self.active_connections[user_id]:
                if conn.websocket is websocket:
                    conn.last_pong = time.monotonic()
                    break

    # ------------------------------------------------------------------
    # Connection count helpers (useful for monitoring)
    # ------------------------------------------------------------------

    @property
    def total_connections(self) -> int:
        return sum(len(conns) for conns in self.active_connections.values())

    @property
    def total_users(self) -> int:
        return len(self.active_connections)


# Global connection manager instance
manager = ConnectionManager()
