"""Tests for async runner utility."""

import asyncio

import pytest

from app.core.async_runner import run_async, run_async_dict, run_async_many


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


def test_run_async_dict_empty_input_returns_empty_dict():
    assert run_async_dict({}) == {}
