"""Tests for LocalCacheService compatibility cache."""

import asyncio
import time

import pytest

from app.services.cache import LocalCacheService


def test_local_cache_set_and_get():
    cache = LocalCacheService()

    cache.set("k", {"v": 1})

    assert cache.get("k") == {"v": 1}


def test_local_cache_get_with_metadata_returns_value_ttl_and_tags():
    cache = LocalCacheService()
    cache.set_tagged("k", {"v": 1}, tags=["beta", "alpha"])

    metadata = cache.get_with_metadata("k")

    assert metadata == {
        "key": "k",
        "value": {"v": 1},
        "ttl_seconds": None,
        "expires_at": None,
        "tags": ["alpha", "beta"],
    }


def test_local_cache_get_with_metadata_includes_remaining_ttl_for_expiring_keys():
    cache = LocalCacheService()
    cache.set("session", "token", ttl_seconds=2)

    metadata = cache.get_with_metadata("session")

    assert metadata is not None
    assert metadata["key"] == "session"
    assert metadata["value"] == "token"
    assert metadata["expires_at"] is not None
    assert metadata["ttl_seconds"] is not None
    assert 0 < metadata["ttl_seconds"] <= 2


def test_local_cache_get_with_metadata_returns_none_and_tracks_miss_for_missing_key():
    cache = LocalCacheService()

    assert cache.get_with_metadata("missing") is None

    stats = cache.stats()
    assert stats["hits"] == 0
    assert stats["misses"] == 1


def test_local_cache_get_many_with_metadata_returns_ordered_unique_metadata_payloads():
    cache = LocalCacheService()
    cache.set_tagged("alpha", {"v": 1}, tags=["group:a", "shared"])
    cache.set("beta", "value", ttl_seconds=2)

    metadata = cache.get_many_with_metadata(["alpha", "beta", "alpha"])

    assert list(metadata.keys()) == ["alpha", "beta"]
    assert metadata["alpha"] == {
        "key": "alpha",
        "value": {"v": 1},
        "ttl_seconds": None,
        "expires_at": None,
        "tags": ["group:a", "shared"],
    }

    beta = metadata["beta"]
    assert beta is not None
    assert beta["key"] == "beta"
    assert beta["value"] == "value"
    assert beta["expires_at"] is not None
    assert beta["ttl_seconds"] is not None
    assert 0 < beta["ttl_seconds"] <= 2


def test_local_cache_get_many_with_metadata_can_include_missing_keys():
    cache = LocalCacheService()
    cache.set("active", "value")

    metadata = cache.get_many_with_metadata(
        ["missing", "active", "unknown"],
        include_missing=True,
    )

    assert metadata["missing"] is None
    assert metadata["active"] == {
        "key": "active",
        "value": "value",
        "ttl_seconds": None,
        "expires_at": None,
        "tags": [],
    }
    assert metadata["unknown"] is None


def test_local_cache_get_many_with_metadata_tracks_lookup_stats_once_per_unique_key():
    cache = LocalCacheService()
    cache.set("present", 1)

    metadata = cache.get_many_with_metadata(["present", "missing", "present"])

    assert metadata == {
        "present": {
            "key": "present",
            "value": 1,
            "ttl_seconds": None,
            "expires_at": None,
            "tags": [],
        }
    }

    stats = cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1


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


def test_local_cache_replace_updates_existing_key_and_preserves_ttl_by_default():
    cache = LocalCacheService()
    cache.set("session", "v1", ttl_seconds=1)

    time.sleep(0.4)

    assert cache.replace("session", "v2") is True
    assert cache.get("session") == "v2"

    ttl = cache.ttl_remaining("session")
    assert ttl is not None
    assert 0 < ttl < 1

    time.sleep(ttl + 0.1)

    assert cache.get("session") is None


def test_local_cache_replace_returns_false_for_missing_or_expired_key():
    cache = LocalCacheService()

    assert cache.replace("missing", "value") is False

    cache.set("temp", "value", ttl_seconds=1)
    time.sleep(1.05)

    assert cache.replace("temp", "next") is False


def test_local_cache_replace_can_override_ttl_when_keep_ttl_is_false():
    cache = LocalCacheService()
    cache.set("token", "old", ttl_seconds=1)

    time.sleep(0.4)

    assert (
        cache.replace(
            "token",
            "new",
            ttl_seconds=2,
            keep_ttl=False,
        )
        is True
    )

    ttl = cache.ttl_remaining("token")
    assert ttl is not None
    assert 1.5 <= ttl <= 2


def test_local_cache_replace_many_replaces_existing_keys_only():
    cache = LocalCacheService()
    cache.set_many({"a": 1, "b": 2})

    replaced = cache.replace_many({"a": 10, "missing": 99, "b": 20})

    assert replaced == 2
    assert cache.get_many(["a", "b", "missing"]) == {"a": 10, "b": 20}


def test_local_cache_compare_and_set_updates_only_on_expected_match():
    cache = LocalCacheService()
    cache.set("version", 1)

    assert cache.compare_and_set("version", expected_value=2, new_value=3) is False
    assert cache.get("version") == 1

    assert cache.compare_and_set("version", expected_value=1, new_value=2) is True
    assert cache.get("version") == 2


def test_local_cache_compare_and_set_preserves_existing_ttl_by_default():
    cache = LocalCacheService()
    cache.set("token", "v1", ttl_seconds=1)

    time.sleep(0.4)

    assert cache.compare_and_set("token", expected_value="v1", new_value="v2") is True

    ttl = cache.ttl_remaining("token")
    assert ttl is not None
    assert 0 < ttl < 1


def test_local_cache_compare_and_set_can_override_ttl_when_keep_ttl_is_false():
    cache = LocalCacheService()
    cache.set("token", "v1", ttl_seconds=1)

    time.sleep(0.4)

    assert (
        cache.compare_and_set(
            "token",
            expected_value="v1",
            new_value="v2",
            ttl_seconds=2,
            keep_ttl=False,
        )
        is True
    )

    ttl = cache.ttl_remaining("token")
    assert ttl is not None
    assert 1.5 <= ttl <= 2


def test_local_cache_compare_and_delete_removes_only_matching_values():
    cache = LocalCacheService()
    cache.set("lock", "owner-a")

    assert cache.compare_and_delete("lock", expected_value="owner-b") is False
    assert cache.get("lock") == "owner-a"

    assert cache.compare_and_delete("lock", expected_value="owner-a") is True
    assert cache.get("lock") is None


def test_local_cache_compare_and_delete_returns_false_for_missing_or_expired_key():
    cache = LocalCacheService()

    assert cache.compare_and_delete("missing", expected_value="x") is False

    cache.set("temp", "value", ttl_seconds=1)
    time.sleep(1.05)

    assert cache.compare_and_delete("temp", expected_value="value") is False


def test_local_cache_peek_returns_value_without_affecting_stats_or_lru_order():
    cache = LocalCacheService(max_entries=2)
    cache.set("a", 1)
    cache.set("b", 2)

    before_stats = cache.stats().copy()
    assert cache.peek("a") == 1
    assert cache.peek("missing", default="fallback") == "fallback"

    after_stats = cache.stats()
    assert after_stats == before_stats

    # Peek should not mark keys as recently used.
    cache.set("c", 3)
    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3


def test_local_cache_peek_many_reads_values_without_mutating_stats():
    cache = LocalCacheService()
    cache.set_many({"alpha": 1, "beta": 2})

    before_stats = cache.stats().copy()

    assert cache.peek_many(["alpha", "missing", "beta", "alpha"]) == {
        "alpha": 1,
        "beta": 2,
    }

    after_stats = cache.stats()
    assert after_stats == before_stats


def test_local_cache_get_or_set_many_populates_missing_keys_once():
    cache = LocalCacheService()
    cache.set("cached", 10)

    calls = {"count": 0, "missing": []}

    def factory(missing_keys: list[str]) -> dict[str, int]:
        calls["count"] += 1
        calls["missing"] = missing_keys
        return {
            "fresh": 20,
            "late": 30,
        }

    values = cache.get_or_set_many(["cached", "fresh", "fresh", "late"], factory)

    assert values == {"cached": 10, "fresh": 20, "late": 30}
    assert calls == {"count": 1, "missing": ["fresh", "late"]}
    assert cache.get("fresh") == 20
    assert cache.get("late") == 30


