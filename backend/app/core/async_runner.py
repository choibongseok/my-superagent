"""Utilities for running async code safely from synchronous contexts."""

from __future__ import annotations

import asyncio
import inspect
import queue
import threading
from collections.abc import Awaitable, Callable, Hashable, Iterable, Mapping
from typing import Any, ParamSpec, TypeVar, cast, overload

P = ParamSpec("P")
T = TypeVar("T")
R = TypeVar("R")
I = TypeVar("I")
D = TypeVar("D")
K = TypeVar("K", bound=Hashable)
A = TypeVar("A")

_MISSING = object()


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


def _validate_batch_size(batch_size: int) -> None:
    """Validate batch size values used by batched helpers."""
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than 0")


def _validate_max_attempts(max_attempts: int) -> None:
    """Validate retry attempt values used by retry helpers."""
    if isinstance(max_attempts, bool) or max_attempts <= 0:
        raise ValueError("max_attempts must be greater than 0")


def _normalize_retry_exceptions(
    retry_exceptions: tuple[type[BaseException], ...],
) -> tuple[type[BaseException], ...]:
    """Validate retry exception tuple inputs."""
    if not isinstance(retry_exceptions, tuple) or not retry_exceptions:
        raise ValueError(
            "retry_exceptions must be a non-empty tuple of exception classes"
        )

    for exception_class in retry_exceptions:
        if not isinstance(exception_class, type) or not issubclass(
            exception_class,
            BaseException,
        ):
            raise TypeError("retry_exceptions must contain exception classes")

    return retry_exceptions


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


def run_async_retry(
    coro_factory: Callable[P, Awaitable[T]],
    *args: P.args,
    timeout: float | None = None,
    max_attempts: int = 3,
    retry_exceptions: tuple[type[BaseException], ...] = (Exception,),
    initial_delay: float = 0.0,
    backoff_factor: float = 1.0,
    max_delay: float | None = None,
    **kwargs: P.kwargs,
) -> T:
    """Run an async callable with retry/backoff support from sync code.

    Retries are attempted when the raised error matches ``retry_exceptions``.
    Backoff starts from ``initial_delay`` and is multiplied by
    ``backoff_factor`` after each retry, optionally capped by ``max_delay``.

    Args:
        coro_factory: Async callable to execute.
        timeout: Optional timeout in seconds for the full retry lifecycle.
        max_attempts: Total number of attempts including the first call.
        retry_exceptions: Tuple of exception classes that should be retried.
        initial_delay: Delay in seconds before the first retry.
        backoff_factor: Multiplier applied to delay after each retry.
        max_delay: Optional upper bound for retry delay.

    Returns:
        The successful result from ``coro_factory``.

    Raises:
        ValueError: If timeout/attempt/delay options are invalid.
        TypeError: If ``coro_factory`` is not callable, retry exception tuple is
            invalid, or the callable returns a non-awaitable value.
        TimeoutError: If execution exceeds ``timeout``.
        BaseException: Re-raises the final matching retry exception.
    """
    if not callable(coro_factory):
        raise TypeError("run_async_retry expects a callable coro_factory")

    _validate_timeout(timeout)
    _validate_max_attempts(max_attempts)
    normalized_retry_exceptions = _normalize_retry_exceptions(retry_exceptions)

    if initial_delay < 0:
        raise ValueError("initial_delay must be greater than or equal to 0")

    if backoff_factor <= 0:
        raise ValueError("backoff_factor must be greater than 0")

    if max_delay is not None and max_delay <= 0:
        raise ValueError("max_delay must be greater than 0")

    async def _run_with_retries() -> T:
        delay = initial_delay

        for attempt in range(1, max_attempts + 1):
            try:
                produced = coro_factory(*args, **kwargs)
            except normalized_retry_exceptions:
                if attempt >= max_attempts:
                    raise
            else:
                if not inspect.isawaitable(produced):
                    raise TypeError("coro_factory must return an awaitable")

                try:
                    return await cast(Awaitable[T], produced)
                except normalized_retry_exceptions:
                    if attempt >= max_attempts:
                        raise

            if delay > 0:
                await asyncio.sleep(delay)

            next_delay = delay * backoff_factor
            if max_delay is not None:
                delay = min(next_delay, max_delay)
            else:
                delay = next_delay

        raise RuntimeError("run_async_retry exhausted retries without returning")

    async def _run_with_timeout() -> T:
        retry_runner = _run_with_retries()
        if timeout is None:
            return await retry_runner
        return await asyncio.wait_for(retry_runner, timeout=timeout)

    def _timeout_error() -> TimeoutError:
        return TimeoutError(f"run_async_retry timed out after {timeout} seconds")

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


