"""Utilities for running async code safely from synchronous contexts."""

from __future__ import annotations

import asyncio
import queue
import threading
from typing import Awaitable, Callable, TypeVar, cast

T = TypeVar("T")


def run_async(coro_factory: Callable[[], Awaitable[T]]) -> T:
    """Run an async coroutine factory from synchronous code.

    This helper supports two scenarios:

    1. No running event loop in the current thread:
       execute with ``asyncio.run``.
    2. A running event loop already exists:
       execute in a dedicated worker thread with its own loop.

    Args:
        coro_factory: Zero-argument callable that returns an awaitable.

    Returns:
        The coroutine result.

    Raises:
        Exception: Re-raises any exception raised inside the coroutine.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro_factory())

    result_queue: queue.Queue[tuple[bool, T | BaseException]] = queue.Queue(maxsize=1)

    def _worker() -> None:
        try:
            result = asyncio.run(coro_factory())
            result_queue.put((True, result))
        except BaseException as exc:  # pragma: no cover - exercised via caller
            result_queue.put((False, exc))

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join()

    success, payload = result_queue.get_nowait()
    if success:
        return cast(T, payload)

    if isinstance(payload, BaseException):
        raise payload

    raise RuntimeError("run_async received an invalid error payload")