def test_local_cache_get_or_set_many_skips_factory_when_all_keys_cached():
    cache = LocalCacheService()
    cache.set_many({"a": 1, "b": 2})

    def should_not_run(_: list[str]) -> dict[str, int]:
        raise AssertionError("factory must not be called when all keys are cached")

    assert cache.get_or_set_many(["a", "b"], should_not_run) == {"a": 1, "b": 2}


def test_local_cache_get_or_set_many_applies_ttl_to_populated_entries():
    cache = LocalCacheService()

    populated = cache.get_or_set_many(
        ["token"],
        lambda missing: {key: "abc123" for key in missing},
        ttl_seconds=1,
    )

    assert populated == {"token": "abc123"}
    assert cache.get("token") == "abc123"

    time.sleep(1.05)

    assert cache.get("token") is None


def test_local_cache_get_or_set_many_validates_factory_output_mapping():
    cache = LocalCacheService()

    with pytest.raises(TypeError, match="factory must return a mapping"):
        cache.get_or_set_many(
            ["missing"],
            lambda _: ["not", "a", "mapping"],  # type: ignore[arg-type]
        )


def test_local_cache_get_or_set_many_requires_all_missing_keys_in_factory_result():
    cache = LocalCacheService()

    with pytest.raises(ValueError, match="missing values for keys: beta"):
        cache.get_or_set_many(
            ["alpha", "beta"],
            lambda _: {"alpha": 1},
        )


@pytest.mark.asyncio
async def test_local_cache_get_or_set_many_async_populates_missing_keys_once():
    cache = LocalCacheService()
    cache.set("cached", 1)

    calls: dict[str, object] = {"count": 0, "missing": []}

    async def factory(missing_keys: list[str]) -> dict[str, str]:
        calls["count"] = int(calls["count"]) + 1
        calls["missing"] = missing_keys
        await asyncio.sleep(0.01)
        return {key: key.upper() for key in missing_keys}

    values = await cache.get_or_set_many_async(
        ["cached", "fresh", "fresh", "late"],
        factory,
    )

    assert values == {"cached": 1, "fresh": "FRESH", "late": "LATE"}
    assert calls == {"count": 1, "missing": ["fresh", "late"]}
    assert cache.get("fresh") == "FRESH"
    assert cache.get("late") == "LATE"


@pytest.mark.asyncio
async def test_local_cache_get_or_set_many_async_accepts_sync_factory():
    cache = LocalCacheService()

    values = await cache.get_or_set_many_async(
        ["x", "y"],
        lambda missing_keys: {key: len(key) for key in missing_keys},
    )

    assert values == {"x": 1, "y": 1}


@pytest.mark.asyncio
async def test_local_cache_get_or_set_many_async_validates_factory_results():
    cache = LocalCacheService()

    with pytest.raises(TypeError, match="factory must return a mapping"):
        await cache.get_or_set_many_async(
            ["missing"],
            lambda _: ["not", "a", "mapping"],  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="missing values for keys: beta"):
        await cache.get_or_set_many_async(
            ["alpha", "beta"],
            lambda _: {"alpha": 1},
        )


def test_local_cache_set_if_absent_stores_missing_key_only_once():
    cache = LocalCacheService()

    assert cache.set_if_absent("session", "first") is True
    assert cache.set_if_absent("session", "second") is False
    assert cache.get("session") == "first"


def test_local_cache_set_if_absent_treats_expired_entry_as_missing():
    cache = LocalCacheService()
    cache.set("otp", "1234", ttl_seconds=1)

    time.sleep(1.05)

    assert cache.set_if_absent("otp", "5678") is True
    assert cache.get("otp") == "5678"


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


def test_local_cache_touch_many_refreshes_existing_keys_once():
    cache = LocalCacheService()
    cache.set("session:a", "alpha", ttl_seconds=1)
    cache.set("session:b", "beta", ttl_seconds=1)

    time.sleep(0.4)

    touched = cache.touch_many(
        ["session:a", "missing", "session:a", "session:b"],
        ttl_seconds=2,
    )

    assert touched == 2

    ttl_a = cache.ttl_remaining("session:a")
    ttl_b = cache.ttl_remaining("session:b")
    assert ttl_a is not None and 1.5 <= ttl_a <= 2
    assert ttl_b is not None and 1.5 <= ttl_b <= 2


def test_local_cache_expire_sets_ttl_for_existing_key():
    cache = LocalCacheService()
    cache.set("session", "active")

    assert cache.expire("session", ttl_seconds=1) is True

    ttl = cache.ttl_remaining("session")
    assert ttl is not None
    assert 0 < ttl <= 1

    time.sleep(1.05)
    assert cache.get("session") is None


def test_local_cache_expire_returns_false_for_missing_or_expired_key():
    cache = LocalCacheService()

    assert cache.expire("missing", ttl_seconds=1) is False

    cache.set("short", "value", ttl_seconds=1)
    time.sleep(1.05)

    assert cache.expire("short", ttl_seconds=1) is False


def test_local_cache_expire_rejects_non_positive_ttl():
    cache = LocalCacheService()
    cache.set("session", "active")

    with pytest.raises(ValueError, match="ttl_seconds must be greater than 0"):
        cache.expire("session", ttl_seconds=0)

    with pytest.raises(ValueError, match="ttl_seconds must be greater than 0"):
        cache.expire("session", ttl_seconds=-1)


def test_local_cache_expire_many_refreshes_existing_keys_once():
    cache = LocalCacheService()
    cache.set_many({"session:a": "a", "session:b": "b"})

    expired = cache.expire_many(
        ["session:a", "missing", "session:a", "session:b"],
        ttl_seconds=2,
    )

    assert expired == 2

    ttl_a = cache.ttl_remaining("session:a")
    ttl_b = cache.ttl_remaining("session:b")
    assert ttl_a is not None and 1.5 <= ttl_a <= 2
    assert ttl_b is not None and 1.5 <= ttl_b <= 2


def test_local_cache_persist_removes_existing_expiration():
    cache = LocalCacheService()
    cache.set("token", "abc", ttl_seconds=1)

    assert cache.persist("token") is True
    assert cache.ttl_remaining("token") is None

    time.sleep(1.05)
    assert cache.get("token") == "abc"


def test_local_cache_persist_returns_false_for_missing_or_non_expiring_keys():
    cache = LocalCacheService()
    cache.set("stable", "value")

    assert cache.persist("missing") is False
    assert cache.persist("stable") is False


def test_local_cache_persist_many_removes_expiration_from_existing_keys_once():
    cache = LocalCacheService()
    cache.set("a", 1, ttl_seconds=1)
    cache.set("b", 2, ttl_seconds=1)
    cache.set("c", 3)

    persisted = cache.persist_many(["a", "missing", "a", "b", "c"])

    assert persisted == 2
    assert cache.ttl_remaining("a") is None
    assert cache.ttl_remaining("b") is None
    assert cache.ttl_remaining("c") is None


def test_local_cache_get_and_touch_refreshes_ttl_and_returns_value():
    cache = LocalCacheService()
    cache.set("auth-token", "abc", ttl_seconds=1)

    time.sleep(0.6)

    assert cache.get_and_touch("auth-token", ttl_seconds=1) == "abc"

    # Sliding TTL should keep key alive past original expiration.
    time.sleep(0.6)
    assert cache.get("auth-token") == "abc"

    time.sleep(0.6)
    assert cache.get("auth-token") is None


def test_local_cache_get_and_touch_returns_default_on_miss_and_tracks_lookup():
    cache = LocalCacheService()

    assert (
        cache.get_and_touch("missing", ttl_seconds=60, default="fallback") == "fallback"
    )

    stats = cache.stats()
    assert stats["hits"] == 0
    assert stats["misses"] == 1


def test_local_cache_get_and_touch_many_returns_values_once_and_refreshes_ttl():
    cache = LocalCacheService()
    cache.set("session:a", "alpha", ttl_seconds=1)
    cache.set("session:b", "beta", ttl_seconds=1)

    time.sleep(0.4)

    values = cache.get_and_touch_many(
        ["session:a", "missing", "session:a", "session:b"],
        ttl_seconds=2,
    )

    assert values == {
        "session:a": "alpha",
        "session:b": "beta",
    }

    ttl_a = cache.ttl_remaining("session:a")
    ttl_b = cache.ttl_remaining("session:b")
    assert ttl_a is not None and 1.5 <= ttl_a <= 2
    assert ttl_b is not None and 1.5 <= ttl_b <= 2


def test_local_cache_get_and_touch_many_skips_missing_keys_and_tracks_lookups_once():
    cache = LocalCacheService()
    cache.set("present", 1)

    values = cache.get_and_touch_many(["present", "missing", "present"], ttl_seconds=5)

    assert values == {"present": 1}

    stats = cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1


