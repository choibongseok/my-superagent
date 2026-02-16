"""Tests for async runner utility."""

import asyncio

import pytest

from app.core.async_runner import (
    run_async,
    run_async_all,
    run_async_all_batched,
    run_async_any,
    run_async_any_batched,
    run_async_at_least,
    run_async_at_least_batched,
    run_async_at_most,
    run_async_at_most_batched,
    run_async_count,
    run_async_count_batched,
    run_async_dict,
    run_async_exactly,
    run_async_exactly_batched,
    run_async_filter,
    run_async_filter_batched,
    run_async_find,
    run_async_find_batched,
    run_async_first,
    run_async_group_by,
    run_async_group_by_batched,
    run_async_index,
    run_async_index_batched,
    run_async_many,
    run_async_map,
    run_async_map_batched,
    run_async_none,
    run_async_none_batched,
    run_async_partition,
    run_async_partition_batched,
    run_async_reduce,
    run_async_retry,
    run_async_sort,
    run_async_sort_batched,
    run_async_starmap,
    run_async_starmap_batched,
)


async def _compute_value() -> int:
    await asyncio.sleep(0.01)
    return 42


def test_run_async_without_existing_event_loop_returns_result():
    assert run_async(_compute_value) == 42


@pytest.mark.asyncio
async def test_run_async_with_existing_event_loop_returns_result():
    result = run_async(_compute_value)
    assert result == 42


def test_run_async_propagates_exceptions_without_existing_event_loop():
    async def _raise_error() -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        run_async(_raise_error)


@pytest.mark.asyncio
async def test_run_async_propagates_exceptions_with_existing_event_loop():
    async def _raise_error() -> None:
        raise RuntimeError("loop-boom")

    with pytest.raises(RuntimeError, match="loop-boom"):
        run_async(_raise_error)


def test_run_async_timeout_without_existing_event_loop():
    async def _sleep() -> None:
        await asyncio.sleep(0.1)

    with pytest.raises(TimeoutError, match="timed out"):
        run_async(_sleep, timeout=0.01)


@pytest.mark.asyncio
async def test_run_async_timeout_with_existing_event_loop():
    async def _sleep() -> None:
        await asyncio.sleep(0.1)

    with pytest.raises(TimeoutError, match="timed out"):
        run_async(_sleep, timeout=0.01)


def test_run_async_rejects_non_positive_timeout():
    with pytest.raises(ValueError, match="timeout must be greater than 0"):
        run_async(_compute_value, timeout=0)


def test_run_async_supports_positional_arguments():
    async def _add(left: int, right: int) -> int:
        await asyncio.sleep(0.01)
        return left + right

    assert run_async(_add, 20, 22) == 42


def test_run_async_supports_keyword_arguments():
    async def _format_message(name: str, suffix: str = "") -> str:
        await asyncio.sleep(0.01)
        return f"hello {name}{suffix}"

    assert run_async(_format_message, "codex", suffix="!") == "hello codex!"


def test_run_async_rejects_non_awaitable_return_value():
    def _sync_value() -> int:
        return 42

    with pytest.raises(TypeError, match="must return an awaitable"):
        run_async(_sync_value)


def test_run_async_supports_prebuilt_awaitable_without_existing_event_loop():
    assert run_async(_compute_value()) == 42


@pytest.mark.asyncio
async def test_run_async_supports_prebuilt_awaitable_with_existing_event_loop():
    assert run_async(_compute_value()) == 42


def test_run_async_rejects_extra_arguments_for_prebuilt_awaitable():
    coroutine = _compute_value()
    try:
        with pytest.raises(
            TypeError,
            match="cannot be provided when passing an awaitable",
        ):
            run_async(coroutine, 1)
    finally:
        coroutine.close()


def test_run_async_rejects_non_callable_and_non_awaitable_input():
    with pytest.raises(
        TypeError,
        match="expects an awaitable or a callable returning an awaitable",
    ):
        run_async(123)  # type: ignore[arg-type]


def test_run_async_retry_returns_value_without_retries():
    async def _value() -> str:
        await asyncio.sleep(0.01)
        return "ok"

    assert run_async_retry(_value) == "ok"


def test_run_async_retry_retries_until_success():
    attempts = {"count": 0}

    async def _flaky() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("temporary")
        return "recovered"

    result = run_async_retry(_flaky, max_attempts=3)

    assert result == "recovered"
    assert attempts["count"] == 3


def test_run_async_retry_raises_last_retryable_error_when_exhausted():
    attempts = {"count": 0}

    async def _always_fail() -> str:
        attempts["count"] += 1
        raise RuntimeError("still failing")

    with pytest.raises(RuntimeError, match="still failing"):
        run_async_retry(_always_fail, max_attempts=2)

    assert attempts["count"] == 2


def test_run_async_retry_does_not_retry_non_matching_exceptions():
    attempts = {"count": 0}

    async def _fails_with_type_error() -> str:
        attempts["count"] += 1
        raise TypeError("bad type")

    with pytest.raises(TypeError, match="bad type"):
        run_async_retry(
            _fails_with_type_error,
            max_attempts=5,
            retry_exceptions=(RuntimeError,),
        )

    assert attempts["count"] == 1


def test_run_async_retry_rejects_invalid_retry_configuration():
    async def _value() -> int:
        return 1

    with pytest.raises(ValueError, match="max_attempts must be greater than 0"):
        run_async_retry(_value, max_attempts=0)

    with pytest.raises(
        ValueError,
        match="initial_delay must be greater than or equal to 0",
    ):
        run_async_retry(_value, initial_delay=-0.1)

    with pytest.raises(ValueError, match="backoff_factor must be greater than 0"):
        run_async_retry(_value, backoff_factor=0)

    with pytest.raises(
        ValueError,
        match="retry_exceptions must be a non-empty tuple of exception classes",
    ):
        run_async_retry(_value, retry_exceptions=())

    with pytest.raises(ValueError, match="jitter_ratio must be a number in \[0, 1\]"):
        run_async_retry(_value, jitter_ratio=-0.1)

    with pytest.raises(ValueError, match="jitter_ratio must be a number in \[0, 1\]"):
        run_async_retry(_value, jitter_ratio=1.1)

    with pytest.raises(ValueError, match="jitter_ratio must be a number in \[0, 1\]"):
        run_async_retry(_value, jitter_ratio=True)


def test_run_async_retry_supports_should_retry_predicate_control():
    attempts = {"count": 0}
    retry_decisions: list[tuple[str, int]] = []

    async def _always_fail() -> str:
        attempts["count"] += 1
        raise RuntimeError("retryable boom")

    def _should_retry(exception: BaseException, attempt: int) -> bool:
        retry_decisions.append((str(exception), attempt))
        return attempt < 2

    with pytest.raises(RuntimeError, match="retryable boom"):
        run_async_retry(
            _always_fail,
            max_attempts=5,
            should_retry=_should_retry,
        )

    assert attempts["count"] == 2
    assert retry_decisions == [
        ("retryable boom", 1),
        ("retryable boom", 2),
    ]


def test_run_async_retry_rejects_invalid_should_retry_configuration():
    async def _value() -> int:
        return 1

    with pytest.raises(TypeError, match="should_retry must be callable"):
        run_async_retry(_value, should_retry="yes")  # type: ignore[arg-type]


def test_run_async_retry_rejects_non_boolean_should_retry_results():
    attempts = {"count": 0}

    async def _always_fail() -> str:
        attempts["count"] += 1
        raise RuntimeError("bad")

    def _invalid_should_retry(_: BaseException, __: int) -> str:
        return "yes"

    with pytest.raises(TypeError, match="should_retry must return a boolean"):
        run_async_retry(
            _always_fail,
            max_attempts=3,
            should_retry=_invalid_should_retry,
        )

    assert attempts["count"] == 1