async def _wait_for_first_result(
    awaitables: list[Awaitable[T]],
    *,
    return_exceptions: bool,
) -> T | BaseException:
    """Await the first completed awaitable and cancel all pending work."""
    tasks = [asyncio.ensure_future(awaitable) for awaitable in awaitables]

    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        first_completed = next(task for task in tasks if task in done)

        if return_exceptions:
            try:
                return first_completed.result()
            except BaseException as exc:  # pragma: no cover - covered via tests
                return exc

        return first_completed.result()
    finally:
        for task in tasks:
            if task.done():
                continue
            task.cancel()

        pending_tasks = [task for task in tasks if not task.done()]
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)


def run_async_first(
    *awaitables: Awaitable[T],
    timeout: float | None = None,
    return_exceptions: bool = False,
) -> T | BaseException:
    """Return the first completed awaitable result from synchronous code.

    Any remaining awaitables are cancelled once the first task settles.

    Args:
        *awaitables: Awaitables racing to produce the first outcome.
        timeout: Optional timeout in seconds.
        return_exceptions: When ``True``, return the first raised exception
            instead of propagating it.

    Raises:
        ValueError: If ``timeout`` is not positive or no awaitables are passed.
        TypeError: If any argument is not awaitable.
        TimeoutError: If execution exceeds ``timeout``.
    """
    _validate_timeout(timeout)

    if not awaitables:
        raise ValueError("run_async_first expects at least one awaitable")

    normalized_awaitables = list(awaitables)
    for index, awaitable in enumerate(normalized_awaitables):
        if not inspect.isawaitable(awaitable):
            for candidate in normalized_awaitables[:index]:
                close = getattr(candidate, "close", None)
                if callable(close):
                    close()
            raise TypeError("run_async_first expects awaitable arguments")

    async def _run_with_timeout() -> T | BaseException:
        waiter = _wait_for_first_result(
            normalized_awaitables,
            return_exceptions=return_exceptions,
        )
        if timeout is None:
            return await waiter
        return await asyncio.wait_for(waiter, timeout=timeout)

    def _timeout_error() -> TimeoutError:
        return TimeoutError(f"run_async_first timed out after {timeout} seconds")

    return _run_with_event_loop_bridge(
        _run_with_timeout,
        timeout_error_factory=_timeout_error,
    )


def run_async_map(
    coro_factory: Callable[[I], Awaitable[T]],
    items: Iterable[I],
    *,
    timeout: float | None = None,
    return_exceptions: bool = False,
    max_concurrency: int | None = None,
) -> list[T] | list[T | BaseException]:
    """Map an async callable over items from synchronous code.

    Args:
        coro_factory: Callable that returns an awaitable for each input item.
        items: Iterable of input values.
        timeout: Optional timeout in seconds for the entire mapped batch.
        return_exceptions: Mirror of ``asyncio.gather(return_exceptions=...)``.
        max_concurrency: Optional cap on how many mapped tasks run at once.

    Returns:
        List of results preserving input order.

    Raises:
        ValueError: If ``timeout`` or ``max_concurrency`` are not positive.
        TypeError: If ``coro_factory`` is not callable or does not return awaitables.
        TimeoutError: If execution exceeds ``timeout``.
    """
    if not callable(coro_factory):
        raise TypeError("run_async_map expects a callable coro_factory")

    built_awaitables: list[Awaitable[T]] = []

    try:
        for item in items:
            awaitable = coro_factory(item)
            if not inspect.isawaitable(awaitable):
                raise TypeError("coro_factory must return an awaitable for each item")
            built_awaitables.append(awaitable)
    except Exception:
        for candidate in built_awaitables:
            close = getattr(candidate, "close", None)
            if callable(close):
                close()
        raise

    return run_async_many(
        *built_awaitables,
        timeout=timeout,
        return_exceptions=return_exceptions,
        max_concurrency=max_concurrency,
    )


