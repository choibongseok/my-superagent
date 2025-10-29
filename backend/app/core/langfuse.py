"""LangFuse integration for LLM observability."""

import os
from functools import wraps
from typing import Any, Callable

from langfuse import Langfuse
from langfuse.callback import CallbackHandler

# Initialize LangFuse client
langfuse_client = Langfuse(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
    host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
)


def get_langfuse_handler(
    user_id: str | None = None,
    session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> CallbackHandler:
    """
    Create LangFuse callback handler for tracing.

    Args:
        user_id: User identifier
        session_id: Session identifier
        metadata: Additional metadata

    Returns:
        CallbackHandler instance
    """
    return CallbackHandler(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
        host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        user_id=user_id,
        session_id=session_id,
        metadata=metadata,
    )


def trace_llm(
    name: str | None = None,
    metadata: dict[str, Any] | None = None,
):
    """
    Decorator for tracing LLM calls with LangFuse.

    Usage:
        @trace_llm(name="research_agent", metadata={"version": "1.0"})
        def my_agent_function():
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            trace_name = name or func.__name__
            trace = langfuse_client.trace(
                name=trace_name,
                metadata=metadata,
            )

            try:
                result = await func(*args, **kwargs, trace_id=trace.id)
                trace.update(output=result)
                return result
            except Exception as e:
                trace.update(
                    output=None,
                    status_message=str(e),
                    level="ERROR",
                )
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            trace_name = name or func.__name__
            trace = langfuse_client.trace(
                name=trace_name,
                metadata=metadata,
            )

            try:
                result = func(*args, **kwargs, trace_id=trace.id)
                trace.update(output=result)
                return result
            except Exception as e:
                trace.update(
                    output=None,
                    status_message=str(e),
                    level="ERROR",
                )
                raise

        # Detect if function is async
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


__all__ = [
    "langfuse_client",
    "get_langfuse_handler",
    "trace_llm",
]