def test_local_cache_get_and_touch_many_can_make_entries_non_expiring():
    cache = LocalCacheService()
    cache.set("session", "token", ttl_seconds=1)

    assert cache.get_and_touch_many(["session"], ttl_seconds=None) == {
        "session": "token"
    }

    time.sleep(1.05)

    assert cache.get("session") == "token"
    assert cache.ttl_remaining("session") is None


def test_local_cache_increment_initializes_missing_key():
    cache = LocalCacheService()

    updated = cache.increment("counter", amount=3, initial=10)

    assert updated == 13
    assert cache.get("counter") == 13


def test_local_cache_increment_preserves_existing_ttl_by_default():
    cache = LocalCacheService()
    cache.set("counter", 1, ttl_seconds=1)

    time.sleep(0.4)
    updated = cache.increment("counter", amount=2)

    assert updated == 3
    ttl = cache.ttl_remaining("counter")
    assert ttl is not None
    assert 0 < ttl < 1

    time.sleep(ttl + 0.1)
    assert cache.get("counter") is None


def test_local_cache_increment_overrides_ttl_when_explicitly_provided():
    cache = LocalCacheService()
    cache.set("counter", 1, ttl_seconds=1)

    time.sleep(0.4)
    updated = cache.increment("counter", amount=1, ttl_seconds=2)

    assert updated == 2
    ttl = cache.ttl_remaining("counter")
    assert ttl is not None
    assert 1.5 <= ttl <= 2


def test_local_cache_increment_rejects_non_numeric_values():
    cache = LocalCacheService()
    cache.set("counter", "not-a-number")

    with pytest.raises(TypeError, match="existing cache value must be a numeric value"):
        cache.increment("counter")


def test_local_cache_decrement_supports_missing_keys_and_non_negative_amount():
    cache = LocalCacheService()

    assert cache.decrement("credits", amount=2, initial=5) == 3

    with pytest.raises(ValueError, match="amount must be greater than or equal to 0"):
        cache.decrement("credits", amount=-1)


def test_local_cache_increment_many_updates_multiple_keys_in_request_order():
    cache = LocalCacheService()
    cache.set("alpha", 1)

    updated = cache.increment_many(
        {
            "alpha": 2,
            "beta": 5,
            "gamma": 1,
        },
        initial=10,
    )

    assert updated == {
        "alpha": 3,
        "beta": 15,
        "gamma": 11,
    }
    assert cache.get_many(["alpha", "beta", "gamma"]) == {
        "alpha": 3,
        "beta": 15,
        "gamma": 11,
    }


def test_local_cache_increment_many_preserves_existing_ttl_by_default():
    cache = LocalCacheService()
    cache.set("quota", 7, ttl_seconds=1)

    time.sleep(0.4)

    updated = cache.increment_many({"quota": 1})

    assert updated == {"quota": 8}
    ttl = cache.ttl_remaining("quota")
    assert ttl is not None
    assert 0 < ttl < 1


def test_local_cache_increment_many_can_override_ttl_for_all_updated_keys():
    cache = LocalCacheService()
    cache.set("alpha", 1, ttl_seconds=1)
    cache.set("beta", 2)

    time.sleep(0.4)

    updated = cache.increment_many(
        {
            "alpha": 1,
            "beta": 1,
        },
        ttl_seconds=2,
    )

    assert updated == {"alpha": 2, "beta": 3}

    alpha_ttl = cache.ttl_remaining("alpha")
    beta_ttl = cache.ttl_remaining("beta")
    assert alpha_ttl is not None and 1.5 <= alpha_ttl <= 2
    assert beta_ttl is not None and 1.5 <= beta_ttl <= 2


def test_local_cache_decrement_many_updates_multiple_keys_and_supports_initial():
    cache = LocalCacheService()
    cache.set("credits", 10)

    updated = cache.decrement_many(
        {
            "credits": 3,
            "fallback": 2,
        },
        initial=5,
    )

    assert updated == {"credits": 7, "fallback": 3}
    assert cache.get("credits") == 7
    assert cache.get("fallback") == 3


def test_local_cache_decrement_many_rejects_negative_amounts():
    cache = LocalCacheService()

    with pytest.raises(ValueError, match="amount must be greater than or equal to 0"):
        cache.decrement_many({"credits": -1})


def test_local_cache_pop_returns_value_and_removes_key():
    cache = LocalCacheService()
    cache.set("token", "abc123")

    assert cache.pop("token") == "abc123"
    assert cache.get("token") is None


def test_local_cache_pop_returns_default_for_missing_or_expired_key():
    cache = LocalCacheService()

    assert cache.pop("missing", default="fallback") == "fallback"

    cache.set("temp", "value", ttl_seconds=1)
    time.sleep(1.05)

    assert cache.pop("temp", default="expired") == "expired"


def test_local_cache_pop_many_returns_existing_values_and_removes_keys_once():
    cache = LocalCacheService()
    cache.set_many({"alpha": 1, "beta": 2, "gamma": 3})

    popped = cache.pop_many(["alpha", "missing", "alpha", "gamma"])

    assert popped == {"alpha": 1, "gamma": 3}
    assert cache.get_many(["alpha", "beta", "gamma"]) == {"beta": 2}


def test_local_cache_pop_many_skips_expired_keys_and_tracks_lookup_stats():
    cache = LocalCacheService()
    cache.set("short", "x", ttl_seconds=1)
    cache.set("stable", "y")

    time.sleep(1.05)

    popped = cache.pop_many(["short", "stable", "missing"])

    assert popped == {"stable": "y"}

    stats = cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 2
    assert stats["deletes"] == 1


def test_local_cache_copy_preserves_source_and_remaining_ttl():
    cache = LocalCacheService()
    cache.set("session:source", "token", ttl_seconds=2)

    time.sleep(0.4)

    assert cache.copy("session:source", "session:copy") is True
    assert cache.get("session:source") == "token"
    assert cache.get("session:copy") == "token"

    ttl_source = cache.ttl_remaining("session:source")
    ttl_copy = cache.ttl_remaining("session:copy")
    assert ttl_source is not None
    assert ttl_copy is not None
    assert 1.0 <= ttl_copy <= 2
    assert abs(ttl_source - ttl_copy) < 0.2


def test_local_cache_copy_preserves_tags_for_source_and_target():
    cache = LocalCacheService()
    cache.set_tagged("source", "value", tags=["alpha", "shared"])

    assert cache.copy("source", "target") is True

    assert cache.list_tags("source") == ["alpha", "shared"]
    assert cache.list_tags("target") == ["alpha", "shared"]


def test_local_cache_copy_overwrite_replaces_target_tags_with_source_tags():
    cache = LocalCacheService()
    cache.set_tagged("source", "fresh", tags=["active", "primary"])
    cache.set_tagged("target", "stale", tags=["deprecated"])

    assert cache.copy("source", "target", overwrite=True) is True

    assert cache.get("target") == "fresh"
    assert cache.list_tags("target") == ["active", "primary"]
    assert cache.clear_tag("deprecated") == 0


def test_local_cache_copy_fails_when_source_missing_or_target_exists_without_overwrite():
    cache = LocalCacheService()
    cache.set_many({"source": "value", "target": "other"})

    assert cache.copy("missing", "new-target") is False
    assert cache.copy("source", "target") is False

    assert cache.get("source") == "value"
    assert cache.get("target") == "other"


def test_local_cache_copy_can_overwrite_target_and_tracks_mutations():
    cache = LocalCacheService()
    cache.set("source", "fresh", ttl_seconds=1)
    cache.set("target", "stale")

    time.sleep(0.4)

    assert cache.copy("source", "target", overwrite=True) is True
    assert cache.get("source") == "fresh"
    assert cache.get("target") == "fresh"

    ttl = cache.ttl_remaining("target")
    assert ttl is not None
    assert 0 < ttl < 1

    stats = cache.stats()
    assert stats["sets"] == 3
    assert stats["deletes"] == 1


def test_local_cache_copy_many_copies_only_successful_mappings():
    cache = LocalCacheService()
    cache.set_many({"alpha": 1, "beta": 2})

    copied = cache.copy_many(
        {
            "alpha": "copy:alpha",
            "missing": "copy:missing",
            "beta": "copy:beta",
        }
    )

    assert copied == 2
    assert cache.get_many(["alpha", "beta", "copy:alpha", "copy:beta"]) == {
        "alpha": 1,
        "beta": 2,
        "copy:alpha": 1,
        "copy:beta": 2,
    }


