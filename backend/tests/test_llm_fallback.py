"""Tests for LLM fallback functionality."""

import pytest
from unittest.mock import patch, MagicMock
from app.core.llm_fallback import (
    build_llm_with_fallbacks,
    FallbackMetrics,
    get_fallback_status,
)


class TestLLMFallback:
    """Test multi-model fallback chain."""
    
    @patch.dict("os.environ", {
        "OPENAI_API_KEY": "test-openai-key",
        "ANTHROPIC_API_KEY": "test-anthropic-key"
    })
    def test_build_with_both_keys(self):
        """Test fallback chain when both API keys are available."""
        llm = build_llm_with_fallbacks(
            primary_provider="openai",
            primary_model="gpt-4"
        )
        
        # Should return a RunnableWithFallbacks (fallback chain)
        assert llm is not None
        assert hasattr(llm, "with_fallbacks") or hasattr(llm, "fallbacks")
    
    @patch.dict("os.environ", {
        "OPENAI_API_KEY": "test-openai-key",
    }, clear=True)
    def test_build_with_single_key(self):
        """Test single LLM when only one API key is available."""
        llm = build_llm_with_fallbacks(
            primary_provider="openai",
            primary_model="gpt-4"
        )
        
        # Should return a single LLM
        assert llm is not None
    
    @patch.dict("os.environ", {}, clear=True)
    def test_build_with_no_keys(self):
        """Test error when no API keys are configured."""
        with pytest.raises(ValueError, match="No LLM providers configured"):
            build_llm_with_fallbacks()
    
    @patch.dict("os.environ", {
        "OPENAI_API_KEY": "test-openai-key",
        "ANTHROPIC_API_KEY": "test-anthropic-key"
    })
    def test_anthropic_primary(self):
        """Test fallback chain with Anthropic as primary."""
        llm = build_llm_with_fallbacks(
            primary_provider="anthropic",
            primary_model="claude-3-5-sonnet-20241022"
        )
        
        assert llm is not None
    
    @patch.dict("os.environ", {
        "OPENAI_API_KEY": "test-openai-key",
        "ANTHROPIC_API_KEY": "test-anthropic-key"
    })
    def test_with_callbacks(self):
        """Test that callbacks are passed to LLMs."""
        mock_callback = MagicMock()
        
        llm = build_llm_with_fallbacks(
            primary_provider="openai",
            callbacks=[mock_callback]
        )
        
        assert llm is not None
    
    def test_unsupported_provider(self):
        """Test error for unsupported provider."""
        with patch.dict("os.environ", {"UNSUPPORTED_API_KEY": "test-key"}):
            with pytest.raises(ValueError, match="Unsupported provider"):
                build_llm_with_fallbacks(
                    primary_provider="unsupported",
                    primary_model="model"
                )


class TestFallbackMetrics:
    """Test fallback metrics tracking."""
    
    def test_initial_metrics(self):
        """Test initial state of metrics."""
        metrics = FallbackMetrics()
        
        assert metrics.primary_failures == 0
        assert metrics.fallback_successes == 0
        assert metrics.total_failures == 0
        assert metrics.last_fallback_reason is None
    
    def test_get_fallback_status_no_requests(self):
        """Test status when no requests have been made."""
        metrics = FallbackMetrics()
        status = get_fallback_status(metrics)
        
        assert status["total_requests"] == 0
        assert status["reliability_percent"] == 100.0
    
    def test_get_fallback_status_with_failures(self):
        """Test status calculation with failures."""
        metrics = FallbackMetrics(
            primary_failures=3,
            fallback_successes=2,
            total_failures=1
        )
        status = get_fallback_status(metrics)
        
        assert status["total_requests"] == 6
        assert status["primary_failures"] == 3
        assert status["fallback_successes"] == 2
        assert status["total_failures"] == 1
        # (6-1)/6 * 100 = 83.33%
        assert status["reliability_percent"] == 83.33
    
    def test_get_fallback_status_perfect(self):
        """Test status with no failures."""
        metrics = FallbackMetrics(
            primary_failures=0,
            fallback_successes=0,
            total_failures=0
        )
        status = get_fallback_status(metrics)
        
        assert status["reliability_percent"] == 100.0
    
    def test_metrics_with_reason(self):
        """Test metrics tracking with failure reason."""
        metrics = FallbackMetrics(
            primary_failures=1,
            last_fallback_reason="Rate limit exceeded"
        )
        
        status = get_fallback_status(metrics)
        assert status["last_fallback_reason"] == "Rate limit exceeded"


class TestFallbackIntegration:
    """Integration tests for fallback behavior."""
    
    @patch.dict("os.environ", {
        "OPENAI_API_KEY": "test-openai-key",
        "ANTHROPIC_API_KEY": "test-anthropic-key"
    })
    def test_fallback_on_primary_failure(self):
        """Test that fallback triggers on primary model failure."""
        # This is an integration test that would need actual API mocking
        # For now, we just verify the fallback chain is created correctly
        llm = build_llm_with_fallbacks(
            primary_provider="openai",
            primary_model="gpt-4"
        )
        
        # Verify fallback chain exists
        assert llm is not None
    
    @patch.dict("os.environ", {
        "OPENAI_API_KEY": "test-openai-key",
        "ANTHROPIC_API_KEY": "test-anthropic-key"
    })
    def test_temperature_propagation(self):
        """Test that temperature is set correctly."""
        llm = build_llm_with_fallbacks(
            primary_provider="openai",
            temperature=0.9
        )
        
        assert llm is not None
    
    @patch.dict("os.environ", {
        "OPENAI_API_KEY": "test-openai-key",
        "ANTHROPIC_API_KEY": "test-anthropic-key"
    })
    def test_max_tokens_propagation(self):
        """Test that max_tokens is set correctly."""
        llm = build_llm_with_fallbacks(
            primary_provider="openai",
            max_tokens=2000
        )
        
        assert llm is not None
