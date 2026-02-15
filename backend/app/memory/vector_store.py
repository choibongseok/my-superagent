"""Vector Store Memory implementation for semantic search.

This module provides vector-based memory storage using PGVector for
semantic similarity search across conversation history.
"""

import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional, Tuple

from langchain.embeddings import OpenAIEmbeddings
from langchain.memory import VectorStoreRetrieverMemory
from langchain.vectorstores import PGVector
from langchain_core.documents import Document

from app.core.config import settings

logger = logging.getLogger(__name__)

# Floating-point comparison epsilon for score calculations
# Used to determine when standard deviation is effectively zero
SCORE_EPSILON = 1e-6


class _UnavailableVectorStore:
    """Fallback vector-store shim used when PGVector initialization fails."""

    def __init__(self, reason: str):
        self.reason = reason

    def _raise(self) -> None:
        raise RuntimeError(
            "Vector store is unavailable. "
            f"Original initialization error: {self.reason}"
        )

    def add_documents(self, *_args: Any, **_kwargs: Any) -> List[str]:
        self._raise()

    def similarity_search(self, *_args: Any, **_kwargs: Any) -> List[Document]:
        self._raise()

    def similarity_search_with_relevance_scores(
        self, *_args: Any, **_kwargs: Any
    ) -> List[tuple[Document, float]]:
        self._raise()

    def as_retriever(self, *_args: Any, **_kwargs: Any) -> Any:
        self._raise()


