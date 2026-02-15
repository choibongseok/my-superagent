"""Tests for Redis cache key utilities and cache decorators."""

import pytest

from app.core.cache import cache, cache_key, cached


def test_cache_key_normalizes_nested_mappings_deterministically():
    left_payload = {
        "filters": {
            "region": "apac",
            "team": ["platform", "search"],
        },
        "limit": 10,
    }
    right_payload = {
        "limit": 10,
        "filters": {
            "team": ["platform", "search"],
            "region": "apac",
        },
    }

    assert cache_key(left_payload) == cache_key(right_payload)


def test_cache_key_distinguishes_string_and_numeric_scalars():
    assert cache_key("1") != cache_key(1)


@pytest.mark.asyncio
async def test_cached_auto_skips_bound_instance_for_default_key_builder(monkeypatch):
    cached_values: dict[str, int] = {}
    key_events: list[tuple[str, str]] = []

    async def fake_get(key: str):
        key_events.append(("get", key))
        return cached_values.get(key)

    async def fake_set(key: str, value: int, ttl=None):
        key_events.append(("set", key))
        cached_values[key] = value
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)

    class ExampleService:
        def __init__(self):
            self.calls = 0

        @cached(prefix="example")
        async def compute(self, value: int) -> int:
            self.calls += 1
            return value * 2

    first = ExampleService()
    second = ExampleService()

    assert await first.compute(21) == 42
    assert await second.compute(21) == 42

    assert first.calls == 1
    assert second.calls == 0

    set_events = [event for event in key_events if event[0] == "set"]
    get_keys = {key for event, key in key_events if event == "get"}

    assert len(set_events) == 1
    assert len(get_keys) == 1


@pytest.mark.asyncio
async def test_cached_can_include_instance_identity_when_requested(monkeypatch):
    cached_values: dict[str, int] = {}

    async def fake_get(key: str):
        return cached_values.get(key)

    async def fake_set(key: str, value: int, ttl=None):
        cached_values[key] = value
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)

    class ExampleService:
        def __init__(self):
            self.calls = 0

        @cached(prefix="example", skip_first_arg=False)
        async def compute(self, value: int) -> int:
            self.calls += 1
            return value * 2

    first = ExampleService()
    second = ExampleService()

    assert await first.compute(21) == 42
    assert await second.compute(21) == 42

    assert first.calls == 1
    assert second.calls == 1
    assert len(cached_values) == 2


def test_cached_rejects_invalid_skip_first_arg_flag():
    with pytest.raises(ValueError, match="skip_first_arg must be a boolean"):
        cached(prefix="example", skip_first_arg="yes")
