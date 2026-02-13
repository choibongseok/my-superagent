"""Tests for async runner utility."""

import asyncio

import pytest

from app.core.async_runner import run_async


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
