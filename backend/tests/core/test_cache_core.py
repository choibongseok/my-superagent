"""Tests for Redis cache key utilities and cache decorators."""

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from app.core.cache import cache, cache_key, cached, invalidate_cache
from app.core.config import settings


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


def test_cache_key_normalizes_binary_payloads_across_buffer_types():
    payload = b"\x00\xffagenthq"

    assert cache_key(payload) == cache_key(bytearray(payload))
    assert cache_key(payload) == cache_key(memoryview(payload))


def test_cache_key_distinguishes_different_binary_payloads():
    assert cache_key(memoryview(b"alpha")) != cache_key(memoryview(b"beta"))


def test_cache_key_normalizes_dataclass_instances_deterministically():
    @dataclass
    class Filters:
        region: str
        team: list[str]

    @dataclass
    class Query:
        filters: Filters
        limit: int

    left = Query(filters=Filters(region="apac", team=["platform", "search"]), limit=10)
    right = Query(
        filters=Filters(team=["platform", "search"], region="apac"),
        limit=10,
    )

    assert cache_key(left) == cache_key(right)


def test_cache_key_uses_model_dump_payloads_when_available():
    class FakeModel:
        def __init__(self, payload):
            self._payload = payload

        def model_dump(self, mode="python"):
            assert mode == "json"
            return self._payload

    left = FakeModel(
        {
            "filters": {"region": "apac", "team": ["platform", "search"]},
            "limit": 10,
        }
    )
    right = FakeModel(
        {
            "limit": 10,
            "filters": {"team": ["platform", "search"], "region": "apac"},
        }
    )

    assert cache_key(left) == cache_key(right)


@pytest.mark.asyncio
async def test_cached_supports_sync_callables(monkeypatch):
    cached_values: dict[str, int] = {}

    async def fake_get(key: str):
        return cached_values.get(key)

    async def fake_set(key: str, value: int, ttl=None):
        cached_values[key] = value
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)

    calls = {"count": 0}

    @cached(prefix="example")
    def compute(value: int) -> int:
        calls["count"] += 1
        return value * 2

    assert await compute(21) == 42
    assert await compute(21) == 42

    assert calls["count"] == 1
    assert cached_values == {"example:21": 42}


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


def test_cached_rejects_invalid_cache_control_flag_configuration():
    with pytest.raises(ValueError, match="refresh_flag must be a string"):
        cached(prefix="example", refresh_flag=123)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="disable_flag cannot be empty"):
        cached(prefix="example", disable_flag="   ")

    with pytest.raises(
        ValueError,
        match="refresh_flag and disable_flag must be different values",
    ):
        cached(prefix="example", refresh_flag="cache", disable_flag="cache")


@pytest.mark.asyncio
async def test_cached_refresh_flag_bypasses_read_and_updates_cached_value(monkeypatch):
    cached_values: dict[str, int] = {}
    events: list[tuple[str, str, int | None]] = []

    async def fake_get(key: str):
        events.append(("get", key, None))
        return cached_values.get(key)

    async def fake_set(key: str, value: int, ttl=None):
        events.append(("set", key, value))
        cached_values[key] = value
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)

    calls = {"count": 0}

    @cached(prefix="example")
    async def compute(value: int) -> int:
        calls["count"] += 1
        return value + calls["count"]

    assert await compute(10) == 11
    assert await compute(10) == 11
    assert await compute(10, refresh_cache=True) == 12
    assert await compute(10) == 12

    assert calls["count"] == 2

    get_events = [event for event in events if event[0] == "get"]
    set_events = [event for event in events if event[0] == "set"]

    # First call misses, second and fourth hit, refresh call skips read.
    assert len(get_events) == 3
    assert len(set_events) == 2


@pytest.mark.asyncio
async def test_cached_disable_flag_bypasses_cache_for_single_call(monkeypatch):
    cached_values: dict[str, int] = {}

    async def fake_get(key: str):
        return cached_values.get(key)

    async def fake_set(key: str, value: int, ttl=None):
        cached_values[key] = value
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)

    calls = {"count": 0}

    @cached(prefix="example")
    async def compute(value: int) -> int:
        calls["count"] += 1
        return value + calls["count"]

    assert await compute(10) == 11
    assert await compute(10, disable_cache=True) == 12
    assert await compute(10) == 11

    assert calls["count"] == 2
    assert len(cached_values) == 1


@pytest.mark.asyncio
async def test_cached_supports_custom_cache_control_flag_names(monkeypatch):
    cached_values: dict[str, int] = {}

    async def fake_get(key: str):
        return cached_values.get(key)

    async def fake_set(key: str, value: int, ttl=None):
        cached_values[key] = value
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)

    calls = {"count": 0}

    @cached(
        prefix="example",
        refresh_flag="force_refresh",
        disable_flag="skip_cache",
    )
    async def compute(value: int) -> int:
        calls["count"] += 1
        return value + calls["count"]

    assert await compute(10) == 11
    assert await compute(10, force_refresh=True) == 12
    assert await compute(10, skip_cache=True) == 13
    assert await compute(10) == 12

    assert calls["count"] == 3