def test_run_async_retry_applies_jitter_to_retry_delays(monkeypatch):
    attempts = {"count": 0}
    sleep_calls: list[float] = []
    jitter_bounds: list[tuple[float, float]] = []

    async def _flaky() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("temporary")
        return "ok"

    async def _fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    jitter_values = iter([0.15, 0.5])

    def _fake_uniform(lower: float, upper: float) -> float:
        jitter_bounds.append((lower, upper))
        return next(jitter_values)

    monkeypatch.setattr("app.core.async_runner.asyncio.sleep", _fake_sleep)
    monkeypatch.setattr("app.core.async_runner.random.uniform", _fake_uniform)

    result = run_async_retry(
        _flaky,
        max_attempts=3,
        initial_delay=0.2,
        backoff_factor=2.0,
        jitter_ratio=0.5,
    )

    assert result == "ok"
    assert attempts["count"] == 3
    assert len(jitter_bounds) == 2
    assert jitter_bounds[0] == pytest.approx((0.1, 0.3))
    assert jitter_bounds[1] == pytest.approx((0.2, 0.6))
    assert sleep_calls == pytest.approx([0.15, 0.5])


def test_run_async_retry_with_zero_jitter_uses_base_delay(monkeypatch):
    attempts = {"count": 0}
    sleep_calls: list[float] = []

    async def _flaky() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("temporary")
        return "ok"

    async def _fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    def _unexpected_uniform(_lower: float, _upper: float) -> float:
        raise AssertionError("random.uniform should not be called when jitter_ratio=0")

    monkeypatch.setattr("app.core.async_runner.asyncio.sleep", _fake_sleep)
    monkeypatch.setattr("app.core.async_runner.random.uniform", _unexpected_uniform)

    result = run_async_retry(
        _flaky,
        max_attempts=3,
        initial_delay=0.2,
        backoff_factor=2.0,
        jitter_ratio=0.0,
    )

    assert result == "ok"
    assert attempts["count"] == 3
    assert sleep_calls == [0.2, 0.4]


def test_run_async_retry_timeout_applies_to_entire_retry_lifecycle():
    async def _slow_fail() -> int:
        await asyncio.sleep(0.05)
        raise RuntimeError("slow boom")

    with pytest.raises(TimeoutError, match="run_async_retry timed out"):
        run_async_retry(
            _slow_fail,
            timeout=0.06,
            max_attempts=3,
            initial_delay=0.05,
        )


def test_run_async_many_without_existing_event_loop_returns_ordered_results():
    async def _double(value: int) -> int:
        await asyncio.sleep(0.01)
        return value * 2

    assert run_async_many(_double(1), _double(2), _double(3)) == [2, 4, 6]


@pytest.mark.asyncio
async def test_run_async_many_with_existing_event_loop_returns_results():
    async def _format(index: int) -> str:
        await asyncio.sleep(0.01)
        return f"task-{index}"

    assert run_async_many(_format(1), _format(2)) == ["task-1", "task-2"]


def test_run_async_many_propagates_exceptions_by_default():
    async def _ok() -> str:
        return "ok"

    async def _fail() -> str:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        run_async_many(_ok(), _fail())


@pytest.mark.asyncio
async def test_run_async_many_can_return_exceptions_when_requested():
    async def _ok() -> int:
        await asyncio.sleep(0.01)
        return 7

    async def _fail() -> int:
        await asyncio.sleep(0.01)
        raise ValueError("bad")

    results = run_async_many(_ok(), _fail(), return_exceptions=True)

    assert results[0] == 7
    assert isinstance(results[1], ValueError)
    assert str(results[1]) == "bad"


def test_run_async_many_timeout_without_existing_event_loop():
    async def _sleep() -> None:
        await asyncio.sleep(0.1)

    with pytest.raises(TimeoutError, match="run_async_many timed out"):
        run_async_many(_sleep(), timeout=0.01)


def test_run_async_many_rejects_non_awaitable_arguments():
    coroutine = _compute_value()
    try:
        with pytest.raises(TypeError, match="expects awaitable arguments"):
            run_async_many(coroutine, 123)  # type: ignore[arg-type]
    finally:
        coroutine.close()


def test_run_async_many_empty_input_returns_empty_list():
    assert run_async_many() == []


def test_run_async_many_rejects_non_positive_max_concurrency():
    coroutine = _compute_value()
    try:
        with pytest.raises(ValueError, match="max_concurrency must be greater than 0"):
            run_async_many(coroutine, max_concurrency=0)
    finally:
        coroutine.close()


def test_run_async_many_honors_max_concurrency_limit():
    active = 0
    max_active = 0

    async def _tracked(value: int) -> int:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return value

    results = run_async_many(
        _tracked(1),
        _tracked(2),
        _tracked(3),
        _tracked(4),
        max_concurrency=2,
    )

    assert results == [1, 2, 3, 4]
    assert max_active == 2


def test_run_async_first_returns_earliest_completed_result():
    async def _slow() -> str:
        await asyncio.sleep(0.05)
        return "slow"

    async def _fast() -> str:
        await asyncio.sleep(0.01)
        return "fast"

    result = run_async_first(_slow(), _fast())

    assert result == "fast"


@pytest.mark.asyncio
async def test_run_async_first_with_existing_event_loop_returns_result():
    async def _value() -> int:
        await asyncio.sleep(0.01)
        return 7

    assert run_async_first(_value()) == 7


def test_run_async_first_rejects_empty_input():
    with pytest.raises(ValueError, match="expects at least one awaitable"):
        run_async_first()


def test_run_async_first_rejects_non_awaitable_arguments():
    coroutine = _compute_value()
    try:
        with pytest.raises(TypeError, match="expects awaitable arguments"):
            run_async_first(coroutine, 123)  # type: ignore[arg-type]
    finally:
        coroutine.close()


def test_run_async_first_timeout_without_existing_event_loop():
    async def _sleep() -> None:
        await asyncio.sleep(0.1)

    with pytest.raises(TimeoutError, match="run_async_first timed out"):
        run_async_first(_sleep(), timeout=0.01)


def test_run_async_first_propagates_first_exception_by_default():
    async def _fail() -> str:
        await asyncio.sleep(0.01)
        raise RuntimeError("boom")

    async def _slow() -> str:
        await asyncio.sleep(0.05)
        return "slow"

    with pytest.raises(RuntimeError, match="boom"):
        run_async_first(_fail(), _slow())


def test_run_async_first_can_return_exceptions_when_requested():
    async def _fail() -> str:
        await asyncio.sleep(0.01)
        raise ValueError("bad")

    async def _slow() -> str:
        await asyncio.sleep(0.05)
        return "slow"

    result = run_async_first(_fail(), _slow(), return_exceptions=True)

    assert isinstance(result, ValueError)
    assert str(result) == "bad"


def test_run_async_first_cancels_pending_awaitables_after_first_completion():
    cancellation_flag = {"cancelled": False}

    async def _slow() -> str:
        try:
            await asyncio.sleep(1)
            return "slow"
        except asyncio.CancelledError:
            cancellation_flag["cancelled"] = True
            raise

    async def _fast() -> str:
        await asyncio.sleep(0.01)
        return "fast"

    assert run_async_first(_slow(), _fast()) == "fast"
    assert cancellation_flag["cancelled"] is True


def test_run_async_dict_without_existing_event_loop_returns_results():
    async def _double(value: int) -> int:
        await asyncio.sleep(0.01)
        return value * 2

    result = run_async_dict(
        {
            "left": _double(2),
            "right": _double(3),
        }
    )

    assert result == {"left": 4, "right": 6}


@pytest.mark.asyncio
async def test_run_async_dict_with_existing_event_loop_returns_results():
    async def _label(index: int) -> str:
        await asyncio.sleep(0.01)
        return f"item-{index}"

    result = run_async_dict({"a": _label(1), "b": _label(2)})

    assert result == {"a": "item-1", "b": "item-2"}