def test_local_cache_copy_same_key_is_noop_for_existing_and_missing_keys():
    cache = LocalCacheService()
    cache.set("stable", "value")

    assert cache.copy("stable", "stable") is True
    assert cache.copy("missing", "missing") is False


def test_local_cache_copy_respects_lru_eviction_when_cache_is_full():
    cache = LocalCacheService(max_entries=2)
    cache.set("alpha", 1)
    cache.set("beta", 2)

    assert cache.copy("alpha", "gamma") is True

    assert cache.get("alpha") == 1
    assert cache.get("beta") is None
    assert cache.get("gamma") == 1


def test_local_cache_rename_moves_value_and_preserves_remaining_ttl():
    cache = LocalCacheService()
    cache.set("session:old", "token", ttl_seconds=2)

    time.sleep(0.4)

    assert cache.rename("session:old", "session:new") is True
    assert cache.get("session:old") is None
    assert cache.get("session:new") == "token"

    ttl = cache.ttl_remaining("session:new")
    assert ttl is not None
    assert 1.0 <= ttl <= 2


def test_local_cache_rename_moves_source_tags_to_new_key():
    cache = LocalCacheService()
    cache.set_tagged("session:old", "token", tags=["auth", "session"])

    assert cache.rename("session:old", "session:new") is True

    assert cache.list_tags("session:old") == []
    assert cache.list_tags("session:new") == ["auth", "session"]
    assert cache.clear_tag("auth") == 1


def test_local_cache_rename_overwrite_replaces_target_tags_with_source_tags():
    cache = LocalCacheService()
    cache.set_tagged("source", "fresh", tags=["active", "owner:a"])
    cache.set_tagged("target", "stale", tags=["owner:b", "legacy"])

    assert cache.rename("source", "target", overwrite=True) is True

    assert cache.get("source") is None
    assert cache.get("target") == "fresh"
    assert cache.list_tags("target") == ["active", "owner:a"]
    assert cache.clear_tags(["owner:b", "legacy"]) == 0


def test_local_cache_rename_fails_when_source_missing_or_target_exists_without_overwrite():
    cache = LocalCacheService()
    cache.set_many({"source": "value", "target": "other"})

    assert cache.rename("missing", "new-target") is False
    assert cache.rename("source", "target") is False

    assert cache.get("source") == "value"
    assert cache.get("target") == "other"


def test_local_cache_rename_can_overwrite_target_and_preserve_source_ttl():
    cache = LocalCacheService()
    cache.set("source", "fresh", ttl_seconds=1)
    cache.set("target", "stale")

    time.sleep(0.4)

    assert cache.rename("source", "target", overwrite=True) is True
    assert cache.get("source") is None
    assert cache.get("target") == "fresh"

    ttl = cache.ttl_remaining("target")
    assert ttl is not None
    assert 0 < ttl < 1


def test_local_cache_rename_same_key_is_noop_for_existing_and_missing_keys():
    cache = LocalCacheService()
    cache.set("stable", "value")

    assert cache.rename("stable", "stable") is True
    assert cache.rename("missing", "missing") is False


def test_local_cache_rename_many_moves_only_successful_mappings():
    cache = LocalCacheService()
    cache.set_many({"alpha": 1, "beta": 2, "target": "occupied"})

    renamed = cache.rename_many(
        {
            "alpha": "renamed:alpha",
            "missing": "renamed:missing",
            "beta": "target",
        }
    )

    assert renamed == 1
    assert cache.get("alpha") is None
    assert cache.get("renamed:alpha") == 1
    assert cache.get("beta") == 2
    assert cache.get("target") == "occupied"


def test_local_cache_rename_many_supports_overwrite_for_each_mapping():
    cache = LocalCacheService()
    cache.set("source", "fresh", ttl_seconds=1)
    cache.set("target", "stale")

    time.sleep(0.4)

    renamed = cache.rename_many({"source": "target"}, overwrite=True)

    assert renamed == 1
    assert cache.get("source") is None
    assert cache.get("target") == "fresh"

    ttl = cache.ttl_remaining("target")
    assert ttl is not None
    assert 0 < ttl < 1


def test_local_cache_swap_exchanges_values_ttls_and_tags():
    cache = LocalCacheService()
    cache.set_tagged("left", "L", tags=["group:left"], ttl_seconds=1)
    cache.set_tagged("right", "R", tags=["group:right"])

    time.sleep(0.4)

    assert cache.swap("left", "right") is True

    assert cache.get("left") == "R"
    assert cache.get("right") == "L"
    assert cache.list_tags("left") == ["group:right"]
    assert cache.list_tags("right") == ["group:left"]

    left_ttl = cache.ttl_remaining("left")
    right_ttl = cache.ttl_remaining("right")
    assert left_ttl is None
    assert right_ttl is not None
    assert 0 < right_ttl < 1


def test_local_cache_swap_returns_false_without_mutating_when_any_key_missing():
    cache = LocalCacheService()
    cache.set("left", "L")

    assert cache.swap("left", "right") is False

    assert cache.get("left") == "L"
    assert cache.get("right") is None


def test_local_cache_swap_same_key_is_noop_for_existing_and_missing_keys():
    cache = LocalCacheService()
    cache.set("stable", "value")

    assert cache.swap("stable", "stable") is True
    assert cache.swap("missing", "missing") is False


def test_local_cache_delete_many_returns_removed_count():
    cache = LocalCacheService()
    cache.set_many({"alpha": 1, "beta": 2, "gamma": 3})

    removed = cache.delete_many(["alpha", "gamma", "missing"])

    assert removed == 2
    assert cache.get_many(["alpha", "beta", "gamma"]) == {"beta": 2}


def test_local_cache_set_tagged_replaces_key_tags_and_supports_tag_lookup():
    cache = LocalCacheService()

    cache.set_tagged("profile:1", {"name": "A"}, tags=["users", "profile"])

    assert cache.list_tags("profile:1") == ["profile", "users"]

    cache.set_tagged("profile:1", {"name": "A+"}, tags=["active"])

    assert cache.list_tags("profile:1") == ["active"]
    assert cache.clear_tag("users") == 0
    assert cache.clear_tag("active") == 1
    assert cache.get("profile:1") is None


def test_local_cache_tag_and_untag_manage_existing_keys_only():
    cache = LocalCacheService()

    assert cache.tag("missing", ["alpha"]) is False
    assert cache.untag("missing") is False

    cache.set("session", "token")

    assert cache.tag("session", ["auth", "sensitive", "auth"]) is True
    assert cache.list_tags("session") == ["auth", "sensitive"]

    assert cache.untag("session", ["auth"]) is True
    assert cache.list_tags("session") == ["sensitive"]

    assert cache.untag("session") is True
    assert cache.list_tags("session") == []


def test_local_cache_list_tag_stats_returns_sorted_counts():
    cache = LocalCacheService()
    cache.set_tagged("session:alpha", 1, tags=["session", "active"])
    cache.set_tagged("session:beta", 2, tags=["session"])
    cache.set_tagged("user:alpha", 3, tags=["active", "user"])

    assert cache.list_tag_stats() == [
        {"tag": "active", "count": 2},
        {"tag": "session", "count": 2},
        {"tag": "user", "count": 1},
    ]


def test_local_cache_list_tag_stats_supports_prefix_and_include_keys():
    cache = LocalCacheService()
    cache.set_tagged("session:alpha", 1, tags=["session", "active"])
    cache.set_tagged("session:beta", 2, tags=["session"])
    cache.set_tagged("user:alpha", 3, tags=["active", "user"])

    assert cache.list_tag_stats(prefix="session:", include_keys=True) == [
        {"tag": "active", "count": 1, "keys": ["session:alpha"]},
        {
            "tag": "session",
            "count": 2,
            "keys": ["session:alpha", "session:beta"],
        },
    ]


def test_local_cache_list_tag_stats_supports_pattern_offset_and_limit():
    cache = LocalCacheService()
    cache.set_tagged("session:alpha", 1, tags=["session", "active"])
    cache.set_tagged("session:beta", 2, tags=["session"])
    cache.set_tagged("user:alpha", 3, tags=["active", "user"])

    assert cache.list_tag_stats(pattern="*:alpha", offset=1, limit=1) == [
        {"tag": "session", "count": 1}
    ]


