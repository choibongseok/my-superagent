"""
Tests for VectorStoreMemory scoring and adaptive threshold logic.

This module tests the complex scoring algorithms in vector_store.py,
including input validation, edge cases, and adaptive threshold calculations.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
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