@pytest.mark.asyncio
async def test_cached_rejects_non_boolean_cache_control_flags(monkeypatch):
    async def fake_get(_: str):
        return None

    async def fake_set(_: str, __: int, ttl=None):
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)

    @cached(prefix="example")
    async def compute(value: int) -> int:
        return value

    with pytest.raises(ValueError, match="refresh_cache must be a boolean"):
        await compute(1, refresh_cache="yes")

    with pytest.raises(ValueError, match="disable_cache must be a boolean"):
        await compute(1, disable_cache="yes")


def test_cached_rejects_non_callable_cache_condition():
    with pytest.raises(ValueError, match="cache_condition must be callable"):
        cached(prefix="example", cache_condition="not-callable")  # type: ignore[arg-type]


def test_cached_rejects_invalid_coalesce_inflight_flag():
    with pytest.raises(ValueError, match="coalesce_inflight must be a boolean"):
        cached(prefix="example", coalesce_inflight="yes")  # type: ignore[arg-type]


def test_cached_rejects_invalid_cache_none_flag():
    with pytest.raises(ValueError, match="cache_none must be a boolean"):
        cached(prefix="example", cache_none="yes")  # type: ignore[arg-type]


def test_cached_rejects_invalid_ignored_kwargs_configuration():
    with pytest.raises(
        ValueError,
        match="ignored_kwargs must be an iterable of non-empty strings",
    ):
        cached(prefix="example", ignored_kwargs="trace_id")

    with pytest.raises(
        ValueError,
        match="ignored_kwargs must be an iterable of non-empty strings",
    ):
        cached(prefix="example", ignored_kwargs=["trace_id", "  "])

    with pytest.raises(
        ValueError,
        match="ignored_kwargs must be an iterable of non-empty strings",
    ):
        cached(prefix="example", ignored_kwargs=["trace_id", 123])


def test_cached_rejects_invalid_ignored_arg_positions_configuration():
    with pytest.raises(
        ValueError,
        match="ignored_arg_positions must be an iterable of non-negative integers",
    ):
        cached(prefix="example", ignored_arg_positions="1")

    with pytest.raises(
        ValueError,
        match="ignored_arg_positions must be an iterable of non-negative integers",
    ):
        cached(prefix="example", ignored_arg_positions=[-1])

    with pytest.raises(
        ValueError,
        match="ignored_arg_positions must be an iterable of non-negative integers",
    ):
        cached(prefix="example", ignored_arg_positions=[True])


@pytest.mark.asyncio
async def test_cached_can_ignore_selected_kwargs_in_cache_key(monkeypatch):
    cached_values: dict[str, str] = {}

    async def fake_get(key: str):
        return cached_values.get(key)

    async def fake_set(key: str, value: str, ttl=None):
        cached_values[key] = value
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)

    calls = {"count": 0}

    @cached(prefix="example", ignored_kwargs=["trace_id"])
    async def compute(value: int, *, trace_id: str) -> str:
        calls["count"] += 1
        return f"{value}:{trace_id}:{calls['count']}"

    assert await compute(10, trace_id="first") == "10:first:1"
    assert await compute(10, trace_id="second") == "10:first:1"

    assert calls["count"] == 1
    assert cached_values == {"example:10": "10:first:1"}


@pytest.mark.asyncio
async def test_cached_ignored_kwargs_still_reach_function_when_recomputing(monkeypatch):
    cached_values: dict[str, str] = {}

    async def fake_get(key: str):
        return cached_values.get(key)

    async def fake_set(key: str, value: str, ttl=None):
        cached_values[key] = value
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)

    @cached(prefix="example", ignored_kwargs=["trace_id"])
    async def compute(value: int, *, trace_id: str) -> str:
        return f"{value}:{trace_id}"

    assert await compute(10, trace_id="first") == "10:first"
    assert await compute(10, trace_id="second", refresh_cache=True) == "10:second"
    assert await compute(10, trace_id="third") == "10:second"


@pytest.mark.asyncio
async def test_cached_can_ignore_selected_positional_args_in_cache_key(monkeypatch):
    cached_values: dict[str, str] = {}

    async def fake_get(key: str):
        return cached_values.get(key)

    async def fake_set(key: str, value: str, ttl=None):
        cached_values[key] = value
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)

    calls = {"count": 0}

    @cached(prefix="example", ignored_arg_positions=[1])
    async def compute(value: int, trace_id: str) -> str:
        calls["count"] += 1
        return f"{value}:{trace_id}:{calls['count']}"

    assert await compute(10, "first") == "10:first:1"
    assert await compute(10, "second") == "10:first:1"

    assert calls["count"] == 1
    assert cached_values == {"example:10": "10:first:1"}