def test_local_cache_list_tag_stats_rejects_invalid_pagination_and_flags():
    cache = LocalCacheService()

    with pytest.raises(ValueError, match="offset must be greater than or equal to 0"):
        cache.list_tag_stats(offset=-1)

    with pytest.raises(ValueError, match="limit must be greater than 0"):
        cache.list_tag_stats(limit=0)

    with pytest.raises(ValueError, match="include_keys must be a boolean"):
        cache.list_tag_stats(include_keys="yes")  # type: ignore[arg-type]


def test_local_cache_list_tag_stats_ignores_expired_entries():
    cache = LocalCacheService()
    cache.set_tagged("temp", "value", tags=["volatile"], ttl_seconds=1)

    time.sleep(1.05)

    assert cache.list_tag_stats() == []
    assert cache.clear_tag("volatile") == 0


def test_local_cache_clear_tags_removes_union_of_tagged_keys_once():
    cache = LocalCacheService()
    cache.set_tagged("alpha", 1, tags=["group:a", "shared"])
    cache.set_tagged("beta", 2, tags=["group:b", "shared"])
    cache.set_tagged("gamma", 3, tags=["group:c"])

    removed = cache.clear_tags(["shared", "group:c", "shared", ""])

    assert removed == 3
    assert cache.get("alpha") is None
    assert cache.get("beta") is None
    assert cache.get("gamma") is None


def test_local_cache_clear_tags_supports_match_all_mode():
    cache = LocalCacheService()
    cache.set_tagged("alpha", 1, tags=["group:a", "shared"])
    cache.set_tagged("beta", 2, tags=["group:b", "shared"])
    cache.set_tagged("gamma", 3, tags=["group:a", "group:b", "shared"])

    removed = cache.clear_tags(["group:a", "shared"], match_all_tags=True)

    assert removed == 2
    assert cache.get("alpha") is None
    assert cache.get("gamma") is None
    assert cache.get("beta") == 2


def test_local_cache_clear_tags_rejects_invalid_match_all_tags_flag():
    cache = LocalCacheService()

    with pytest.raises(ValueError, match="match_all_tags must be a boolean"):
        cache.clear_tags(["group:a"], match_all_tags="yes")  # type: ignore[arg-type]


def test_local_cache_clear_tag_ignores_expired_entries():
    cache = LocalCacheService()
    cache.set_tagged("temp", "value", tags=["volatile"], ttl_seconds=1)

    time.sleep(1.05)

    assert cache.get("temp") is None
    assert cache.clear_tag("volatile") == 0


def test_local_cache_tag_rejects_non_string_values():
    cache = LocalCacheService()
    cache.set("safe", "value")

    with pytest.raises(TypeError, match="tags must contain only strings"):
        cache.tag("safe", ["ok", 123])  # type: ignore[list-item]


def test_local_cache_list_namespaces_returns_sorted_namespaces_and_optional_counts():
    cache = LocalCacheService()
    cache.set_many(
        {
            "session:alpha": 1,
            "session:beta": 2,
            "user:alpha": 3,
            "orphan": 4,
        }
    )

    assert cache.list_namespaces() == ["orphan", "session", "user"]

    assert cache.list_namespaces(include_counts=True) == [
        {"namespace": "orphan", "count": 1},
        {"namespace": "session", "count": 2},
        {"namespace": "user", "count": 1},
    ]

    assert cache.list_namespaces(prefix="s") == ["session"]


def test_local_cache_list_namespaces_supports_custom_separator_and_pagination():
    cache = LocalCacheService()
    cache.set_many(
        {
            "team/alpha": 1,
            "team/beta": 2,
            "project/alpha": 3,
        }
    )

    assert cache.list_namespaces(separator="/", offset=1, limit=1) == ["team"]


def test_local_cache_list_namespaces_rejects_invalid_inputs():
    cache = LocalCacheService()

    with pytest.raises(ValueError, match="prefix must be a string"):
        cache.list_namespaces(prefix=123)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="separator cannot be empty"):
        cache.list_namespaces(separator="   ")

    with pytest.raises(ValueError, match="offset must be greater than or equal to 0"):
        cache.list_namespaces(offset=-1)

    with pytest.raises(ValueError, match="limit must be greater than 0"):
        cache.list_namespaces(limit=0)

    with pytest.raises(ValueError, match="include_counts must be a boolean"):
        cache.list_namespaces(include_counts="yes")  # type: ignore[arg-type]


def test_local_cache_clear_namespace_removes_matching_keys_only():
    cache = LocalCacheService()
    cache.set_many(
        {
            "session": "root",
            "session:alpha": 1,
            "session:beta": 2,
            "user:alpha": 3,
        }
    )

    removed = cache.clear_namespace("session")

    assert removed == 3
    assert cache.get("session") is None
    assert cache.get("session:alpha") is None
    assert cache.get("session:beta") is None
    assert cache.get("user:alpha") == 3


@pytest.mark.asyncio
async def test_local_cache_clear_namespace_cancels_matching_inflight_tasks():
    cache = LocalCacheService()
    gate = asyncio.Event()

    async def factory() -> str:
        await gate.wait()
        return "ready"

    task = asyncio.create_task(cache.get_or_set_async("session:pending", factory))
    await asyncio.sleep(0)

    removed = cache.clear_namespace("session")
    gate.set()

    assert removed == 1
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cache.get("session:pending") is None


def test_local_cache_clear_namespace_rejects_invalid_inputs():
    cache = LocalCacheService()

    with pytest.raises(ValueError, match="namespace cannot be empty"):
        cache.clear_namespace("   ")

    with pytest.raises(ValueError, match="namespace cannot contain separator"):
        cache.clear_namespace("session:alpha")

    with pytest.raises(ValueError, match="separator cannot be empty"):
        cache.clear_namespace("session", separator="")


def test_local_cache_clear_namespaces_removes_union_of_matching_namespaces():
    cache = LocalCacheService()
    cache.set_many(
        {
            "session:alpha": 1,
            "session:beta": 2,
            "user:alpha": 3,
            "task:1": 4,
        }
    )

    removed = cache.clear_namespaces(["session", "user", "session"])

    assert removed == 3
    assert cache.get("session:alpha") is None
    assert cache.get("session:beta") is None
    assert cache.get("user:alpha") is None
    assert cache.get("task:1") == 4


def test_local_cache_clear_namespaces_supports_custom_separator():
    cache = LocalCacheService()
    cache.set_many(
        {
            "team/alpha": 1,
            "team/beta": 2,
            "project/alpha": 3,
        }
    )

    removed = cache.clear_namespaces(["team"], separator="/")

    assert removed == 2
    assert cache.get("team/alpha") is None
    assert cache.get("team/beta") is None
    assert cache.get("project/alpha") == 3


def test_local_cache_clear_namespaces_rejects_invalid_inputs():
    cache = LocalCacheService()

    with pytest.raises(ValueError, match="namespace cannot be empty"):
        cache.clear_namespaces(["session", "   "])

    with pytest.raises(ValueError, match="namespace cannot contain separator"):
        cache.clear_namespaces(["session:alpha"])

    with pytest.raises(ValueError, match="separator cannot be empty"):
        cache.clear_namespaces(["session"], separator="")


@pytest.mark.asyncio
async def test_local_cache_clear_namespaces_cancels_matching_inflight_tasks():
    cache = LocalCacheService()
    gate = asyncio.Event()

    async def factory() -> str:
        await gate.wait()
        return "ready"

    task = asyncio.create_task(cache.get_or_set_async("session:pending", factory))
    await asyncio.sleep(0)

    removed = cache.clear_namespaces(["session"])
    gate.set()

    assert removed == 1
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cache.get("session:pending") is None


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


def test_local_cache_clear_prefixes_removes_union_of_prefix_matches():
    cache = LocalCacheService()
    cache.set_many(
        {
            "user:1:profile": {"name": "A"},
            "user:1:settings": {"theme": "dark"},
            "workspace:1": {"title": "Project"},
            "task:1": {"status": "done"},
        }
    )

    removed = cache.clear_prefixes(["user:", "workspace:", "user:", ""])

    assert removed == 3
    assert cache.get("user:1:profile") is None
    assert cache.get("user:1:settings") is None
    assert cache.get("workspace:1") is None
    assert cache.get("task:1") == {"status": "done"}


def test_local_cache_clear_prefixes_returns_zero_for_empty_prefixes():
    cache = LocalCacheService()
    cache.set("stable", "value")

    assert cache.clear_prefixes([]) == 0
    assert cache.clear_prefixes([""]) == 0
    assert cache.get("stable") == "value"


