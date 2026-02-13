"""Utilities for running async code safely from synchronous contexts."""

from __future__ import annotations

import asyncio
import queue
import threading
from typing import Awaitable, Callable, TypeVar, cast

T = TypeVar("T")


def run_async(coro_factory: Callable[[], Awaitable[T]], timeout: float | None = None) -> T:
    """Run an async coroutine factory from synchronous code.

    This helper supports two scenarios:

    1. No running event loop in the current thread:
       execute with ``asyncio.run``.
    2. A running event loop already exists:
       execute in a dedicated worker thread with its own loop.

    Args:
        coro_factory: Zero-argument callable that returns an awaitable.
        timeout: Optional timeout in seconds. If provided and the coroutine
            does not complete within the deadline, ``TimeoutError`` is raised.

    Returns:
        The coroutine result.

    Raises:
        Exception: Re-raises any exception raised inside the coroutine.
    """
    if timeout is not None and timeout <= 0:
        raise ValueError("timeout must be greater than 0")

    async def _run_with_timeout() -> T:
        coro = coro_factory()
        if timeout is None:
            return await coro
        return await asyncio.wait_for(coro, timeout=timeout)

    def _timeout_error() -> TimeoutError:
        return TimeoutError(f"run_async timed out after {timeout} seconds")

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        try:
            return asyncio.run(_run_with_timeout())
        except asyncio.TimeoutError as exc:
            raise _timeout_error() from exc

    result_queue: queue.Queue[tuple[bool, T | BaseException]] = queue.Queue(maxsize=1)

    def _worker() -> None:
        try:
            result = asyncio.run(_run_with_timeout())
            result_queue.put((True, result))
        except BaseException as exc:  # pragma: no cover - exercised via caller
            result_queue.put((False, exc))

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join()

    success, payload = result_queue.get_nowait()
    if success:
        return cast(T, payload)

    if isinstance(payload, asyncio.TimeoutError):
        raise _timeout_error() from payload

    if isinstance(payload, BaseException):
        raise payload

    raise RuntimeError("run_async received an invalid error payload")
