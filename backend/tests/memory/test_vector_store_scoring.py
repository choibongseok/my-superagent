"""
Tests for VectorStoreMemory scoring and adaptive threshold logic.

This module tests the complex scoring algorithms in vector_store.py,
including input validation, edge cases, and adaptive threshold calculations.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from langchain_core.documents import Document

from app.memory.vector_store import VectorStoreMemory, SCORE_EPSILON


class TestVectorStoreInitializationFallback:
    """Test degraded-mode initialization behavior when PGVector is unavailable."""

    @patch("app.memory.vector_store.OpenAIEmbeddings")
    @patch("app.memory.vector_store.PGVector", side_effect=RuntimeError("db down"))
    def test_initialization_falls_back_to_degraded_mode(
        self,
        _mock_pgvector,
        _mock_embeddings,
    ):
        """VectorStoreMemory should initialize without crashing when PGVector fails."""
        memory = VectorStoreMemory(user_id="test_user")

        assert memory.available is False

    @patch("app.memory.vector_store.OpenAIEmbeddings")
    @patch("app.memory.vector_store.PGVector", side_effect=RuntimeError("db down"))
    def test_degraded_mode_provides_clear_runtime_error(
        self,
        _mock_pgvector,
        _mock_embeddings,
    ):
        """Degraded mode should raise an actionable error on vector operations."""
        memory = VectorStoreMemory(user_id="test_user")

        with pytest.raises(RuntimeError, match="Vector store is unavailable"):
            memory.search(query="test")

    @patch(
        "app.memory.vector_store.OpenAIEmbeddings",
        side_effect=RuntimeError("missing openai api key"),
    )
    def test_initialization_falls_back_when_embeddings_init_fails(
        self,
        _mock_embeddings,
    ):
        """Embedding init failures should also trigger degraded mode."""
        memory = VectorStoreMemory(user_id="test_user")

        assert memory.available is False

        with pytest.raises(RuntimeError, match="Vector store is unavailable"):
            memory.search(query="test")


class TestVectorStoreScoringValidation:
    """Test input validation for scoring parameters."""

    def test_score_threshold_validation_too_low(self):
        """Test that score_threshold < 0 raises ValueError."""
        memory = VectorStoreMemory(user_id="test_user")

        with pytest.raises(ValueError, match="score_threshold must be in"):
            memory.search_with_scores(query="test", score_threshold=-0.1)

    def test_score_threshold_validation_too_high(self):
        """Test that score_threshold > 1 raises ValueError."""
        memory = VectorStoreMemory(user_id="test_user")

        with pytest.raises(ValueError, match="score_threshold must be in"):
            memory.search_with_scores(query="test", score_threshold=1.5)

    def test_min_adaptive_threshold_validation(self):
        """Test that min_adaptive_threshold is validated."""
        memory = VectorStoreMemory(user_id="test_user")

        with pytest.raises(ValueError, match="min_adaptive_threshold must be in"):
            memory.search_with_scores(query="test", min_adaptive_threshold=2.0)

    def test_std_multiplier_validation(self):
        """Test that adaptive_std_multiplier must be non-negative."""
        memory = VectorStoreMemory(user_id="test_user")

        with pytest.raises(
            ValueError, match="adaptive_std_multiplier must be non-negative"
        ):
            memory.search_with_scores(query="test", adaptive_std_multiplier=-1.0)

    def test_valid_parameters_accepted(self):
        """Test that valid parameters don't raise errors."""
        memory = VectorStoreMemory(user_id="test_user")

        # Mock the vector store to avoid actual DB calls
        with patch.object(
            memory.vector_store,
            "similarity_search_with_relevance_scores",
            return_value=[],
        ):
            # Should not raise
            result = memory.search_with_scores(
                query="test",
                score_threshold=0.7,
                min_adaptive_threshold=0.5,
                adaptive_std_multiplier=1.5,
            )
            assert result == []


class TestSearchFilterScoping:
    """Test metadata filtering support for scored vector searches."""

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_search_with_scores_applies_filter_and_user_scope(self):
        """Caller-provided filters should be merged with enforced user scoping."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5
        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=[]
        )

        memory.search_with_scores(
            query="test",
            adaptive_threshold=False,
            score_threshold=0.1,
            filter_dict={"session_id": "session-123", "topic": "product"},
        )

        memory.vector_store.similarity_search_with_relevance_scores.assert_called_once_with(
            "test",
            k=5,
            score_threshold=0.1,
            filter={
                "session_id": "session-123",
                "topic": "product",
                "user_id": "test_user",
            },
        )

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_search_with_scores_filter_cannot_override_user_id(self):
        """user_id from filter_dict must never override the active user scope."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5
        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=[]
        )

        memory.search_with_scores(
            query="test",
            adaptive_threshold=False,
            score_threshold=0.1,
            filter_dict={"user_id": "malicious", "session_id": "session-123"},
        )

        called_filter = memory.vector_store.similarity_search_with_relevance_scores.call_args.kwargs[
            "filter"
        ]
        assert called_filter["user_id"] == "test_user"
        assert called_filter["session_id"] == "session-123"

    def test_search_with_scores_filter_validation(self):
        """Non-dictionary filter_dict values should fail fast."""
        memory = VectorStoreMemory(user_id="test_user")

        with pytest.raises(ValueError, match="filter_dict must be a dictionary"):
            memory.search_with_scores(query="test", filter_dict="invalid")