def test_local_cache_clear_pattern_removes_glob_matches_only():
    cache = LocalCacheService()
    cache.set_many(
        {
            "user:1:profile": {"name": "A"},
            "user:2:profile": {"name": "B"},
            "user:2:settings": {"theme": "dark"},
            "workspace:1": {"title": "Project"},
        }
    )

    removed = cache.clear_pattern("user:*:profile")

    assert removed == 2
    assert cache.get("user:1:profile") is None
    assert cache.get("user:2:profile") is None
    assert cache.get("user:2:settings") == {"theme": "dark"}
    assert cache.get("workspace:1") == {"title": "Project"}


def test_local_cache_clear_patterns_removes_union_of_pattern_matches():
    cache = LocalCacheService()
    cache.set_many(
        {
            "task:1:result": {"status": "done"},
            "task:2:result": {"status": "pending"},
            "task:2:error": {"message": "boom"},
            "metrics:latency": 123,
        }
    )

    removed = cache.clear_patterns(["task:*:result", "task:*:error", ""])

    assert removed == 3
    assert cache.get("task:1:result") is None
    assert cache.get("task:2:result") is None
    assert cache.get("task:2:error") is None
    assert cache.get("metrics:latency") == 123


def test_local_cache_clear_patterns_returns_zero_for_empty_patterns():
    cache = LocalCacheService()
    cache.set("stable", "value")

    assert cache.clear_patterns([]) == 0
    assert cache.clear_patterns([""]) == 0
    assert cache.get("stable") == "value"


def test_local_cache_clear_where_supports_combined_prefix_pattern_and_tags():
    cache = LocalCacheService()
    cache.set_tagged("session:alpha", 1, tags=["active", "session"])
    cache.set_tagged("session:beta", 2, tags=["session"])
    cache.set_tagged("user:alpha", 3, tags=["active"])

    removed = cache.clear_where(prefix="session:", pattern="*:alpha", tags=["active"])

    assert removed == 1
    assert cache.get("session:alpha") is None
    assert cache.get("session:beta") == 2
    assert cache.get("user:alpha") == 3


def test_local_cache_clear_where_supports_match_all_tag_filtering():
    cache = LocalCacheService()
    cache.set_tagged("alpha", 1, tags=["group:a", "shared"])
    cache.set_tagged("beta", 2, tags=["group:b", "shared"])
    cache.set_tagged("gamma", 3, tags=["group:a"])

    removed = cache.clear_where(tags=["group:a", "shared"], match_all_tags=True)

    assert removed == 1
    assert cache.get("alpha") is None
    assert cache.get("beta") == 2
    assert cache.get("gamma") == 3


def test_local_cache_clear_where_requires_at_least_one_filter():
    cache = LocalCacheService()

    with pytest.raises(ValueError, match="at least one filter must be provided"):
        cache.clear_where()


@pytest.mark.asyncio
async def test_local_cache_clear_prefix_cancels_matching_inflight_tasks():
    cache = LocalCacheService()
    gate = asyncio.Event()

    async def factory() -> str:
        await gate.wait()
        return "ready"

    task = asyncio.create_task(cache.get_or_set_async("session:pending", factory))
    await asyncio.sleep(0)

    removed = cache.clear_prefix("session:")
    gate.set()

    assert removed == 1
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cache.get("session:pending") is None


@pytest.mark.asyncio
async def test_local_cache_clear_prefixes_cancels_matching_inflight_tasks():
    cache = LocalCacheService()
    gate = asyncio.Event()

    async def factory() -> str:
        await gate.wait()
        return "ready"

    task = asyncio.create_task(cache.get_or_set_async("job:pending", factory))
    await asyncio.sleep(0)

    removed = cache.clear_prefixes(["session:", "job:"])
    gate.set()

    assert removed == 1
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cache.get("job:pending") is None


@pytest.mark.asyncio
async def test_local_cache_clear_pattern_cancels_matching_inflight_tasks():
    cache = LocalCacheService()
    gate = asyncio.Event()

    async def factory() -> str:
        await gate.wait()
        return "ready"

    task = asyncio.create_task(cache.get_or_set_async("user:42:pending", factory))
    await asyncio.sleep(0)

    removed = cache.clear_pattern("user:*:pending")
    gate.set()

    assert removed == 1
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cache.get("user:42:pending") is None


@pytest.mark.asyncio
async def test_local_cache_clear_patterns_cancels_matching_inflight_tasks():
    cache = LocalCacheService()
    gate = asyncio.Event()

    async def factory() -> str:
        await gate.wait()
        return "ready"

    task = asyncio.create_task(cache.get_or_set_async("task:99:error", factory))
    await asyncio.sleep(0)

    removed = cache.clear_patterns(["task:*:result", "task:*:error"])
    gate.set()

    assert removed == 1
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cache.get("task:99:error") is None


@pytest.mark.asyncio
async def test_local_cache_clear_where_cancels_matching_inflight_tasks():
    cache = LocalCacheService()
    gate = asyncio.Event()

    async def factory() -> str:
        await gate.wait()
        return "ready"

    task = asyncio.create_task(cache.get_or_set_async("session:pending", factory))
    await asyncio.sleep(0)

    removed = cache.clear_where(prefix="session:")
    gate.set()

    assert removed == 1
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cache.get("session:pending") is None


def test_local_cache_pop_where_returns_removed_values_for_matching_entries():
    cache = LocalCacheService()
    cache.set_tagged("session:alpha", {"state": "active"}, tags=["session", "active"])
    cache.set_tagged("session:beta", {"state": "idle"}, tags=["session"])
    cache.set_tagged("user:alpha", {"state": "active"}, tags=["active"])

    popped = cache.pop_where(prefix="session:", tags=["active"])

    assert popped == {"session:alpha": {"state": "active"}}
    assert cache.get("session:alpha") is None
    assert cache.get("session:beta") == {"state": "idle"}
    assert cache.get("user:alpha") == {"state": "active"}


def test_local_cache_pop_where_supports_match_all_tag_filtering():
    cache = LocalCacheService()
    cache.set_tagged("alpha", 1, tags=["group:a", "shared"])
    cache.set_tagged("beta", 2, tags=["group:b", "shared"])
    cache.set_tagged("gamma", 3, tags=["group:a"])

    popped = cache.pop_where(tags=["group:a", "shared"], match_all_tags=True)

    assert popped == {"alpha": 1}
    assert cache.get("alpha") is None
    assert cache.get("beta") == 2
    assert cache.get("gamma") == 3


def test_local_cache_pop_where_requires_at_least_one_filter():
    cache = LocalCacheService()

    with pytest.raises(ValueError, match="at least one filter must be provided"):
        cache.pop_where()


@pytest.mark.asyncio
async def test_local_cache_pop_where_cancels_matching_inflight_tasks():
    cache = LocalCacheService()
    gate = asyncio.Event()
    cache.set("session:stable", "ready")

    async def factory() -> str:
        await gate.wait()
        return "pending-ready"

    task = asyncio.create_task(cache.get_or_set_async("session:pending", factory))
    await asyncio.sleep(0)

    popped = cache.pop_where(prefix="session:")
    gate.set()

    assert popped == {"session:stable": "ready"}
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cache.get("session:pending") is None


def test_local_cache_prune_expired_removes_only_expired_entries():
    cache = LocalCacheService()
    cache.set("short", "x", ttl_seconds=1)
    cache.set("long", "y", ttl_seconds=10)
    cache.set("persistent", "z")

    time.sleep(1.05)

    removed = cache.prune_expired()

    assert removed == 1
    assert cache.get("short") is None
    assert cache.get("long") == "y"
    assert cache.get("persistent") == "z"


def test_local_cache_prune_expired_returns_zero_when_no_entries_expire():
    cache = LocalCacheService()
    cache.set("persistent", "value")

    assert cache.prune_expired() == 0


def test_local_cache_list_keys_supports_prefix_pattern_and_limit():
    cache = LocalCacheService()
    cache.set_many(
        {
            "session:alpha": 1,
            "session:beta": 2,
            "session:gamma": 3,
            "user:delta": 4,
        }
    )

    assert cache.list_keys(prefix="session:") == [
        "session:alpha",
        "session:beta",
        "session:gamma",
    ]
    assert cache.list_keys(pattern="*:beta") == ["session:beta"]
    assert cache.list_keys(prefix="session:", pattern="session:g*") == ["session:gamma"]
    assert cache.list_keys(prefix="session:", limit=2) == [
        "session:alpha",
        "session:beta",
    ]


