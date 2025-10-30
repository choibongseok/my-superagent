"""WebSocket connection manager."""

import json
import logging
from typing import Dict, List, Set
from uuid import UUID
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections."""

    def __init__(self):
        # user_id -> list of websocket connections
        self.active_connections: Dict[UUID, List[WebSocket]] = {}
        # chat_id -> set of user_ids
        self.chat_rooms: Dict[UUID, Set[UUID]] = {}

    async def connect(self, websocket: WebSocket, user_id: UUID):
        """Accept a new WebSocket connection."""
        await websocket.accept()

        if user_id not in self.active_connections:
            self.active_connections[user_id] = []

        self.active_connections[user_id].append(websocket)
        logger.info(f"User {user_id} connected. Total connections: {len(self.active_connections[user_id])}")

    def disconnect(self, websocket: WebSocket, user_id: UUID):
        """Remove a WebSocket connection."""
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
                logger.info(f"User {user_id} disconnected. Remaining connections: {len(self.active_connections[user_id])}")

            # Remove user from active connections if no connections left
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

                # Remove user from all chat rooms
                for chat_id in list(self.chat_rooms.keys()):
                    if user_id in self.chat_rooms[chat_id]:
                        self.chat_rooms[chat_id].remove(user_id)
                    # Remove empty chat rooms
                    if not self.chat_rooms[chat_id]:
                        del self.chat_rooms[chat_id]

    async def send_personal_message(self, message: dict, user_id: UUID):
        """Send a message to all connections of a specific user."""
        if user_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Error sending message to user {user_id}: {e}")
                    disconnected.append(connection)

            # Clean up disconnected connections
            for connection in disconnected:
                self.disconnect(connection, user_id)

    async def send_to_chat(self, message: dict, chat_id: UUID, exclude_user: UUID = None):
        """Send a message to all users in a chat room."""
        if chat_id in self.chat_rooms:
            for user_id in self.chat_rooms[chat_id]:
                if exclude_user and user_id == exclude_user:
                    continue
                await self.send_personal_message(message, user_id)

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected users."""
        for user_id in list(self.active_connections.keys()):
            await self.send_personal_message(message, user_id)

    def join_chat(self, chat_id: UUID, user_id: UUID):
        """Add a user to a chat room."""
        if chat_id not in self.chat_rooms:
            self.chat_rooms[chat_id] = set()

        self.chat_rooms[chat_id].add(user_id)
        logger.info(f"User {user_id} joined chat {chat_id}. Room size: {len(self.chat_rooms[chat_id])}")

    def leave_chat(self, chat_id: UUID, user_id: UUID):
        """Remove a user from a chat room."""
        if chat_id in self.chat_rooms and user_id in self.chat_rooms[chat_id]:
            self.chat_rooms[chat_id].remove(user_id)
            logger.info(f"User {user_id} left chat {chat_id}. Room size: {len(self.chat_rooms[chat_id])}")

            # Remove empty chat rooms
            if not self.chat_rooms[chat_id]:
                del self.chat_rooms[chat_id]

    def get_online_users(self) -> List[UUID]:
        """Get list of all online users."""
        return list(self.active_connections.keys())

    def is_user_online(self, user_id: UUID) -> bool:
        """Check if a user is online."""
        return user_id in self.active_connections

    def get_chat_users(self, chat_id: UUID) -> Set[UUID]:
        """Get all users in a chat room."""
        return self.chat_rooms.get(chat_id, set())


# Global connection manager instance
manager = ConnectionManager()