class TestRelevanceClassification:
    """Test the _classify_relevance helper method."""

    def test_high_relevance_strong_confidence(self):
        """Test classification for score >= 0.85."""
        memory = VectorStoreMemory(user_id="test_user")

        relevance, confidence = memory._classify_relevance(0.90)
        assert relevance == "high"
        assert confidence == "strong"

    def test_medium_relevance_moderate_confidence(self):
        """Test classification for 0.7 <= score < 0.85."""
        memory = VectorStoreMemory(user_id="test_user")

        relevance, confidence = memory._classify_relevance(0.75)
        assert relevance == "medium"
        assert confidence == "moderate"

    def test_low_relevance_weak_confidence(self):
        """Test classification for 0.5 <= score < 0.7."""
        memory = VectorStoreMemory(user_id="test_user")

        relevance, confidence = memory._classify_relevance(0.6)
        assert relevance == "low"
        assert confidence == "weak"

    def test_very_low_relevance(self):
        """Test classification for score < 0.5."""
        memory = VectorStoreMemory(user_id="test_user")

        relevance, confidence = memory._classify_relevance(0.3)
        assert relevance == "very_low"
        assert confidence == "weak"

    def test_dynamic_high_with_adaptive_threshold(self):
        """Test dynamic classification when score exceeds adaptive threshold * 1.3."""
        memory = VectorStoreMemory(user_id="test_user")

        # Score 0.78 would normally be "medium", but with adaptive_threshold=0.6,
        # 0.78 >= max(0.6 * 1.3, 0.8) = 0.8 is False (0.78 < 0.8)
        # so it should still be "medium"
        relevance, confidence = memory._classify_relevance(0.78, adaptive_threshold=0.6)
        assert relevance == "medium"

        # But with adaptive_threshold=0.65, 0.78 >= max(0.65*1.3, 0.8) = max(0.845, 0.8) = 0.845 is False
        relevance, confidence = memory._classify_relevance(
            0.85, adaptive_threshold=0.65
        )
        assert relevance == "high"  # Absolute threshold kicks in

    def test_boundary_conditions(self):
        """Test edge cases at exact boundaries."""
        memory = VectorStoreMemory(user_id="test_user")

        # Exactly 0.85
        relevance, confidence = memory._classify_relevance(0.85)
        assert relevance == "high"
        assert confidence == "strong"

        # Just below 0.85
        relevance, confidence = memory._classify_relevance(0.85 - SCORE_EPSILON)
        assert relevance == "medium"

        # Exactly 0.7
        relevance, confidence = memory._classify_relevance(0.7)
        assert relevance == "medium"
        assert confidence == "moderate"

        # Exactly 0.5
        relevance, confidence = memory._classify_relevance(0.5)
        assert relevance == "low"


class TestScoreSanitization:
    """Test score validation and sanitization from vector store results."""

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_out_of_range_scores_clamped(self, caplog):
        """Test that scores outside [0, 1] are clamped and logged."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        # Mock vector store
        mock_doc = Document(page_content="test", metadata={})
        mock_results = [
            (mock_doc, 1.5),  # Too high
            (mock_doc, -0.1),  # Too low
            (mock_doc, 0.8),  # Valid
        ]

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=mock_results
        )

        with caplog.at_level("WARNING"):
            results = memory.search_with_scores(
                query="test", adaptive_threshold=False, score_threshold=0.0
            )

        # Check that warnings were logged
        assert "out of [0, 1] range" in caplog.text

        # Verify scores were clamped
        assert len(results) == 3
        assert results[0]["score"] == 1.0  # Clamped from 1.5
        assert results[1]["score"] == 0.0  # Clamped from -0.1
        assert results[2]["score"] == 0.8  # Unchanged

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_invalid_score_types_skipped(self, caplog):
        """Test that non-numeric scores are skipped with warning."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        # Mock vector store
        mock_doc = Document(page_content="test", metadata={})
        mock_results = [
            (mock_doc, "invalid"),  # String score
            (mock_doc, 0.8),  # Valid
            (mock_doc, None),  # None score
        ]

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=mock_results
        )

        with caplog.at_level("WARNING"):
            results = memory.search_with_scores(
                query="test", adaptive_threshold=False, score_threshold=0.0
            )

        # Check that warnings were logged
        assert "Invalid score type" in caplog.text

        # Only valid score should remain
        assert len(results) == 1
        assert results[0]["score"] == 0.8


class TestConfidenceFiltering:
    """Test optional confidence-level filtering for scored searches."""

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_min_confidence_validation(self):
        """Unsupported confidence floors should fail fast with a clear error."""
        memory = VectorStoreMemory(user_id="test_user")

        with pytest.raises(
            ValueError,
            match="min_confidence must be one of: weak, moderate, strong",
        ):
            memory.search_with_scores(query="test", min_confidence="expert")

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_min_confidence_filters_out_weaker_results(self):
        """min_confidence='moderate' should keep only moderate/strong matches."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        high_doc = Document(page_content="high", metadata={"id": "high"})
        moderate_doc = Document(page_content="moderate", metadata={"id": "moderate"})
        weak_doc = Document(page_content="weak", metadata={"id": "weak"})

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=[
                (high_doc, 0.9),
                (moderate_doc, 0.74),
                (weak_doc, 0.55),
            ]
        )

        results = memory.search_with_scores(
            query="test",
            adaptive_threshold=False,
            score_threshold=0.0,
            min_confidence="moderate",
        )

        assert [result["content"] for result in results] == ["high", "moderate"]
        assert [result["confidence"] for result in results] == ["strong", "moderate"]


class TestRelevanceFiltering:
    """Test optional relevance-level filtering for scored searches."""

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_min_relevance_validation(self):
        """Unsupported relevance floors should fail fast with a clear error."""
        memory = VectorStoreMemory(user_id="test_user")

        with pytest.raises(
            ValueError,
            match="min_relevance must be one of: very_low, low, medium, high",
        ):
            memory.search_with_scores(query="test", min_relevance="critical")

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_min_relevance_filters_lower_quality_results(self):
        """min_relevance='medium' should keep only medium/high relevance matches."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        high_doc = Document(page_content="high", metadata={"id": "high"})
        medium_doc = Document(page_content="medium", metadata={"id": "medium"})
        low_doc = Document(page_content="low", metadata={"id": "low"})
        very_low_doc = Document(page_content="very_low", metadata={"id": "very_low"})

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=[
                (high_doc, 0.9),
                (medium_doc, 0.72),
                (low_doc, 0.56),
                (very_low_doc, 0.41),
            ]
        )

        results = memory.search_with_scores(
            query="test",
            adaptive_threshold=False,
            score_threshold=0.0,
            min_relevance="  MEDIUM  ",
        )

        assert [result["content"] for result in results] == ["high", "medium"]
        assert [result["relevance"] for result in results] == ["high", "medium"]


