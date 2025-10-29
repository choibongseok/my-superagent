"""Conversation Memory implementation for multi-turn dialogues.

This module provides conversation buffer memory management for maintaining
context across multiple turns in agent conversations.
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from langchain.memory import ConversationBufferMemory, ConversationSummaryMemory
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)


class ConversationMemory:
    """
    Manages conversation memory for multi-turn dialogues.

    Features:
        - Conversation buffer for short-term memory
        - Automatic summarization for long conversations
        - Token limit management
        - Message filtering and retrieval

    Usage:
        memory = ConversationMemory(user_id="user123", session_id="session456")
        memory.add_user_message("Hello, how are you?")
        memory.add_ai_message("I'm doing well, thank you!")

        messages = memory.get_messages()
        context = memory.get_context()
    """

    def __init__(
        self,
        user_id: str,
        session_id: str,
        max_token_limit: int = 2000,
        use_summary: bool = False,
        llm: Optional[ChatOpenAI] = None,
    ):
        """
        Initialize conversation memory.

        Args:
            user_id: User identifier
            session_id: Session identifier
            max_token_limit: Maximum tokens to keep in memory
            use_summary: Use summarization for long conversations
            llm: LLM instance for summarization
        """
        self.user_id = user_id
        self.session_id = session_id
        self.max_token_limit = max_token_limit
        self.use_summary = use_summary

        # Initialize memory backend
        if use_summary and llm:
            self.memory = ConversationSummaryMemory(
                llm=llm,
                memory_key="chat_history",
                return_messages=True,
                max_token_limit=max_token_limit,
            )
        else:
            self.memory = ConversationBufferMemory(
                memory_key="chat_history",
                return_messages=True,
                max_token_limit=max_token_limit,
            )

        # Metadata
        self.metadata: Dict[str, Any] = {
            "user_id": user_id,
            "session_id": session_id,
            "created_at": datetime.utcnow().isoformat(),
            "turn_count": 0,
        }

        logger.info(
            f"ConversationMemory initialized for user={user_id}, "
            f"session={session_id}, summary={use_summary}"
        )

    def add_user_message(self, message: str) -> None:
        """
        Add user message to conversation history.

        Args:
            message: User message content
        """
        self.memory.chat_memory.add_message(HumanMessage(content=message))
        self.metadata["turn_count"] += 1
        self.metadata["last_user_message"] = message
        self.metadata["last_updated"] = datetime.utcnow().isoformat()

        logger.debug(f"Added user message to session {self.session_id}")

    def add_ai_message(self, message: str) -> None:
        """
        Add AI message to conversation history.

        Args:
            message: AI message content
        """
        self.memory.chat_memory.add_message(AIMessage(content=message))
        self.metadata["last_ai_message"] = message
        self.metadata["last_updated"] = datetime.utcnow().isoformat()

        logger.debug(f"Added AI message to session {self.session_id}")

    def add_messages(self, messages: List[BaseMessage]) -> None:
        """
        Add multiple messages to conversation history.

        Args:
            messages: List of messages to add
        """
        for message in messages:
            self.memory.chat_memory.add_message(message)
            if isinstance(message, HumanMessage):
                self.metadata["turn_count"] += 1

        self.metadata["last_updated"] = datetime.utcnow().isoformat()
        logger.debug(f"Added {len(messages)} messages to session {self.session_id}")

    def get_messages(self, last_n: Optional[int] = None) -> List[BaseMessage]:
        """
        Get conversation messages.

        Args:
            last_n: Number of recent messages to retrieve (None for all)

        Returns:
            List of conversation messages
        """
        messages = self.memory.chat_memory.messages

        if last_n is not None:
            messages = messages[-last_n:]

        return messages

    def get_context(self) -> str:
        """
        Get conversation context as formatted string.

        Returns:
            Formatted conversation history
        """
        messages = self.get_messages()

        context_parts = []
        for msg in messages:
            role = "Human" if isinstance(msg, HumanMessage) else "AI"
            context_parts.append(f"{role}: {msg.content}")

        return "\n".join(context_parts)

    def get_summary(self) -> Optional[str]:
        """
        Get conversation summary (if using summary memory).

        Returns:
            Summary string or None
        """
        if isinstance(self.memory, ConversationSummaryMemory):
            return self.memory.buffer
        return None

    def clear(self) -> None:
        """Clear all conversation history."""
        self.memory.clear()
        self.metadata["turn_count"] = 0
        self.metadata["cleared_at"] = datetime.utcnow().isoformat()

        logger.info(f"Cleared memory for session {self.session_id}")

    def get_turn_count(self) -> int:
        """
        Get number of conversation turns.

        Returns:
            Turn count
        """
        return self.metadata.get("turn_count", 0)

    def get_metadata(self) -> Dict[str, Any]:
        """
        Get conversation metadata.

        Returns:
            Metadata dictionary
        """
        return self.metadata.copy()

    def to_dict(self) -> Dict[str, Any]:
        """
        Export conversation memory to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "messages": [
                {
                    "role": "human" if isinstance(msg, HumanMessage) else "ai",
                    "content": msg.content,
                }
                for msg in self.get_messages()
            ],
            "metadata": self.metadata,
            "summary": self.get_summary(),
        }

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
        llm: Optional[ChatOpenAI] = None,
    ) -> "ConversationMemory":
        """
        Create ConversationMemory from dictionary.

        Args:
            data: Dictionary representation
            llm: LLM instance for summarization

        Returns:
            ConversationMemory instance
        """
        memory = cls(
            user_id=data["user_id"],
            session_id=data["session_id"],
            use_summary=data.get("summary") is not None,
            llm=llm,
        )

        # Restore messages
        for msg_data in data.get("messages", []):
            if msg_data["role"] == "human":
                memory.add_user_message(msg_data["content"])
            else:
                memory.add_ai_message(msg_data["content"])

        # Restore metadata
        if "metadata" in data:
            memory.metadata.update(data["metadata"])

        return memory


__all__ = ["ConversationMemory"]