class VectorStoreMemory:
    """
    Vector-based memory storage with semantic search capabilities.

    Features:
        - Semantic similarity search
        - Long-term memory storage
        - Efficient retrieval using vector embeddings
        - Integration with PGVector

    Confidence levels are represented in ascending order as:
    ``weak`` < ``moderate`` < ``strong``.

    Usage:
        memory = VectorStoreMemory(user_id="user123", session_id="session456")
        memory.add_memory("I love pizza", metadata={"topic": "food"})

        results = memory.search("What food do I like?", k=3)
        for result in results:
            print(result["content"])
    """

    CONFIDENCE_LEVEL_ORDER: Dict[str, int] = {
        "weak": 1,
        "moderate": 2,
        "strong": 3,
    }
    RELEVANCE_LEVEL_ORDER: Dict[str, int] = {
        "very_low": 1,
        "low": 2,
        "medium": 3,
        "high": 4,
    }

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

        self.available = True

        try:
            # Initialize PGVector store
            self.vector_store = PGVector(
                collection_name=self.collection_name,
                connection_string=settings.DATABASE_URL.replace(
                    "postgresql+asyncpg://", "postgresql://"
                ),
                embedding_function=self.embeddings,
            )

            # Create retriever
            self.retriever = self.vector_store.as_retriever(search_kwargs={"k": top_k})

            # LangChain memory wrapper
            self.memory = VectorStoreRetrieverMemory(
                retriever=self.retriever,
                memory_key="relevant_memories",
            )

            logger.info(
                f"VectorStoreMemory initialized for user={user_id}, "
                f"session={session_id}, collection={self.collection_name}"
            )
        except Exception as error:
            self.available = False
            self.vector_store = _UnavailableVectorStore(str(error))
            self.retriever = None
            self.memory = None
            logger.warning(
                "VectorStoreMemory initialized in degraded mode for "
                "user=%s, session=%s. Vector backend unavailable: %s",
                user_id,
                session_id,
                error,
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
            documents.append(Document(page_content=content, metadata=memory_metadata))

        ids = self.vector_store.add_documents(documents)

        logger.debug(
            f"Added {len(ids)} memories to vector store "
            f"(user={self.user_id}, session={self.session_id})"
        )

        return ids

    def _classify_relevance(
        self, score: float, adaptive_threshold: Optional[float] = None
    ) -> tuple[str, str]:
        """
        Classify relevance and confidence levels based on similarity score.

        Args:
            score: Similarity score (0-1)
            adaptive_threshold: Optional adaptive threshold for dynamic classification

        Returns:
            Tuple of (relevance_level, confidence_level)
            - relevance: "high", "medium", "low", "very_low"
            - confidence: "strong", "moderate", "weak"
        """
        # Dynamic relevance classification based on score distribution
        # Combines adaptive threshold awareness with absolute quality bounds
        dynamic_high = adaptive_threshold is not None and score >= max(
            adaptive_threshold * 1.3, 0.8
        )

        if dynamic_high or score >= 0.85:
            relevance = "high"
        elif score >= 0.7:
            relevance = "medium"
        elif score >= 0.5:
            relevance = "low"
        else:
            relevance = "very_low"

        # Confidence classification
        if score >= 0.85:
            confidence = "strong"
        elif score >= 0.7:
            confidence = "moderate"
        else:
            confidence = "weak"

        return relevance, confidence

    @classmethod
    def _normalize_min_confidence(
        cls,
        min_confidence: Optional[str],
    ) -> Optional[str]:
        """Normalize and validate optional confidence floor filters."""
        if min_confidence is None:
            return None

        if not isinstance(min_confidence, str):
            raise ValueError("min_confidence must be one of: weak, moderate, strong")

        normalized_confidence = min_confidence.strip().lower()
        if normalized_confidence not in cls.CONFIDENCE_LEVEL_ORDER:
            raise ValueError("min_confidence must be one of: weak, moderate, strong")

        return normalized_confidence

    @classmethod
    def _normalize_min_relevance(
        cls,
        min_relevance: Optional[str],
    ) -> Optional[str]:
        """Normalize and validate optional relevance floor filters."""
        if min_relevance is None:
            return None

        if not isinstance(min_relevance, str):
            raise ValueError(
                "min_relevance must be one of: very_low, low, medium, high"
            )

        normalized_relevance = min_relevance.strip().lower()
        if normalized_relevance not in cls.RELEVANCE_LEVEL_ORDER:
            raise ValueError(
                "min_relevance must be one of: very_low, low, medium, high"
            )

        return normalized_relevance

    def _build_user_scoped_filter(
        self,
        filter_dict: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build a metadata filter scoped to the current user.

        Args:
            filter_dict: Optional metadata filter from caller.

        Returns:
            Filter dictionary with enforced ``user_id``.

        Raises:
            ValueError: If filter_dict is provided and is not a dictionary.
        """
        if filter_dict is None:
            return {"user_id": self.user_id}

        if not isinstance(filter_dict, dict):
            raise ValueError("filter_dict must be a dictionary when provided")

        # Enforce user scoping even if caller tries to override user_id.
        return {**filter_dict, "user_id": self.user_id}

    @staticmethod
    def _normalize_content_for_deduplication(content: Any) -> str:
        """Normalize content strings for duplicate detection.

        Deduplication is case-insensitive and whitespace-insensitive to avoid
        returning near-identical memories that differ only by casing or spacing.
        """
        if not isinstance(content, str):
            content = str(content)

        return " ".join(content.split()).casefold()

    @classmethod
    def _deduplicate_results_by_content(
        cls,
        results: List[Tuple[Document, float]],
    ) -> List[Tuple[Document, float]]:
        """Drop duplicate results using normalized document content."""
        seen_contents: set[str] = set()
        deduplicated_results: List[Tuple[Document, float]] = []

        for doc, score in results:
            content_key = cls._normalize_content_for_deduplication(doc.page_content)
            if content_key in seen_contents:
                continue

            seen_contents.add(content_key)
            deduplicated_results.append((doc, score))

        return deduplicated_results

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
        search_kwargs = {
            "k": k,
            "filter": self._build_user_scoped_filter(filter_dict),
        }

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
        filter_dict: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None,
        adaptive_threshold: bool = True,
        adaptive_std_multiplier: float = 1.5,
        min_adaptive_threshold: float = 0.5,
        min_confidence: Optional[str] = None,
        min_relevance: Optional[str] = None,
        max_score_gap: Optional[float] = None,
        min_score_margin: Optional[float] = None,
        sort_by_score: bool = False,
        include_score_context: bool = False,
        unique_content: bool = False,
        offset: Optional[int] = None,
        max_results_per_session: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search memories with similarity scores.

        Args:
            query: Search query
            k: Number of results
            filter_dict: Optional metadata filters (always scoped to current user)
            score_threshold: Minimum similarity score (0-1). If None and
                adaptive_threshold is True, will be calculated based on result quality.
            adaptive_threshold: When True and score_threshold is None, automatically
                filters results based on score distribution.
            adaptive_std_multiplier: Standard deviation multiplier for adaptive threshold
                (default 1.5). Higher values are more permissive, lower are stricter.
            min_adaptive_threshold: Minimum floor for adaptive threshold (default 0.5).
                Prevents accepting very low-quality results even if they're relatively good.
            min_confidence: Optional confidence floor filter. Accepted values are
                ``"weak"``, ``"moderate"``, and ``"strong"``. When set,
                results below that confidence level are excluded.
            min_relevance: Optional relevance floor filter. Accepted values are
                ``"very_low"``, ``"low"``, ``"medium"``, and ``"high"``.
                When set, results below that relevance level are excluded.
            max_score_gap: Optional score-band filter applied relative to the
                strongest candidate after thresholding. When set, only results
                where ``top_score - score <= max_score_gap`` are retained.
                Accepted range is ``[0, 1]``.
            min_score_margin: Optional minimum margin above the active
                threshold baseline. When set, only results where
                ``score >= baseline_threshold + min_score_margin`` are kept.
                Baseline threshold is the adaptive/explicit threshold when
                available, otherwise ``0.0``. Accepted range is ``[0, 1]``.
            sort_by_score: When ``True``, sort accepted results by descending score
                before applying the final ``k`` limit. Ties preserve original
                vector-store order for deterministic pagination.
            include_score_context: When ``True``, attach a ``score_context`` object
                to each result with explainability details (rank, top-score gap,
                and threshold margin).
            unique_content: When ``True``, collapse duplicate memories by
                normalized content (case/whitespace insensitive) before applying
                pagination.
            offset: Optional zero-based pagination offset applied after filtering
                and ordering but before the final ``k`` limit. Must be >= 0 when
                provided.
            max_results_per_session: Optional per-session cap used to diversify
                ranked results. When set, at most this many memories are retained
                for each distinct ``metadata.session_id`` while preserving rank
                order. Messages without ``session_id`` are not capped.

        Returns:
            List of memories with scores and enhanced relevance metadata

        Raises:
            ValueError: If thresholds/parameters are invalid, including unsupported
                ``min_confidence``/``min_relevance`` values, invalid
                ``max_score_gap``/``min_score_margin``/``offset``/
                ``max_results_per_session`` values,
                or non-boolean ``include_score_context``/``unique_content``.
        """
        # Input validation
        if score_threshold is not None and not (0.0 <= score_threshold <= 1.0):
            raise ValueError(
                f"score_threshold must be in [0, 1], got {score_threshold}"
            )

        if not (0.0 <= min_adaptive_threshold <= 1.0):
            raise ValueError(
                f"min_adaptive_threshold must be in [0, 1], got {min_adaptive_threshold}"
            )

        if adaptive_std_multiplier < 0:
            raise ValueError(
                f"adaptive_std_multiplier must be non-negative, got {adaptive_std_multiplier}"
            )

        if not isinstance(include_score_context, bool):
            raise ValueError("include_score_context must be a boolean")

        if not isinstance(unique_content, bool):
            raise ValueError("unique_content must be a boolean")

        if offset is not None:
            if isinstance(offset, bool) or not isinstance(offset, int):
                raise ValueError("offset must be an integer")
            if offset < 0:
                raise ValueError("offset cannot be negative")

        if max_results_per_session is not None:
            if isinstance(max_results_per_session, bool) or not isinstance(
                max_results_per_session, int
            ):
                raise ValueError("max_results_per_session must be an integer")
            if max_results_per_session <= 0:
                raise ValueError("max_results_per_session must be greater than 0")

        if max_score_gap is not None:
            if isinstance(max_score_gap, bool) or not isinstance(
                max_score_gap, (int, float)
            ):
                raise ValueError(
                    f"max_score_gap must be in [0, 1], got {max_score_gap}"
                )

            max_score_gap = float(max_score_gap)
            if not (0.0 <= max_score_gap <= 1.0):
                raise ValueError(
                    f"max_score_gap must be in [0, 1], got {max_score_gap}"
                )

        if min_score_margin is not None:
            if isinstance(min_score_margin, bool) or not isinstance(
                min_score_margin, (int, float)
            ):
                raise ValueError(
                    f"min_score_margin must be in [0, 1], got {min_score_margin}"
                )

            min_score_margin = float(min_score_margin)
            if not (0.0 <= min_score_margin <= 1.0):
                raise ValueError(
                    f"min_score_margin must be in [0, 1], got {min_score_margin}"
                )

        normalized_min_confidence = self._normalize_min_confidence(min_confidence)
        min_confidence_rank = (
            self.CONFIDENCE_LEVEL_ORDER[normalized_min_confidence]
            if normalized_min_confidence is not None
            else None
        )

        normalized_min_relevance = self._normalize_min_relevance(min_relevance)
        min_relevance_rank = (
            self.RELEVANCE_LEVEL_ORDER[normalized_min_relevance]
            if normalized_min_relevance is not None
            else None
        )

        k = k or self.top_k
        normalized_offset = offset or 0
        search_filter = self._build_user_scoped_filter(filter_dict)

        # Request enough candidates to support post-filter pagination.
        requested_result_count = k + normalized_offset

        # Use a low initial threshold or None to get all candidates
        initial_threshold = score_threshold if score_threshold is not None else 0.0

        results = self.vector_store.similarity_search_with_relevance_scores(
            query,
            k=(requested_result_count * 2)
            if adaptive_threshold and score_threshold is None
            else requested_result_count,
            score_threshold=initial_threshold,
            filter=search_filter,
        )

        # Validate and sanitize scores from vector store
        # Scores should be in [0, 1] but we guard against malformed results
        sanitized_results = []
        for doc, score in results:
            if not isinstance(score, (int, float)):
                logger.warning(f"Invalid score type: {type(score)}, skipping result")
                continue
            # Clamp score to valid range
            clamped_score = min(max(float(score), 0.0), 1.0)
            if abs(clamped_score - score) > SCORE_EPSILON:
                logger.warning(
                    f"Score {score} out of [0, 1] range, clamped to {clamped_score}"
                )
            sanitized_results.append((doc, clamped_score))

        results = sanitized_results

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
            variance = sum((s - mean_score) ** 2 for s in scores) / max(
                len(scores) - 1, 1
            )
            std_dev = variance**0.5

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
            # Special case: if std_dev is near-zero (all scores virtually identical)
            if std_dev < SCORE_EPSILON:
                # All scores are virtually identical, use a permissive threshold
                # But ensure we still filter out uniformly low-quality results
                if mean_score >= 0.7:
                    # High uniform quality - accept all
                    adaptive_threshold_value = max(
                        min_adaptive_threshold, mean_score * 0.95
                    )
                elif mean_score >= 0.5:
                    # Medium uniform quality - be slightly more selective
                    adaptive_threshold_value = max(
                        min_adaptive_threshold, mean_score * 0.9
                    )
                else:
                    # Low uniform quality - use minimum threshold to filter
                    adaptive_threshold_value = min_adaptive_threshold
                    logger.debug(
                        f"Uniform low-quality results detected (mean={mean_score:.3f}), "
                        f"applying strict minimum threshold"
                    )
            else:
                adaptive_threshold_value = max(
                    min_adaptive_threshold, mean_score - dynamic_multiplier * std_dev
                )

            # Additional safeguard: if top score is very high, be more selective
            # Use a smooth transition based on top score quality
            top_score = max(scores)
            # Clamp top_score to [0, 1] as a safety guard (shouldn't exceed 1.0 in normal operation)
            top_score = min(max(top_score, 0.0), 1.0)

            if top_score >= 0.85:
                # Scale selectivity based on top score quality
                # High scores (0.85-1.0) require proportionally higher threshold
                # Linear interpolation: 0.85->0.65, 1.0->0.70 (clamped to prevent overflow)
                score_range = min(top_score - 0.85, 0.15)  # Max 0.15 for top_score=1.0
                selectivity_factor = 0.65 + score_range * (
                    0.33 / 0.15
                )  # Normalized multiplier
                top_score_threshold = top_score * selectivity_factor
                adaptive_threshold_value = max(
                    adaptive_threshold_value, top_score_threshold
                )

            # Filter results
            results = [
                (doc, score)
                for doc, score in results
                if score >= adaptive_threshold_value
            ]

            applied_threshold = adaptive_threshold_value

            logger.debug(
                f"Applied adaptive threshold: {adaptive_threshold_value:.3f} "
                f"(mean={mean_score:.3f}, std={std_dev:.3f}, cv={cv:.3f}, "
                f"multiplier={dynamic_multiplier:.2f}, top={top_score:.3f})"
            )

        if min_score_margin is not None and results:
            baseline_threshold = (
                applied_threshold if applied_threshold is not None else 0.0
            )
            minimum_allowed_score = min(1.0, baseline_threshold + min_score_margin)
            results = [
                (doc, score)
                for doc, score in results
                if score + SCORE_EPSILON >= minimum_allowed_score
            ]
            logger.debug(
                "Applied min_score_margin filtering: margin=%.3f, baseline=%.3f, min=%.3f, kept=%d",
                min_score_margin,
                baseline_threshold,
                minimum_allowed_score,
                len(results),
            )

        if max_score_gap is not None and results:
            top_score_after_threshold = max(score for _, score in results)
            minimum_allowed_score = max(0.0, top_score_after_threshold - max_score_gap)
            results = [
                (doc, score)
                for doc, score in results
                if score + SCORE_EPSILON >= minimum_allowed_score
            ]
            logger.debug(
                "Applied max_score_gap filtering: gap=%.3f, top=%.3f, min=%.3f, kept=%d",
                max_score_gap,
                top_score_after_threshold,
                minimum_allowed_score,
                len(results),
            )

        if sort_by_score:
            indexed_results = list(enumerate(results))
            indexed_results.sort(key=lambda item: (-item[1][1], item[0]))
            results = [result for _, result in indexed_results]

        if unique_content:
            original_count = len(results)
            results = self._deduplicate_results_by_content(results)
            logger.debug(
                "Applied unique_content deduplication: before=%d, after=%d",
                original_count,
                len(results),
            )

        if max_results_per_session is not None and results:
            diversified_results: List[Tuple[Document, float]] = []
            per_session_counts: Dict[str, int] = {}

            for doc, score in results:
                metadata = doc.metadata if isinstance(doc.metadata, dict) else {}
                session_identifier = metadata.get("session_id")

                if session_identifier is None:
                    diversified_results.append((doc, score))
                    continue

                session_key = str(session_identifier)
                session_count = per_session_counts.get(session_key, 0)
                if session_count >= max_results_per_session:
                    continue

                per_session_counts[session_key] = session_count + 1
                diversified_results.append((doc, score))

            logger.debug(
                "Applied max_results_per_session filtering: limit=%d, before=%d, after=%d",
                max_results_per_session,
                len(results),
                len(diversified_results),
            )
            results = diversified_results

        if normalized_offset:
            results = results[normalized_offset:]

        if len(results) > k:
            results = results[:k]

        top_score = max((score for _, score in results), default=None)
        formatted_results = []
        for rank, (doc, score) in enumerate(results, start=1):
            relevance, confidence = self._classify_relevance(score, applied_threshold)

            if (
                min_relevance_rank is not None
                and self.RELEVANCE_LEVEL_ORDER[relevance] < min_relevance_rank
            ):
                continue

            if (
                min_confidence_rank is not None
                and self.CONFIDENCE_LEVEL_ORDER[confidence] < min_confidence_rank
            ):
                continue

            result_payload = {
                "content": doc.page_content,
                "metadata": doc.metadata,
                "score": score,
                "relevance": relevance,
                "confidence": confidence,
            }

            if include_score_context and top_score is not None:
                threshold_for_margin = (
                    applied_threshold if applied_threshold is not None else 0.0
                )
                result_payload["score_context"] = {
                    "rank": rank,
                    "top_score": top_score,
                    "gap_from_top": max(0.0, top_score - score),
                    "margin_above_threshold": score - threshold_for_margin,
                    "applied_threshold": applied_threshold,
                }

            formatted_results.append(result_payload)

        threshold_label = (
            f"{applied_threshold:.3f}" if applied_threshold is not None else "N/A"
        )
        logger.debug(
            f"Found {len(formatted_results)} memories above threshold "
            f"{threshold_label} for query: '{query[:50]}...'"
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
            context_parts.append(f"[Memory {i}] ({timestamp})\n{result['content']}")

        return "\n\n".join(context_parts)

    @contextmanager
    def _collection_session(
        self,
    ) -> Generator[Tuple[Optional[Any], Optional[Any]], None, None]:
        """Yield an active vector-store session and target collection.

        Yields:
            Tuple of (session, collection). Either value can be None when
            the backend is unavailable or the collection does not exist.
        """
        if not self.available:
            logger.warning(
                "Vector store unavailable for user=%s, session=%s",
                self.user_id,
                self.session_id,
            )
            yield None, None
            return

        session_factory = getattr(self.vector_store, "_make_session", None)
        get_collection = getattr(self.vector_store, "get_collection", None)
        if not callable(session_factory) or not callable(get_collection):
            logger.warning(
                "Vector store does not expose session helpers for collection operations"
            )
            yield None, None
            return

        with session_factory() as session:
            collection = get_collection(session)
            if collection is None:
                logger.debug(
                    "Collection '%s' not found for user=%s",
                    self.collection_name,
                    self.user_id,
                )
            yield session, collection

    def _fetch_collection_embeddings(
        self,
        session: Any,
        collection: Any,
    ) -> List[Any]:
        """Fetch all embedding rows for the active collection."""
        embedding_store = getattr(self.vector_store, "EmbeddingStore", None)
        if embedding_store is None:
            logger.warning("Vector store EmbeddingStore model is unavailable")
            return []

        return (
            session.query(embedding_store)
            .filter(embedding_store.collection_id == collection.uuid)
            .all()
        )

    def delete_session_memories(self, session_id: str) -> int:
        """Delete all memories for a specific session.

        Args:
            session_id: Session identifier

        Returns:
            Number of deleted memories
        """
        if not session_id:
            raise ValueError("session_id is required")

        with self._collection_session() as (session, collection):
            if session is None or collection is None:
                return 0

            embeddings = self._fetch_collection_embeddings(session, collection)
            to_delete = []
            for embedding in embeddings:
                metadata = getattr(embedding, "cmetadata", None)
                if not isinstance(metadata, dict):
                    metadata = {}

                metadata_user_id = metadata.get("user_id")
                if metadata_user_id and metadata_user_id != self.user_id:
                    continue

                if metadata.get("session_id") == session_id:
                    to_delete.append(embedding)

            for embedding in to_delete:
                session.delete(embedding)

            if to_delete:
                session.commit()

            deleted_count = len(to_delete)
            logger.info(
                "Deleted %d vector memories for user=%s session=%s",
                deleted_count,
                self.user_id,
                session_id,
            )
            return deleted_count

    def clear_user_memories(self) -> int:
        """Clear all memories for the current user.

        Returns:
            Number of deleted memories
        """
        with self._collection_session() as (session, collection):
            if session is None or collection is None:
                return 0

            embeddings = self._fetch_collection_embeddings(session, collection)
            to_delete = []
            for embedding in embeddings:
                metadata = getattr(embedding, "cmetadata", None)
                if not isinstance(metadata, dict):
                    metadata = {}

                metadata_user_id = metadata.get("user_id")
                if metadata_user_id and metadata_user_id != self.user_id:
                    continue

                to_delete.append(embedding)

            for embedding in to_delete:
                session.delete(embedding)

            if to_delete:
                session.commit()

            deleted_count = len(to_delete)
            logger.info(
                "Cleared %d vector memories for user=%s",
                deleted_count,
                self.user_id,
            )
            return deleted_count

    def get_memory_count(self) -> int:
        """Get total number of memories for the current user."""
        with self._collection_session() as (session, collection):
            if session is None or collection is None:
                return 0

            embedding_store = getattr(self.vector_store, "EmbeddingStore", None)
            if embedding_store is None:
                logger.warning("Vector store EmbeddingStore model is unavailable")
                return 0

            return (
                session.query(embedding_store)
                .filter(embedding_store.collection_id == collection.uuid)
                .count()
            )


__all__ = ["VectorStoreMemory"]