def test_local_cache_list_keys_supports_offset_and_limit_after_sorting():
    cache = LocalCacheService()
    cache.set_many(
        {
            "alpha": 1,
            "beta": 2,
            "gamma": 3,
            "delta": 4,
        }
    )

    assert cache.list_keys(offset=0) == ["alpha", "beta", "delta", "gamma"]
    assert cache.list_keys(offset=2) == ["delta", "gamma"]
    assert cache.list_keys(offset=1, limit=2) == ["beta", "delta"]
    assert cache.list_keys(offset=10) == []


def test_local_cache_list_keys_supports_descending_sort_order():
    cache = LocalCacheService()
    cache.set_many(
        {
            "alpha": 1,
            "beta": 2,
            "gamma": 3,
            "delta": 4,
        }
    )

    assert cache.list_keys(descending=True) == ["gamma", "delta", "beta", "alpha"]
    assert cache.list_keys(descending=True, offset=1, limit=2) == ["delta", "beta"]


def test_local_cache_list_keys_supports_tag_filters_with_any_or_all_matching():
    cache = LocalCacheService()
    cache.set_tagged("alpha", 1, tags=["group:a", "shared"])
    cache.set_tagged("beta", 2, tags=["group:b"])
    cache.set_tagged("gamma", 3, tags=["group:b", "shared"])

    assert cache.list_keys(tags=["group:b"]) == ["beta", "gamma"]
    assert cache.list_keys(tags=["group:b", "shared"]) == ["alpha", "beta", "gamma"]
    assert cache.list_keys(tags=["group:b", "shared"], match_all_tags=True) == ["gamma"]


def test_local_cache_list_keys_supports_tag_filters_with_prefix_pattern_and_limit():
    cache = LocalCacheService()
    cache.set_tagged("session:alpha", 1, tags=["session", "active"])
    cache.set_tagged("session:beta", 2, tags=["session"])
    cache.set_tagged("user:gamma", 3, tags=["active"])

    assert cache.list_keys(tags=["active"], prefix="session:") == ["session:alpha"]
    assert cache.list_keys(tags=["session"], pattern="*:beta") == ["session:beta"]
    assert cache.list_keys(tags=["session", "active"], limit=1) == ["session:alpha"]


def test_local_cache_list_keys_rejects_invalid_match_all_tags_flag():
    cache = LocalCacheService()

    with pytest.raises(ValueError, match="match_all_tags must be a boolean"):
        cache.list_keys(match_all_tags="yes")  # type: ignore[arg-type]


def test_local_cache_list_keys_rejects_non_boolean_descending_flag():
    cache = LocalCacheService()

    with pytest.raises(ValueError, match="descending must be a boolean"):
        cache.list_keys(descending="yes")  # type: ignore[arg-type]


def test_local_cache_list_keys_rejects_non_string_tags():
    cache = LocalCacheService()
    cache.set_tagged("safe", "value", tags=["ok"])

    with pytest.raises(TypeError, match="tags must contain only strings"):
        cache.list_keys(tags=["ok", 123])  # type: ignore[list-item]


def test_local_cache_list_keys_ignores_expired_tagged_keys():
    cache = LocalCacheService()
    cache.set_tagged("short", "x", tags=["volatile"], ttl_seconds=1)
    cache.set_tagged("stable", "y", tags=["volatile"])

    time.sleep(1.05)

    assert cache.list_keys(tags=["volatile"]) == ["stable"]


def test_local_cache_list_keys_rejects_non_positive_limit():
    cache = LocalCacheService()

    with pytest.raises(ValueError, match="limit must be greater than 0"):
        cache.list_keys(limit=0)


def test_local_cache_list_keys_rejects_negative_offset():
    cache = LocalCacheService()

    with pytest.raises(ValueError, match="offset must be greater than or equal to 0"):
        cache.list_keys(offset=-1)


def test_local_cache_list_entries_includes_ttl_metadata_and_optional_values():
    cache = LocalCacheService()
    cache.set("persistent", {"v": 1})
    cache.set("temporary", "value", ttl_seconds=2)

    without_values = cache.list_entries()
    assert [entry["key"] for entry in without_values] == ["persistent", "temporary"]
    assert all("value" not in entry for entry in without_values)

    with_values = cache.list_entries(include_values=True)
    assert with_values[0]["value"] == {"v": 1}
    assert with_values[0]["ttl_seconds"] is None
    assert with_values[1]["value"] == "value"
    assert with_values[1]["ttl_seconds"] is not None
    assert 0 < with_values[1]["ttl_seconds"] <= 2


def test_local_cache_list_entries_supports_offset_and_limit_after_filtering():
    cache = LocalCacheService()
    cache.set_many(
        {
            "session:alpha": {"v": 1},
            "session:beta": {"v": 2},
            "session:delta": {"v": 4},
            "session:gamma": {"v": 3},
            "user:zeta": {"v": 26},
        }
    )

    entries = cache.list_entries(
        prefix="session:", offset=1, limit=2, include_values=True
    )

    assert entries == [
        {"key": "session:beta", "ttl_seconds": None, "value": {"v": 2}},
        {"key": "session:delta", "ttl_seconds": None, "value": {"v": 4}},
    ]


def test_local_cache_list_entries_supports_descending_sort_order():
    cache = LocalCacheService()
    cache.set_many(
        {
            "session:alpha": {"v": 1},
            "session:beta": {"v": 2},
            "session:delta": {"v": 4},
            "session:gamma": {"v": 3},
        }
    )

    entries = cache.list_entries(
        prefix="session:",
        descending=True,
        offset=1,
        limit=2,
        include_values=True,
    )

    assert entries == [
        {"key": "session:delta", "ttl_seconds": None, "value": {"v": 4}},
        {"key": "session:beta", "ttl_seconds": None, "value": {"v": 2}},
    ]


def test_local_cache_list_entries_can_include_tags_and_absolute_expiration():
    cache = LocalCacheService()
    cache.set_tagged("persistent", {"v": 1}, tags=["stable", "alpha"])
    cache.set_tagged("temporary", "value", tags=["volatile"], ttl_seconds=2)

    entries = cache.list_entries(include_entry_tags=True, include_expires_at=True)

    assert entries[0]["key"] == "persistent"
    assert entries[0]["tags"] == ["alpha", "stable"]
    assert entries[0]["expires_at"] is None

    assert entries[1]["key"] == "temporary"
    assert entries[1]["tags"] == ["volatile"]
    assert entries[1]["expires_at"] is not None
    assert entries[1]["ttl_seconds"] is not None
    assert 0 < entries[1]["ttl_seconds"] <= 2


def test_local_cache_list_entries_supports_tag_filters():
    cache = LocalCacheService()
    cache.set_tagged("session:alpha", {"v": 1}, tags=["session", "active"])
    cache.set_tagged("session:beta", {"v": 2}, tags=["session"])
    cache.set_tagged("user:gamma", {"v": 3}, tags=["active"])

    filtered = cache.list_entries(
        tags=["active"], prefix="session:", include_values=True
    )

    assert filtered == [
        {
            "key": "session:alpha",
            "ttl_seconds": None,
            "value": {"v": 1},
        }
    ]

    all_tagged = cache.list_entries(
        tags=["session", "active"],
        match_all_tags=True,
    )
    assert [entry["key"] for entry in all_tagged] == ["session:alpha"]


def test_local_cache_list_entries_rejects_negative_offset():
    cache = LocalCacheService()

    with pytest.raises(ValueError, match="offset must be greater than or equal to 0"):
        cache.list_entries(offset=-1)


def test_local_cache_list_entries_ignores_expired_keys():
    cache = LocalCacheService()
    cache.set("expired", "x", ttl_seconds=1)
    cache.set("active", "y")

    time.sleep(1.05)

    entries = cache.list_entries(include_values=True)
    assert entries == [{"key": "active", "ttl_seconds": None, "value": "y"}]


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


def test_local_cache_stats_track_hits_misses_and_mutations():
    cache = LocalCacheService()

    cache.set("alpha", 1)
    assert cache.get("alpha") == 1
    assert cache.get("missing") is None
    assert cache.has("alpha") is True
    assert cache.has("missing") is False
    assert cache.get_or_set("alpha", lambda: 99) == 1
    assert cache.get_or_set("beta", lambda: 2) == 2

    stats = cache.stats()

    assert stats["sets"] == 2
    assert stats["hits"] == 3
    assert stats["misses"] == 3
    assert stats["lookups"] == 6
    assert stats["hit_rate"] == pytest.approx(0.5)
    assert stats["miss_rate"] == pytest.approx(0.5)
    assert stats["entries"] == 2