@pytest.mark.asyncio
async def test_cached_ignored_arg_positions_apply_after_skip_first_arg(monkeypatch):
    cached_values: dict[str, str] = {}

    async def fake_get(key: str):
        return cached_values.get(key)

    async def fake_set(key: str, value: str, ttl=None):
        cached_values[key] = value
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)

    class ExampleService:
        @cached(prefix="example", ignored_arg_positions=[1])
        async def compute(self, value: int, trace_id: str) -> str:
            return f"{value}:{trace_id}"

    service = ExampleService()

    assert await service.compute(10, "first") == "10:first"
    assert await service.compute(10, "second") == "10:first"

    assert cached_values == {"example:10": "10:first"}


@pytest.mark.asyncio
async def test_cached_cache_condition_can_skip_writing_specific_results(monkeypatch):
    cached_values: dict[str, int | None] = {}

    async def fake_get(key: str):
        return cached_values.get(key)

    async def fake_set(key: str, value: int | None, ttl=None):
        cached_values[key] = value
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)

    calls = {"count": 0}

    @cached(prefix="example", cache_condition=lambda value: value is not None)
    async def compute(value: int) -> int | None:
        calls["count"] += 1
        if calls["count"] == 1:
            return None
        return value + calls["count"]

    assert await compute(10) is None
    assert await compute(10) == 12
    assert await compute(10) == 12

    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_cached_cache_condition_must_return_boolean(monkeypatch):
    async def fake_get(_: str):
        return None

    async def fake_set(_: str, __: int, ttl=None):
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)

    @cached(prefix="example", cache_condition=lambda _: "yes")
    async def compute(value: int) -> int:
        return value

    with pytest.raises(ValueError, match="cache_condition must return a boolean"):
        await compute(1)


@pytest.mark.asyncio
async def test_cached_does_not_cache_none_results_by_default(monkeypatch):
    cached_values: dict[str, int | None] = {}

    async def fake_get(key: str):
        return cached_values[key] if key in cached_values else None

    async def fake_set(key: str, value: int | None, ttl=None):
        cached_values[key] = value
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)

    calls = {"count": 0}

    @cached(prefix="example")
    async def compute(value: int) -> int | None:
        calls["count"] += 1
        return None

    assert await compute(10) is None
    assert await compute(10) is None

    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_cached_can_cache_none_results_when_enabled(monkeypatch):
    cached_values: dict[str, Any] = {}

    async def fake_get(key: str):
        return cached_values[key] if key in cached_values else None

    async def fake_set(key: str, value: Any, ttl=None):
        cached_values[key] = value
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)

    calls = {"count": 0}

    @cached(prefix="example", cache_none=True)
    async def compute(value: int) -> int | None:
        calls["count"] += 1
        return None

    assert await compute(10) is None
    assert await compute(10) is None

    assert calls["count"] == 1
    assert cached_values == {
        "example:10": {
            "__openclaw_cached_payload_v1__": True,
            "value": None,
        }
    }


@pytest.mark.asyncio
async def test_cached_supports_async_key_builder(monkeypatch):
    cached_values: dict[str, int] = {}

    async def fake_get(key: str):
        return cached_values.get(key)

    async def fake_set(key: str, value: int, ttl=None):
        cached_values[key] = value
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)

    calls = {"count": 0}

    async def build_key(value: int) -> str:
        return f"value:{value}"

    @cached(prefix="example", key_builder=build_key)
    async def compute(value: int) -> int:
        calls["count"] += 1
        return value * 2

    assert await compute(21) == 42
    assert await compute(21) == 42

    assert calls["count"] == 1
    assert cached_values == {"example:value:21": 42}


@pytest.mark.asyncio
async def test_cached_supports_async_cache_condition(monkeypatch):
    cached_values: dict[str, int] = {}

    async def fake_get(key: str):
        return cached_values.get(key)

    async def fake_set(key: str, value: int, ttl=None):
        cached_values[key] = value
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)

    calls = {"count": 0}

    async def should_cache(value: int) -> bool:
        return value % 2 == 0

    @cached(prefix="example", cache_condition=should_cache)
    async def compute(value: int) -> int:
        calls["count"] += 1
        return value

    assert await compute(1) == 1
    assert await compute(1) == 1
    assert await compute(2) == 2
    assert await compute(2) == 2

    assert calls["count"] == 3
    assert cached_values == {"example:2": 2}