class TestSelectivityFactorEdgeCases:
    """Test edge cases in selectivity factor calculation."""

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_top_score_above_one_clamped(self):
        """Test that top_score > 1.0 is clamped before selectivity calculation."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        # Mock vector store - this shouldn't happen in practice, but we test the guard
        mock_doc = Document(page_content="test", metadata={})
        # After sanitization, this will be clamped to 1.0
        mock_results = [
            (mock_doc, 1.2),  # Will be clamped
        ]

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=mock_results
        )

        # Should not raise, and should handle clamped score correctly
        results = memory.search_with_scores(query="test", score_threshold=0.0)

        # Verify it was processed without error
        assert len(results) == 1
        assert results[0]["score"] == 1.0


class TestAdaptiveThresholdLogic:
    """Test adaptive threshold calculations."""

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_single_result_below_minimum_rejected(self, caplog):
        """Test that single result below min_adaptive_threshold is rejected."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        mock_doc = Document(page_content="test", metadata={})
        mock_results = [(mock_doc, 0.3)]  # Below default min_adaptive_threshold of 0.5

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=mock_results
        )

        with caplog.at_level("DEBUG"):
            results = memory.search_with_scores(
                query="test", min_adaptive_threshold=0.5
            )

        assert len(results) == 0
        assert "Single result rejected" in caplog.text

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_single_result_above_minimum_accepted(self, caplog):
        """Test that single result above min_adaptive_threshold is accepted."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        mock_doc = Document(page_content="test", metadata={})
        mock_results = [(mock_doc, 0.75)]

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=mock_results
        )

        with caplog.at_level("DEBUG"):
            results = memory.search_with_scores(
                query="test", min_adaptive_threshold=0.5
            )

        assert len(results) == 1
        assert "Single result accepted" in caplog.text

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_uniform_low_quality_filtered(self, caplog):
        """Test that uniformly low-quality results trigger strict filtering."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        mock_doc = Document(page_content="test", metadata={})
        # All scores virtually identical and low quality (std_dev < epsilon)
        mock_results = [
            (mock_doc, 0.45),
            (mock_doc, 0.45),
            (mock_doc, 0.45),
        ]

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=mock_results
        )

        with caplog.at_level("DEBUG"):
            results = memory.search_with_scores(
                query="test", min_adaptive_threshold=0.5
            )

        # Should apply strict minimum threshold and filter out all results
        assert len(results) == 0
        assert "Uniform low-quality results detected" in caplog.text


