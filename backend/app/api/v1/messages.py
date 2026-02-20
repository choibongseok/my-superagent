"""Message endpoints."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.models.user import User
from app.models.chat import Chat
from app.models.message import Message, MessageRole
from app.schemas.message import MessageCreate, MessageResponse, MessageListResponse
from app.core.websocket import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/messages", tags=["messages"])


@router.post("", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def create_message(
    message_data: MessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new message."""
    # Verify chat exists and belongs to user
    chat_query = select(Chat).where(
        Chat.id == message_data.chat_id,
        Chat.user_id == current_user.id
    )
    chat_result = await db.execute(chat_query)
    chat = chat_result.scalar_one_or_none()

    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found",
        )

    # Create message
    message = Message(
        chat_id=message_data.chat_id,
        user_id=current_user.id,
        role=message_data.role,
        content=message_data.content,
    )

    db.add(message)
    await db.commit()
    await db.refresh(message)

    # Broadcast message to WebSocket connections
    await manager.send_to_chat(
        {
            "type": "new_message",
            "message": {
                "id": str(message.id),
                "chat_id": str(message.chat_id),
                "user_id": str(message.user_id),
                "role": message.role.value,
                "content": message.content,
                "created_at": message.created_at.isoformat(),
                "updated_at": message.updated_at.isoformat() if message.updated_at else message.created_at.isoformat(),
            },
        },
        chat_id=message.chat_id,
    )

    logger.info(f"Message created: {message.id} in chat {message.chat_id}")
    return message


@router.get("", response_model=MessageListResponse)
async def list_messages(
    chat_id: UUID,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List messages in a chat."""
    # Verify chat exists and belongs to user
    chat_query = select(Chat).where(
        Chat.id == chat_id,
        Chat.user_id == current_user.id
    )
    chat_result = await db.execute(chat_query)
    chat = chat_result.scalar_one_or_none()

    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found",
        )

    # Get messages
    query = (
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.created_at.asc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    messages = result.scalars().all()

    # Get total count
    from sqlalchemy import func
    count_query = select(func.count()).select_from(Message).where(Message.chat_id == chat_id)
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    return MessageListResponse(messages=messages, total=total)


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str,
):
    """WebSocket endpoint for real-time messaging and events.

    Supported client message types:
        join_chat   – { "type": "join_chat", "chat_id": "<uuid>" }
        leave_chat  – { "type": "leave_chat", "chat_id": "<uuid>" }
        ping        – { "type": "ping" }  (keepalive reply)
        pong        – { "type": "pong" }  (heartbeat ack)
        typing      – { "type": "typing", "chat_id": "<uuid>", "active": true|false }
        get_presence – { "type": "get_presence" }
        subscribe_tasks – { "type": "subscribe_tasks" } (opt-in for task events)

    Server-pushed event types (see EventType enum):
        new_message, task_created, task_progress, task_completed,
        task_failed, task_cancelled, typing_start, typing_stop,
        user_online, user_offline, presence_list, server_heartbeat
    """
    from app.core.security import decode_token
    from uuid import UUID as _UUID

    try:
        payload = decode_token(
            token,
            expected_type="access",
            required_claims=("sub",),
        )
        if not payload:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        user_id = _UUID(payload["sub"])
    except Exception as e:
        logger.error(f"WebSocket authentication failed: {e}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    conn = await manager.connect(websocket, user_id)

    # Send initial presence list to the new connection
    await manager.send_presence_list(user_id)

    try:
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type")

            if message_type == "join_chat":
                chat_id = _UUID(data["chat_id"])
                manager.join_chat(chat_id, user_id, websocket)
                await websocket.send_json({
                    "type": "joined_chat",
                    "chat_id": str(chat_id),
                })

            elif message_type == "leave_chat":
                chat_id = _UUID(data["chat_id"])
                manager.leave_chat(chat_id, user_id, websocket)
                await websocket.send_json({
                    "type": "left_chat",
                    "chat_id": str(chat_id),
                })

            elif message_type == "ping":
                manager.record_pong(websocket, user_id)
                await websocket.send_json({"type": "pong"})

            elif message_type == "pong":
                # Client acknowledging a server heartbeat
                manager.record_pong(websocket, user_id)

            elif message_type == "typing":
                chat_id_str = data.get("chat_id")
                if chat_id_str:
                    chat_id = _UUID(chat_id_str)
                    active = data.get("active", True)
                    if active:
                        await manager.typing_start(chat_id, user_id)
                    else:
                        await manager.typing_stop(chat_id, user_id)

            elif message_type == "get_presence":
                await manager.send_presence_list(user_id)

            elif message_type == "subscribe_tasks":
                # Acknowledgement — task events already go to the user
                await websocket.send_json({
                    "type": "subscribed",
                    "channel": "tasks",
                })

            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown message type: {message_type}",
                })

    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
        logger.info(f"WebSocket disconnected for user {user_id}")
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}")
        manager.disconnect(websocket, user_id)
