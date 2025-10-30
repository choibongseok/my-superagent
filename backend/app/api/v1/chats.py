"""Chat endpoints."""

import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_current_user, get_db
from app.models.user import User
from app.models.chat import Chat
from app.models.message import Message
from app.schemas.chat import (
    ChatCreate,
    ChatUpdate,
    ChatResponse,
    ChatWithMessages,
    ChatListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chats", tags=["chats"])


@router.post("", response_model=ChatResponse, status_code=status.HTTP_201_CREATED)
async def create_chat(
    chat_data: ChatCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new chat."""
    chat = Chat(
        title=chat_data.title,
        user_id=current_user.id,
    )

    db.add(chat)
    await db.commit()
    await db.refresh(chat)

    logger.info(f"Chat created: {chat.id} by user {current_user.id}")
    return chat


@router.get("", response_model=ChatListResponse)
async def list_chats(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List user's chats."""
    # Get total count
    count_query = select(func.count()).select_from(Chat).where(Chat.user_id == current_user.id)
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Get chats
    query = (
        select(Chat)
        .where(Chat.user_id == current_user.id)
        .order_by(Chat.updated_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    chats = result.scalars().all()

    return ChatListResponse(chats=chats, total=total)


@router.get("/{chat_id}", response_model=ChatWithMessages)
async def get_chat(
    chat_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific chat with messages."""
    query = (
        select(Chat)
        .where(Chat.id == chat_id, Chat.user_id == current_user.id)
        .options(selectinload(Chat.messages))
    )
    result = await db.execute(query)
    chat = result.scalar_one_or_none()

    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found",
        )

    return chat


@router.patch("/{chat_id}", response_model=ChatResponse)
async def update_chat(
    chat_id: UUID,
    chat_data: ChatUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a chat."""
    query = select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id)
    result = await db.execute(query)
    chat = result.scalar_one_or_none()

    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found",
        )

    if chat_data.title is not None:
        chat.title = chat_data.title

    await db.commit()
    await db.refresh(chat)

    logger.info(f"Chat updated: {chat.id}")
    return chat


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(
    chat_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a chat."""
    query = select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id)
    result = await db.execute(query)
    chat = result.scalar_one_or_none()

    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found",
        )

    await db.delete(chat)
    await db.commit()

    logger.info(f"Chat deleted: {chat_id} by user {current_user.id}")