class TestEpsilonConsistency:
    """Test that SCORE_EPSILON is used consistently."""

    def test_epsilon_constant_exists(self):
        """Verify SCORE_EPSILON constant is defined."""
        assert SCORE_EPSILON == 1e-6

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_epsilon_used_in_std_dev_check(self):
        """Test that epsilon is used for zero std_dev check."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        mock_doc = Document(page_content="test", metadata={})
        # Results with std_dev < SCORE_EPSILON (all identical)
        identical_score = 0.75
        mock_results = [
            (mock_doc, identical_score),
            (mock_doc, identical_score),
            (mock_doc, identical_score + SCORE_EPSILON / 2),  # Within epsilon
        ]

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=mock_results
        )

        # Should handle near-zero std_dev gracefully
        results = memory.search_with_scores(query="test")

        # Should accept all results (high uniform quality)
        assert len(results) == 3


class TestScoreSorting:
    """Test optional score-based sorting for deterministic ranking."""

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_sort_by_score_orders_results_descending(self):
        """sort_by_score should reorder results by descending similarity score."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        low_doc = Document(page_content="low", metadata={})
        high_doc = Document(page_content="high", metadata={})
        medium_doc = Document(page_content="medium", metadata={})

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=[
                (low_doc, 0.31),
                (high_doc, 0.92),
                (medium_doc, 0.65),
            ]
        )

        results = memory.search_with_scores(
            query="test",
            adaptive_threshold=False,
            score_threshold=0.0,
            sort_by_score=True,
        )

        assert [result["content"] for result in results] == ["high", "medium", "low"]
        assert [result["score"] for result in results] == [0.92, 0.65, 0.31]

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_sort_by_score_preserves_input_order_for_ties(self):
        """Equal scores should keep original order for stable pagination."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        first_doc = Document(page_content="first", metadata={})
        second_doc = Document(page_content="second", metadata={})

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=[
                (first_doc, 0.8),
                (second_doc, 0.8),
            ]
        )

        results = memory.search_with_scores(
            query="test",
            adaptive_threshold=False,
            score_threshold=0.0,
            sort_by_score=True,
        )

        assert [result["content"] for result in results] == ["first", "second"]


class TestTimestampWindowFiltering:
    """Test optional timestamp boundaries for scored search results."""

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_timestamp_boundary_validation(self):
        """Timestamp boundaries should reject invalid values and ranges."""
        memory = VectorStoreMemory(user_id="test_user")

        with pytest.raises(
            ValueError,
            match="created_after must be a datetime object or ISO-8601 string",
        ):
            memory.search_with_scores(query="test", created_after=123)

        with pytest.raises(
            ValueError,
            match="created_before must be a valid ISO-8601 datetime",
        ):
            memory.search_with_scores(query="test", created_before="not-a-date")

        with pytest.raises(
            ValueError,
            match="created_after must be earlier than or equal to created_before",
        ):
            memory.search_with_scores(
                query="test",
                created_after="2026-02-15T10:00:00Z",
                created_before="2026-02-15T09:00:00Z",
            )

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_max_age_hours_validation(self):
        """max_age_hours should reject invalid values."""
        memory = VectorStoreMemory(user_id="test_user")

        with pytest.raises(ValueError, match="max_age_hours must be a positive number"):
            memory.search_with_scores(query="test", max_age_hours="2")

        with pytest.raises(ValueError, match="max_age_hours must be a positive number"):
            memory.search_with_scores(query="test", max_age_hours=True)

        with pytest.raises(ValueError, match="max_age_hours must be greater than 0"):
            memory.search_with_scores(query="test", max_age_hours=0)

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_max_age_hours_filters_outdated_memories(self):
        """max_age_hours should keep only results inside the recency window."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        now = datetime.now(timezone.utc)
        old_doc = Document(
            page_content="old",
            metadata={"timestamp": (now - timedelta(hours=3)).isoformat()},
        )
        recent_doc = Document(
            page_content="recent",
            metadata={"timestamp": (now - timedelta(minutes=20)).isoformat()},
        )

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=[
                (old_doc, 0.9),
                (recent_doc, 0.87),
            ]
        )

        results = memory.search_with_scores(
            query="test",
            adaptive_threshold=False,
            score_threshold=0.0,
            max_age_hours=1,
        )

        assert [result["content"] for result in results] == ["recent"]

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_created_after_wins_when_stricter_than_max_age_window(self):
        """When both are set, the stricter lower time boundary should apply."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        now = datetime.now(timezone.utc)
        inside_max_age_only = Document(
            page_content="inside-max-age",
            metadata={"timestamp": (now - timedelta(hours=1)).isoformat()},
        )
        inside_both = Document(
            page_content="inside-both",
            metadata={"timestamp": (now - timedelta(minutes=20)).isoformat()},
        )

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=[
                (inside_max_age_only, 0.9),
                (inside_both, 0.88),
            ]
        )

        results = memory.search_with_scores(
            query="test",
            adaptive_threshold=False,
            score_threshold=0.0,
            max_age_hours=2,
            created_after=(now - timedelta(minutes=30)).isoformat(),
        )

        assert [result["content"] for result in results] == ["inside-both"]

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_created_after_filters_out_older_memories(self):
        """created_after should keep only memories newer than the lower bound."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        old_doc = Document(
            page_content="old",
            metadata={"timestamp": "2026-02-14T10:00:00Z"},
        )
        new_doc = Document(
            page_content="new",
            metadata={"timestamp": "2026-02-15T10:00:00Z"},
        )

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=[
                (old_doc, 0.91),
                (new_doc, 0.88),
            ]
        )

        results = memory.search_with_scores(
            query="test",
            adaptive_threshold=False,
            score_threshold=0.0,
            created_after="2026-02-15T00:00:00Z",
        )

        assert [result["content"] for result in results] == ["new"]

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_timestamp_boundaries_support_datetime_inputs(self):
        """created_before/created_after should accept datetime objects."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        naive_timestamp_doc = Document(
            page_content="naive",
            metadata={"timestamp": "2026-02-15T09:30:00"},
        )
        utc_timestamp_doc = Document(
            page_content="utc",
            metadata={"timestamp": "2026-02-15T11:00:00+00:00"},
        )

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=[
                (naive_timestamp_doc, 0.85),
                (utc_timestamp_doc, 0.84),
            ]
        )

        results = memory.search_with_scores(
            query="test",
            adaptive_threshold=False,
            score_threshold=0.0,
            created_after=datetime(2026, 2, 15, 9, 0, tzinfo=timezone.utc),
            created_before=datetime(2026, 2, 15, 10, 0),
        )

        assert [result["content"] for result in results] == ["naive"]


class TestOffsetPagination:
    """Test optional offset pagination for scored search results."""

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_offset_validation(self):
        """offset must be an integer >= 0 when provided."""
        memory = VectorStoreMemory(user_id="test_user")

        with pytest.raises(ValueError, match="offset must be an integer"):
            memory.search_with_scores(query="test", offset=1.5)

        with pytest.raises(ValueError, match="offset must be an integer"):
            memory.search_with_scores(query="test", offset=True)

        with pytest.raises(ValueError, match="offset cannot be negative"):
            memory.search_with_scores(query="test", offset=-1)

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_offset_skips_ranked_results_before_k_limit(self):
        """offset should paginate after ordering and before final k trimming."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        top_doc = Document(page_content="top", metadata={})
        second_doc = Document(page_content="second", metadata={})
        third_doc = Document(page_content="third", metadata={})

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=[
                (top_doc, 0.91),
                (second_doc, 0.84),
                (third_doc, 0.77),
            ]
        )

        results = memory.search_with_scores(
            query="test",
            k=2,
            offset=1,
            adaptive_threshold=False,
            score_threshold=0.0,
            sort_by_score=True,
        )

        assert [result["content"] for result in results] == ["second", "third"]

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_offset_increases_requested_candidate_count(self):
        """Vector-store candidate fetch size should account for offset + k."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        doc = Document(page_content="only", metadata={})

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=[(doc, 0.8)]
        )

        memory.search_with_scores(
            query="test",
            k=2,
            offset=3,
            adaptive_threshold=False,
            score_threshold=0.0,
        )

        memory.vector_store.similarity_search_with_relevance_scores.assert_called_once_with(
            "test",
            k=5,
            score_threshold=0.0,
            filter={"user_id": "test_user"},
        )


class TestUniqueContentDeduplication:
    """Test optional duplicate collapsing based on memory content."""

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_unique_content_validation(self):
        """unique_content must be a boolean."""
        memory = VectorStoreMemory(user_id="test_user")

        with pytest.raises(ValueError, match="unique_content must be a boolean"):
            memory.search_with_scores(query="test", unique_content="yes")

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_unique_content_collapses_whitespace_and_case_duplicates(self):
        """Duplicates should collapse when content differs only by case/spacing."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        top_doc = Document(page_content="Project launch checklist", metadata={"id": 1})
        duplicate_doc = Document(
            page_content="  project   LAUNCH   checklist  ", metadata={"id": 2}
        )
        unique_doc = Document(
            page_content="Budget approval pending", metadata={"id": 3}
        )

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=[
                (duplicate_doc, 0.88),
                (top_doc, 0.91),
                (unique_doc, 0.72),
            ]
        )

        results = memory.search_with_scores(
            query="test",
            adaptive_threshold=False,
            score_threshold=0.0,
            sort_by_score=True,
            unique_content=True,
        )

        assert [result["content"] for result in results] == [
            "Project launch checklist",
            "Budget approval pending",
        ]
        assert [result["score"] for result in results] == [0.91, 0.72]

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_unique_content_disabled_keeps_duplicates(self):
        """Duplicate content should remain when unique_content is False."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        first_doc = Document(page_content="Status update", metadata={"id": 1})
        duplicate_doc = Document(page_content="status update", metadata={"id": 2})

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=[
                (first_doc, 0.81),
                (duplicate_doc, 0.8),
            ]
        )

        results = memory.search_with_scores(
            query="test",
            adaptive_threshold=False,
            score_threshold=0.0,
            unique_content=False,
        )

        assert [result["content"] for result in results] == [
            "Status update",
            "status update",
        ]


class TestRequiredTermsFiltering:
    """Test optional lexical constraints layered on semantic search."""

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_required_terms_validation(self):
        """required_terms must be a non-empty list of non-empty strings."""
        memory = VectorStoreMemory(user_id="test_user")

        with pytest.raises(
            ValueError, match="required_terms must be a list of non-empty strings"
        ):
            memory.search_with_scores(query="test", required_terms="roadmap")

        with pytest.raises(ValueError, match="required_terms cannot be empty"):
            memory.search_with_scores(query="test", required_terms=[])

        with pytest.raises(
            ValueError, match="required_terms must contain only non-empty strings"
        ):
            memory.search_with_scores(query="test", required_terms=["roadmap", "  "])

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_required_terms_mode_validation(self):
        """required_terms_mode should accept only 'all' or 'any'."""
        memory = VectorStoreMemory(user_id="test_user")

        with pytest.raises(
            ValueError, match="required_terms_mode must be either 'all' or 'any'"
        ):
            memory.search_with_scores(
                query="test",
                required_terms=["roadmap"],
                required_terms_mode="strict",
            )

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_required_terms_all_mode_keeps_only_full_matches(self):
        """Mode=all should keep content containing every required term."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        full_match = Document(
            page_content="Project roadmap and release plan", metadata={}
        )
        partial_match = Document(page_content="Project roadmap draft", metadata={})

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=[
                (full_match, 0.9),
                (partial_match, 0.88),
            ]
        )

        results = memory.search_with_scores(
            query="test",
            adaptive_threshold=False,
            score_threshold=0.0,
            required_terms=["roadmap", "release plan"],
            required_terms_mode="all",
        )

        assert [result["content"] for result in results] == [
            "Project roadmap and release plan"
        ]

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_required_terms_any_mode_is_case_and_whitespace_insensitive(self):
        """Mode=any should support normalized lexical matching."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        roadmap_doc = Document(page_content="Roadmap retrospective", metadata={})
        launch_doc = Document(
            page_content="  product    LAUNCH checklist  ", metadata={}
        )
        unrelated_doc = Document(page_content="Budget review", metadata={})

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=[
                (roadmap_doc, 0.91),
                (launch_doc, 0.86),
                (unrelated_doc, 0.82),
            ]
        )

        results = memory.search_with_scores(
            query="test",
            adaptive_threshold=False,
            score_threshold=0.0,
            required_terms=["  ROADMAP  ", "launch checklist"],
            required_terms_mode="any",
            sort_by_score=True,
        )

        assert [result["content"] for result in results] == [
            "Roadmap retrospective",
            "  product    LAUNCH checklist  ",
        ]


class TestExcludedTermsFiltering:
    """Test optional negative lexical constraints for semantic search."""

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_excluded_terms_validation(self):
        """excluded_terms must be a non-empty list of non-empty strings."""
        memory = VectorStoreMemory(user_id="test_user")

        with pytest.raises(
            ValueError, match="excluded_terms must be a list of non-empty strings"
        ):
            memory.search_with_scores(query="test", excluded_terms="roadmap")

        with pytest.raises(ValueError, match="excluded_terms cannot be empty"):
            memory.search_with_scores(query="test", excluded_terms=[])

        with pytest.raises(
            ValueError, match="excluded_terms must contain only non-empty strings"
        ):
            memory.search_with_scores(query="test", excluded_terms=["roadmap", "  "])

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_excluded_terms_mode_validation(self):
        """excluded_terms_mode should accept only 'all' or 'any'."""
        memory = VectorStoreMemory(user_id="test_user")

        with pytest.raises(
            ValueError, match="excluded_terms_mode must be either 'all' or 'any'"
        ):
            memory.search_with_scores(
                query="test",
                excluded_terms=["roadmap"],
                excluded_terms_mode="strict",
            )

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_excluded_terms_any_mode_filters_case_and_whitespace_insensitively(self):
        """Mode=any should remove results containing at least one excluded term."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        roadmap_doc = Document(page_content="Roadmap retrospective", metadata={})
        launch_doc = Document(
            page_content="  product    LAUNCH checklist  ", metadata={}
        )
        clean_doc = Document(page_content="Budget review", metadata={})

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=[
                (roadmap_doc, 0.91),
                (launch_doc, 0.86),
                (clean_doc, 0.82),
            ]
        )

        results = memory.search_with_scores(
            query="test",
            adaptive_threshold=False,
            score_threshold=0.0,
            excluded_terms=["  ROADMAP  ", "launch checklist"],
            excluded_terms_mode="any",
            sort_by_score=True,
        )

        assert [result["content"] for result in results] == ["Budget review"]

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_excluded_terms_all_mode_excludes_only_when_all_terms_are_present(self):
        """Mode=all should keep docs that do not contain every excluded term."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        full_match_doc = Document(
            page_content="Project roadmap with launch plan", metadata={}
        )
        partial_match_doc = Document(page_content="Project roadmap draft", metadata={})
        clean_doc = Document(page_content="Budget review", metadata={})

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=[
                (full_match_doc, 0.92),
                (partial_match_doc, 0.88),
                (clean_doc, 0.8),
            ]
        )

        results = memory.search_with_scores(
            query="test",
            adaptive_threshold=False,
            score_threshold=0.0,
            excluded_terms=["roadmap", "launch plan"],
            excluded_terms_mode="all",
            sort_by_score=True,
        )

        assert [result["content"] for result in results] == [
            "Project roadmap draft",
            "Budget review",
        ]


class TestSessionIdFiltering:
    """Test optional session-id allow/deny filtering controls."""

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_session_ids_validation(self):
        """session_ids must be a non-empty list of non-empty strings."""
        memory = VectorStoreMemory(user_id="test_user")

        with pytest.raises(
            ValueError, match="session_ids must be a list of non-empty strings"
        ):
            memory.search_with_scores(query="test", session_ids="session-1")

        with pytest.raises(ValueError, match="session_ids cannot be empty"):
            memory.search_with_scores(query="test", session_ids=[])

        with pytest.raises(
            ValueError, match="session_ids must contain only non-empty strings"
        ):
            memory.search_with_scores(query="test", session_ids=["session-1", " "])

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_excluded_session_ids_validation(self):
        """excluded_session_ids must be a non-empty list of non-empty strings."""
        memory = VectorStoreMemory(user_id="test_user")

        with pytest.raises(
            ValueError,
            match="excluded_session_ids must be a list of non-empty strings",
        ):
            memory.search_with_scores(query="test", excluded_session_ids="session-1")

        with pytest.raises(
            ValueError, match="excluded_session_ids must contain only non-empty strings"
        ):
            memory.search_with_scores(
                query="test",
                excluded_session_ids=["session-1", ""],
            )

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_session_id_filters_cannot_overlap(self):
        """Overlapping allow/deny filters should fail fast with clear feedback."""
        memory = VectorStoreMemory(user_id="test_user")

        with pytest.raises(
            ValueError,
            match="session_ids and excluded_session_ids cannot overlap",
        ):
            memory.search_with_scores(
                query="test",
                session_ids=["session-1"],
                excluded_session_ids=["session-1"],
            )

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_session_ids_allowlist_keeps_only_matching_sessions(self):
        """session_ids should retain only results from explicitly allowed sessions."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        allowed_doc = Document(
            page_content="allowed",
            metadata={"session_id": "session-1"},
        )
        other_doc = Document(
            page_content="other",
            metadata={"session_id": "session-2"},
        )
        missing_session_doc = Document(page_content="missing-session", metadata={})

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=[
                (allowed_doc, 0.9),
                (other_doc, 0.87),
                (missing_session_doc, 0.85),
            ]
        )

        results = memory.search_with_scores(
            query="test",
            adaptive_threshold=False,
            score_threshold=0.0,
            session_ids=["  session-1  "],
        )

        assert [result["content"] for result in results] == ["allowed"]

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_excluded_session_ids_denylist_removes_only_target_sessions(self):
        """excluded_session_ids should remove matching sessions and keep others."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        denied_doc = Document(
            page_content="denied",
            metadata={"session_id": "session-2"},
        )
        kept_doc = Document(
            page_content="kept",
            metadata={"session_id": "session-1"},
        )
        global_doc = Document(page_content="global", metadata={})

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=[
                (denied_doc, 0.9),
                (kept_doc, 0.88),
                (global_doc, 0.84),
            ]
        )

        results = memory.search_with_scores(
            query="test",
            adaptive_threshold=False,
            score_threshold=0.0,
            excluded_session_ids=["session-2", "session-2"],
        )

        assert [result["content"] for result in results] == ["kept", "global"]


class TestSessionDiversification:
    """Test optional per-session result diversification controls."""

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_max_results_per_session_validation(self):
        """max_results_per_session must be a positive integer when provided."""
        memory = VectorStoreMemory(user_id="test_user")

        with pytest.raises(
            ValueError, match="max_results_per_session must be an integer"
        ):
            memory.search_with_scores(query="test", max_results_per_session=1.5)

        with pytest.raises(
            ValueError, match="max_results_per_session must be an integer"
        ):
            memory.search_with_scores(query="test", max_results_per_session=True)

        with pytest.raises(
            ValueError, match="max_results_per_session must be greater than 0"
        ):
            memory.search_with_scores(query="test", max_results_per_session=0)

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_max_results_per_session_limits_each_session_bucket(self):
        """Diversification should retain only the top N matches per session_id."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 10

        session_one_top = Document(page_content="s1-top", metadata={"session_id": "s1"})
        session_one_second = Document(
            page_content="s1-second", metadata={"session_id": "s1"}
        )
        session_two_top = Document(page_content="s2-top", metadata={"session_id": "s2"})
        no_session_doc = Document(page_content="global", metadata={})

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=[
                (session_one_top, 0.95),
                (session_one_second, 0.90),
                (session_two_top, 0.87),
                (no_session_doc, 0.81),
            ]
        )

        results = memory.search_with_scores(
            query="test",
            adaptive_threshold=False,
            score_threshold=0.0,
            sort_by_score=True,
            max_results_per_session=1,
        )

        assert [result["content"] for result in results] == [
            "s1-top",
            "s2-top",
            "global",
        ]