@pytest.mark.asyncio
async def test_cached_async_cache_condition_must_return_boolean(monkeypatch):
    async def fake_get(_: str):
        return None

    async def fake_set(_: str, __: int, ttl=None):
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)

    async def invalid_condition(_: int) -> str:
        return "yes"

    @cached(prefix="example", cache_condition=invalid_condition)
    async def compute(value: int) -> int:
        return value

    with pytest.raises(ValueError, match="cache_condition must return a boolean"):
        await compute(1)


@pytest.mark.asyncio
async def test_cached_coalesces_concurrent_calls_for_the_same_key(monkeypatch):
    cached_values: dict[str, int] = {}

    async def fake_get(key: str):
        return cached_values.get(key)

    async def fake_set(key: str, value: int, ttl=None):
        cached_values[key] = value
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)

    calls = {"count": 0}

    @cached(prefix="example")
    async def compute(value: int) -> int:
        calls["count"] += 1
        await asyncio.sleep(0.01)
        return value * 2

    first, second, third = await asyncio.gather(
        compute(21),
        compute(21),
        compute(21),
    )

    assert (first, second, third) == (42, 42, 42)
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_cached_can_disable_inflight_coalescing(monkeypatch):
    cached_values: dict[str, int] = {}

    async def fake_get(key: str):
        return cached_values.get(key)

    async def fake_set(key: str, value: int, ttl=None):
        cached_values[key] = value
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)

    calls = {"count": 0}

    @cached(prefix="example", coalesce_inflight=False)
    async def compute(value: int) -> int:
        calls["count"] += 1
        await asyncio.sleep(0.01)
        return value * 2

    first, second = await asyncio.gather(compute(21), compute(21))

    assert (first, second) == (42, 42)
    assert calls["count"] == 2


def test_cached_rejects_invalid_max_key_length_configuration():
    with pytest.raises(ValueError, match="max_key_length must be an integer"):
        cached(prefix="example", max_key_length="64")

    with pytest.raises(ValueError, match="max_key_length is too small for hashed keys"):
        cached(prefix="example", max_key_length=20)


@pytest.mark.asyncio
async def test_cached_hashes_keys_that_exceed_max_length(monkeypatch):
    cached_values: dict[str, str] = {}
    observed_keys: list[str] = []

    async def fake_get(key: str):
        observed_keys.append(key)
        return cached_values.get(key)

    async def fake_set(key: str, value: str, ttl=None):
        observed_keys.append(key)
        cached_values[key] = value
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)

    calls = {"count": 0}

    @cached(prefix="example", max_key_length=36)
    async def compute(payload: str) -> str:
        calls["count"] += 1
        return f"{payload}:{calls['count']}"

    long_payload = "x" * 200

    first = await compute(long_payload)
    second = await compute(long_payload)

    assert first == second
    assert calls["count"] == 1
    assert len(cached_values) == 1

    key = next(iter(cached_values))
    assert key.startswith("example:h:")
    assert len(key) <= 36
    assert all(observed_key == key for observed_key in observed_keys)


@pytest.mark.asyncio
async def test_cached_keeps_short_keys_when_max_key_length_is_configured(monkeypatch):
    cached_values: dict[str, int] = {}

    async def fake_get(key: str):
        return cached_values.get(key)

    async def fake_set(key: str, value: int, ttl=None):
        cached_values[key] = value
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)

    @cached(prefix="example", max_key_length=64)
    async def compute(value: int) -> int:
        return value * 2

    assert await compute(21) == 42
    assert await compute(21) == 42

    assert cached_values == {"example:21": 42}


def test_cached_rejects_invalid_key_version_configuration():
    with pytest.raises(
        ValueError,
        match="key_version must be a non-empty string or integer",
    ):
        cached(prefix="example", key_version="   ")

    with pytest.raises(
        ValueError,
        match="key_version must be a non-empty string or integer",
    ):
        cached(prefix="example", key_version=True)


@pytest.mark.asyncio
async def test_cached_namespaces_keys_with_key_version(monkeypatch):
    cached_values: dict[str, int] = {}

    async def fake_get(key: str):
        return cached_values.get(key)

    async def fake_set(key: str, value: int, ttl=None):
        cached_values[key] = value
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)

    calls = {"count": 0}

    @cached(prefix="example", key_version="2026-02")
    async def compute(value: int) -> int:
        calls["count"] += 1
        return value * 2

    assert await compute(21) == 42
    assert await compute(21) == 42

    assert calls["count"] == 1
    assert cached_values == {"example:v2026-02:21": 42}


