"""Tests for DEMO_MODE / Mock LLM provider — Idea #245.

Verifies that:
1. DemoLLM returns realistic responses without API keys
2. build_llm_with_fallbacks returns DemoLLM when DEMO_MODE=true and no keys
3. Intent detection picks correct response templates
4. Deterministic output for same input
5. Health endpoint reports demo_mode status
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from langchain_core.messages import HumanMessage

from app.core.mock_llm import DemoLLM, _detect_intent


# ---------------------------------------------------------------------------
# DemoLLM unit tests
# ---------------------------------------------------------------------------

class TestDemoLLM:
    """Test the mock LLM directly."""

    def test_basic_invocation(self):
        llm = DemoLLM(demo_delay_ms=0)
        result = llm.invoke([HumanMessage(content="Hello world")])
        assert result.content
        assert len(result.content) > 50
        assert "demo response" in result.content.lower()

    def test_research_intent(self):
        llm = DemoLLM(demo_delay_ms=0)
        result = llm.invoke([HumanMessage(content="Research AI trends in 2026")])
        assert "Research Summary" in result.content or "analysis" in result.content.lower()

    def test_docs_intent(self):
        llm = DemoLLM(demo_delay_ms=0)
        result = llm.invoke([HumanMessage(content="Write a quarterly report")])
        assert "Report" in result.content or "document" in result.content.lower()

    def test_sheets_intent(self):
        llm = DemoLLM(demo_delay_ms=0)
        result = llm.invoke([HumanMessage(content="Analyze this spreadsheet data")])
        assert "Spreadsheet" in result.content or "data" in result.content.lower()

    def test_slides_intent(self):
        llm = DemoLLM(demo_delay_ms=0)
        result = llm.invoke([HumanMessage(content="Create a presentation deck")])
        assert "Presentation" in result.content or "Slide" in result.content

    def test_deterministic_same_input(self):
        llm = DemoLLM(demo_delay_ms=0)
        r1 = llm.invoke([HumanMessage(content="Test prompt")])
        r2 = llm.invoke([HumanMessage(content="Test prompt")])
        assert r1.content == r2.content

    def test_different_input_same_intent(self):
        llm = DemoLLM(demo_delay_ms=0)
        # Both map to default — determinism depends on hash
        r1 = llm.invoke([HumanMessage(content="Hello")])
        r2 = llm.invoke([HumanMessage(content="Goodbye")])
        # Both should produce valid responses (may or may not differ)
        assert r1.content
        assert r2.content

    def test_llm_type(self):
        llm = DemoLLM()
        assert llm._llm_type == "demo-mock"

    def test_identifying_params(self):
        llm = DemoLLM(demo_delay_ms=100)
        params = llm._identifying_params
        assert params["model_name"] == "demo-mock-v1"
        assert params["demo_delay_ms"] == 100

    def test_empty_messages(self):
        llm = DemoLLM(demo_delay_ms=0)
        result = llm.invoke([])
        assert result.content  # should still return a default response

    def test_system_only_messages(self):
        from langchain_core.messages import SystemMessage
        llm = DemoLLM(demo_delay_ms=0)
        result = llm.invoke([SystemMessage(content="You are a helper")])
        # No human message → uses empty string → default intent
        assert result.content


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------

class TestIntentDetection:
    """Test the _detect_intent helper."""

    def test_research_keywords(self):
        assert _detect_intent("research market trends") == "research"
        assert _detect_intent("analyze competitor data") == "research"
        assert _detect_intent("investigate customer behavior") == "research"

    def test_docs_keywords(self):
        assert _detect_intent("write a report for Q4") == "docs"
        assert _detect_intent("create a document summary") == "docs"
        assert _detect_intent("draft a memo about budgets") == "docs"

    def test_sheets_keywords(self):
        assert _detect_intent("create a spreadsheet with sales data") == "sheets"
        assert _detect_intent("calculate monthly totals from csv") == "sheets"

    def test_slides_keywords(self):
        assert _detect_intent("build a presentation about AI") == "slides"
        assert _detect_intent("make slides for the keynote") == "slides"

    def test_default_fallback(self):
        assert _detect_intent("hello how are you") == "default"
        assert _detect_intent("") == "default"

    def test_mixed_keywords_highest_wins(self):
        # "research" + "analyze" = 2 research keywords
        result = _detect_intent("research and analyze data trends study")
        assert result == "research"


# ---------------------------------------------------------------------------
# build_llm_with_fallbacks integration
# ---------------------------------------------------------------------------

class TestFallbackDemoMode:
    """Test that build_llm_with_fallbacks returns DemoLLM in demo mode."""

    def test_demo_mode_no_keys(self):
        with patch("app.core.llm_fallback.settings") as mock_settings:
            mock_settings.DEMO_MODE = True
            mock_settings.OPENAI_API_KEY = ""
            mock_settings.ANTHROPIC_API_KEY = ""
            mock_settings.OPENAI_MODEL = "gpt-4"
            mock_settings.ANTHROPIC_MODEL = "claude-3"

            from app.core.llm_fallback import build_llm_with_fallbacks

            llm = build_llm_with_fallbacks()
            assert isinstance(llm, DemoLLM)

    def test_no_demo_mode_no_keys_raises(self):
        with patch("app.core.llm_fallback.settings") as mock_settings:
            mock_settings.DEMO_MODE = False
            mock_settings.OPENAI_API_KEY = ""
            mock_settings.ANTHROPIC_API_KEY = ""
            mock_settings.OPENAI_MODEL = "gpt-4"
            mock_settings.ANTHROPIC_MODEL = "claude-3"

            from app.core.llm_fallback import build_llm_with_fallbacks

            with pytest.raises(RuntimeError, match="No LLM API keys configured"):
                build_llm_with_fallbacks()

    def test_demo_mode_with_keys_uses_real(self):
        """When API keys exist, use real provider even in demo mode."""
        with patch("app.core.llm_fallback.settings") as mock_settings:
            mock_settings.DEMO_MODE = True
            mock_settings.OPENAI_API_KEY = "sk-test123"
            mock_settings.ANTHROPIC_API_KEY = ""
            mock_settings.OPENAI_MODEL = "gpt-4"
            mock_settings.ANTHROPIC_MODEL = "claude-3"

            from app.core.llm_fallback import build_llm_with_fallbacks

            llm = build_llm_with_fallbacks()
            # Should be real OpenAI, not DemoLLM
            assert not isinstance(llm, DemoLLM)


# ---------------------------------------------------------------------------
# get_fallback_status includes demo_mode
# ---------------------------------------------------------------------------

class TestFallbackStatusDemoMode:
    """Test that get_fallback_status reports demo_mode."""

    def test_status_includes_demo_mode_flag(self):
        with patch("app.core.llm_fallback.settings") as mock_settings:
            mock_settings.DEMO_MODE = True
            mock_settings.OPENAI_API_KEY = ""
            mock_settings.ANTHROPIC_API_KEY = ""
            mock_settings.OPENAI_MODEL = "gpt-4"
            mock_settings.ANTHROPIC_MODEL = "claude-3"

            from app.core.llm_fallback import get_fallback_status

            status = get_fallback_status()
            assert status["demo_mode"] is True

    def test_status_demo_mode_false(self):
        with patch("app.core.llm_fallback.settings") as mock_settings:
            mock_settings.DEMO_MODE = False
            mock_settings.OPENAI_API_KEY = "sk-real"
            mock_settings.ANTHROPIC_API_KEY = ""
            mock_settings.OPENAI_MODEL = "gpt-4"
            mock_settings.ANTHROPIC_MODEL = "claude-3"

            from app.core.llm_fallback import get_fallback_status

            status = get_fallback_status()
            assert status["demo_mode"] is False


# ---------------------------------------------------------------------------
# Health API reports demo_mode
# ---------------------------------------------------------------------------

class TestHealthDemoEndpoint:
    """Test the /health/llm endpoint includes demo_mode."""

    def test_llm_health_shows_demo_mode(self):
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        response = client.get("/api/v1/health/llm")
        assert response.status_code == 200
        data = response.json()
        assert "demo_mode" in data