def test_run_async_dict_propagates_exceptions_by_default():
    async def _ok() -> str:
        return "ok"

    async def _fail() -> str:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        run_async_dict({"ok": _ok(), "fail": _fail()})


@pytest.mark.asyncio
async def test_run_async_dict_can_return_exceptions_when_requested():
    async def _ok() -> int:
        await asyncio.sleep(0.01)
        return 1

    async def _fail() -> int:
        await asyncio.sleep(0.01)
        raise ValueError("bad")

    result = run_async_dict(
        {"good": _ok(), "bad": _fail()},
        return_exceptions=True,
    )

    assert result["good"] == 1
    assert isinstance(result["bad"], ValueError)
    assert str(result["bad"]) == "bad"


def test_run_async_dict_timeout_without_existing_event_loop():
    async def _sleep() -> None:
        await asyncio.sleep(0.1)

    with pytest.raises(TimeoutError, match="run_async_dict timed out"):
        run_async_dict({"slow": _sleep()}, timeout=0.01)


def test_run_async_dict_rejects_non_awaitable_values():
    coroutine = _compute_value()
    try:
        with pytest.raises(TypeError, match="expects awaitable values"):
            run_async_dict({"ok": coroutine, "bad": 123})  # type: ignore[arg-type]
    finally:
        coroutine.close()


def test_run_async_dict_rejects_non_positive_max_concurrency():
    coroutine = _compute_value()
    try:
        with pytest.raises(ValueError, match="max_concurrency must be greater than 0"):
            run_async_dict({"ok": coroutine}, max_concurrency=0)
    finally:
        coroutine.close()


def test_run_async_dict_honors_max_concurrency_limit():
    active = 0
    max_active = 0

    async def _tracked(value: int) -> int:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return value

    result = run_async_dict(
        {
            "a": _tracked(1),
            "b": _tracked(2),
            "c": _tracked(3),
            "d": _tracked(4),
        },
        max_concurrency=2,
    )

    assert result == {"a": 1, "b": 2, "c": 3, "d": 4}
    assert max_active == 2


def test_run_async_dict_empty_input_returns_empty_dict():
    assert run_async_dict({}) == {}


def test_run_async_map_without_existing_event_loop_returns_ordered_results():
    async def _double(value: int) -> int:
        await asyncio.sleep(0.01)
        return value * 2

    result = run_async_map(_double, [1, 2, 3])

    assert result == [2, 4, 6]


@pytest.mark.asyncio
async def test_run_async_map_with_existing_event_loop_returns_results():
    async def _label(value: int) -> str:
        await asyncio.sleep(0.01)
        return f"item-{value}"

    result = run_async_map(_label, [1, 2])

    assert result == ["item-1", "item-2"]


def test_run_async_map_propagates_exceptions_by_default():
    async def _explode(value: int) -> int:
        if value == 2:
            raise RuntimeError("boom")
        return value

    with pytest.raises(RuntimeError, match="boom"):
        run_async_map(_explode, [1, 2, 3])


def test_run_async_map_can_return_exceptions_when_requested():
    async def _explode(value: int) -> int:
        if value == 2:
            raise ValueError("bad")
        return value

    result = run_async_map(_explode, [1, 2, 3], return_exceptions=True)

    assert result[0] == 1
    assert isinstance(result[1], ValueError)
    assert str(result[1]) == "bad"
    assert result[2] == 3


def test_run_async_map_rejects_non_callable_factory():
    with pytest.raises(TypeError, match="expects a callable coro_factory"):
        run_async_map(123, [1, 2])  # type: ignore[arg-type]


def test_run_async_map_rejects_non_awaitable_factory_results():
    def _sync_factory(value: int) -> int:
        return value

    with pytest.raises(TypeError, match="must return an awaitable"):
        run_async_map(_sync_factory, [1, 2])


def test_run_async_map_honors_max_concurrency_limit():
    active = 0
    max_active = 0

    async def _tracked(value: int) -> int:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return value

    result = run_async_map(_tracked, [1, 2, 3, 4], max_concurrency=2)

    assert result == [1, 2, 3, 4]
    assert max_active == 2


def test_run_async_map_empty_input_returns_empty_list():
    async def _noop(value: int) -> int:
        return value

    assert run_async_map(_noop, []) == []


def test_run_async_map_batched_returns_ordered_results_across_batches():
    async def _double(value: int) -> int:
        await asyncio.sleep(0.01)
        return value * 2

    result = run_async_map_batched(_double, [1, 2, 3, 4, 5], batch_size=2)

    assert result == [2, 4, 6, 8, 10]


@pytest.mark.asyncio
async def test_run_async_map_batched_with_existing_event_loop_returns_results():
    async def _label(value: int) -> str:
        await asyncio.sleep(0.01)
        return f"item-{value}"

    result = run_async_map_batched(_label, [1, 2, 3], batch_size=2)

    assert result == ["item-1", "item-2", "item-3"]


def test_run_async_map_batched_can_return_exceptions_when_requested():
    async def _explode(value: int) -> int:
        if value == 2:
            raise ValueError("bad")
        return value

    result = run_async_map_batched(
        _explode,
        [1, 2, 3],
        batch_size=2,
        return_exceptions=True,
    )

    assert result[0] == 1
    assert isinstance(result[1], ValueError)
    assert str(result[1]) == "bad"
    assert result[2] == 3


def test_run_async_map_batched_rejects_non_positive_batch_size():
    async def _noop(value: int) -> int:
        return value

    with pytest.raises(ValueError, match="batch_size must be greater than 0"):
        run_async_map_batched(_noop, [1], batch_size=0)


def test_run_async_map_batched_rejects_non_awaitable_factory_results():
    def _sync_factory(value: int) -> int:
        return value

    with pytest.raises(TypeError, match="must return an awaitable"):
        run_async_map_batched(_sync_factory, [1], batch_size=1)


def test_run_async_map_batched_honors_max_concurrency_limit():
    active = 0
    max_active = 0

    async def _tracked(value: int) -> int:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return value

    result = run_async_map_batched(
        _tracked,
        [1, 2, 3, 4],
        batch_size=4,
        max_concurrency=2,
    )

    assert result == [1, 2, 3, 4]
    assert max_active == 2


def test_run_async_map_batched_timeout_applies_to_entire_run():
    async def _sleep(value: int) -> int:
        await asyncio.sleep(0.03)
        return value

    with pytest.raises(TimeoutError, match="run_async_map_batched timed out"):
        run_async_map_batched(_sleep, [1, 2, 3], batch_size=1, timeout=0.05)


def test_run_async_filter_returns_items_matching_async_predicate():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_filter(_is_even, [1, 2, 3, 4, 5]) == [2, 4]


@pytest.mark.asyncio
async def test_run_async_filter_with_existing_event_loop_returns_results():
    async def _keep_prefix(value: str) -> bool:
        await asyncio.sleep(0.01)
        return value.startswith("agent")

    assert run_async_filter(_keep_prefix, ["agent-1", "task-2", "agent-3"]) == [
        "agent-1",
        "agent-3",
    ]


def test_run_async_filter_rejects_non_callable_predicate():
    with pytest.raises(TypeError, match="expects a callable coro_predicate"):
        run_async_filter(123, [1, 2])  # type: ignore[arg-type]


def test_run_async_filter_rejects_non_bool_predicate_results():
    async def _invalid(_: int) -> str:
        return "yes"

    with pytest.raises(TypeError, match="predicate must return bool"):
        run_async_filter(_invalid, [1])


def test_run_async_filter_honors_max_concurrency_limit():
    active = 0
    max_active = 0

    async def _tracked(value: int) -> bool:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return value % 2 == 0

    assert run_async_filter(_tracked, [1, 2, 3, 4], max_concurrency=2) == [2, 4]
    assert max_active == 2


