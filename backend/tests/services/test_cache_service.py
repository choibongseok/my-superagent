"""Tests for LocalCacheService compatibility cache."""

import time

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
