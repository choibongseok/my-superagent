"""Multi-Model Fallback Chain (#232).

Builds an LLM with automatic fallback: primary → secondary → tertiary.
Uses LangChain's ``with_fallbacks()`` so failures transparently retry
on the next provider.

Usage::

    from app.core.llm_fallback import build_llm_with_fallbacks

    llm = build_llm_with_fallbacks(callbacks=[handler])
    # llm is a RunnableWithFallbacks when multiple keys are present,
    # or a plain ChatModel when only one key exists.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence

from langchain_core.language_models import BaseChatModel

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelSpec:
    """Lightweight descriptor for an LLM provider + model."""

    provider: str  # "openai" | "anthropic"
    model: str
    api_key_setting: str  # Settings attribute name that holds the key


# Ordered fallback chain — first available key wins as primary.
_DEFAULT_CHAIN: Sequence[ModelSpec] = (
    ModelSpec("openai", settings.OPENAI_MODEL, "OPENAI_API_KEY"),
    ModelSpec("anthropic", settings.ANTHROPIC_MODEL, "ANTHROPIC_API_KEY"),
)


def _has_key(spec: ModelSpec) -> bool:
    """Return True when the API key for *spec* is configured (non-empty)."""
    return bool(getattr(settings, spec.api_key_setting, ""))


def _make_chat_model(
    spec: ModelSpec,
    *,
    temperature: float = 0.7,
    max_tokens: int = 4000,
    callbacks: Optional[List[Any]] = None,
) -> BaseChatModel:
    """Instantiate a single ChatModel for the given spec."""

    if spec.provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=spec.model,
            temperature=temperature,
            max_tokens=max_tokens,
            callbacks=callbacks,
        )

    if spec.provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=spec.model,
            temperature=temperature,
            max_tokens=max_tokens,
            callbacks=callbacks,
        )

    raise ValueError(f"Unsupported provider: {spec.provider}")


def build_llm_with_fallbacks(
    *,
    primary_provider: Optional[str] = None,
    primary_model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 4000,
    callbacks: Optional[List[Any]] = None,
    chain: Optional[Sequence[ModelSpec]] = None,
) -> BaseChatModel:
    """Build an LLM with automatic fallback across configured providers.

    Parameters
    ----------
    primary_provider:
        Preferred provider (``"openai"`` or ``"anthropic"``).  If set the
        chain is re-ordered so this provider comes first.
    primary_model:
        Override the model name for the primary provider.
    temperature / max_tokens:
        Passed through to every model in the chain.
    callbacks:
        LangChain callbacks (e.g. LangFuse handler).
    chain:
        Custom fallback chain; defaults to ``_DEFAULT_CHAIN``.

    Returns
    -------
    BaseChatModel
        A single ``ChatModel`` when only one key is available, or a
        ``RunnableWithFallbacks`` wrapping primary + fallbacks when
        multiple keys exist.

    Raises
    ------
    RuntimeError
        If no API keys are configured at all.
    """

    specs = list(chain or _DEFAULT_CHAIN)

    # Re-order if caller requests a specific primary provider.
    if primary_provider:
        preferred = [s for s in specs if s.provider == primary_provider]
        rest = [s for s in specs if s.provider != primary_provider]
        if preferred and primary_model:
            preferred = [ModelSpec(preferred[0].provider, primary_model, preferred[0].api_key_setting)]
        specs = preferred + rest

    # Filter to specs with valid keys.
    available = [s for s in specs if _has_key(s)]

    if not available:
        # In demo mode, return mock LLM instead of crashing
        if settings.DEMO_MODE:
            from app.core.mock_llm import DemoLLM

            logger.info("DEMO_MODE active — using mock LLM (no API keys required)")
            return DemoLLM(callbacks=callbacks or [])

        raise RuntimeError(
            "No LLM API keys configured. Set at least one of: "
            + ", ".join(s.api_key_setting for s in specs)
        )

    build_kwargs = dict(temperature=temperature, max_tokens=max_tokens, callbacks=callbacks)

    primary = _make_chat_model(available[0], **build_kwargs)
    fallbacks = [_make_chat_model(s, **build_kwargs) for s in available[1:]]

    if fallbacks:
        provider_names = [available[0].provider] + [s.provider for s in available[1:]]
        logger.info(
            "LLM fallback chain configured: %s",
            " → ".join(provider_names),
        )
        return primary.with_fallbacks(fallbacks)

    logger.info("Single LLM configured: %s (no fallbacks available)", available[0].provider)
    return primary


def get_fallback_status() -> dict:
    """Return a dict describing which providers are available.

    Useful for health-check / admin endpoints.
    """
    status: dict[str, Any] = {
        spec.provider: {
            "model": spec.model,
            "configured": _has_key(spec),
        }
        for spec in _DEFAULT_CHAIN
    }
    status["demo_mode"] = settings.DEMO_MODE
    return status