def test_local_cache_stats_lookup_rates_default_to_zero_without_lookups():
    cache = LocalCacheService()

    cache.set("alpha", 1)
    stats = cache.stats()

    assert stats["lookups"] == 0
    assert stats["hit_rate"] == 0.0
    assert stats["miss_rate"] == 0.0


def test_local_cache_stats_include_set_if_absent_and_pop_lookups():
    cache = LocalCacheService()

    assert cache.set_if_absent("key", "value") is True
    assert cache.set_if_absent("key", "ignored") is False
    assert cache.pop("key") == "value"
    assert cache.pop("key") is None

    stats = cache.stats()

    assert stats["sets"] == 1
    assert stats["deletes"] == 1
    assert stats["hits"] == 2
    assert stats["misses"] == 2


def test_local_cache_stats_track_expirations_and_evictions():
    cache = LocalCacheService(max_entries=1)

    cache.set("temp", "x", ttl_seconds=1)
    time.sleep(1.05)
    assert cache.get("temp") is None

    cache.set("a", 1)
    cache.set("b", 2)

    stats = cache.stats()

    assert stats["expirations"] == 1
    assert stats["evictions"] == 1


def test_local_cache_stats_can_be_reset_without_touching_entries():
    cache = LocalCacheService()
    cache.set("persist", "value")
    assert cache.get("missing") is None

    snapshot = cache.stats(reset=True)

    assert snapshot["sets"] == 1
    assert snapshot["misses"] == 1
    assert snapshot["entries"] == 1

    reset_stats = cache.stats()
    assert reset_stats["sets"] == 0
    assert reset_stats["misses"] == 0
    assert reset_stats["entries"] == 1


@pytest.mark.asyncio
async def test_local_cache_delete_cancels_inflight_population():
    cache = LocalCacheService()
    gate = asyncio.Event()

    async def _factory() -> str:
        await gate.wait()
        return "value"

    task = asyncio.create_task(cache.get_or_set_async("session:key", _factory))
    await asyncio.sleep(0)

    cache.delete("session:key")
    gate.set()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert cache.get("session:key") is None


@pytest.mark.asyncio
async def test_local_cache_clear_cancels_all_inflight_population():
    cache = LocalCacheService()
    gate = asyncio.Event()

    async def _factory_one() -> str:
        await gate.wait()
        return "one"

    async def _factory_two() -> str:
        await gate.wait()
        return "two"

    task_one = asyncio.create_task(cache.get_or_set_async("k1", _factory_one))
    task_two = asyncio.create_task(cache.get_or_set_async("k2", _factory_two))
    await asyncio.sleep(0)

    cache.clear()
    gate.set()

    with pytest.raises(asyncio.CancelledError):
        await task_one
    with pytest.raises(asyncio.CancelledError):
        await task_two

    assert cache.get("k1") is None
    assert cache.get("k2") is None


def test_local_cache_export_state_includes_active_entries_with_ttl_and_tags():
    cache = LocalCacheService()
    cache.set_tagged("profile", {"name": "Agent"}, tags=["user", "active"])
    cache.set("session", "token", ttl_seconds=2)
    cache.set("expired", "gone", ttl_seconds=1)

    time.sleep(1.05)

    snapshot = cache.export_state()

    assert snapshot["max_entries"] is None
    assert [entry["key"] for entry in snapshot["entries"]] == [
        "profile",
        "session",
    ]

    profile_entry = snapshot["entries"][0]
    assert profile_entry == {
        "key": "profile",
        "value": {"name": "Agent"},
        "ttl_seconds": None,
        "tags": ["active", "user"],
    }

    session_entry = snapshot["entries"][1]
    assert session_entry["key"] == "session"
    assert session_entry["value"] == "token"
    assert session_entry["tags"] == []
    assert session_entry["ttl_seconds"] is not None
    assert 0 < session_entry["ttl_seconds"] <= 2


def test_local_cache_export_state_supports_filters_and_pagination():
    cache = LocalCacheService()
    cache.set_tagged("session:alpha", 1, tags=["session", "active"])
    cache.set_tagged("session:beta", 2, tags=["session"])
    cache.set_tagged("user:alpha", 3, tags=["user", "active"])

    filtered = cache.export_state(
        tags=["active"],
        pattern="*:alpha",
        include_stats=True,
    )

    assert [entry["key"] for entry in filtered["entries"]] == [
        "session:alpha",
        "user:alpha",
    ]
    assert "stats" in filtered

    paginated = cache.export_state(prefix="session:", offset=1, limit=1)
    assert [entry["key"] for entry in paginated["entries"]] == ["session:beta"]

    descending = cache.export_state(prefix="session:", descending=True)
    assert [entry["key"] for entry in descending["entries"]] == [
        "session:beta",
        "session:alpha",
    ]

    match_all = cache.export_state(
        tags=["session", "active"],
        match_all_tags=True,
    )
    assert [entry["key"] for entry in match_all["entries"]] == ["session:alpha"]


def test_local_cache_export_state_validates_filter_arguments():
    cache = LocalCacheService()
    cache.set("alpha", 1)

    with pytest.raises(ValueError, match="offset must be greater than or equal to 0"):
        cache.export_state(offset=-1)

    with pytest.raises(ValueError, match="limit must be greater than 0"):
        cache.export_state(limit=0)

    with pytest.raises(ValueError, match="match_all_tags must be a boolean"):
        cache.export_state(match_all_tags="yes")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="descending must be a boolean"):
        cache.export_state(descending="yes")  # type: ignore[arg-type]


def test_local_cache_import_state_restores_entries_and_can_clear_existing_data():
    source = LocalCacheService(max_entries=10)
    source.set_tagged("user:1", {"name": "Ada"}, tags=["user", "vip"])
    source.set("session:1", "token", ttl_seconds=2)

    snapshot = source.export_state(include_stats=True)

    target = LocalCacheService(max_entries=10)
    target.set("stale", True)

    imported = target.import_state(snapshot, clear_existing=True)

    assert imported == 2
    assert target.get("stale") is None
    assert target.get("user:1") == {"name": "Ada"}
    assert target.list_tags("user:1") == ["user", "vip"]
    assert target.get("session:1") == "token"

    remaining_ttl = target.ttl_remaining("session:1")
    assert remaining_ttl is not None
    assert 0 < remaining_ttl <= 2


def test_local_cache_import_state_validates_snapshot_shape():
    cache = LocalCacheService()

    with pytest.raises(TypeError, match="mapping"):
        cache.import_state([])  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="entries"):
        cache.import_state({})

    with pytest.raises(TypeError, match="iterable"):
        cache.import_state({"entries": "invalid"})

    with pytest.raises(ValueError, match="non-empty string"):
        cache.import_state({"entries": [{"key": "", "value": 1}]})

    with pytest.raises(TypeError, match="tags"):
        cache.import_state(
            {
                "entries": [
                    {
                        "key": "alpha",
                        "value": 1,
                        "tags": "not-iterable",
                    }
                ]
            }
        )


def test_local_cache_import_state_can_restore_exported_stats():
    source = LocalCacheService(max_entries=10)
    source.set("alpha", 1)
    source.get("alpha")
    source.get("missing")

    snapshot = source.export_state(include_stats=True)

    target = LocalCacheService(max_entries=10)
    target.set("stale", True)
    target.get("stale")
    target.get("other-miss")

    imported = target.import_state(
        snapshot,
        clear_existing=True,
        restore_stats=True,
    )

    assert imported == 1
    restored_stats = target.stats()
    for stat_name in (
        "hits",
        "misses",
        "sets",
        "deletes",
        "evictions",
        "expirations",
    ):
        assert restored_stats[stat_name] == snapshot["stats"][stat_name]


def test_local_cache_import_state_restore_stats_requires_valid_stats_payload():
    cache = LocalCacheService()

    with pytest.raises(ValueError, match="restore_stats must be a boolean"):
        cache.import_state({"entries": []}, restore_stats="yes")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="stats"):
        cache.import_state(
            {"entries": [{"key": "alpha", "value": 1}]},
            restore_stats=True,
        )

    with pytest.raises(TypeError, match="snapshot stats field 'hits'"):
        cache.import_state(
            {"entries": [], "stats": {"hits": "bad"}},
            restore_stats=True,
        )

    with pytest.raises(
        ValueError, match="snapshot stats field 'hits' must be non-negative"
    ):
        cache.import_state(
            {"entries": [], "stats": {"hits": -1}},
            restore_stats=True,
        )
