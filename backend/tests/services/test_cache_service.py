"""Tests for LocalCacheService compatibility cache."""

import asyncio
import time

import pytest

from app.services.cache import LocalCacheService


def test_local_cache_set_and_get():
    cache = LocalCacheService()

    cache.set("k", {"v": 1})

    assert cache.get("k") == {"v": 1}


def test_local_cache_ttl_expiration():
    cache = LocalCacheService()

    cache.set("temp", "value", ttl_seconds=1)
    assert cache.get("temp") == "value"

    time.sleep(1.05)
    assert cache.get("temp") is None


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