class TestScoreGapFiltering:
    """Test optional score-gap filtering relative to the strongest match."""

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_max_score_gap_validation(self):
        """max_score_gap values outside [0, 1] should fail fast."""
        memory = VectorStoreMemory(user_id="test_user")

        with pytest.raises(ValueError, match="max_score_gap must be in"):
            memory.search_with_scores(query="test", max_score_gap=-0.1)

        with pytest.raises(ValueError, match="max_score_gap must be in"):
            memory.search_with_scores(query="test", max_score_gap=1.1)

        with pytest.raises(ValueError, match="max_score_gap must be in"):
            memory.search_with_scores(query="test", max_score_gap=True)

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_max_score_gap_filters_results_far_from_top_score(self):
        """Only candidates within the score gap from the top match should remain."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        top_doc = Document(page_content="top", metadata={})
        nearby_doc = Document(page_content="nearby", metadata={})
        far_doc = Document(page_content="far", metadata={})

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=[
                (top_doc, 0.91),
                (nearby_doc, 0.84),
                (far_doc, 0.68),
            ]
        )

        results = memory.search_with_scores(
            query="test",
            adaptive_threshold=False,
            score_threshold=0.0,
            max_score_gap=0.1,
        )

        assert [result["content"] for result in results] == ["top", "nearby"]
        assert [result["score"] for result in results] == [0.91, 0.84]

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_max_score_gap_zero_keeps_only_top_ties(self):
        """A zero score gap should keep only highest-score ties."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        first_top = Document(page_content="top-1", metadata={})
        second_top = Document(page_content="top-2", metadata={})
        lower = Document(page_content="lower", metadata={})

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=[
                (first_top, 0.9),
                (second_top, 0.9),
                (lower, 0.85),
            ]
        )

        results = memory.search_with_scores(
            query="test",
            adaptive_threshold=False,
            score_threshold=0.0,
            max_score_gap=0.0,
        )

        assert [result["content"] for result in results] == ["top-1", "top-2"]


