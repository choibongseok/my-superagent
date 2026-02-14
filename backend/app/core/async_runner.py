"""Utilities for running async code safely from synchronous contexts."""

from __future__ import annotations

import asyncio
import inspect
import queue
import threading
from collections.abc import Awaitable, Callable, Hashable, Mapping
from typing import Any, ParamSpec, TypeVar, cast, overload

P = ParamSpec("P")
T = TypeVar("T")
R = TypeVar("R")
K = TypeVar("K", bound=Hashable)


@overload
def run_async(
    coro_factory: Callable[P, Awaitable[T]],
    *args: P.args,
    timeout: float | None = None,
    **kwargs: P.kwargs,
) -> T:
    ...


@overload
def run_async(
    awaitable: Awaitable[T],
    *,
    timeout: float | None = None,
) -> T:
    ...


def _validate_timeout(timeout: float | None) -> None:
    """Validate timeout values shared by async runner helpers."""
    if timeout is not None and timeout <= 0:
        raise ValueError("timeout must be greater than 0")


def _validate_max_concurrency(max_concurrency: int | None) -> None:
    """Validate optional max concurrency values."""
    if max_concurrency is None:
        return

    if max_concurrency <= 0:
        raise ValueError("max_concurrency must be greater than 0")


def _run_with_event_loop_bridge(
    runner: Callable[[], Awaitable[R]],
    *,
    timeout_error_factory: Callable[[], TimeoutError] | None = None,
) -> R:
    """Execute awaitable runner in both loop-free and loop-running contexts."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        try:
            return asyncio.run(runner())
        except asyncio.TimeoutError as exc:
            if timeout_error_factory is not None:
                raise timeout_error_factory() from exc
            raise

    result_queue: queue.Queue[tuple[bool, R | BaseException]] = queue.Queue(maxsize=1)

    def _worker() -> None:
        try:
            result = asyncio.run(runner())
            result_queue.put((True, result))
        except BaseException as exc:  # pragma: no cover - exercised via caller
            result_queue.put((False, exc))

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join()

    success, payload = result_queue.get_nowait()
    if success:
        return cast(R, payload)

    if isinstance(payload, asyncio.TimeoutError) and timeout_error_factory is not None:
        raise timeout_error_factory() from payload

    if isinstance(payload, BaseException):
        raise payload

    raise RuntimeError("run_async received an invalid error payload")


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
    _validate_timeout(timeout)

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

    return _run_with_event_loop_bridge(
        _run_with_timeout,
        timeout_error_factory=_timeout_error,
    )


async def _gather_with_optional_limit(
    awaitables: list[Awaitable[T]],
    *,
    max_concurrency: int | None,
    return_exceptions: bool,
) -> list[T] | list[T | BaseException]:
    """Gather awaitables, optionally capping concurrent execution."""
    if max_concurrency is None or max_concurrency >= len(awaitables):
        return await asyncio.gather(*awaitables, return_exceptions=return_exceptions)

    semaphore = asyncio.Semaphore(max_concurrency)

    async def _run(awaitable: Awaitable[T]) -> T:
        async with semaphore:
            return await awaitable

    wrapped_awaitables = [_run(awaitable) for awaitable in awaitables]
    return await asyncio.gather(
        *wrapped_awaitables,
        return_exceptions=return_exceptions,
    )


def run_async_many(
    *awaitables: Awaitable[T],
    timeout: float | None = None,
    return_exceptions: bool = False,
    max_concurrency: int | None = None,
) -> list[T] | list[T | BaseException]:
    """Run multiple awaitables concurrently from synchronous code.

    Args:
        *awaitables: Awaitables to execute concurrently.
        timeout: Optional timeout in seconds for the entire batch.
        return_exceptions: Mirror of ``asyncio.gather(return_exceptions=...)``.
        max_concurrency: Optional cap on how many awaitables run at once.

    Returns:
        List of results preserving input order.

    Raises:
        ValueError: If ``timeout`` or ``max_concurrency`` are not positive.
        TypeError: If any argument is not awaitable.
        TimeoutError: If execution exceeds ``timeout``.
    """
    _validate_timeout(timeout)
    _validate_max_concurrency(max_concurrency)

    if not awaitables:
        return []

    normalized_awaitables = list(awaitables)
    for index, awaitable in enumerate(normalized_awaitables):
        if not inspect.isawaitable(awaitable):
            for candidate in normalized_awaitables[:index]:
                close = getattr(candidate, "close", None)
                if callable(close):
                    close()
            raise TypeError("run_async_many expects awaitable arguments")

    async def _run_with_timeout() -> list[T] | list[T | BaseException]:
        gatherer = _gather_with_optional_limit(
            normalized_awaitables,
            max_concurrency=max_concurrency,
            return_exceptions=return_exceptions,
        )
        if timeout is None:
            return await gatherer
        return await asyncio.wait_for(gatherer, timeout=timeout)

    def _timeout_error() -> TimeoutError:
        return TimeoutError(f"run_async_many timed out after {timeout} seconds")

    return _run_with_event_loop_bridge(
        _run_with_timeout,
        timeout_error_factory=_timeout_error,
    )


def run_async_dict(
    awaitables: Mapping[K, Awaitable[T]],
    *,
    timeout: float | None = None,
    return_exceptions: bool = False,
    max_concurrency: int | None = None,
) -> dict[K, T] | dict[K, T | BaseException]:
    """Run labeled awaitables concurrently from synchronous code.

    Args:
        awaitables: Mapping of labels to awaitables.
        timeout: Optional timeout in seconds for the entire batch.
        return_exceptions: Mirror of ``asyncio.gather(return_exceptions=...)``.
        max_concurrency: Optional cap on how many awaitables run at once.

    Returns:
        Dictionary preserving insertion order with each label's result.

    Raises:
        ValueError: If ``timeout`` or ``max_concurrency`` are not positive.
        TypeError: If any mapping value is not awaitable.
        TimeoutError: If execution exceeds ``timeout``.
    """
    _validate_timeout(timeout)
    _validate_max_concurrency(max_concurrency)

    if not awaitables:
        return {}

    labeled_awaitables = list(awaitables.items())

    for index, (_, awaitable) in enumerate(labeled_awaitables):
        if not inspect.isawaitable(awaitable):
            for _, candidate in labeled_awaitables[:index]:
                close = getattr(candidate, "close", None)
                if callable(close):
                    close()
            raise TypeError("run_async_dict expects awaitable values")

    keys = [key for key, _ in labeled_awaitables]
    values = [awaitable for _, awaitable in labeled_awaitables]

    async def _run_with_timeout() -> dict[K, T] | dict[K, T | BaseException]:
        gatherer = _gather_with_optional_limit(
            values,
            max_concurrency=max_concurrency,
            return_exceptions=return_exceptions,
        )
        if timeout is None:
            results = await gatherer
        else:
            results = await asyncio.wait_for(gatherer, timeout=timeout)

        return dict(zip(keys, results, strict=True))

    def _timeout_error() -> TimeoutError:
        return TimeoutError(f"run_async_dict timed out after {timeout} seconds")

    return _run_with_event_loop_bridge(
        _run_with_timeout,
        timeout_error_factory=_timeout_error,
    )