def run_async_map_batched(
    coro_factory: Callable[[I], Awaitable[T]],
    items: Iterable[I],
    *,
    batch_size: int,
    timeout: float | None = None,
    return_exceptions: bool = False,
    max_concurrency: int | None = None,
) -> list[T] | list[T | BaseException]:
    """Map an async callable over items in bounded batches.

    Unlike :func:`run_async_map`, this helper builds and executes awaitables in
    batches to keep memory usage predictable for large iterables.

    Args:
        coro_factory: Callable that returns an awaitable for each input item.
        items: Iterable of input values.
        batch_size: Number of items to execute per batch.
        timeout: Optional timeout in seconds for the entire batched execution.
        return_exceptions: Mirror of ``asyncio.gather(return_exceptions=...)``.
        max_concurrency: Optional cap on concurrent tasks inside each batch.

    Returns:
        List of results preserving input order.

    Raises:
        ValueError: If ``batch_size``, ``timeout``, or ``max_concurrency`` are invalid.
        TypeError: If ``coro_factory`` is not callable or does not return awaitables.
        TimeoutError: If execution exceeds ``timeout``.
    """
    if not callable(coro_factory):
        raise TypeError("run_async_map_batched expects a callable coro_factory")

    _validate_batch_size(batch_size)
    _validate_timeout(timeout)
    _validate_max_concurrency(max_concurrency)

    async def _run_all_batches() -> list[T] | list[T | BaseException]:
        results: list[T] | list[T | BaseException] = []
        batch: list[I] = []

        async def _flush_batch(
            current_batch: list[I],
        ) -> list[T] | list[T | BaseException]:
            awaitables: list[Awaitable[T]] = []
            try:
                for item in current_batch:
                    awaitable = coro_factory(item)
                    if not inspect.isawaitable(awaitable):
                        raise TypeError(
                            "coro_factory must return an awaitable for each item"
                        )
                    awaitables.append(awaitable)
            except Exception:
                for candidate in awaitables:
                    close = getattr(candidate, "close", None)
                    if callable(close):
                        close()
                raise

            return await _gather_with_optional_limit(
                awaitables,
                max_concurrency=max_concurrency,
                return_exceptions=return_exceptions,
            )

        for item in items:
            batch.append(item)
            if len(batch) < batch_size:
                continue

            batch_results = await _flush_batch(batch)
            results.extend(batch_results)
            batch = []

        if batch:
            batch_results = await _flush_batch(batch)
            results.extend(batch_results)

        return results

    async def _run_with_timeout() -> list[T] | list[T | BaseException]:
        if timeout is None:
            return await _run_all_batches()
        return await asyncio.wait_for(_run_all_batches(), timeout=timeout)

    def _timeout_error() -> TimeoutError:
        return TimeoutError(f"run_async_map_batched timed out after {timeout} seconds")

    return _run_with_event_loop_bridge(
        _run_with_timeout,
        timeout_error_factory=_timeout_error,
    )


def _coerce_filter_result(result: Any, *, function_name: str) -> bool:
    """Validate predicate output for filter helpers."""
    if not isinstance(result, bool):
        raise TypeError(f"{function_name} predicate must return bool values")
    return result


def run_async_filter(
    coro_predicate: Callable[[I], Awaitable[bool]],
    items: Iterable[I],
    *,
    timeout: float | None = None,
    max_concurrency: int | None = None,
) -> list[I]:
    """Filter items using an async predicate from synchronous code.

    Args:
        coro_predicate: Async callable returning ``True`` when item is kept.
        items: Iterable of candidate values.
        timeout: Optional timeout in seconds for the entire predicate run.
        max_concurrency: Optional cap on predicate concurrency.

    Returns:
        Filtered list preserving input order.

    Raises:
        TypeError: If predicate is not callable or returns non-bool values.
        ValueError: If timeout/max_concurrency are invalid.
        TimeoutError: If execution exceeds ``timeout``.
    """
    if not callable(coro_predicate):
        raise TypeError("run_async_filter expects a callable coro_predicate")

    materialized_items = list(items)
    if not materialized_items:
        return []

    predicate_results = run_async_map(
        coro_predicate,
        materialized_items,
        timeout=timeout,
        max_concurrency=max_concurrency,
    )

    return [
        item
        for item, include in zip(materialized_items, predicate_results, strict=True)
        if _coerce_filter_result(include, function_name="run_async_filter")
    ]


