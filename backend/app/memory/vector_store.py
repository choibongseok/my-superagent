"""Vector Store Memory implementation for semantic search.

This module provides vector-based memory storage using PGVector for
semantic similarity search across conversation history.
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
import json

from langchain.memory import VectorStoreRetrieverMemory
from langchain.vectorstores import PGVector
from langchain.embeddings import OpenAIEmbeddings
from langchain_core.documents import Document
from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine

logger = logging.getLogger(__name__)


class VectorStoreMemory:
    """
    Vector-based memory storage with semantic search capabilities.

    Features:
        - Semantic similarity search
        - Long-term memory storage
        - Efficient retrieval using vector embeddings
        - Integration with PGVector

    Usage:
        memory = VectorStoreMemory(user_id="user123", session_id="session456")
        memory.add_memory("I love pizza", metadata={"topic": "food"})

        results = memory.search("What food do I like?", k=3)
        for result in results:
            print(result["content"])
    """

    def __init__(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        collection_name: str = "conversation_memory",
        embedding_model: str = "text-embedding-3-small",
        top_k: int = 5,
    ):
        """
        Initialize vector store memory.

        Args:
            user_id: User identifier
            session_id: Optional session identifier
            collection_name: PGVector collection name
            embedding_model: OpenAI embedding model
            top_k: Number of results to retrieve by default
        """
        self.user_id = user_id
        self.session_id = session_id
        self.collection_name = f"{collection_name}_{user_id}"
        self.top_k = top_k

        # Initialize embeddings
        self.embeddings = OpenAIEmbeddings(
            model=embedding_model,
            openai_api_key=settings.OPENAI_API_KEY,
        )

        # Initialize PGVector store
        self.vector_store = PGVector(
            collection_name=self.collection_name,
            connection_string=settings.DATABASE_URL.replace(
                "postgresql+asyncpg://", "postgresql://"
            ),
            embedding_function=self.embeddings,
        )

        # Create retriever
        self.retriever = self.vector_store.as_retriever(
            search_kwargs={"k": top_k}
        )

        # LangChain memory wrapper
        self.memory = VectorStoreRetrieverMemory(
            retriever=self.retriever,
            memory_key="relevant_memories",
        )

        logger.info(
            f"VectorStoreMemory initialized for user={user_id}, "
            f"session={session_id}, collection={self.collection_name}"
        )

    def add_memory(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Add memory to vector store.

        Args:
            content: Memory content
            metadata: Optional metadata

        Returns:
            Memory ID
        """
        # Prepare metadata
        memory_metadata = {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "timestamp": datetime.utcnow().isoformat(),
            **(metadata or {}),
        }

        # Add to vector store
        doc = Document(
            page_content=content,
            metadata=memory_metadata,
        )

        ids = self.vector_store.add_documents([doc])
        memory_id = ids[0] if ids else None

        logger.debug(
            f"Added memory to vector store: {memory_id} "
            f"(user={self.user_id}, session={self.session_id})"
        )

        return memory_id

    def add_memories(
        self,
        contents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> List[str]:
        """
        Add multiple memories to vector store.

        Args:
            contents: List of memory contents
            metadatas: Optional list of metadata dicts

        Returns:
            List of memory IDs
        """
        if metadatas is None:
            metadatas = [{} for _ in contents]

        documents = []
        for content, metadata in zip(contents, metadatas):
            memory_metadata = {
                "user_id": self.user_id,
                "session_id": self.session_id,
                "timestamp": datetime.utcnow().isoformat(),
                **metadata,
            }
            documents.append(
                Document(page_content=content, metadata=memory_metadata)
            )

        ids = self.vector_store.add_documents(documents)

        logger.debug(
            f"Added {len(ids)} memories to vector store "
            f"(user={self.user_id}, session={self.session_id})"
        )

        return ids

    def search(
        self,
        query: str,
        k: Optional[int] = None,
        filter_dict: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search memories by semantic similarity.

        Args:
            query: Search query
            k: Number of results (None for default)
            filter_dict: Optional metadata filters

        Returns:
            List of matching memories with metadata
        """
        k = k or self.top_k

        # Build search kwargs
        search_kwargs = {"k": k}
        if filter_dict:
            # Add user_id filter
            filter_dict = {
                "user_id": self.user_id,
                **filter_dict,
            }
            search_kwargs["filter"] = filter_dict
        else:
            search_kwargs["filter"] = {"user_id": self.user_id}

        # Search
        results = self.vector_store.similarity_search(query, **search_kwargs)

        # Format results
        formatted_results = []
        for doc in results:
            formatted_results.append(
                {
                    "content": doc.page_content,
                    "metadata": doc.metadata,
                }
            )

        logger.debug(
            f"Found {len(formatted_results)} memories for query: '{query[:50]}...'"
        )

        return formatted_results

    def search_with_scores(
        self,
        query: str,
        k: Optional[int] = None,
        score_threshold: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """
        Search memories with similarity scores.

        Args:
            query: Search query
            k: Number of results
            score_threshold: Minimum similarity score (0-1)

        Returns:
            List of memories with scores
        """
        k = k or self.top_k

        results = self.vector_store.similarity_search_with_relevance_scores(
            query,
            k=k,
            score_threshold=score_threshold,
            filter={"user_id": self.user_id},
        )

        formatted_results = []
        for doc, score in results:
            formatted_results.append(
                {
                    "content": doc.page_content,
                    "metadata": doc.metadata,
                    "score": score,
                }
            )

        logger.debug(
            f"Found {len(formatted_results)} memories above threshold "
            f"{score_threshold} for query: '{query[:50]}...'"
        )

        return formatted_results

    def get_relevant_context(
        self,
        query: str,
        k: int = 3,
    ) -> str:
        """
        Get relevant context for a query as formatted string.

        Args:
            query: Query string
            k: Number of results

        Returns:
            Formatted context string
        """
        results = self.search(query, k=k)

        if not results:
            return ""

        context_parts = []
        for i, result in enumerate(results, 1):
            timestamp = result["metadata"].get("timestamp", "Unknown")
            context_parts.append(
                f"[Memory {i}] ({timestamp})\n{result['content']}"
            )

        return "\n\n".join(context_parts)

    def delete_session_memories(self, session_id: str) -> int:
        """
        Delete all memories for a specific session.

        Args:
            session_id: Session identifier

        Returns:
            Number of deleted memories
        """
        # Note: PGVector doesn't have built-in delete by metadata
        # This would require custom SQL or recreating the collection
        logger.warning(
            f"Session memory deletion not fully implemented. "
            f"Consider recreating collection for session {session_id}"
        )
        return 0

    def clear_user_memories(self) -> None:
        """Clear all memories for the current user."""
        # This would require dropping the entire collection
        logger.warning(
            f"User memory clearing not fully implemented. "
            f"Consider dropping collection {self.collection_name}"
        )

    def get_memory_count(self) -> int:
        """
        Get total number of memories for user.

        Returns:
            Memory count
        """
        # This would require querying the vector store
        # For now, return estimate
        logger.warning("Memory count not implemented, returning 0")
        return 0


__all__ = ["VectorStoreMemory"]
