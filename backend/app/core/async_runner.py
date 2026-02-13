"""Utilities for running async code safely from synchronous contexts."""

from __future__ import annotations

import asyncio
import inspect
import queue
import threading
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar, cast, overload

P = ParamSpec("P")
T = TypeVar("T")


@overload
def run_async(
    coro_factory: Callable[P, Awaitable[T]],
    *args: P.args,
    timeout: float | None = None,
    **kwargs: P.kwargs,
) -> T: ...


@overload
def run_async(
    awaitable: Awaitable[T],
    *,
    timeout: float | None = None,
) -> T: ...


def run_async(
    coro_or_factory: Callable[..., Awaitable[T]] | Awaitable[T],
    *args: Any,
    timeout: float | None = None,
    **kwargs: Any,
) -> T:
    """Run async work from synchronous code.

    Accepts either:
    1) a coroutine factory (async callable) + optional args/kwargs, or
    2) a pre-built awaitable object.

    It safely executes from both loop-free and loop-running contexts.
    """
    if timeout is not None and timeout <= 0:
        raise ValueError("timeout must be greater than 0")

    def _build_awaitable() -> Awaitable[T]:
        if inspect.isawaitable(coro_or_factory):
            if args or kwargs:
                raise TypeError(
                    "args/kwargs cannot be provided when passing an awaitable"
                )
            return cast(Awaitable[T], coro_or_factory)

        if not callable(coro_or_factory):
            raise TypeError(
                "run_async expects an awaitable or a callable returning an awaitable"
            )

        coro = coro_or_factory(*args, **kwargs)
        if not inspect.isawaitable(coro):
            raise TypeError("coro_factory must return an awaitable")

        return cast(Awaitable[T], coro)

    async def _run_with_timeout() -> T:
        awaitable = _build_awaitable()
        if timeout is None:
            return await awaitable
        return await asyncio.wait_for(awaitable, timeout=timeout)

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