def test_run_async_filter_timeout_applies_to_entire_run():
    async def _slow(_: int) -> bool:
        await asyncio.sleep(0.1)
        return True

    with pytest.raises(TimeoutError, match="run_async_many timed out"):
        run_async_filter(_slow, [1, 2, 3], timeout=0.01)


def test_run_async_filter_supports_start_and_stop_offsets():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_filter(_is_even, [2, 3, 4, 5], start=1) == [4]
    assert run_async_filter(_is_even, [2, 3, 4, 5], stop=2) == [2]


def test_run_async_filter_rejects_invalid_offsets():
    async def _is_even(value: int) -> bool:
        return value % 2 == 0

    with pytest.raises(ValueError, match="start must be an integer"):
        run_async_filter(_is_even, [1, 2, 3], start=True)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="stop cannot be negative"):
        run_async_filter(_is_even, [1, 2, 3], stop=-1)


def test_run_async_filter_batched_returns_items_matching_predicate():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_filter_batched(_is_even, [1, 2, 3, 4, 5], batch_size=2) == [2, 4]


def test_run_async_filter_batched_rejects_non_bool_predicate_results():
    async def _invalid(_: int) -> int:
        return 1

    with pytest.raises(TypeError, match="predicate must return bool"):
        run_async_filter_batched(_invalid, [1], batch_size=1)


def test_run_async_filter_batched_rejects_non_positive_batch_size_for_empty_items():
    async def _always_true(_: int) -> bool:
        return True

    with pytest.raises(ValueError, match="batch_size must be greater than 0"):
        run_async_filter_batched(_always_true, [], batch_size=0)


def test_run_async_filter_batched_supports_start_and_stop_offsets():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_filter_batched(_is_even, [2, 3, 4, 5], batch_size=2, start=1) == [
        4
    ]
    assert run_async_filter_batched(_is_even, [2, 3, 4, 5], batch_size=2, stop=2) == [2]


def test_run_async_count_returns_number_of_matching_items():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_count(_is_even, [1, 2, 3, 4, 5]) == 2


@pytest.mark.asyncio
async def test_run_async_count_with_existing_event_loop_returns_count():
    async def _contains_agent(value: str) -> bool:
        await asyncio.sleep(0.01)
        return "agent" in value

    assert run_async_count(_contains_agent, ["agent-1", "task-2", "agent-3"]) == 2


def test_run_async_count_rejects_non_bool_predicate_results():
    async def _invalid(_: int) -> str:
        return "yes"

    with pytest.raises(TypeError, match="predicate must return bool"):
        run_async_count(_invalid, [1])


def test_run_async_count_supports_start_and_stop_offsets():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_count(_is_even, [2, 3, 4, 5], start=1) == 1
    assert run_async_count(_is_even, [2, 3, 4, 5], stop=2) == 1


def test_run_async_count_batched_returns_number_of_matching_items():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_count_batched(_is_even, [1, 2, 3, 4, 5], batch_size=2) == 2


def test_run_async_count_batched_rejects_non_bool_predicate_results():
    async def _invalid(_: int) -> int:
        return 1

    with pytest.raises(TypeError, match="predicate must return bool"):
        run_async_count_batched(_invalid, [1], batch_size=1)


def test_run_async_count_batched_rejects_non_positive_batch_size_for_empty_items():
    async def _always_true(_: int) -> bool:
        return True

    with pytest.raises(ValueError, match="batch_size must be greater than 0"):
        run_async_count_batched(_always_true, [], batch_size=0)


def test_run_async_count_batched_supports_start_and_stop_offsets():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_count_batched(_is_even, [2, 3, 4, 5], batch_size=2, start=1) == 1
    assert run_async_count_batched(_is_even, [2, 3, 4, 5], batch_size=2, stop=2) == 1


def test_run_async_any_returns_true_when_predicate_matches_any_item():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_any(_is_even, [1, 3, 4, 5]) is True


def test_run_async_any_returns_false_when_predicate_matches_no_items():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_any(_is_even, [1, 3, 5]) is False


def test_run_async_any_empty_input_returns_false():
    async def _always_true(_: int) -> bool:
        return True

    assert run_async_any(_always_true, []) is False


def test_run_async_any_supports_start_and_stop_offsets():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_any(_is_even, [2, 3, 5], start=1) is False
    assert run_async_any(_is_even, [1, 3, 4, 6], stop=3) is True


def test_run_async_any_rejects_invalid_offsets():
    async def _is_even(value: int) -> bool:
        return value % 2 == 0

    with pytest.raises(ValueError, match="start must be an integer"):
        run_async_any(_is_even, [1, 2, 3], start=True)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="stop cannot be negative"):
        run_async_any(_is_even, [1, 2, 3], stop=-1)


def test_run_async_any_rejects_non_bool_predicate_results():
    async def _invalid(_: int) -> str:
        return "yes"

    with pytest.raises(TypeError, match="predicate must return bool"):
        run_async_any(_invalid, [1])


