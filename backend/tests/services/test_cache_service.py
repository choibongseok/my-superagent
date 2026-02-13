"""Tests for LocalCacheService compatibility cache."""

import asyncio
import time

import pytest

from app.services.cache import LocalCacheService


def test_local_cache_set_and_get():
    cache = LocalCacheService()

    cache.set("k", {"v": 1})

    assert cache.get("k") == {"v": 1}


def test_local_cache_rejects_non_positive_max_entries():
    with pytest.raises(ValueError, match="max_entries must be greater than 0"):
        LocalCacheService(max_entries=0)


def test_local_cache_ttl_expiration():
    cache = LocalCacheService()

    cache.set("temp", "value", ttl_seconds=1)
    assert cache.get("temp") == "value"

    time.sleep(1.05)
    assert cache.get("temp") is None


def test_local_cache_max_entries_evicts_least_recently_used_key():
    cache = LocalCacheService(max_entries=2)

    cache.set("a", 1)
    cache.set("b", 2)
    assert cache.get("a") == 1  # mark "a" as most recently used

    cache.set("c", 3)

    assert cache.get("a") == 1
    assert cache.get("b") is None
    assert cache.get("c") == 3


def test_local_cache_max_entries_purges_expired_keys_before_evicting_active_entries():
    cache = LocalCacheService(max_entries=2)

    cache.set("short-lived", "x", ttl_seconds=1)
    cache.set("stable", "y")
    time.sleep(1.05)

    cache.set("fresh", "z")

    assert cache.get("short-lived") is None
    assert cache.get("stable") == "y"
    assert cache.get("fresh") == "z"


def test_local_cache_bulk_set_and_get_many():
    cache = LocalCacheService()

    cache.set_many({"a": 1, "b": 2, "c": 3})

    assert cache.get_many(["a", "missing", "c"]) == {"a": 1, "c": 3}


def test_local_cache_has_respects_expiration():
    cache = LocalCacheService()

    cache.set("session", "abc", ttl_seconds=1)
    assert cache.has("session") is True

    time.sleep(1.05)
    assert cache.has("session") is False


def test_local_cache_get_or_set_populates_once():
    cache = LocalCacheService()
    calls = {"count": 0}

    def factory() -> str:
        calls["count"] += 1
        return "computed-value"

    first = cache.get_or_set("lazy", factory)
    second = cache.get_or_set("lazy", factory)

    assert first == "computed-value"
    assert second == "computed-value"
    assert calls["count"] == 1


def test_local_cache_ttl_remaining_reports_seconds_for_expiring_keys():
    cache = LocalCacheService()

    cache.set("expiring", "value", ttl_seconds=2)

    ttl = cache.ttl_remaining("expiring")
    assert ttl is not None
    assert 0 < ttl <= 2


def test_local_cache_ttl_remaining_returns_none_for_missing_or_non_expiring_keys():
    cache = LocalCacheService()
    cache.set("persistent", "value")

    assert cache.ttl_remaining("missing") is None
    assert cache.ttl_remaining("persistent") is None


def test_local_cache_touch_extends_existing_ttl():
    cache = LocalCacheService()
    cache.set("session", "abc", ttl_seconds=1)

    time.sleep(0.6)
    assert cache.touch("session", ttl_seconds=1) is True

    # Should still exist because TTL was refreshed.
    time.sleep(0.6)
    assert cache.get("session") == "abc"

    # Refreshed TTL should eventually expire.
    time.sleep(0.6)
    assert cache.get("session") is None


def test_local_cache_touch_returns_false_for_missing_or_expired_keys():
    cache = LocalCacheService()

    assert cache.touch("missing", ttl_seconds=10) is False

    cache.set("temp", "value", ttl_seconds=1)
    time.sleep(1.05)

    assert cache.touch("temp", ttl_seconds=10) is False
    assert cache.get("temp") is None


def test_local_cache_touch_can_convert_key_to_non_expiring():
    cache = LocalCacheService()
    cache.set("config", "stable", ttl_seconds=1)

    assert cache.touch("config", ttl_seconds=None) is True

    time.sleep(1.05)
    assert cache.get("config") == "stable"
    assert cache.ttl_remaining("config") is None


def test_local_cache_delete_many_returns_removed_count():
    cache = LocalCacheService()
    cache.set_many({"alpha": 1, "beta": 2, "gamma": 3})

    removed = cache.delete_many(["alpha", "gamma", "missing"])

    assert removed == 2
    assert cache.get_many(["alpha", "beta", "gamma"]) == {"beta": 2}


def test_local_cache_clear_prefix_removes_matching_keys_only():
    cache = LocalCacheService()
    cache.set_many(
        {
            "user:1:profile": {"name": "A"},
            "user:2:profile": {"name": "B"},
            "workspace:1": {"title": "Project"},
        }
    )

    removed = cache.clear_prefix("user:")

    assert removed == 2
    assert cache.get("workspace:1") == {"title": "Project"}
    assert cache.get("user:1:profile") is None
    assert cache.get("user:2:profile") is None


def test_local_cache_size_counts_only_active_entries():
    cache = LocalCacheService()
    cache.set("persist", "ok")
    cache.set("expiring", "soon-gone", ttl_seconds=1)

    assert cache.size() == 2
    time.sleep(1.05)

    assert cache.size() == 1
    assert cache.has("expiring") is False


@pytest.mark.asyncio
async def test_local_cache_get_or_set_async_populates_once():
    cache = LocalCacheService()
    calls = {"count": 0}

    async def factory() -> str:
        calls["count"] += 1
        return "computed-async-value"

    first = await cache.get_or_set_async("lazy-async", factory)
    second = await cache.get_or_set_async("lazy-async", factory)

    assert first == "computed-async-value"
    assert second == "computed-async-value"
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_local_cache_get_or_set_async_accepts_sync_factory():
    cache = LocalCacheService()

    result = await cache.get_or_set_async("sync-factory", lambda: "sync-value")

    assert result == "sync-value"
    assert cache.get("sync-factory") == "sync-value"


@pytest.mark.asyncio
async def test_local_cache_get_or_set_async_deduplicates_concurrent_calls():
    cache = LocalCacheService()
    calls = {"count": 0}

    async def factory() -> str:
        calls["count"] += 1
        await asyncio.sleep(0.05)
        return "shared"

    results = await asyncio.gather(
        cache.get_or_set_async("concurrent", factory),
        cache.get_or_set_async("concurrent", factory),
        cache.get_or_set_async("concurrent", factory),
    )

    assert results == ["shared", "shared", "shared"]
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_local_cache_get_or_set_async_cleans_inflight_when_factory_fails():
    cache = LocalCacheService()
    calls = {"count": 0}

    async def flaky_factory() -> str:
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("boom")
        return "recovered"

    with pytest.raises(RuntimeError, match="boom"):
        await cache.get_or_set_async("flaky", flaky_factory)

    assert await cache.get_or_set_async("flaky", flaky_factory) == "recovered"
    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_local_cache_get_or_set_async_keeps_shared_task_alive_on_cancellation():
    cache = LocalCacheService()
    calls = {"count": 0}
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_factory() -> str:
        calls["count"] += 1
        started.set()
        await release.wait()
        return "stable-value"

    first_caller = asyncio.create_task(
        cache.get_or_set_async("shared-key", slow_factory)
    )
    await started.wait()

    first_caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first_caller

    second_caller = asyncio.create_task(
        cache.get_or_set_async("shared-key", slow_factory)
    )
    release.set()

    assert await second_caller == "stable-value"
    assert cache.get("shared-key") == "stable-value"
    assert calls["count"] == 1
