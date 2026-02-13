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
        score_threshold: Optional[float] = None,
        adaptive_threshold: bool = True,
        adaptive_std_multiplier: float = 1.5,
        min_adaptive_threshold: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """
        Search memories with similarity scores.

        Args:
            query: Search query
            k: Number of results
            score_threshold: Minimum similarity score (0-1). If None and
                adaptive_threshold is True, will be calculated based on result quality.
            adaptive_threshold: When True and score_threshold is None, automatically
                filters results based on score distribution.
            adaptive_std_multiplier: Standard deviation multiplier for adaptive threshold
                (default 1.5). Higher values are more permissive, lower are stricter.
            min_adaptive_threshold: Minimum floor for adaptive threshold (default 0.5).
                Prevents accepting very low-quality results even if they're relatively good.

        Returns:
            List of memories with scores and enhanced relevance metadata
        """
        k = k or self.top_k

        # Use a low initial threshold or None to get all candidates
        initial_threshold = score_threshold if score_threshold is not None else 0.0

        results = self.vector_store.similarity_search_with_relevance_scores(
            query,
            k=k * 2 if adaptive_threshold and score_threshold is None else k,
            score_threshold=initial_threshold,
            filter={"user_id": self.user_id},
        )

        # Apply adaptive threshold if requested and no explicit threshold provided
        applied_threshold = score_threshold
        
        # Handle empty results early
        if len(results) == 0:
            logger.debug(f"No results found for query: '{query[:50]}...'")
            return []
        
        # Handle single-result edge case
        if adaptive_threshold and score_threshold is None and len(results) == 1:
            single_score = results[0][1]
            # For single results, use a more conservative threshold
            # Accept if score is reasonably high, reject if very low
            if single_score < min_adaptive_threshold:
                results = []
                applied_threshold = min_adaptive_threshold
                logger.debug(
                    f"Single result rejected: score {single_score:.3f} below "
                    f"minimum threshold {min_adaptive_threshold:.3f}"
                )
            else:
                applied_threshold = max(single_score * 0.9, min_adaptive_threshold)
                logger.debug(
                    f"Single result accepted: score {single_score:.3f} "
                    f"(threshold: {applied_threshold:.3f})"
                )
        elif adaptive_threshold and score_threshold is None and len(results) > 1:
            scores = [score for _, score in results]
            mean_score = sum(scores) / len(scores)
            
            # Calculate standard deviation with Bessel's correction for sample variance
            # Using n-1 instead of n provides better estimate for population variance
            variance = sum((s - mean_score) ** 2 for s in scores) / max(len(scores) - 1, 1)
            std_dev = variance ** 0.5
            
            # Dynamic threshold based on score distribution
            # Uses coefficient of variation (CV) to adjust sensitivity:
            # - High CV (diverse scores) -> more selective (higher threshold)
            # - Low CV (similar scores) -> less selective (lower threshold)
            cv = std_dev / mean_score if mean_score > 0 else 0
            
            # Adjust multiplier based on variation
            # More variation = stricter filtering to avoid low-quality outliers
            # Cap CV influence to prevent extreme adjustments
            cv_adjustment = min(cv * 0.5, 0.8)
            dynamic_multiplier = adaptive_std_multiplier * (1 + cv_adjustment)
            
            # Keep results within dynamic standard deviations below mean
            # Special case: if std_dev is 0 (all scores identical), use mean as threshold
            if std_dev < 1e-6:
                # All scores are virtually identical, use a permissive threshold
                # But ensure we still filter out uniformly low-quality results
                if mean_score >= 0.7:
                    # High uniform quality - accept all
                    adaptive_threshold_value = max(min_adaptive_threshold, mean_score * 0.95)
                elif mean_score >= 0.5:
                    # Medium uniform quality - be slightly more selective
                    adaptive_threshold_value = max(min_adaptive_threshold, mean_score * 0.9)
                else:
                    # Low uniform quality - use minimum threshold to filter
                    adaptive_threshold_value = min_adaptive_threshold
                    logger.debug(
                        f"Uniform low-quality results detected (mean={mean_score:.3f}), "
                        f"applying strict minimum threshold"
                    )
            else:
                adaptive_threshold_value = max(
                    min_adaptive_threshold,
                    mean_score - dynamic_multiplier * std_dev
                )
            
            # Additional safeguard: if top score is very high, be more selective
            # Use a smooth transition based on top score quality
            top_score = max(scores)
            if top_score >= 0.85:
                # Scale selectivity based on top score quality
                # High scores (0.85-1.0) require proportionally higher threshold
                selectivity_factor = 0.65 + (top_score - 0.85) * 0.33  # 0.65 to 0.70
                top_score_threshold = top_score * selectivity_factor
                adaptive_threshold_value = max(
                    adaptive_threshold_value,
                    top_score_threshold
                )
            
            # Filter results
            results = [(doc, score) for doc, score in results 
                      if score >= adaptive_threshold_value][:k]
            
            applied_threshold = adaptive_threshold_value
            
            logger.debug(
                f"Applied adaptive threshold: {adaptive_threshold_value:.3f} "
                f"(mean={mean_score:.3f}, std={std_dev:.3f}, cv={cv:.3f}, "
                f"multiplier={dynamic_multiplier:.2f}, top={top_score:.3f})"
            )

        formatted_results = []
        for doc, score in results:
            # Dynamic relevance classification based on score distribution
            # Combines adaptive threshold awareness with absolute quality bounds
            dynamic_high = (
                applied_threshold is not None 
                and score >= max(applied_threshold * 1.3, 0.8)
            )
            
            if dynamic_high or score >= 0.85:
                relevance = "high"
            elif score >= 0.7:
                relevance = "medium"
            elif score >= 0.5:
                relevance = "low"
            else:
                relevance = "very_low"
            
            formatted_results.append(
                {
                    "content": doc.page_content,
                    "metadata": doc.metadata,
                    "score": score,
                    "relevance": relevance,
                    "confidence": "strong" if score >= 0.85 else "moderate" if score >= 0.7 else "weak",
                }
            )

        logger.debug(
            f"Found {len(formatted_results)} memories above threshold "
            f"{applied_threshold:.3f if applied_threshold else 'N/A'} "
            f"for query: '{query[:50]}...'"
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