def test_run_async_any_batched_returns_true_when_predicate_matches_any_item():
    async def _is_positive(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value > 0

    assert run_async_any_batched(_is_positive, [-2, -1, 0, 1], batch_size=2) is True


def test_run_async_any_batched_supports_start_and_stop_offsets():
    async def _is_positive(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value > 0

    assert (
        run_async_any_batched(
            _is_positive,
            [-1, -2, 3],
            batch_size=2,
            start=1,
        )
        is True
    )
    assert (
        run_async_any_batched(
            _is_positive,
            [-1, -2, 3],
            batch_size=2,
            stop=2,
        )
        is False
    )


def test_run_async_any_batched_rejects_non_positive_batch_size_for_empty_items():
    async def _always_true(_: int) -> bool:
        return True

    with pytest.raises(ValueError, match="batch_size must be greater than 0"):
        run_async_any_batched(_always_true, [], batch_size=0)


def test_run_async_none_returns_true_when_no_items_match():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_none(_is_even, [1, 3, 5]) is True


def test_run_async_none_returns_false_when_any_item_matches():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_none(_is_even, [1, 2, 3]) is False


def test_run_async_none_empty_input_returns_true():
    async def _always_false(_: int) -> bool:
        return False

    assert run_async_none(_always_false, []) is True


def test_run_async_none_supports_start_and_stop_offsets():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_none(_is_even, [2, 4, 5], start=2) is True
    assert run_async_none(_is_even, [1, 3, 4, 6], stop=3) is False


def test_run_async_none_rejects_non_bool_predicate_results():
    async def _invalid(_: int) -> str:
        return "yes"

    with pytest.raises(TypeError, match="predicate must return bool"):
        run_async_none(_invalid, [1])


def test_run_async_none_batched_returns_true_when_no_items_match():
    async def _is_positive(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value > 0

    assert run_async_none_batched(_is_positive, [-2, -1, 0], batch_size=2) is True


def test_run_async_none_batched_supports_start_and_stop_offsets():
    async def _is_positive(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value > 0

    assert (
        run_async_none_batched(
            _is_positive,
            [-1, 2, 3],
            batch_size=2,
            stop=1,
        )
        is True
    )
    assert (
        run_async_none_batched(
            _is_positive,
            [-1, 2, 3],
            batch_size=2,
            start=1,
        )
        is False
    )


def test_run_async_none_batched_rejects_non_positive_batch_size_for_empty_items():
    async def _always_false(_: int) -> bool:
        return False

    with pytest.raises(ValueError, match="batch_size must be greater than 0"):
        run_async_none_batched(_always_false, [], batch_size=0)


def test_run_async_all_returns_true_when_predicate_matches_all_items():
    async def _is_positive(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value > 0

    assert run_async_all(_is_positive, [1, 2, 3]) is True


def test_run_async_all_returns_false_when_any_item_fails_predicate():
    async def _is_positive(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value > 0

    assert run_async_all(_is_positive, [1, 2, 0, 3]) is False


def test_run_async_all_empty_input_returns_true():
    async def _always_false(_: int) -> bool:
        return False

    assert run_async_all(_always_false, []) is True


def test_run_async_all_supports_start_and_stop_offsets():
    async def _is_positive(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value > 0

    assert run_async_all(_is_positive, [0, 1, 2], start=1) is True
    assert run_async_all(_is_positive, [1, 2, 0], stop=2) is True


def test_run_async_all_rejects_non_bool_predicate_results():
    async def _invalid(_: int) -> int:
        return 1

    with pytest.raises(TypeError, match="predicate must return bool"):
        run_async_all(_invalid, [1])


def test_run_async_all_batched_returns_false_when_any_item_fails_predicate():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_all_batched(_is_even, [2, 4, 5, 6], batch_size=2) is False


def test_run_async_all_batched_supports_start_and_stop_offsets():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_all_batched(_is_even, [1, 2, 4], batch_size=2, start=1) is True
    assert run_async_all_batched(_is_even, [2, 4, 5], batch_size=2, stop=2) is True


def test_run_async_all_batched_rejects_invalid_offsets():
    async def _is_even(value: int) -> bool:
        return value % 2 == 0

    with pytest.raises(ValueError, match="start must be an integer"):
        run_async_all_batched(
            _is_even,
            [1, 2, 3],
            batch_size=2,
            start=True,  # type: ignore[arg-type]
        )


def test_run_async_all_batched_rejects_non_positive_batch_size_for_empty_items():
    async def _always_true(_: int) -> bool:
        return True

    with pytest.raises(ValueError, match="batch_size must be greater than 0"):
        run_async_all_batched(_always_true, [], batch_size=0)


def test_run_async_at_least_returns_true_when_threshold_is_met():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_at_least(_is_even, [1, 2, 3, 4], 2) is True
    assert run_async_at_least(_is_even, [1, 3, 5], 1) is False


def test_run_async_at_least_supports_offsets_and_zero_threshold():
    async def _is_positive(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value > 0

    assert run_async_at_least(_is_positive, [-1, 2, 3], 2, start=1) is True
    assert run_async_at_least(_is_positive, [1, 2, 3], 3, stop=2) is False
    assert run_async_at_least(_is_positive, [], 0) is True


def test_run_async_at_least_rejects_invalid_threshold():
    async def _is_even(value: int) -> bool:
        return value % 2 == 0

    with pytest.raises(
        ValueError, match="minimum_matches must be a non-negative integer"
    ):
        run_async_at_least(_is_even, [1, 2], -1)

    with pytest.raises(
        ValueError, match="minimum_matches must be a non-negative integer"
    ):
        run_async_at_least(_is_even, [1, 2], True)  # type: ignore[arg-type]


def test_run_async_at_least_batched_supports_threshold_offsets_and_batch_size():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert (
        run_async_at_least_batched(
            _is_even,
            [1, 2, 3, 4],
            2,
            batch_size=2,
            start=1,
        )
        is True
    )

    with pytest.raises(ValueError, match="batch_size must be greater than 0"):
        run_async_at_least_batched(_is_even, [1], 1, batch_size=0)


def test_run_async_at_most_returns_true_when_count_stays_under_threshold():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_at_most(_is_even, [1, 2, 3], 1) is True
    assert run_async_at_most(_is_even, [2, 4, 6], 2) is False


def test_run_async_at_most_batched_supports_offsets():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_at_most_batched(_is_even, [2, 4, 5], 1, batch_size=2, stop=2) is (
        False
    )
    assert run_async_at_most_batched(_is_even, [2, 4, 5], 1, batch_size=2, start=2) is (
        True
    )


def test_run_async_exactly_matches_required_count():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_exactly(_is_even, [1, 2, 4, 5], 2) is True
    assert run_async_exactly(_is_even, [1, 2, 4, 5], 3) is False
    assert run_async_exactly(_is_even, [], 0) is True


def test_run_async_exactly_batched_supports_offsets_and_validation():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_exactly_batched(_is_even, [1, 2, 4, 5], 2, batch_size=2) is True
    assert (
        run_async_exactly_batched(
            _is_even,
            [1, 2, 4, 5],
            1,
            batch_size=2,
            stop=2,
        )
        is True
    )

    with pytest.raises(
        ValueError, match="required_matches must be a non-negative integer"
    ):
        run_async_exactly_batched(_is_even, [1], -1, batch_size=1)


def test_run_async_exactly_rejects_non_bool_predicate_results():
    async def _invalid(_: int) -> int:
        return 1

    with pytest.raises(TypeError, match="predicate must return bool"):
        run_async_exactly(_invalid, [1], 1)


def test_run_async_index_returns_first_matching_index():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_index(_is_even, [1, 3, 4, 6]) == 2


def test_run_async_index_supports_start_offset():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_index(_is_even, [2, 4, 6], start=1) == 1


def test_run_async_index_supports_stop_offset():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_index(_is_even, [1, 3, 4, 6], stop=3) == 2


def test_run_async_index_rejects_invalid_start_offset():
    async def _is_even(value: int) -> bool:
        return value % 2 == 0

    with pytest.raises(ValueError, match="start must be an integer"):
        run_async_index(_is_even, [1, 2, 3], start=1.5)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="start must be an integer"):
        run_async_index(_is_even, [1, 2, 3], start=True)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="start cannot be negative"):
        run_async_index(_is_even, [1, 2, 3], start=-1)


def test_run_async_index_rejects_invalid_stop_offset():
    async def _is_even(value: int) -> bool:
        return value % 2 == 0

    with pytest.raises(ValueError, match="stop must be an integer when provided"):
        run_async_index(_is_even, [1, 2, 3], stop=1.5)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="stop must be an integer when provided"):
        run_async_index(_is_even, [1, 2, 3], stop=True)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="stop cannot be negative"):
        run_async_index(_is_even, [1, 2, 3], stop=-1)


@pytest.mark.asyncio
async def test_run_async_index_with_existing_event_loop_returns_first_match_index():
    async def _contains_target(value: str) -> bool:
        await asyncio.sleep(0.01)
        return "target" in value

    assert run_async_index(_contains_target, ["alpha", "target-1", "target-2"]) == 1


def test_run_async_index_returns_default_when_no_items_match():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_index(_is_even, [1, 3, 5], default=-1) == -1


def test_run_async_index_respects_start_stop_window_when_no_items_match():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_index(_is_even, [2, 4, 6], start=2, stop=2, default=-1) == -1


def test_run_async_index_raises_lookup_error_when_no_items_match_and_no_default():
    async def _always_false(_: int) -> bool:
        return False

    with pytest.raises(LookupError, match="did not match any items"):
        run_async_index(_always_false, [1, 2, 3])


def test_run_async_index_rejects_non_bool_predicate_results():
    async def _invalid(_: int) -> str:
        return "yes"

    with pytest.raises(TypeError, match="predicate must return bool"):
        run_async_index(_invalid, [1])


def test_run_async_index_batched_returns_first_match_index_across_batches():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_index_batched(_is_even, [1, 3, 5, 8], batch_size=2) == 3


def test_run_async_index_batched_supports_start_offset():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_index_batched(_is_even, [2, 4, 6], batch_size=2, start=1) == 1


def test_run_async_index_batched_supports_stop_offset():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_index_batched(_is_even, [1, 3, 4, 6], batch_size=2, stop=3) == 2


def test_run_async_index_batched_rejects_invalid_start_offset():
    async def _is_even(value: int) -> bool:
        return value % 2 == 0

    with pytest.raises(ValueError, match="start must be an integer"):
        run_async_index_batched(
            _is_even,
            [1, 2, 3],
            batch_size=2,
            start=1.5,  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="start cannot be negative"):
        run_async_index_batched(_is_even, [1, 2, 3], batch_size=2, start=-1)


def test_run_async_index_batched_rejects_invalid_stop_offset():
    async def _is_even(value: int) -> bool:
        return value % 2 == 0

    with pytest.raises(ValueError, match="stop must be an integer when provided"):
        run_async_index_batched(
            _is_even,
            [1, 2, 3],
            batch_size=2,
            stop=1.5,  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="stop cannot be negative"):
        run_async_index_batched(_is_even, [1, 2, 3], batch_size=2, stop=-1)


def test_run_async_index_batched_short_circuits_after_first_match():
    evaluated: list[int] = []

    async def _is_even(value: int) -> bool:
        evaluated.append(value)
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_index_batched(_is_even, [1, 2, 3, 4, 5], batch_size=2) == 1
    assert evaluated == [1, 2]


def test_run_async_index_batched_returns_default_when_no_items_match():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_index_batched(_is_even, [1, 3, 5], batch_size=2, default=-1) == -1


def test_run_async_index_batched_respects_start_stop_window_when_no_items_match():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert (
        run_async_index_batched(
            _is_even,
            [2, 4, 6],
            batch_size=2,
            start=2,
            stop=2,
            default=-1,
        )
        == -1
    )


def test_run_async_index_batched_raises_lookup_error_when_no_match_and_no_default():
    async def _always_false(_: int) -> bool:
        return False

    with pytest.raises(LookupError, match="did not match any items"):
        run_async_index_batched(_always_false, [1, 2, 3], batch_size=2)


def test_run_async_index_batched_rejects_non_positive_batch_size_for_empty_items():
    async def _always_true(_: int) -> bool:
        return True

    with pytest.raises(ValueError, match="batch_size must be greater than 0"):
        run_async_index_batched(_always_true, [], batch_size=0)


def test_run_async_find_returns_first_item_matching_predicate():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_find(_is_even, [1, 3, 4, 6]) == 4


def test_run_async_find_supports_start_offset():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_find(_is_even, [2, 4, 6], start=1) == 4


def test_run_async_find_supports_stop_offset():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_find(_is_even, [1, 3, 4, 6], stop=3) == 4


def test_run_async_find_rejects_invalid_start_offset():
    async def _is_even(value: int) -> bool:
        return value % 2 == 0

    with pytest.raises(ValueError, match="start must be an integer"):
        run_async_find(_is_even, [1, 2, 3], start=1.5)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="start cannot be negative"):
        run_async_find(_is_even, [1, 2, 3], start=-1)


def test_run_async_find_rejects_invalid_stop_offset():
    async def _is_even(value: int) -> bool:
        return value % 2 == 0

    with pytest.raises(ValueError, match="stop must be an integer when provided"):
        run_async_find(_is_even, [1, 2, 3], stop=1.5)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="stop cannot be negative"):
        run_async_find(_is_even, [1, 2, 3], stop=-1)


@pytest.mark.asyncio
async def test_run_async_find_with_existing_event_loop_returns_first_match():
    async def _contains_target(value: str) -> bool:
        await asyncio.sleep(0.01)
        return "target" in value

    assert run_async_find(_contains_target, ["alpha", "target-1", "target-2"]) == (
        "target-1"
    )


def test_run_async_find_returns_default_when_no_items_match():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_find(_is_even, [1, 3, 5], default=-1) == -1


def test_run_async_find_respects_start_stop_window_when_no_items_match():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_find(_is_even, [2, 4, 6], start=2, stop=2, default=-1) == -1


def test_run_async_find_raises_lookup_error_when_no_items_match_and_no_default():
    async def _always_false(_: int) -> bool:
        return False

    with pytest.raises(LookupError, match="did not match any items"):
        run_async_find(_always_false, [1, 2, 3])


def test_run_async_find_rejects_non_bool_predicate_results():
    async def _invalid(_: int) -> str:
        return "yes"

    with pytest.raises(TypeError, match="predicate must return bool"):
        run_async_find(_invalid, [1])


def test_run_async_find_batched_returns_first_match_across_batches():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_find_batched(_is_even, [1, 3, 5, 8], batch_size=2) == 8


def test_run_async_find_batched_supports_start_offset():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_find_batched(_is_even, [2, 4, 6], batch_size=2, start=1) == 4


def test_run_async_find_batched_supports_stop_offset():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_find_batched(_is_even, [1, 3, 4, 6], batch_size=2, stop=3) == 4


def test_run_async_find_batched_rejects_invalid_start_offset():
    async def _is_even(value: int) -> bool:
        return value % 2 == 0

    with pytest.raises(ValueError, match="start must be an integer"):
        run_async_find_batched(
            _is_even,
            [1, 2, 3],
            batch_size=2,
            start=True,  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="start cannot be negative"):
        run_async_find_batched(_is_even, [1, 2, 3], batch_size=2, start=-1)


def test_run_async_find_batched_rejects_invalid_stop_offset():
    async def _is_even(value: int) -> bool:
        return value % 2 == 0

    with pytest.raises(ValueError, match="stop must be an integer when provided"):
        run_async_find_batched(
            _is_even,
            [1, 2, 3],
            batch_size=2,
            stop=1.5,  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="stop cannot be negative"):
        run_async_find_batched(_is_even, [1, 2, 3], batch_size=2, stop=-1)


def test_run_async_find_batched_short_circuits_after_first_match():
    evaluated: list[int] = []

    async def _is_even(value: int) -> bool:
        evaluated.append(value)
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_find_batched(_is_even, [1, 2, 3, 4, 5], batch_size=2) == 2
    assert evaluated == [1, 2]


def test_run_async_find_batched_avoids_later_batch_errors_after_match():
    async def _predicate(value: int) -> bool:
        if value == 4:
            raise RuntimeError("should not evaluate later batches")

        await asyncio.sleep(0.01)
        return value == 2

    assert run_async_find_batched(_predicate, [1, 2, 3, 4], batch_size=2) == 2


def test_run_async_find_batched_returns_default_when_no_items_match():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert run_async_find_batched(_is_even, [1, 3, 5], batch_size=2, default=-1) == -1


def test_run_async_find_batched_respects_start_stop_window_when_no_items_match():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    assert (
        run_async_find_batched(
            _is_even,
            [2, 4, 6],
            batch_size=2,
            start=2,
            stop=2,
            default=-1,
        )
        == -1
    )


def test_run_async_find_batched_raises_lookup_error_when_no_match_and_no_default():
    async def _always_false(_: int) -> bool:
        return False

    with pytest.raises(LookupError, match="did not match any items"):
        run_async_find_batched(_always_false, [1, 2, 3], batch_size=2)


def test_run_async_find_batched_rejects_non_positive_batch_size_for_empty_items():
    async def _always_true(_: int) -> bool:
        return True

    with pytest.raises(ValueError, match="batch_size must be greater than 0"):
        run_async_find_batched(_always_true, [], batch_size=0)


def test_run_async_partition_returns_matched_and_rejected_lists():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    matched, rejected = run_async_partition(_is_even, [1, 2, 3, 4, 5])

    assert matched == [2, 4]
    assert rejected == [1, 3, 5]


@pytest.mark.asyncio
async def test_run_async_partition_with_existing_event_loop_returns_partitions():
    async def _is_agent(task_name: str) -> bool:
        await asyncio.sleep(0.01)
        return task_name.startswith("agent")

    matched, rejected = run_async_partition(
        _is_agent,
        ["agent-1", "task-2", "agent-3"],
    )

    assert matched == ["agent-1", "agent-3"]
    assert rejected == ["task-2"]


def test_run_async_partition_rejects_non_callable_predicate():
    with pytest.raises(TypeError, match="expects a callable coro_predicate"):
        run_async_partition(123, [1, 2])  # type: ignore[arg-type]


def test_run_async_partition_rejects_non_bool_predicate_results():
    async def _invalid(_: int) -> str:
        return "yes"

    with pytest.raises(TypeError, match="predicate must return bool"):
        run_async_partition(_invalid, [1])


def test_run_async_partition_supports_start_and_stop_offsets():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    matched, rejected = run_async_partition(_is_even, [2, 3, 4, 5], start=1, stop=3)

    assert matched == [4]
    assert rejected == [3]


def test_run_async_partition_batched_returns_matched_and_rejected_lists():
    async def _is_positive(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value > 0

    matched, rejected = run_async_partition_batched(
        _is_positive,
        [-2, -1, 0, 1, 2],
        batch_size=2,
    )

    assert matched == [1, 2]
    assert rejected == [-2, -1, 0]


def test_run_async_partition_batched_rejects_non_positive_batch_size_for_empty_items():
    async def _always_true(_: int) -> bool:
        return True

    with pytest.raises(ValueError, match="batch_size must be greater than 0"):
        run_async_partition_batched(_always_true, [], batch_size=0)


def test_run_async_partition_batched_supports_start_and_stop_offsets():
    async def _is_even(value: int) -> bool:
        await asyncio.sleep(0.01)
        return value % 2 == 0

    matched, rejected = run_async_partition_batched(
        _is_even,
        [2, 3, 4, 5],
        batch_size=2,
        start=1,
        stop=4,
    )

    assert matched == [4]
    assert rejected == [3, 5]


def test_run_async_group_by_groups_items_using_async_selector():
    async def _group_by_priority(task: dict[str, object]) -> str:
        await asyncio.sleep(0.01)
        return str(task["priority"])

    tasks = [
        {"id": "a", "priority": "high"},
        {"id": "b", "priority": "low"},
        {"id": "c", "priority": "high"},
    ]

    grouped = run_async_group_by(_group_by_priority, tasks)

    assert grouped == {
        "high": [tasks[0], tasks[2]],
        "low": [tasks[1]],
    }


@pytest.mark.asyncio
async def test_run_async_group_by_with_existing_event_loop_returns_groups():
    async def _group(value: str) -> str:
        await asyncio.sleep(0.01)
        return value.split("-", 1)[0]

    grouped = run_async_group_by(_group, ["agent-1", "task-2", "agent-3"])

    assert grouped == {
        "agent": ["agent-1", "agent-3"],
        "task": ["task-2"],
    }


def test_run_async_group_by_rejects_non_callable_selector():
    with pytest.raises(TypeError, match="expects a callable coro_key_selector"):
        run_async_group_by(123, [1, 2])  # type: ignore[arg-type]


def test_run_async_group_by_rejects_unhashable_selector_results():
    async def _invalid_key(value: int) -> list[int]:
        await asyncio.sleep(0.01)
        return [value]

    with pytest.raises(TypeError, match="key selector must return hashable values"):
        run_async_group_by(_invalid_key, [1])


def test_run_async_group_by_supports_start_and_stop_offsets():
    async def _group(value: int) -> str:
        await asyncio.sleep(0.01)
        return "even" if value % 2 == 0 else "odd"

    grouped = run_async_group_by(_group, [1, 2, 3, 4], start=1, stop=3)

    assert grouped == {"even": [2], "odd": [3]}


def test_run_async_group_by_batched_groups_items_across_batches():
    async def _group_by_parity(value: int) -> str:
        await asyncio.sleep(0.01)
        return "even" if value % 2 == 0 else "odd"

    grouped = run_async_group_by_batched(
        _group_by_parity,
        [1, 2, 3, 4, 5],
        batch_size=2,
    )

    assert grouped == {
        "odd": [1, 3, 5],
        "even": [2, 4],
    }


def test_run_async_group_by_batched_honors_max_concurrency_limit():
    active = 0
    max_active = 0

    async def _tracked(value: int) -> str:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return "even" if value % 2 == 0 else "odd"

    grouped = run_async_group_by_batched(
        _tracked,
        [1, 2, 3, 4],
        batch_size=4,
        max_concurrency=2,
    )

    assert grouped == {
        "odd": [1, 3],
        "even": [2, 4],
    }
    assert max_active == 2


def test_run_async_group_by_batched_rejects_non_positive_batch_size_for_empty_items():
    async def _selector(_: int) -> str:
        return "any"

    with pytest.raises(ValueError, match="batch_size must be greater than 0"):
        run_async_group_by_batched(_selector, [], batch_size=0)


def test_run_async_group_by_batched_supports_start_and_stop_offsets():
    async def _group(value: int) -> str:
        await asyncio.sleep(0.01)
        return "even" if value % 2 == 0 else "odd"

    grouped = run_async_group_by_batched(
        _group,
        [1, 2, 3, 4],
        batch_size=2,
        start=1,
        stop=4,
    )

    assert grouped == {"even": [2, 4], "odd": [3]}


def test_run_async_group_by_batched_timeout_applies_to_entire_run():
    async def _slow(_: int) -> str:
        await asyncio.sleep(0.1)
        return "slow"

    with pytest.raises(TimeoutError, match="run_async_map_batched timed out"):
        run_async_group_by_batched(_slow, [1, 2], batch_size=1, timeout=0.01)


def test_run_async_sort_orders_items_using_async_keys():
    async def _sort_key(task: dict[str, int]) -> int:
        await asyncio.sleep(0.01)
        return task["priority"]

    tasks = [
        {"id": 1, "priority": 3},
        {"id": 2, "priority": 1},
        {"id": 3, "priority": 2},
    ]

    sorted_tasks = run_async_sort(_sort_key, tasks)

    assert [task["id"] for task in sorted_tasks] == [2, 3, 1]


def test_run_async_sort_preserves_input_order_for_equal_keys():
    async def _sort_key(task: dict[str, int]) -> int:
        return task["priority"]

    tasks = [
        {"id": 1, "priority": 2},
        {"id": 2, "priority": 2},
        {"id": 3, "priority": 1},
    ]

    sorted_tasks = run_async_sort(_sort_key, tasks)

    assert [task["id"] for task in sorted_tasks] == [3, 1, 2]


def test_run_async_sort_supports_reverse_sorting():
    async def _sort_key(value: int) -> int:
        await asyncio.sleep(0.01)
        return value

    assert run_async_sort(_sort_key, [1, 3, 2], reverse=True) == [3, 2, 1]


def test_run_async_sort_validates_reverse_flag():
    async def _sort_key(value: int) -> int:
        return value

    with pytest.raises(ValueError, match="reverse must be a boolean"):
        run_async_sort(_sort_key, [1, 2, 3], reverse="yes")  # type: ignore[arg-type]


def test_run_async_sort_supports_start_and_stop_offsets():
    async def _sort_key(value: int) -> int:
        await asyncio.sleep(0.01)
        return value

    assert run_async_sort(_sort_key, [4, 1, 3, 2], start=1) == [1, 2, 3]
    assert run_async_sort(_sort_key, [4, 1, 3, 2], stop=3) == [1, 3, 4]


def test_run_async_sort_rejects_non_comparable_keys():
    async def _invalid_key(value: int) -> dict[str, int]:
        return {"value": value}

    with pytest.raises(TypeError, match="must return mutually comparable values"):
        run_async_sort(_invalid_key, [1, 2, 3])


def test_run_async_sort_batched_orders_items_across_batches():
    async def _sort_key(value: int) -> int:
        await asyncio.sleep(0.01)
        return abs(value)

    sorted_values = run_async_sort_batched(_sort_key, [3, -1, 2, -4], batch_size=2)

    assert sorted_values == [-1, 2, 3, -4]


def test_run_async_sort_batched_validates_reverse_flag():
    async def _sort_key(value: int) -> int:
        return value

    with pytest.raises(ValueError, match="reverse must be a boolean"):
        run_async_sort_batched(
            _sort_key,
            [1, 2, 3],
            batch_size=2,
            reverse=1,  # type: ignore[arg-type]
        )


def test_run_async_sort_batched_rejects_non_positive_batch_size_for_empty_items():
    async def _sort_key(value: int) -> int:
        return value

    with pytest.raises(ValueError, match="batch_size must be greater than 0"):
        run_async_sort_batched(_sort_key, [], batch_size=0)


def test_run_async_sort_batched_supports_start_and_stop_offsets():
    async def _sort_key(value: int) -> int:
        await asyncio.sleep(0.01)
        return value

    assert run_async_sort_batched(
        _sort_key,
        [4, 1, 3, 2],
        batch_size=2,
        start=1,
    ) == [1, 2, 3]
    assert run_async_sort_batched(
        _sort_key,
        [4, 1, 3, 2],
        batch_size=2,
        stop=3,
    ) == [1, 3, 4]


def test_run_async_sort_batched_rejects_non_comparable_keys():
    async def _invalid_key(value: int) -> dict[str, int]:
        return {"value": value}

    with pytest.raises(TypeError, match="must return mutually comparable values"):
        run_async_sort_batched(_invalid_key, [1, 2], batch_size=1)


def test_run_async_reduce_without_initial_uses_first_item_as_accumulator():
    async def _add(accumulator: int, value: int) -> int:
        await asyncio.sleep(0.01)
        return accumulator + value

    assert run_async_reduce(_add, [1, 2, 3, 4]) == 10


@pytest.mark.asyncio
async def test_run_async_reduce_with_existing_event_loop_returns_value():
    async def _concat(accumulator: str, value: str) -> str:
        await asyncio.sleep(0.01)
        return f"{accumulator}-{value}"

    assert run_async_reduce(_concat, ["a", "b", "c"], initial="start") == "start-a-b-c"


def test_run_async_reduce_supports_initial_value_for_empty_iterables():
    async def _add(accumulator: int, value: int) -> int:
        await asyncio.sleep(0.01)
        return accumulator + value

    assert run_async_reduce(_add, [], initial=42) == 42


def test_run_async_reduce_raises_lookup_error_for_empty_iterable_without_initial():
    async def _add(accumulator: int, value: int) -> int:
        return accumulator + value

    with pytest.raises(
        LookupError,
        match="cannot reduce an empty iterable",
    ):
        run_async_reduce(_add, [])


def test_run_async_reduce_rejects_non_callable_reducer():
    with pytest.raises(TypeError, match="expects a callable coro_reducer"):
        run_async_reduce(123, [1, 2, 3])  # type: ignore[arg-type]


def test_run_async_reduce_rejects_non_awaitable_reducer_results():
    def _sync_add(accumulator: int, value: int) -> int:
        return accumulator + value

    with pytest.raises(TypeError, match="must return an awaitable"):
        run_async_reduce(_sync_add, [1, 2, 3])


def test_run_async_reduce_timeout_applies_to_entire_reduction():
    async def _slow_add(accumulator: int, value: int) -> int:
        await asyncio.sleep(0.03)
        return accumulator + value

    with pytest.raises(TimeoutError, match="run_async_reduce timed out"):
        run_async_reduce(_slow_add, [1, 2, 3], initial=0, timeout=0.05)


def test_run_async_starmap_supports_positional_argument_groups():
    async def _add(left: int, right: int) -> int:
        await asyncio.sleep(0.01)
        return left + right

    result = run_async_starmap(_add, [(1, 2), (20, 22)])

    assert result == [3, 42]


@pytest.mark.asyncio
async def test_run_async_starmap_with_existing_event_loop_returns_results():
    async def _format(prefix: str, index: int) -> str:
        await asyncio.sleep(0.01)
        return f"{prefix}-{index}"

    result = run_async_starmap(_format, [("task", 1), ("task", 2)])

    assert result == ["task-1", "task-2"]


def test_run_async_starmap_supports_keyword_argument_mappings():
    async def _label(*, prefix: str, value: int) -> str:
        await asyncio.sleep(0.01)
        return f"{prefix}:{value}"

    result = run_async_starmap(
        _label,
        [
            {"prefix": "item", "value": 1},
            {"value": 2, "prefix": "item"},
        ],
    )

    assert result == ["item:1", "item:2"]


def test_run_async_starmap_honors_max_concurrency_limit():
    active = 0
    max_active = 0

    async def _tracked(left: int, right: int) -> int:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return left + right

    result = run_async_starmap(
        _tracked,
        [(1, 1), (2, 2), (3, 3), (4, 4)],
        max_concurrency=2,
    )

    assert result == [2, 4, 6, 8]
    assert max_active == 2


def test_run_async_starmap_rejects_invalid_item_shapes():
    async def _noop(*args: int) -> int:
        return len(args)

    with pytest.raises(
        TypeError,
        match="items must be iterables of args or mappings of kwargs",
    ):
        run_async_starmap(_noop, [123])  # type: ignore[list-item]


def test_run_async_starmap_rejects_non_awaitable_factory_results():
    def _sync_add(left: int, right: int) -> int:
        return left + right

    with pytest.raises(TypeError, match="must return an awaitable"):
        run_async_starmap(_sync_add, [(1, 2)])


def test_run_async_starmap_batched_returns_ordered_results_across_batches():
    async def _add(left: int, right: int) -> int:
        await asyncio.sleep(0.01)
        return left + right

    result = run_async_starmap_batched(
        _add,
        [(1, 2), {"left": 20, "right": 22}, (3, 4)],
        batch_size=2,
    )

    assert result == [3, 42, 7]


@pytest.mark.asyncio
async def test_run_async_starmap_batched_with_existing_event_loop_returns_results():
    async def _format(prefix: str, index: int) -> str:
        await asyncio.sleep(0.01)
        return f"{prefix}-{index}"

    result = run_async_starmap_batched(
        _format,
        [("task", 1), {"prefix": "task", "index": 2}],
        batch_size=1,
    )

    assert result == ["task-1", "task-2"]


def test_run_async_starmap_batched_can_return_exceptions_when_requested():
    async def _explode(left: int, right: int) -> int:
        if left == 2:
            raise ValueError("bad")
        return left + right

    result = run_async_starmap_batched(
        _explode,
        [(1, 1), (2, 2), (3, 3)],
        batch_size=2,
        return_exceptions=True,
    )

    assert result[0] == 2
    assert isinstance(result[1], ValueError)
    assert str(result[1]) == "bad"
    assert result[2] == 6


def test_run_async_starmap_batched_rejects_non_positive_batch_size():
    async def _noop(*args: int) -> int:
        return len(args)

    with pytest.raises(ValueError, match="batch_size must be greater than 0"):
        run_async_starmap_batched(_noop, [(1,)], batch_size=0)


def test_run_async_starmap_batched_rejects_invalid_item_shapes():
    async def _noop(*args: int) -> int:
        return len(args)

    with pytest.raises(
        TypeError,
        match="items must be iterables of args or mappings of kwargs",
    ):
        run_async_starmap_batched(_noop, [123], batch_size=1)  # type: ignore[list-item]


def test_run_async_starmap_batched_rejects_non_awaitable_factory_results():
    def _sync_add(left: int, right: int) -> int:
        return left + right

    with pytest.raises(TypeError, match="must return an awaitable"):
        run_async_starmap_batched(_sync_add, [(1, 2)], batch_size=1)


def test_run_async_starmap_batched_honors_max_concurrency_limit():
    active = 0
    max_active = 0

    async def _tracked(left: int, right: int) -> int:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return left + right

    result = run_async_starmap_batched(
        _tracked,
        [(1, 1), (2, 2), (3, 3), (4, 4)],
        batch_size=4,
        max_concurrency=2,
    )

    assert result == [2, 4, 6, 8]
    assert max_active == 2


def test_run_async_starmap_batched_timeout_applies_to_entire_run():
    async def _sleep(left: int, right: int) -> int:
        await asyncio.sleep(0.03)
        return left + right

    with pytest.raises(TimeoutError, match="run_async_starmap_batched timed out"):
        run_async_starmap_batched(
            _sleep, [(1, 1), (2, 2), (3, 3)], batch_size=1, timeout=0.05
        )