def run_async_filter_batched(
    coro_predicate: Callable[[I], Awaitable[bool]],
    items: Iterable[I],
    *,
    batch_size: int,
    timeout: float | None = None,
    max_concurrency: int | None = None,
) -> list[I]:
    """Batch-oriented variant of :func:`run_async_filter`.

    This helper bounds in-memory awaitable creation for large iterables while
    preserving item order.
    """
    if not callable(coro_predicate):
        raise TypeError("run_async_filter_batched expects a callable coro_predicate")

    materialized_items = list(items)
    if not materialized_items:
        _validate_batch_size(batch_size)
        return []

    predicate_results = run_async_map_batched(
        coro_predicate,
        materialized_items,
        batch_size=batch_size,
        timeout=timeout,
        max_concurrency=max_concurrency,
    )

    return [
        item
        for item, include in zip(materialized_items, predicate_results, strict=True)
        if _coerce_filter_result(include, function_name="run_async_filter_batched")
    ]


def run_async_count(
    coro_predicate: Callable[[I], Awaitable[bool]],
    items: Iterable[I],
    *,
    timeout: float | None = None,
    max_concurrency: int | None = None,
) -> int:
    """Count items matching an async predicate from synchronous code.

    Args:
        coro_predicate: Async callable returning ``True`` when item is counted.
        items: Iterable of candidate values.
        timeout: Optional timeout in seconds for the full predicate run.
        max_concurrency: Optional cap on predicate concurrency.

    Returns:
        Number of items whose predicate result is ``True``.

    Raises:
        TypeError: If predicate is not callable or returns non-bool values.
        ValueError: If timeout/max_concurrency are invalid.
        TimeoutError: If execution exceeds ``timeout``.
    """
    if not callable(coro_predicate):
        raise TypeError("run_async_count expects a callable coro_predicate")

    predicate_results = run_async_map(
        coro_predicate,
        list(items),
        timeout=timeout,
        max_concurrency=max_concurrency,
    )

    return sum(
        _coerce_filter_result(include, function_name="run_async_count")
        for include in predicate_results
    )


def run_async_count_batched(
    coro_predicate: Callable[[I], Awaitable[bool]],
    items: Iterable[I],
    *,
    batch_size: int,
    timeout: float | None = None,
    max_concurrency: int | None = None,
) -> int:
    """Batch-oriented variant of :func:`run_async_count`.

    This helper bounds in-memory awaitable creation for large iterables while
    counting predicate matches.
    """
    if not callable(coro_predicate):
        raise TypeError("run_async_count_batched expects a callable coro_predicate")

    predicate_results = run_async_map_batched(
        coro_predicate,
        list(items),
        batch_size=batch_size,
        timeout=timeout,
        max_concurrency=max_concurrency,
    )

    return sum(
        _coerce_filter_result(include, function_name="run_async_count_batched")
        for include in predicate_results
    )


def run_async_partition(
    coro_predicate: Callable[[I], Awaitable[bool]],
    items: Iterable[I],
    *,
    timeout: float | None = None,
    max_concurrency: int | None = None,
) -> tuple[list[I], list[I]]:
    """Partition items into matching/non-matching groups via async predicate.

    Returns a two-item tuple ``(matched, rejected)`` preserving input order
    inside each partition.
    """
    if not callable(coro_predicate):
        raise TypeError("run_async_partition expects a callable coro_predicate")

    materialized_items = list(items)
    if not materialized_items:
        return [], []

    predicate_results = run_async_map(
        coro_predicate,
        materialized_items,
        timeout=timeout,
        max_concurrency=max_concurrency,
    )

    matched: list[I] = []
    rejected: list[I] = []
    for item, include in zip(materialized_items, predicate_results, strict=True):
        if _coerce_filter_result(include, function_name="run_async_partition"):
            matched.append(item)
        else:
            rejected.append(item)

    return matched, rejected