@pytest.mark.asyncio
async def test_cached_isolates_versions_between_namespaces(monkeypatch):
    cached_values: dict[str, int] = {}

    async def fake_get(key: str):
        return cached_values.get(key)

    async def fake_set(key: str, value: int, ttl=None):
        cached_values[key] = value
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)

    @cached(prefix="example", key_version=1)
    async def compute_v1(value: int) -> int:
        return value + 1

    @cached(prefix="example", key_version=2)
    async def compute_v2(value: int) -> int:
        return value + 2

    assert await compute_v1(10) == 11
    assert await compute_v2(10) == 12

    assert cached_values == {
        "example:v1:10": 11,
        "example:v2:10": 12,
    }


@pytest.mark.asyncio
async def test_invalidate_cache_supports_key_version_namespace(monkeypatch):
    deleted_keys: list[str] = []

    async def fake_delete(key: str):
        deleted_keys.append(key)
        return True

    monkeypatch.setattr(cache, "delete", fake_delete)

    await invalidate_cache("example", 21, key_version="2026-02")

    assert deleted_keys == ["example:v2026-02:21"]


@pytest.mark.asyncio
async def test_invalidate_cache_hashes_key_when_max_key_length_is_configured(
    monkeypatch,
):
    deleted_keys: list[str] = []

    async def fake_delete(key: str):
        deleted_keys.append(key)
        return True

    monkeypatch.setattr(cache, "delete", fake_delete)

    await invalidate_cache("example", "x" * 200, max_key_length=36)

    assert len(deleted_keys) == 1
    assert deleted_keys[0].startswith("example:h:")
    assert len(deleted_keys[0]) <= 36


@pytest.mark.asyncio
async def test_invalidate_cache_rejects_invalid_max_key_length_configuration():
    with pytest.raises(ValueError, match="max_key_length must be an integer"):
        await invalidate_cache("example", 1, max_key_length="64")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="max_key_length is too small for hashed keys"):
        await invalidate_cache("example", 1, max_key_length=20)


@pytest.mark.asyncio
async def test_invalidate_cache_supports_custom_key_builder(monkeypatch):
    deleted_keys: list[str] = []

    async def fake_delete(key: str):
        deleted_keys.append(key)
        return True

    monkeypatch.setattr(cache, "delete", fake_delete)

    await invalidate_cache(
        "example",
        21,
        key_builder=lambda value: f"value:{value}",
    )

    assert deleted_keys == ["example:value:21"]


@pytest.mark.asyncio
async def test_invalidate_cache_supports_async_key_builder(monkeypatch):
    deleted_keys: list[str] = []

    async def fake_delete(key: str):
        deleted_keys.append(key)
        return True

    monkeypatch.setattr(cache, "delete", fake_delete)

    async def build_key(value: int) -> str:
        return f"value:{value}"

    await invalidate_cache("example", 21, key_builder=build_key)

    assert deleted_keys == ["example:value:21"]


@pytest.mark.asyncio
async def test_invalidate_cache_can_ignore_selected_kwargs(monkeypatch):
    deleted_keys: list[str] = []

    async def fake_delete(key: str):
        deleted_keys.append(key)
        return True

    monkeypatch.setattr(cache, "delete", fake_delete)

    await invalidate_cache(
        "example",
        21,
        trace_id="abc123",
        ignored_kwargs=["trace_id"],
    )

    assert deleted_keys == ["example:21"]


@pytest.mark.asyncio
async def test_invalidate_cache_can_ignore_selected_positional_args(monkeypatch):
    deleted_keys: list[str] = []

    async def fake_delete(key: str):
        deleted_keys.append(key)
        return True

    monkeypatch.setattr(cache, "delete", fake_delete)

    await invalidate_cache(
        "example",
        21,
        "trace-a",
        ignored_arg_positions=[1],
    )

    assert deleted_keys == ["example:21"]


@pytest.mark.asyncio
async def test_invalidate_cache_can_skip_first_arg_when_requested(monkeypatch):
    deleted_keys: list[str] = []

    async def fake_delete(key: str):
        deleted_keys.append(key)
        return True

    monkeypatch.setattr(cache, "delete", fake_delete)

    class ExampleService:
        pass

    service = ExampleService()

    await invalidate_cache(
        "example",
        service,
        21,
        skip_first_arg=True,
    )

    assert deleted_keys == ["example:21"]


@pytest.mark.asyncio
async def test_invalidate_cache_applies_ignored_positions_after_skip_first_arg(
    monkeypatch,
):
    deleted_keys: list[str] = []

    async def fake_delete(key: str):
        deleted_keys.append(key)
        return True

    monkeypatch.setattr(cache, "delete", fake_delete)

    class ExampleService:
        pass

    service = ExampleService()

    await invalidate_cache(
        "example",
        service,
        21,
        "trace-a",
        skip_first_arg=True,
        ignored_arg_positions=[1],
    )

    assert deleted_keys == ["example:21"]