class TestRelativeScoreFiltering:
    """Test optional relative score filtering anchored to top candidate."""

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_min_relative_score_validation(self):
        """min_relative_score values outside [0, 1] should fail fast."""
        memory = VectorStoreMemory(user_id="test_user")

        with pytest.raises(ValueError, match="min_relative_score must be in"):
            memory.search_with_scores(query="test", min_relative_score=-0.1)

        with pytest.raises(ValueError, match="min_relative_score must be in"):
            memory.search_with_scores(query="test", min_relative_score=1.1)

        with pytest.raises(ValueError, match="min_relative_score must be in"):
            memory.search_with_scores(query="test", min_relative_score=True)

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_min_relative_score_filters_using_top_score_ratio(self):
        """Only candidates within the relative ratio from top score should remain."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        top_doc = Document(page_content="top", metadata={})
        close_doc = Document(page_content="close", metadata={})
        far_doc = Document(page_content="far", metadata={})

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=[
                (top_doc, 0.91),
                (close_doc, 0.83),
                (far_doc, 0.62),
            ]
        )

        results = memory.search_with_scores(
            query="test",
            adaptive_threshold=False,
            score_threshold=0.0,
            min_relative_score=0.9,
        )

        assert [result["content"] for result in results] == ["top", "close"]
        assert [result["score"] for result in results] == [0.91, 0.83]

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_min_relative_score_zero_keeps_all_thresholded_results(self):
        """A zero relative score floor should not remove any thresholded results."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        first_doc = Document(page_content="first", metadata={})
        second_doc = Document(page_content="second", metadata={})

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=[
                (first_doc, 0.78),
                (second_doc, 0.51),
            ]
        )

        results = memory.search_with_scores(
            query="test",
            adaptive_threshold=False,
            score_threshold=0.0,
            min_relative_score=0.0,
        )

        assert [result["content"] for result in results] == ["first", "second"]