def run_async_partition_batched(
    coro_predicate: Callable[[I], Awaitable[bool]],
    items: Iterable[I],
    *,
    batch_size: int,
    timeout: float | None = None,
    max_concurrency: int | None = None,
) -> tuple[list[I], list[I]]:
    """Batch-oriented variant of :func:`run_async_partition`."""
    if not callable(coro_predicate):
        raise TypeError("run_async_partition_batched expects a callable coro_predicate")

    materialized_items = list(items)
    if not materialized_items:
        _validate_batch_size(batch_size)
        return [], []

    predicate_results = run_async_map_batched(
        coro_predicate,
        materialized_items,
        batch_size=batch_size,
        timeout=timeout,
        max_concurrency=max_concurrency,
    )

    matched: list[I] = []
    rejected: list[I] = []
    for item, include in zip(materialized_items, predicate_results, strict=True):
        if _coerce_filter_result(
            include,
            function_name="run_async_partition_batched",
        ):
            matched.append(item)
        else:
            rejected.append(item)

    return matched, rejected


def run_async_reduce(
    coro_reducer: Callable[[A, I], Awaitable[A]],
    items: Iterable[I],
    *,
    timeout: float | None = None,
    initial: A | object = _MISSING,
) -> A:
    """Reduce ``items`` using an async reducer from synchronous code.

    Args:
        coro_reducer: Async callable receiving ``(accumulator, item)``.
        items: Iterable of values to reduce.
        timeout: Optional timeout in seconds for the full reduction.
        initial: Optional initial accumulator value. When omitted, the first
            item is used as the starting accumulator (matching ``functools.reduce``).

    Returns:
        Final reduced accumulator value.

    Raises:
        TypeError: If ``coro_reducer`` is not callable or does not return an awaitable.
        ValueError: If ``timeout`` is not positive.
        LookupError: If ``items`` is empty and ``initial`` is not provided.
        TimeoutError: If execution exceeds ``timeout``.
    """
    if not callable(coro_reducer):
        raise TypeError("run_async_reduce expects a callable coro_reducer")

    _validate_timeout(timeout)

    materialized_items = list(items)

    if initial is _MISSING:
        if not materialized_items:
            raise LookupError(
                "run_async_reduce cannot reduce an empty iterable without an initial value"
            )
        accumulator: A = cast(A, materialized_items[0])
        remaining_items = materialized_items[1:]
    else:
        accumulator = cast(A, initial)
        remaining_items = materialized_items

    async def _run_reducer() -> A:
        current = accumulator
        for item in remaining_items:
            produced = coro_reducer(current, item)
            if not inspect.isawaitable(produced):
                raise TypeError("coro_reducer must return an awaitable")
            current = await cast(Awaitable[A], produced)

        return current

    async def _run_with_timeout() -> A:
        if timeout is None:
            return await _run_reducer()
        return await asyncio.wait_for(_run_reducer(), timeout=timeout)

    def _timeout_error() -> TimeoutError:
        return TimeoutError(f"run_async_reduce timed out after {timeout} seconds")

    return _run_with_event_loop_bridge(
        _run_with_timeout,
        timeout_error_factory=_timeout_error,
    )


def _build_starmap_awaitable(
    coro_factory: Callable[..., Awaitable[T]],
    item: Iterable[Any] | Mapping[str, Any],
    *,
    function_name: str,
) -> Awaitable[T]:
    """Build one awaitable for ``run_async_starmap`` helpers."""
    if isinstance(item, Mapping):
        awaitable = coro_factory(**dict(item))
    else:
        if isinstance(item, (str, bytes, bytearray)):
            raise TypeError(
                f"{function_name} items must be iterables of args "
                "or mappings of kwargs"
            )

        try:
            args = tuple(item)
        except TypeError as exc:
            raise TypeError(
                f"{function_name} items must be iterables of args "
                "or mappings of kwargs"
            ) from exc

        awaitable = coro_factory(*args)

    if not inspect.isawaitable(awaitable):
        raise TypeError("coro_factory must return an awaitable for each item")

    return cast(Awaitable[T], awaitable)