@pytest.mark.asyncio
async def test_invalidate_cache_rejects_invalid_key_builder_configuration():
    with pytest.raises(ValueError, match="key_builder must be callable"):
        await invalidate_cache("example", 21, key_builder="value:21")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_invalidate_cache_rejects_invalid_ignored_kwargs_configuration():
    with pytest.raises(
        ValueError,
        match="ignored_kwargs must be an iterable of non-empty strings",
    ):
        await invalidate_cache("example", 21, ignored_kwargs="trace_id")

    with pytest.raises(
        ValueError,
        match="ignored_kwargs must be an iterable of non-empty strings",
    ):
        await invalidate_cache("example", 21, ignored_kwargs=["trace_id", "  "])


@pytest.mark.asyncio
async def test_invalidate_cache_rejects_invalid_ignored_arg_positions_configuration():
    with pytest.raises(
        ValueError,
        match="ignored_arg_positions must be an iterable of non-negative integers",
    ):
        await invalidate_cache("example", 21, "trace", ignored_arg_positions="1")

    with pytest.raises(
        ValueError,
        match="ignored_arg_positions must be an iterable of non-negative integers",
    ):
        await invalidate_cache("example", 21, "trace", ignored_arg_positions=[-1])


@pytest.mark.asyncio
async def test_invalidate_cache_rejects_invalid_skip_first_arg_configuration():
    with pytest.raises(ValueError, match="skip_first_arg must be a boolean"):
        await invalidate_cache("example", 21, skip_first_arg="yes")  # type: ignore[arg-type]


def test_cached_rejects_invalid_refresh_ttl_configuration():
    with pytest.raises(ValueError, match="refresh_ttl_on_hit must be a boolean"):
        cached(prefix="example", refresh_ttl_on_hit="yes")  # type: ignore[arg-type]

    with pytest.raises(
        ValueError,
        match="hit_ttl must be a positive integer when provided",
    ):
        cached(prefix="example", hit_ttl=0)

    with pytest.raises(
        ValueError,
        match="ttl_jitter must be a non-negative integer when provided",
    ):
        cached(prefix="example", ttl_jitter="5")  # type: ignore[arg-type]

    with pytest.raises(
        ValueError,
        match="ttl_jitter must be a non-negative integer when provided",
    ):
        cached(prefix="example", ttl_jitter=-1)

    with pytest.raises(
        ValueError,
        match="ttl_jitter_mode must be one of: increase, symmetric",
    ):
        cached(prefix="example", ttl_jitter_mode="")

    with pytest.raises(
        ValueError,
        match="ttl_jitter_mode must be one of: increase, symmetric",
    ):
        cached(prefix="example", ttl_jitter_mode="decrease")

    with pytest.raises(
        ValueError,
        match="ttl_resolver must be callable when provided",
    ):
        cached(prefix="example", ttl_resolver="60")  # type: ignore[arg-type]

    with pytest.raises(
        ValueError,
        match="hit_ttl_resolver must be callable when provided",
    ):
        cached(prefix="example", hit_ttl_resolver="10")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_cached_applies_ttl_jitter_to_cache_writes(monkeypatch):
    cached_values: dict[str, int] = {}
    set_events: list[tuple[str, int]] = []

    async def fake_get(key: str):
        return cached_values.get(key)

    async def fake_set(key: str, value: int, ttl=None):
        assert ttl is not None
        set_events.append((key, ttl))
        cached_values[key] = value
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)
    monkeypatch.setattr("app.core.cache.random.randint", lambda _start, _end: 4)

    @cached(prefix="example", ttl=30, ttl_jitter=10)
    async def compute(value: int) -> int:
        return value * 2

    assert await compute(21) == 42
    assert set_events == [("example:21", 34)]


@pytest.mark.asyncio
async def test_cached_supports_symmetric_ttl_jitter_mode(monkeypatch):
    cached_values: dict[str, int] = {}
    set_events: list[tuple[str, int]] = []
    randint_ranges: list[tuple[int, int]] = []

    async def fake_get(key: str):
        return cached_values.get(key)

    async def fake_set(key: str, value: int, ttl=None):
        assert ttl is not None
        set_events.append((key, ttl))
        cached_values[key] = value
        return True

    def fake_randint(start: int, end: int) -> int:
        randint_ranges.append((start, end))
        return -3

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)
    monkeypatch.setattr("app.core.cache.random.randint", fake_randint)

    @cached(prefix="example", ttl=30, ttl_jitter=10, ttl_jitter_mode="symmetric")
    async def compute(value: int) -> int:
        return value * 2

    assert await compute(21) == 42
    assert set_events == [("example:21", 27)]
    assert randint_ranges == [(-10, 10)]


