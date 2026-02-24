"""Multi-Model Fallback Chain for resilient LLM operations.

Provides automatic fallback to alternative LLM providers when the primary
model fails due to rate limits, timeouts, or service outages.
"""
from dataclasses import dataclass
from typing import List, Optional
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
import os


@dataclass
class ModelSpec:
    """Specification for an LLM model with fallback support."""
    
    provider: str  # "openai", "anthropic", "gemini"
    model: str
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    api_key_env: str = None
    
    def __post_init__(self):
        """Set default API key environment variable if not specified."""
        if self.api_key_env is None:
            if self.provider == "openai":
                self.api_key_env = "OPENAI_API_KEY"
            elif self.provider == "anthropic":
                self.api_key_env = "ANTHROPIC_API_KEY"


@dataclass
class FallbackMetrics:
    """Tracks fallback usage for monitoring and debugging."""
    
    primary_failures: int = 0
    fallback_successes: int = 0
    total_failures: int = 0
    last_fallback_reason: Optional[str] = None


# Default fallback chain: GPT-4 → Claude → (future: Gemini)
DEFAULT_FALLBACK_CHAIN = [
    ModelSpec(
        provider="openai",
        model="gpt-4-turbo-preview",
        temperature=0.7,
        api_key_env="OPENAI_API_KEY"
    ),
    ModelSpec(
        provider="anthropic",
        model="claude-3-5-sonnet-20241022",
        temperature=0.7,
        api_key_env="ANTHROPIC_API_KEY"
    ),
]


def build_llm_with_fallbacks(
    primary_provider: str = "openai",
    primary_model: str = "gpt-4-turbo-preview",
    temperature: float = 0.7,
    max_tokens: Optional[int] = 4000,
    callbacks: Optional[list] = None,
    fallback_metrics: Optional[FallbackMetrics] = None
):
    """Build a LangChain LLM with automatic fallback support.
    
    Creates a primary LLM and automatically adds fallback models when their
    API keys are available. Fallback order: GPT-4 → Claude 3.5 Sonnet
    
    Args:
        primary_provider: Preferred provider ("openai" or "anthropic")
        primary_model: Preferred model name
        temperature: Temperature parameter (0-1)
        max_tokens: Maximum output tokens
        callbacks: LangChain callbacks (e.g., LangFuse handler)
        fallback_metrics: Optional metrics tracker for monitoring
        
    Returns:
        LangChain LLM with fallback chain configured, or single LLM if
        only one provider has an API key configured.
        
    Raises:
        ValueError: If no API keys are configured for any models.
        
    Example:
        ```python
        llm = build_llm_with_fallbacks(
            primary_provider="openai",
            primary_model="gpt-4",
            callbacks=[langfuse_handler]
        )
        response = llm.invoke("Summarize this document")
        # If OpenAI fails (rate limit/timeout), automatically tries Claude
        ```
    """
    if fallback_metrics is None:
        fallback_metrics = FallbackMetrics()
    
    # Build list of LLMs with available API keys
    llms = []
    
    # Primary model
    primary_api_key = os.getenv(
        "OPENAI_API_KEY" if primary_provider == "openai" else "ANTHROPIC_API_KEY"
    )
    
    if primary_api_key:
        if primary_provider == "openai":
            llm = ChatOpenAI(
                model=primary_model,
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=primary_api_key,
                callbacks=callbacks
            )
        elif primary_provider == "anthropic":
            llm = ChatAnthropic(
                model=primary_model,
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=primary_api_key,
                callbacks=callbacks
            )
        else:
            raise ValueError(f"Unsupported provider: {primary_provider}")
        
        llms.append(llm)
    
    # Add fallback models based on available API keys
    if primary_provider != "anthropic":
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if anthropic_key:
            fallback_llm = ChatAnthropic(
                model="claude-3-5-sonnet-20241022",
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=anthropic_key,
                callbacks=callbacks
            )
            llms.append(fallback_llm)
    
    if primary_provider != "openai":
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            fallback_llm = ChatOpenAI(
                model="gpt-4-turbo-preview",
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=openai_key,
                callbacks=callbacks
            )
            llms.append(fallback_llm)
    
    if not llms:
        raise ValueError(
            "No LLM providers configured. Please set at least one API key:\n"
            "OPENAI_API_KEY, ANTHROPIC_API_KEY"
        )
    
    # Use single LLM if only one available
    if len(llms) == 1:
        return llms[0]
    
    # Build fallback chain: primary.with_fallbacks([secondary, ...])
    primary = llms[0]
    fallbacks = llms[1:]
    
    return primary.with_fallbacks(fallbacks)


def get_fallback_status(fallback_metrics: FallbackMetrics) -> dict:
    """Get current fallback usage statistics.
    
    Args:
        fallback_metrics: Metrics tracker instance.
        
    Returns:
        Dictionary with fallback statistics.
    """
    total_requests = (
        fallback_metrics.primary_failures +
        fallback_metrics.fallback_successes +
        fallback_metrics.total_failures
    )
    
    if total_requests == 0:
        reliability = 100.0
    else:
        reliability = (
            (total_requests - fallback_metrics.total_failures) /
            total_requests * 100
        )
    
    return {
        "total_requests": total_requests,
        "primary_failures": fallback_metrics.primary_failures,
        "fallback_successes": fallback_metrics.fallback_successes,
        "total_failures": fallback_metrics.total_failures,
        "reliability_percent": round(reliability, 2),
        "last_fallback_reason": fallback_metrics.last_fallback_reason
    }