def run_async_starmap(
    coro_factory: Callable[..., Awaitable[T]],
    items: Iterable[Iterable[Any] | Mapping[str, Any]],
    *,
    timeout: float | None = None,
    return_exceptions: bool = False,
    max_concurrency: int | None = None,
) -> list[T] | list[T | BaseException]:
    """Map an async callable over iterable arg-tuples or kwarg mappings.

    Each item can be either:
    - an iterable of positional arguments, or
    - a mapping of keyword arguments.

    This is a synchronous bridge around an async equivalent of
    :func:`itertools.starmap`.

    Args:
        coro_factory: Callable that returns an awaitable for each unpacked item.
        items: Iterable of positional-arg iterables or kwarg mappings.
        timeout: Optional timeout in seconds for the entire mapped batch.
        return_exceptions: Mirror of ``asyncio.gather(return_exceptions=...)``.
        max_concurrency: Optional cap on how many mapped tasks run at once.

    Returns:
        List of results preserving input order.

    Raises:
        ValueError: If ``timeout`` or ``max_concurrency`` are not positive.
        TypeError: If ``coro_factory`` is not callable, an item cannot be unpacked,
            or factory calls do not return awaitables.
        TimeoutError: If execution exceeds ``timeout``.
    """
    if not callable(coro_factory):
        raise TypeError("run_async_starmap expects a callable coro_factory")

    built_awaitables: list[Awaitable[T]] = []

    try:
        for item in items:
            built_awaitables.append(
                _build_starmap_awaitable(
                    coro_factory,
                    item,
                    function_name="run_async_starmap",
                )
            )
    except Exception:
        for candidate in built_awaitables:
            close = getattr(candidate, "close", None)
            if callable(close):
                close()
        raise

    return run_async_many(
        *built_awaitables,
        timeout=timeout,
        return_exceptions=return_exceptions,
        max_concurrency=max_concurrency,
    )


def run_async_starmap_batched(
    coro_factory: Callable[..., Awaitable[T]],
    items: Iterable[Iterable[Any] | Mapping[str, Any]],
    *,
    batch_size: int,
    timeout: float | None = None,
    return_exceptions: bool = False,
    max_concurrency: int | None = None,
) -> list[T] | list[T | BaseException]:
    """Map an async callable over unpacked items in bounded batches.

    This batched variant of :func:`run_async_starmap` limits in-memory awaitable
    creation for large iterables while preserving input order.

    Args:
        coro_factory: Callable that returns an awaitable for each unpacked item.
        items: Iterable of positional-arg iterables or kwarg mappings.
        batch_size: Number of unpacked items to execute per batch.
        timeout: Optional timeout in seconds for the entire batched execution.
        return_exceptions: Mirror of ``asyncio.gather(return_exceptions=...)``.
        max_concurrency: Optional cap on concurrent tasks inside each batch.

    Returns:
        List of results preserving input order.

    Raises:
        ValueError: If ``batch_size``, ``timeout``, or ``max_concurrency`` are invalid.
        TypeError: If ``coro_factory`` is not callable, an item cannot be unpacked,
            or factory calls do not return awaitables.
        TimeoutError: If execution exceeds ``timeout``.
    """
    if not callable(coro_factory):
        raise TypeError("run_async_starmap_batched expects a callable coro_factory")

    _validate_batch_size(batch_size)
    _validate_timeout(timeout)
    _validate_max_concurrency(max_concurrency)

    async def _run_all_batches() -> list[T] | list[T | BaseException]:
        results: list[T] | list[T | BaseException] = []
        batch: list[Iterable[Any] | Mapping[str, Any]] = []

        async def _flush_batch(
            current_batch: list[Iterable[Any] | Mapping[str, Any]],
        ) -> list[T] | list[T | BaseException]:
            awaitables: list[Awaitable[T]] = []
            try:
                for item in current_batch:
                    awaitables.append(
                        _build_starmap_awaitable(
                            coro_factory,
                            item,
                            function_name="run_async_starmap_batched",
                        )
                    )
            except Exception:
                for candidate in awaitables:
                    close = getattr(candidate, "close", None)
                    if callable(close):
                        close()
                raise

            return await _gather_with_optional_limit(
                awaitables,
                max_concurrency=max_concurrency,
                return_exceptions=return_exceptions,
            )

        for item in items:
            batch.append(item)
            if len(batch) < batch_size:
                continue

            batch_results = await _flush_batch(batch)
            results.extend(batch_results)
            batch = []

        if batch:
            batch_results = await _flush_batch(batch)
            results.extend(batch_results)

        return results

    async def _run_with_timeout() -> list[T] | list[T | BaseException]:
        if timeout is None:
            return await _run_all_batches()
        return await asyncio.wait_for(_run_all_batches(), timeout=timeout)

    def _timeout_error() -> TimeoutError:
        return TimeoutError(
            f"run_async_starmap_batched timed out after {timeout} seconds"
        )

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