@pytest.mark.asyncio
async def test_cached_symmetric_ttl_jitter_clamps_to_minimum_one(monkeypatch):
    cached_values: dict[str, int] = {}
    set_events: list[tuple[str, int]] = []

    async def fake_get(key: str):
        return cached_values.get(key)

    async def fake_set(key: str, value: int, ttl=None):
        assert ttl is not None
        set_events.append((key, ttl))
        cached_values[key] = value
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)
    monkeypatch.setattr("app.core.cache.random.randint", lambda _start, _end: -10)

    @cached(prefix="example", ttl=2, ttl_jitter=10, ttl_jitter_mode="symmetric")
    async def compute(value: int) -> int:
        return value

    assert await compute(7) == 7
    assert set_events == [("example:7", 1)]


@pytest.mark.asyncio
async def test_cached_applies_ttl_jitter_using_settings_default_ttl(monkeypatch):
    cached_values: dict[str, int] = {}
    set_events: list[tuple[str, int]] = []

    async def fake_get(key: str):
        return cached_values.get(key)

    async def fake_set(key: str, value: int, ttl=None):
        assert ttl is not None
        set_events.append((key, ttl))
        cached_values[key] = value
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)
    monkeypatch.setattr("app.core.cache.random.randint", lambda _start, _end: 3)

    @cached(prefix="example", ttl_jitter=10)
    async def compute(value: int) -> int:
        return value * 2

    assert await compute(21) == 42
    assert set_events == [("example:21", settings.REDIS_DEFAULT_TTL + 3)]


@pytest.mark.asyncio
async def test_cached_ttl_resolver_overrides_cache_write_ttl(monkeypatch):
    cached_values: dict[str, int] = {}
    set_events: list[tuple[str, int | None]] = []

    async def fake_get(key: str):
        return cached_values.get(key)

    async def fake_set(key: str, value: int, ttl=None):
        set_events.append((key, ttl))
        cached_values[key] = value
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)

    @cached(prefix="example", ttl=30, ttl_resolver=lambda result: result + 5)
    async def compute(value: int) -> int:
        return value

    assert await compute(21) == 21
    assert set_events == [("example:21", 26)]


@pytest.mark.asyncio
async def test_cached_ttl_resolver_supports_async_callables(monkeypatch):
    cached_values: dict[str, int] = {}
    set_events: list[tuple[str, int | None]] = []

    async def fake_get(key: str):
        return cached_values.get(key)

    async def fake_set(key: str, value: int, ttl=None):
        set_events.append((key, ttl))
        cached_values[key] = value
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)

    async def resolve_ttl(result: int) -> int:
        return result * 2

    @cached(prefix="example", ttl_resolver=resolve_ttl)
    async def compute(value: int) -> int:
        return value

    assert await compute(7) == 7
    assert set_events == [("example:7", 14)]


@pytest.mark.asyncio
async def test_cached_ttl_resolver_combines_with_ttl_jitter(monkeypatch):
    cached_values: dict[str, int] = {}
    set_events: list[tuple[str, int | None]] = []

    async def fake_get(key: str):
        return cached_values.get(key)

    async def fake_set(key: str, value: int, ttl=None):
        set_events.append((key, ttl))
        cached_values[key] = value
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)
    monkeypatch.setattr("app.core.cache.random.randint", lambda _start, _end: 3)

    @cached(prefix="example", ttl=30, ttl_jitter=10, ttl_resolver=lambda _result: 20)
    async def compute(value: int) -> int:
        return value

    assert await compute(5) == 5
    assert set_events == [("example:5", 23)]


@pytest.mark.asyncio
async def test_cached_ttl_resolver_rejects_invalid_resolved_values(monkeypatch):
    async def fake_get(_: str):
        return None

    async def fake_set(_: str, __: int, ttl=None):
        raise AssertionError("cache.set should not run for invalid ttl_resolver output")

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)

    @cached(prefix="example", ttl_resolver=lambda _result: 0)
    async def compute(value: int) -> int:
        return value

    with pytest.raises(
        ValueError,
        match="ttl_resolver must return a positive integer or None",
    ):
        await compute(1)


@pytest.mark.asyncio
async def test_cached_refreshes_ttl_for_cache_hits_using_default_ttl(monkeypatch):
    cached_values = {"example:21": 42}
    expire_events: list[tuple[str, int]] = []

    async def fake_get(key: str):
        return cached_values.get(key)

    async def fake_set(_: str, __: int, ttl=None):
        raise AssertionError("cache.set should not run on cache hits")

    async def fake_expire(key: str, ttl: int):
        expire_events.append((key, ttl))
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)
    monkeypatch.setattr(cache, "expire", fake_expire)

    @cached(prefix="example", ttl=30, refresh_ttl_on_hit=True)
    async def compute(value: int) -> int:
        raise AssertionError("wrapped function should not execute on cache hit")

    assert await compute(21) == 42
    assert expire_events == [("example:21", 30)]