class TestTopScoreFiltering:
    """Test optional top-score quality guard for scored searches."""

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_min_top_score_validation(self):
        """min_top_score values outside [0, 1] should fail fast."""
        memory = VectorStoreMemory(user_id="test_user")

        with pytest.raises(ValueError, match="min_top_score must be in"):
            memory.search_with_scores(query="test", min_top_score=-0.1)

        with pytest.raises(ValueError, match="min_top_score must be in"):
            memory.search_with_scores(query="test", min_top_score=1.1)

        with pytest.raises(ValueError, match="min_top_score must be in"):
            memory.search_with_scores(query="test", min_top_score=True)

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_min_top_score_rejects_results_when_best_match_is_too_low(self):
        """All candidates should be rejected when top score is below the guard."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        near_doc = Document(page_content="near", metadata={})
        low_doc = Document(page_content="low", metadata={})

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=[
                (near_doc, 0.79),
                (low_doc, 0.71),
            ]
        )

        results = memory.search_with_scores(
            query="test",
            adaptive_threshold=False,
            score_threshold=0.0,
            min_top_score=0.8,
        )

        assert results == []

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_min_top_score_allows_results_when_top_score_meets_boundary(self):
        """The quality guard should be inclusive at the exact threshold boundary."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        top_doc = Document(page_content="top", metadata={})
        second_doc = Document(page_content="second", metadata={})

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=[
                (top_doc, 0.8),
                (second_doc, 0.72),
            ]
        )

        results = memory.search_with_scores(
            query="test",
            adaptive_threshold=False,
            score_threshold=0.0,
            min_top_score=0.8,
        )

        assert [result["content"] for result in results] == ["top", "second"]