@overload
def run_async_find(
    coro_predicate: Callable[[I], Awaitable[bool]],
    items: Iterable[I],
    *,
    timeout: float | None = None,
    max_concurrency: int | None = None,
) -> I:
    ...


@overload
def run_async_find(
    coro_predicate: Callable[[I], Awaitable[bool]],
    items: Iterable[I],
    *,
    timeout: float | None = None,
    max_concurrency: int | None = None,
    default: D,
) -> I | D:
    ...


def run_async_find(
    coro_predicate: Callable[[I], Awaitable[bool]],
    items: Iterable[I],
    *,
    timeout: float | None = None,
    max_concurrency: int | None = None,
    default: Any = _MISSING,
) -> I | D:
    """Return the first item matching an async predicate.

    Args:
        coro_predicate: Async callable returning ``True`` for matching items.
        items: Iterable of candidate values.
        timeout: Optional timeout in seconds for the full predicate run.
        max_concurrency: Optional cap on predicate concurrency.
        default: Fallback value returned when no items match.

    Raises:
        TypeError: If predicate is not callable or returns non-bool values.
        ValueError: If timeout/max_concurrency are invalid.
        LookupError: If no items match and ``default`` is not provided.
        TimeoutError: If execution exceeds ``timeout``.
    """
    if not callable(coro_predicate):
        raise TypeError("run_async_find expects a callable coro_predicate")

    materialized_items = list(items)
    if not materialized_items:
        if default is _MISSING:
            raise LookupError("run_async_find did not match any items")
        return cast(D, default)

    predicate_results = run_async_map(
        coro_predicate,
        materialized_items,
        timeout=timeout,
        max_concurrency=max_concurrency,
    )

    for item, include in zip(materialized_items, predicate_results, strict=True):
        if _coerce_filter_result(include, function_name="run_async_find"):
            return item

    if default is _MISSING:
        raise LookupError("run_async_find did not match any items")

    return cast(D, default)


@overload
def run_async_find_batched(
    coro_predicate: Callable[[I], Awaitable[bool]],
    items: Iterable[I],
    *,
    batch_size: int,
    timeout: float | None = None,
    max_concurrency: int | None = None,
) -> I:
    ...


@overload
def run_async_find_batched(
    coro_predicate: Callable[[I], Awaitable[bool]],
    items: Iterable[I],
    *,
    batch_size: int,
    timeout: float | None = None,
    max_concurrency: int | None = None,
    default: D,
) -> I | D:
    ...


def run_async_find_batched(
    coro_predicate: Callable[[I], Awaitable[bool]],
    items: Iterable[I],
    *,
    batch_size: int,
    timeout: float | None = None,
    max_concurrency: int | None = None,
    default: Any = _MISSING,
) -> I | D:
    """Batch-oriented variant of :func:`run_async_find`."""
    if not callable(coro_predicate):
        raise TypeError("run_async_find_batched expects a callable coro_predicate")

    materialized_items = list(items)
    if not materialized_items:
        _validate_batch_size(batch_size)
        if default is _MISSING:
            raise LookupError("run_async_find_batched did not match any items")
        return cast(D, default)

    predicate_results = run_async_map_batched(
        coro_predicate,
        materialized_items,
        batch_size=batch_size,
        timeout=timeout,
        max_concurrency=max_concurrency,
    )

    for item, include in zip(materialized_items, predicate_results, strict=True):
        if _coerce_filter_result(include, function_name="run_async_find_batched"):
            return item

    if default is _MISSING:
        raise LookupError("run_async_find_batched did not match any items")

    return cast(D, default)