@pytest.mark.asyncio
async def test_cached_refreshes_ttl_with_hit_ttl_override(monkeypatch):
    cached_values = {"example:21": 42}
    expire_events: list[tuple[str, int]] = []

    async def fake_get(key: str):
        return cached_values.get(key)

    async def fake_set(_: str, __: int, ttl=None):
        raise AssertionError("cache.set should not run on cache hits")

    async def fake_expire(key: str, ttl: int):
        expire_events.append((key, ttl))
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)
    monkeypatch.setattr(cache, "expire", fake_expire)

    @cached(prefix="example", ttl=120, refresh_ttl_on_hit=True, hit_ttl=10)
    async def compute(value: int) -> int:
        raise AssertionError("wrapped function should not execute on cache hit")

    assert await compute(21) == 42
    assert expire_events == [("example:21", 10)]


@pytest.mark.asyncio
async def test_cached_refreshes_ttl_for_hits_using_settings_default_when_ttl_omitted(
    monkeypatch,
):
    cached_values = {"example:21": 42}
    expire_events: list[tuple[str, int]] = []

    async def fake_get(key: str):
        return cached_values.get(key)

    async def fake_set(_: str, __: int, ttl=None):
        raise AssertionError("cache.set should not run on cache hits")

    async def fake_expire(key: str, ttl: int):
        expire_events.append((key, ttl))
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)
    monkeypatch.setattr(cache, "expire", fake_expire)

    @cached(prefix="example", refresh_ttl_on_hit=True)
    async def compute(value: int) -> int:
        raise AssertionError("wrapped function should not execute on cache hit")

    assert await compute(21) == 42
    assert expire_events == [("example:21", settings.REDIS_DEFAULT_TTL)]


@pytest.mark.asyncio
async def test_cached_refreshes_ttl_for_hits_using_hit_ttl_resolver(monkeypatch):
    cached_values = {"example:21": 42}
    expire_events: list[tuple[str, int]] = []

    async def fake_get(key: str):
        return cached_values.get(key)

    async def fake_set(_: str, __: int, ttl=None):
        raise AssertionError("cache.set should not run on cache hits")

    async def fake_expire(key: str, ttl: int):
        expire_events.append((key, ttl))
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)
    monkeypatch.setattr(cache, "expire", fake_expire)

    @cached(
        prefix="example",
        ttl=120,
        hit_ttl=10,
        refresh_ttl_on_hit=True,
        hit_ttl_resolver=lambda cached_value: cached_value // 2,
    )
    async def compute(value: int) -> int:
        raise AssertionError("wrapped function should not execute on cache hit")

    assert await compute(21) == 42
    assert expire_events == [("example:21", 21)]


@pytest.mark.asyncio
async def test_cached_hit_ttl_resolver_can_fallback_to_hit_ttl(monkeypatch):
    cached_values = {"example:21": 42}
    expire_events: list[tuple[str, int]] = []

    async def fake_get(key: str):
        return cached_values.get(key)

    async def fake_set(_: str, __: int, ttl=None):
        raise AssertionError("cache.set should not run on cache hits")

    async def fake_expire(key: str, ttl: int):
        expire_events.append((key, ttl))
        return True

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)
    monkeypatch.setattr(cache, "expire", fake_expire)

    async def resolve_hit_ttl(_: int) -> int | None:
        return None

    @cached(
        prefix="example",
        refresh_ttl_on_hit=True,
        hit_ttl=15,
        hit_ttl_resolver=resolve_hit_ttl,
    )
    async def compute(value: int) -> int:
        raise AssertionError("wrapped function should not execute on cache hit")

    assert await compute(21) == 42
    assert expire_events == [("example:21", 15)]


@pytest.mark.asyncio
async def test_cached_hit_ttl_resolver_rejects_invalid_resolved_values(monkeypatch):
    cached_values = {"example:21": 42}

    async def fake_get(key: str):
        return cached_values.get(key)

    async def fake_set(_: str, __: int, ttl=None):
        raise AssertionError("cache.set should not run on cache hits")

    async def fake_expire(_: str, __: int):
        raise AssertionError("cache.expire should not run for invalid resolver values")

    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "set", fake_set)
    monkeypatch.setattr(cache, "expire", fake_expire)

    @cached(
        prefix="example",
        refresh_ttl_on_hit=True,
        hit_ttl_resolver=lambda _cached_value: 0,
    )
    async def compute(value: int) -> int:
        raise AssertionError("wrapped function should not execute on cache hit")

    with pytest.raises(
        ValueError,
        match="hit_ttl_resolver must return a positive integer or None",
    ):
        await compute(21)
