"""Tests for async runner utility."""

import asyncio

import pytest

from app.core.async_runner import (
    run_async,
    run_async_dict,
    run_async_many,
    run_async_map,
    run_async_starmap,
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
