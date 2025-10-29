"""Memory Manager for integrated memory management.

This module provides a unified interface for managing both conversation
memory (short-term) and vector store memory (long-term).
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage

from app.memory.conversation import ConversationMemory
from app.memory.vector_store import VectorStoreMemory
from app.core.config import settings

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    Unified memory management system combining short-term and long-term memory.

    Features:
        - Short-term: Conversation buffer for recent context
        - Long-term: Vector store for semantic search across history
        - Automatic memory consolidation
        - Intelligent context retrieval

    Usage:
        manager = MemoryManager(user_id="user123", session_id="session456")

        # Add conversation turn
        manager.add_turn(
            user_message="What's the weather today?",
            ai_message="It's sunny and warm."
        )

        # Get relevant context
        context = manager.get_context(query="Tell me about the weather")

        # Search long-term memory
        results = manager.search_memory("weather information")
    """

    def __init__(
        self,
        user_id: str,
        session_id: str,
        use_vector_memory: bool = True,
        use_summary: bool = False,
        conversation_max_tokens: int = 2000,
        vector_top_k: int = 5,
        llm: Optional[ChatOpenAI] = None,
    ):
        """
        Initialize memory manager.

        Args:
            user_id: User identifier
            session_id: Session identifier
            use_vector_memory: Enable vector store memory
            use_summary: Use summarization for conversations
            conversation_max_tokens: Max tokens for conversation buffer
            vector_top_k: Number of vector search results
            llm: LLM instance for summarization
        """
        self.user_id = user_id
        self.session_id = session_id
        self.use_vector_memory = use_vector_memory

        # Initialize conversation memory (short-term)
        self.conversation_memory = ConversationMemory(
            user_id=user_id,
            session_id=session_id,
            max_token_limit=conversation_max_tokens,
            use_summary=use_summary,
            llm=llm,
        )

        # Initialize vector store memory (long-term)
        self.vector_memory: Optional[VectorStoreMemory] = None
        if use_vector_memory:
            try:
                self.vector_memory = VectorStoreMemory(
                    user_id=user_id,
                    session_id=session_id,
                    top_k=vector_top_k,
                )
            except Exception as e:
                logger.error(f"Failed to initialize vector memory: {e}")
                self.use_vector_memory = False

        # Metadata
        self.metadata: Dict[str, Any] = {
            "user_id": user_id,
            "session_id": session_id,
            "created_at": datetime.utcnow().isoformat(),
            "vector_memory_enabled": use_vector_memory,
            "summary_enabled": use_summary,
        }

        logger.info(
            f"MemoryManager initialized for user={user_id}, "
            f"session={session_id}, vector={use_vector_memory}"
        )

    def add_turn(
        self,
        user_message: str,
        ai_message: str,
        save_to_vector: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Add a conversation turn (user message + AI response).

        Args:
            user_message: User's message
            ai_message: AI's response
            save_to_vector: Also save to long-term vector memory
            metadata: Optional metadata for vector storage
        """
        # Add to conversation memory
        self.conversation_memory.add_user_message(user_message)
        self.conversation_memory.add_ai_message(ai_message)

        # Optionally save to vector memory
        if save_to_vector and self.vector_memory:
            try:
                # Combine user and AI messages for context
                combined_content = f"User: {user_message}\nAI: {ai_message}"

                vector_metadata = {
                    "turn_type": "conversation",
                    "user_message": user_message,
                    "ai_message": ai_message,
                    **(metadata or {}),
                }

                self.vector_memory.add_memory(
                    content=combined_content,
                    metadata=vector_metadata,
                )
            except Exception as e:
                logger.error(f"Failed to save to vector memory: {e}")

        logger.debug(f"Added conversation turn to session {self.session_id}")

    def add_user_message(self, message: str) -> None:
        """
        Add user message to conversation.

        Args:
            message: User message
        """
        self.conversation_memory.add_user_message(message)

    def add_ai_message(self, message: str) -> None:
        """
        Add AI message to conversation.

        Args:
            message: AI message
        """
        self.conversation_memory.add_ai_message(message)

    def add_memory(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Add memory to long-term storage.

        Args:
            content: Memory content
            metadata: Optional metadata

        Returns:
            Memory ID or None if vector memory disabled
        """
        if not self.vector_memory:
            logger.warning("Vector memory not enabled")
            return None

        try:
            return self.vector_memory.add_memory(content, metadata)
        except Exception as e:
            logger.error(f"Failed to add memory: {e}")
            return None

    def get_recent_messages(
        self,
        last_n: int = 10,
    ) -> List[BaseMessage]:
        """
        Get recent conversation messages.

        Args:
            last_n: Number of recent messages

        Returns:
            List of recent messages
        """
        return self.conversation_memory.get_messages(last_n=last_n)

    def get_conversation_context(self) -> str:
        """
        Get formatted conversation context.

        Returns:
            Conversation history as string
        """
        return self.conversation_memory.get_context()

    def get_context(
        self,
        query: str,
        include_conversation: bool = True,
        include_vector: bool = True,
        vector_k: int = 3,
    ) -> str:
        """
        Get comprehensive context for a query.

        Combines recent conversation history and relevant long-term memories.

        Args:
            query: Context query
            include_conversation: Include recent conversation
            include_vector: Include vector search results
            vector_k: Number of vector results

        Returns:
            Formatted context string
        """
        context_parts = []

        # Add recent conversation
        if include_conversation:
            conv_context = self.get_conversation_context()
            if conv_context:
                context_parts.append("=== Recent Conversation ===\n" + conv_context)

        # Add relevant memories from vector store
        if include_vector and self.vector_memory:
            try:
                vector_context = self.vector_memory.get_relevant_context(
                    query=query,
                    k=vector_k,
                )
                if vector_context:
                    context_parts.append(
                        "=== Relevant Past Memories ===\n" + vector_context
                    )
            except Exception as e:
                logger.error(f"Failed to retrieve vector context: {e}")

        return "\n\n".join(context_parts)

    def search_memory(
        self,
        query: str,
        k: int = 5,
        score_threshold: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """
        Search long-term memory.

        Args:
            query: Search query
            k: Number of results
            score_threshold: Minimum similarity score

        Returns:
            List of matching memories
        """
        if not self.vector_memory:
            logger.warning("Vector memory not enabled")
            return []

        try:
            return self.vector_memory.search_with_scores(
                query=query,
                k=k,
                score_threshold=score_threshold,
            )
        except Exception as e:
            logger.error(f"Memory search failed: {e}")
            return []

    def clear_conversation(self) -> None:
        """Clear conversation memory (short-term)."""
        self.conversation_memory.clear()
        logger.info(f"Cleared conversation for session {self.session_id}")

    def clear_all(self) -> None:
        """Clear all memories (conversation + vector store)."""
        self.clear_conversation()

        if self.vector_memory:
            try:
                self.vector_memory.clear_user_memories()
                logger.info(f"Cleared all memories for user {self.user_id}")
            except Exception as e:
                logger.error(f"Failed to clear vector memories: {e}")

    def get_turn_count(self) -> int:
        """
        Get conversation turn count.

        Returns:
            Number of turns
        """
        return self.conversation_memory.get_turn_count()

    def get_summary(self) -> Optional[str]:
        """
        Get conversation summary (if enabled).

        Returns:
            Summary or None
        """
        return self.conversation_memory.get_summary()

    def get_metadata(self) -> Dict[str, Any]:
        """
        Get memory manager metadata.

        Returns:
            Metadata dictionary
        """
        metadata = self.metadata.copy()
        metadata.update(
            {
                "turn_count": self.get_turn_count(),
                "conversation_metadata": self.conversation_memory.get_metadata(),
            }
        )
        return metadata

    def to_dict(self) -> Dict[str, Any]:
        """
        Export memory manager state to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "conversation": self.conversation_memory.to_dict(),
            "metadata": self.get_metadata(),
        }


__all__ = ["MemoryManager"]