class TestScoreMarginFiltering:
    """Test optional score-margin filtering above the active threshold."""

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_min_score_margin_validation(self):
        """min_score_margin values outside [0, 1] should fail fast."""
        memory = VectorStoreMemory(user_id="test_user")

        with pytest.raises(ValueError, match="min_score_margin must be in"):
            memory.search_with_scores(query="test", min_score_margin=-0.1)

        with pytest.raises(ValueError, match="min_score_margin must be in"):
            memory.search_with_scores(query="test", min_score_margin=1.1)

        with pytest.raises(ValueError, match="min_score_margin must be in"):
            memory.search_with_scores(query="test", min_score_margin=True)

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_min_score_margin_uses_explicit_threshold_baseline(self):
        """Explicit score_threshold should be used as margin baseline."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        top_doc = Document(page_content="top", metadata={})
        near_doc = Document(page_content="near", metadata={})
        below_margin_doc = Document(page_content="below-margin", metadata={})

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=[
                (top_doc, 0.89),
                (near_doc, 0.72),
                (below_margin_doc, 0.69),
            ]
        )

        results = memory.search_with_scores(
            query="test",
            adaptive_threshold=False,
            score_threshold=0.6,
            min_score_margin=0.1,
        )

        assert [result["content"] for result in results] == ["top", "near"]

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_min_score_margin_defaults_to_zero_baseline_without_threshold(self):
        """Without adaptive/explicit thresholds, baseline should default to 0.0."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        high_doc = Document(page_content="high", metadata={})
        low_doc = Document(page_content="low", metadata={})

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=[
                (high_doc, 0.82),
                (low_doc, 0.74),
            ]
        )

        results = memory.search_with_scores(
            query="test",
            adaptive_threshold=False,
            min_score_margin=0.8,
        )

        assert [result["content"] for result in results] == ["high"]


class TestScoreContextExplainability:
    """Test optional score-context metadata for explainable ranking."""

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_include_score_context_validation(self):
        """include_score_context must be a boolean."""
        memory = VectorStoreMemory(user_id="test_user")

        with pytest.raises(ValueError, match="include_score_context must be a boolean"):
            memory.search_with_scores(query="test", include_score_context="yes")

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_include_score_context_attaches_rank_and_margins(self):
        """When enabled, each result should include deterministic score context."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        top_doc = Document(page_content="top", metadata={})
        runner_up_doc = Document(page_content="runner-up", metadata={})

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=[
                (top_doc, 0.91),
                (runner_up_doc, 0.84),
            ]
        )

        results = memory.search_with_scores(
            query="test",
            adaptive_threshold=False,
            score_threshold=0.5,
            sort_by_score=True,
            include_score_context=True,
        )

        first_context = results[0]["score_context"]
        second_context = results[1]["score_context"]

        assert first_context["rank"] == 1
        assert first_context["top_score"] == 0.91
        assert first_context["gap_from_top"] == 0.0
        assert first_context["margin_above_threshold"] == pytest.approx(0.41)
        assert first_context["applied_threshold"] == 0.5

        assert second_context["rank"] == 2
        assert second_context["top_score"] == 0.91
        assert second_context["gap_from_top"] == pytest.approx(0.07)
        assert second_context["margin_above_threshold"] == pytest.approx(0.34)
        assert second_context["applied_threshold"] == 0.5

    @patch.object(VectorStoreMemory, "__init__", lambda x, **kwargs: None)
    def test_score_context_not_included_by_default(self):
        """Existing callers should not receive score_context unless requested."""
        memory = VectorStoreMemory(user_id="test_user")
        memory.user_id = "test_user"
        memory.top_k = 5

        doc = Document(page_content="test", metadata={})

        memory.vector_store = Mock()
        memory.vector_store.similarity_search_with_relevance_scores = Mock(
            return_value=[(doc, 0.8)]
        )

        results = memory.search_with_scores(
            query="test",
            adaptive_threshold=False,
            score_threshold=0.0,
        )

        assert "score_context" not in results[0]
