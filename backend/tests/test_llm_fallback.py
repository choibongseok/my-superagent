"""Tests for #232 Multi-Model Fallback Chain.

Covers:
- Single-provider mode (only one API key set)
- Multi-provider fallback chain construction
- Provider ordering when primary_provider is specified
- Error when no keys configured
- Fallback status endpoint
- BaseAgent integration (uses fallback builder)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.llm_fallback import (
    ModelSpec,
    _has_key,
    _make_chat_model,
    build_llm_with_fallbacks,
    get_fallback_status,
)


# ── Helpers ───────────────────────────────────────────────────────────────


def _patch_settings(**overrides):
    """Return a mock Settings with the given API key overrides."""
    defaults = {"OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": ""}
    defaults.update(overrides)
    mock = MagicMock()
    for k, v in defaults.items():
        setattr(mock, k, v)
    # Forward model names used in default chain
    mock.OPENAI_MODEL = "gpt-4-turbo-preview"
    mock.ANTHROPIC_MODEL = "claude-3-opus-20240229"
    return mock


# ── _has_key ──────────────────────────────────────────────────────────────


class TestHasKey:
    def test_returns_true_when_key_present(self):
        spec = ModelSpec("openai", "gpt-4", "OPENAI_API_KEY")
        with patch("app.core.llm_fallback.settings", _patch_settings(OPENAI_API_KEY="sk-xxx")):
            assert _has_key(spec) is True

    def test_returns_false_when_key_empty(self):
        spec = ModelSpec("openai", "gpt-4", "OPENAI_API_KEY")
        with patch("app.core.llm_fallback.settings", _patch_settings(OPENAI_API_KEY="")):
            assert _has_key(spec) is False

    def test_returns_false_when_key_missing(self):
        spec = ModelSpec("openai", "gpt-4", "NONEXISTENT_KEY")
        mock = MagicMock(spec=[])  # no attributes
        with patch("app.core.llm_fallback.settings", mock):
            assert _has_key(spec) is False


# ── _make_chat_model ──────────────────────────────────────────────────────


class TestMakeChatModel:
    @patch("langchain_openai.ChatOpenAI")
    def test_creates_openai_model(self, mock_cls):
        mock_cls.return_value = MagicMock()
        spec = ModelSpec("openai", "gpt-4", "OPENAI_API_KEY")
        result = _make_chat_model(spec, temperature=0.5, max_tokens=100)
        mock_cls.assert_called_once_with(
            model="gpt-4", temperature=0.5, max_tokens=100, callbacks=None,
        )
        assert result is mock_cls.return_value

    @patch("langchain_anthropic.ChatAnthropic")
    def test_creates_anthropic_model(self, mock_cls):
        mock_cls.return_value = MagicMock()
        spec = ModelSpec("anthropic", "claude-3", "ANTHROPIC_API_KEY")
        result = _make_chat_model(spec, temperature=0.3, max_tokens=200)
        mock_cls.assert_called_once_with(
            model="claude-3", temperature=0.3, max_tokens=200, callbacks=None,
        )
        assert result is mock_cls.return_value

    def test_raises_for_unknown_provider(self):
        spec = ModelSpec("cohere", "command-r", "COHERE_API_KEY")
        with pytest.raises(ValueError, match="Unsupported provider"):
            _make_chat_model(spec)


# ── build_llm_with_fallbacks ─────────────────────────────────────────────


class TestBuildLlmWithFallbacks:
    def _chain(self):
        return [
            ModelSpec("openai", "gpt-4", "OPENAI_API_KEY"),
            ModelSpec("anthropic", "claude-3", "ANTHROPIC_API_KEY"),
        ]

    @patch("app.core.llm_fallback._make_chat_model")
    @patch("app.core.llm_fallback._has_key")
    def test_single_provider_returns_plain_model(self, mock_has, mock_make):
        mock_has.side_effect = lambda s: s.provider == "openai"
        primary = MagicMock()
        mock_make.return_value = primary

        result = build_llm_with_fallbacks(chain=self._chain())

        assert result is primary
        assert mock_make.call_count == 1

    @patch("app.core.llm_fallback._make_chat_model")
    @patch("app.core.llm_fallback._has_key")
    def test_multi_provider_returns_with_fallbacks(self, mock_has, mock_make):
        mock_has.return_value = True
        primary = MagicMock()
        fallback = MagicMock()
        chained = MagicMock()
        primary.with_fallbacks.return_value = chained
        mock_make.side_effect = [primary, fallback]

        result = build_llm_with_fallbacks(chain=self._chain())

        assert result is chained
        primary.with_fallbacks.assert_called_once_with([fallback])

    @patch("app.core.llm_fallback._has_key")
    def test_no_keys_raises_runtime_error(self, mock_has):
        mock_has.return_value = False
        with pytest.raises(RuntimeError, match="No LLM API keys configured"):
            build_llm_with_fallbacks(chain=self._chain())

    @patch("app.core.llm_fallback._make_chat_model")
    @patch("app.core.llm_fallback._has_key")
    def test_primary_provider_reorders_chain(self, mock_has, mock_make):
        mock_has.return_value = True
        models = [MagicMock(), MagicMock()]
        chained = MagicMock()
        models[0].with_fallbacks.return_value = chained
        mock_make.side_effect = models

        build_llm_with_fallbacks(
            primary_provider="anthropic",
            chain=self._chain(),
        )

        # First call should be anthropic (reordered)
        first_spec = mock_make.call_args_list[0][0][0]
        assert first_spec.provider == "anthropic"

    @patch("app.core.llm_fallback._make_chat_model")
    @patch("app.core.llm_fallback._has_key")
    def test_primary_model_override(self, mock_has, mock_make):
        mock_has.return_value = True
        m = MagicMock()
        m.with_fallbacks.return_value = MagicMock()
        mock_make.side_effect = [m, MagicMock()]

        build_llm_with_fallbacks(
            primary_provider="openai",
            primary_model="gpt-4o",
            chain=self._chain(),
        )

        first_spec = mock_make.call_args_list[0][0][0]
        assert first_spec.model == "gpt-4o"

    @patch("app.core.llm_fallback._make_chat_model")
    @patch("app.core.llm_fallback._has_key")
    def test_callbacks_forwarded(self, mock_has, mock_make):
        mock_has.side_effect = lambda s: s.provider == "openai"
        mock_make.return_value = MagicMock()
        cb = MagicMock()

        build_llm_with_fallbacks(callbacks=[cb], chain=self._chain())

        _, kwargs = mock_make.call_args
        assert kwargs["callbacks"] == [cb]


# ── get_fallback_status ───────────────────────────────────────────────────


class TestGetFallbackStatus:
    def test_returns_all_providers(self):
        with patch(
            "app.core.llm_fallback.settings",
            _patch_settings(OPENAI_API_KEY="sk-x", ANTHROPIC_API_KEY=""),
        ):
            status = get_fallback_status()
            assert "openai" in status
            assert "anthropic" in status
            assert status["openai"]["configured"] is True
            assert status["anthropic"]["configured"] is False


# ── Health endpoint ───────────────────────────────────────────────────────


class TestLlmHealthEndpoint:
    @pytest.fixture
    def client(self):
        from httpx import ASGITransport, AsyncClient
        from app.main import app

        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test")

    @pytest.mark.asyncio
    async def test_health_llm_endpoint(self, client):
        with patch(
            "app.api.v1.health.get_fallback_status",
            return_value={
                "openai": {"model": "gpt-4", "configured": True},
                "anthropic": {"model": "claude-3", "configured": True},
            },
        ):
            resp = await client.get("/api/v1/health/llm")
            assert resp.status_code == 200
            data = resp.json()
            assert data["fallback_enabled"] is True
            assert data["chain"] == ["openai", "anthropic"]

    @pytest.mark.asyncio
    async def test_health_llm_single_provider(self, client):
        with patch(
            "app.api.v1.health.get_fallback_status",
            return_value={
                "openai": {"model": "gpt-4", "configured": True},
                "anthropic": {"model": "claude-3", "configured": False},
            },
        ):
            resp = await client.get("/api/v1/health/llm")
            data = resp.json()
            assert data["fallback_enabled"] is False
            assert data["chain"] == ["openai"]


# ── BaseAgent integration ─────────────────────────────────────────────────


class TestBaseAgentFallbackIntegration:
    """Verify BaseAgent._create_llm calls the fallback builder."""

    @patch("app.agents.base.build_llm_with_fallbacks")
    def test_create_llm_delegates_to_fallback_builder(self, mock_build):
        mock_build.return_value = MagicMock()

        from app.agents.base import BaseAgent

        class StubAgent(BaseAgent):
            def _get_metadata(self):
                return {}
            def _create_tools(self):
                return []
            def _create_prompt(self):
                return None

        agent = StubAgent(user_id="u1", llm_provider="anthropic", model="claude-3")
        agent.langfuse_handler = None
        result = agent._create_llm("anthropic", "claude-3", 0.5, 2000)

        mock_build.assert_called_once_with(
            primary_provider="anthropic",
            primary_model="claude-3",
            temperature=0.5,
            max_tokens=2000,
            callbacks=None,
        )
        assert result is mock_build.return_value
