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
