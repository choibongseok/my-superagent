"""Tests for DuckDuckGoSearchTool."""

from __future__ import annotations

import pytest

from app.tools.web_search import DuckDuckGoSearchTool


class _FakeSearchBackend:
    """Small test double for DuckDuckGoSearchRun."""

    def __init__(self, response: object = "ok") -> None:
        self.response = response
        self.queries: list[str] = []

    def run(self, query: str) -> object:
        self.queries.append(query)
        return self.response


class _SequencedSearchBackend:
    """Returns deterministic sequential responses for repeated calls."""

    def __init__(self, responses: list[object]) -> None:
        self.responses = list(responses)
        self.queries: list[str] = []

    def run(self, query: str) -> object:
        self.queries.append(query)
        if not self.responses:
            raise AssertionError("No more fake responses configured")
        return self.responses.pop(0)


class _FailingSearchBackend:
    """Raises deterministic errors to test failure handling paths."""

    def __init__(self, message: str = "backend offline") -> None:
        self.message = message
        self.queries: list[str] = []

    def run(self, query: str) -> object:
        self.queries.append(query)
        raise RuntimeError(self.message)


class _FlakySearchBackend:
    """Fails for the first N calls, then returns a stable success payload."""

    def __init__(
        self, *, failures_before_success: int, success_payload: object
    ) -> None:
        self.failures_before_success = failures_before_success
        self.success_payload = success_payload
        self.queries: list[str] = []

    def run(self, query: str) -> object:
        self.queries.append(query)
        if len(self.queries) <= self.failures_before_success:
            raise RuntimeError("transient outage")
        return self.success_payload


def test_init_rejects_invalid_max_result_chars():
    """Result-length guard should only allow positive integers or None."""
    with pytest.raises(
        ValueError,
        match="max_result_chars must be a positive integer or None",
    ):
        DuckDuckGoSearchTool(max_result_chars=0)

    with pytest.raises(
        ValueError,
        match="max_result_chars must be a positive integer or None",
    ):
        DuckDuckGoSearchTool(max_result_chars=True)  # type: ignore[arg-type]

    with pytest.raises(
        ValueError,
        match="max_result_chars must be a positive integer or None",
    ):
        DuckDuckGoSearchTool(max_result_chars=12.5)  # type: ignore[arg-type]


def test_init_rejects_invalid_max_query_length():
    """Query-length guards should only allow positive integers or None."""
    with pytest.raises(
        ValueError,
        match="max_query_length must be a positive integer or None",
    ):
        DuckDuckGoSearchTool(max_query_length=0)

    with pytest.raises(
        ValueError,
        match="max_query_length must be a positive integer or None",
    ):
        DuckDuckGoSearchTool(max_query_length=True)  # type: ignore[arg-type]

    with pytest.raises(
        ValueError,
        match="max_query_length must be a positive integer or None",
    ):
        DuckDuckGoSearchTool(max_query_length=10.5)  # type: ignore[arg-type]


def test_init_rejects_invalid_max_batch_queries():
    """Batch-size guard should only allow positive integers or None."""
    with pytest.raises(
        ValueError,
        match="max_batch_queries must be a positive integer or None",
    ):
        DuckDuckGoSearchTool(max_batch_queries=0)

    with pytest.raises(
        ValueError,
        match="max_batch_queries must be a positive integer or None",
    ):
        DuckDuckGoSearchTool(max_batch_queries=True)  # type: ignore[arg-type]

    with pytest.raises(
        ValueError,
        match="max_batch_queries must be a positive integer or None",
    ):
        DuckDuckGoSearchTool(max_batch_queries=10.5)  # type: ignore[arg-type]


def test_init_rejects_invalid_cache_options():
    """Cache guards should enforce positive TTL and positive entry caps."""
    with pytest.raises(
        ValueError,
        match="cache_ttl_seconds must be a positive number or None",
    ):
        DuckDuckGoSearchTool(cache_ttl_seconds=0)

    with pytest.raises(
        ValueError,
        match="cache_ttl_seconds must be a positive number or None",
    ):
        DuckDuckGoSearchTool(cache_ttl_seconds=True)  # type: ignore[arg-type]

    with pytest.raises(
        ValueError,
        match="cache_max_entries must be a positive integer",
    ):
        DuckDuckGoSearchTool(cache_max_entries=0)

    with pytest.raises(
        ValueError,
        match="cache_max_entries must be a positive integer",
    ):
        DuckDuckGoSearchTool(cache_max_entries=10.5)  # type: ignore[arg-type]

    with pytest.raises(
        ValueError,
        match="stale_cache_ttl_seconds must be a positive number or None",
    ):
        DuckDuckGoSearchTool(stale_cache_ttl_seconds=0)

    with pytest.raises(
        ValueError,
        match="stale_cache_ttl_seconds must be a positive number or None",
    ):
        DuckDuckGoSearchTool(stale_cache_ttl_seconds=True)  # type: ignore[arg-type]


def test_init_rejects_invalid_retry_options():
    """Retry guards should enforce non-negative integers/floats."""
    with pytest.raises(
        ValueError,
        match="retry_attempts must be a non-negative integer",
    ):
        DuckDuckGoSearchTool(retry_attempts=-1)

    with pytest.raises(
        ValueError,
        match="retry_attempts must be a non-negative integer",
    ):
        DuckDuckGoSearchTool(retry_attempts=1.5)  # type: ignore[arg-type]

    with pytest.raises(
        ValueError,
        match="retry_backoff_seconds must be a non-negative number",
    ):
        DuckDuckGoSearchTool(retry_backoff_seconds=-0.1)

    with pytest.raises(
        ValueError,
        match="retry_backoff_seconds must be a non-negative number",
    ):
        DuckDuckGoSearchTool(retry_backoff_seconds=True)  # type: ignore[arg-type]


def test_init_rejects_invalid_cache_case_sensitive_option():
    """cache_case_sensitive should accept only boolean values."""
    with pytest.raises(
        ValueError,
        match="cache_case_sensitive must be a boolean value",
    ):
        DuckDuckGoSearchTool(cache_case_sensitive="false")  # type: ignore[arg-type]


def test_run_normalizes_query_and_returns_backend_results(monkeypatch):
    """_run should normalize whitespace before delegating to backend."""
    fake_backend = _FakeSearchBackend(response="result payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(max_result_chars=None)

    result = tool._run("  agentic\n\t workflow   ")

    assert result == "result payload"
    assert fake_backend.queries == ["agentic workflow"]


def test_run_retries_transient_failures_before_returning_success(monkeypatch):
    """Retry configuration should recover from transient backend errors."""
    fake_backend = _FlakySearchBackend(
        failures_before_success=2,
        success_payload="eventual payload",
    )
    sleep_calls: list[float] = []

    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )
    monkeypatch.setattr("app.tools.web_search.time.sleep", sleep_calls.append)

    tool = DuckDuckGoSearchTool(
        retry_attempts=2,
        retry_backoff_seconds=0.25,
        cache_ttl_seconds=None,
    )

    result = tool._run("agent retries")

    assert result == "eventual payload"
    assert fake_backend.queries == ["agent retries", "agent retries", "agent retries"]
    assert sleep_calls == [0.25, 0.5]


def test_run_uses_cache_for_normalized_duplicate_queries(monkeypatch):
    """Equivalent normalized queries should reuse cached responses."""
    fake_backend = _SequencedSearchBackend(["first payload", "second payload"])
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=60, cache_max_entries=16)

    first = tool._run("   agentic   workflow")
    second = tool._run("agentic\nworkflow   ")

    assert first == "first payload"
    assert second == "first payload"
    assert fake_backend.queries == ["agentic workflow"]


def test_run_cache_case_sensitivity_is_configurable(monkeypatch):
    """cache_case_sensitive should control cache reuse across casing variants."""
    fake_backend = _SequencedSearchBackend(
        [
            "sensitive-first",
            "sensitive-second",
            "insensitive-first",
            "insensitive-second",
        ]
    )
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    sensitive_tool = DuckDuckGoSearchTool(
        cache_ttl_seconds=60,
        cache_max_entries=16,
        cache_case_sensitive=True,
    )
    insensitive_tool = DuckDuckGoSearchTool(
        cache_ttl_seconds=60,
        cache_max_entries=16,
        cache_case_sensitive=False,
    )

    assert sensitive_tool._run("News AI") == "sensitive-first"
    assert sensitive_tool._run("news ai") == "sensitive-second"

    assert insensitive_tool._run("News AI") == "insensitive-first"
    assert insensitive_tool._run("news ai") == "insensitive-first"

    assert fake_backend.queries == ["News AI", "news ai", "News AI"]


def test_run_cache_entry_expires_after_ttl(monkeypatch):
    """Expired cache entries should trigger a fresh backend search."""
    fake_backend = _SequencedSearchBackend(["v1", "v2"])
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    now = {"value": 100.0}
    monkeypatch.setattr("app.tools.web_search.time.monotonic", lambda: now["value"])

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=5, cache_max_entries=16)

    first = tool._run("agent")
    now["value"] = 103.0
    second = tool._run("agent")
    now["value"] = 106.0
    third = tool._run("agent")

    assert first == "v1"
    assert second == "v1"
    assert third == "v2"
    assert fake_backend.queries == ["agent", "agent"]


def test_run_returns_stale_cache_when_backend_fails(monkeypatch):
    """Expired entries can be reused when backend lookup fails within stale window."""
    priming_backend = _FakeSearchBackend(response="fresh snapshot")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: priming_backend,
    )

    now = {"value": 50.0}
    monkeypatch.setattr("app.tools.web_search.time.monotonic", lambda: now["value"])

    tool = DuckDuckGoSearchTool(
        cache_ttl_seconds=5,
        cache_max_entries=16,
        stale_cache_ttl_seconds=60,
    )

    assert tool._run("agent") == "fresh snapshot"

    now["value"] = 60.0
    tool._search = _FailingSearchBackend(message="upstream timeout")

    result = tool._run("agent")

    assert result.startswith("fresh snapshot")
    assert "[stale cache fallback due to search error: upstream timeout]" in result


def test_run_stale_cache_fallback_after_retry_exhaustion(monkeypatch):
    """Stale cache fallback should kick in after all retries fail."""
    priming_backend = _FakeSearchBackend(response="fresh snapshot")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: priming_backend,
    )

    now = {"value": 10.0}
    monkeypatch.setattr("app.tools.web_search.time.monotonic", lambda: now["value"])

    tool = DuckDuckGoSearchTool(
        cache_ttl_seconds=5,
        cache_max_entries=16,
        stale_cache_ttl_seconds=40,
        retry_attempts=2,
    )
    assert tool._run("agent") == "fresh snapshot"

    now["value"] = 20.0
    failing_backend = _FailingSearchBackend(message="still down")
    tool._search = failing_backend

    result = tool._run("agent")

    assert result.startswith("fresh snapshot")
    assert "[stale cache fallback due to search error: still down]" in result
    assert failing_backend.queries == ["agent", "agent", "agent"]


def test_run_stale_cache_window_expiry_returns_error(monkeypatch):
    """Stale fallback should be skipped once the stale window has elapsed."""
    priming_backend = _FakeSearchBackend(response="fresh snapshot")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: priming_backend,
    )

    now = {"value": 10.0}
    monkeypatch.setattr("app.tools.web_search.time.monotonic", lambda: now["value"])

    tool = DuckDuckGoSearchTool(
        cache_ttl_seconds=5,
        cache_max_entries=16,
        stale_cache_ttl_seconds=20,
    )

    assert tool._run("agent") == "fresh snapshot"

    now["value"] = 40.0
    tool._search = _FailingSearchBackend(message="service unavailable")

    result = tool._run("agent")

    assert result == "Search failed: service unavailable"


def test_run_cache_evicts_oldest_entry_when_capacity_exceeded(monkeypatch):
    """Cache should evict least-recently-used queries when full."""
    fake_backend = _SequencedSearchBackend(["alpha-1", "beta-1", "alpha-2"])
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    now = {"value": 10.0}
    monkeypatch.setattr("app.tools.web_search.time.monotonic", lambda: now["value"])

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=300, cache_max_entries=1)

    assert tool._run("alpha") == "alpha-1"
    now["value"] = 11.0
    assert tool._run("beta") == "beta-1"
    now["value"] = 12.0
    assert tool._run("alpha") == "alpha-2"

    assert fake_backend.queries == ["alpha", "beta", "alpha"]


def test_invalidate_cache_removes_normalized_query_entries(monkeypatch):
    """invalidate_cache should target normalized query keys when provided."""
    fake_backend = _SequencedSearchBackend(["alpha-1", "alpha-2"])
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=300, cache_max_entries=16)

    assert tool._run("  alpha\nquery  ") == "alpha-1"
    assert tool._run("alpha query") == "alpha-1"

    assert tool.invalidate_cache(" alpha\tquery ") == 1
    assert tool.invalidate_cache("alpha query") == 0

    assert tool._run("alpha query") == "alpha-2"
    assert fake_backend.queries == ["alpha query", "alpha query"]


def test_invalidate_cache_rejects_multiple_selectors(monkeypatch):
    """Only one invalidate selector should be accepted per call."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=300, cache_max_entries=16)

    with pytest.raises(ValueError, match="mutually exclusive"):
        tool.invalidate_cache("alpha", prefix="a")

    with pytest.raises(ValueError, match="mutually exclusive"):
        tool.invalidate_cache(prefix="a", pattern="a*")

    with pytest.raises(ValueError, match="mutually exclusive"):
        tool.invalidate_cache(queries=["alpha"], pattern="a*")

    with pytest.raises(ValueError, match="mutually exclusive"):
        tool.invalidate_cache(pattern="a*", regex="a.*")

    with pytest.raises(ValueError, match="mutually exclusive"):
        tool.invalidate_cache(contains="alpha", prefix="a")

    with pytest.raises(ValueError, match="mutually exclusive"):
        tool.invalidate_cache(suffix="alpha", pattern="*alpha")

    with pytest.raises(ValueError, match="mutually exclusive"):
        tool.invalidate_cache(query="alpha", older_than_seconds=10)

    with pytest.raises(ValueError, match="mutually exclusive"):
        tool.invalidate_cache(status="expired", pattern="*alpha*")

    with pytest.raises(ValueError, match="mutually exclusive"):
        tool.invalidate_cache(older_than_seconds=10, younger_than_seconds=5)


def test_invalidate_cache_rejects_invalid_older_than_selector(monkeypatch):
    """Age selector should accept only positive numeric values."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=300, cache_max_entries=16)

    with pytest.raises(
        ValueError, match="older_than_seconds must be a positive number"
    ):
        tool.invalidate_cache(older_than_seconds=0)

    with pytest.raises(
        ValueError, match="older_than_seconds must be a positive number"
    ):
        tool.invalidate_cache(older_than_seconds=-1)

    with pytest.raises(
        ValueError, match="older_than_seconds must be a positive number"
    ):
        tool.invalidate_cache(older_than_seconds=True)  # type: ignore[arg-type]

    with pytest.raises(
        ValueError, match="older_than_seconds must be a positive number"
    ):
        tool.invalidate_cache(older_than_seconds="10")  # type: ignore[arg-type]


def test_invalidate_cache_rejects_invalid_younger_than_selector(monkeypatch):
    """Young-age selector should accept only positive numeric values."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=300, cache_max_entries=16)

    with pytest.raises(
        ValueError, match="younger_than_seconds must be a positive number"
    ):
        tool.invalidate_cache(younger_than_seconds=0)

    with pytest.raises(
        ValueError, match="younger_than_seconds must be a positive number"
    ):
        tool.invalidate_cache(younger_than_seconds=-1)

    with pytest.raises(
        ValueError, match="younger_than_seconds must be a positive number"
    ):
        tool.invalidate_cache(younger_than_seconds=True)  # type: ignore[arg-type]

    with pytest.raises(
        ValueError, match="younger_than_seconds must be a positive number"
    ):
        tool.invalidate_cache(younger_than_seconds="10")  # type: ignore[arg-type]


def test_invalidate_cache_rejects_invalid_limit_selector(monkeypatch):
    """limit should accept only positive integer values when provided."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=300, cache_max_entries=16)

    with pytest.raises(ValueError, match="limit must be a positive integer"):
        tool.invalidate_cache(limit=0)

    with pytest.raises(ValueError, match="limit must be a positive integer"):
        tool.invalidate_cache(limit=-1)

    with pytest.raises(ValueError, match="limit must be a positive integer"):
        tool.invalidate_cache(limit=True)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="limit must be a positive integer"):
        tool.invalidate_cache(limit=1.5)  # type: ignore[arg-type]


def test_invalidate_cache_can_remove_entries_older_than_threshold(monkeypatch):
    """Age selector should evict cache entries above the provided age threshold."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    now = {"value": 100.0}
    monkeypatch.setattr("app.tools.web_search.time.monotonic", lambda: now["value"])

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=300, cache_max_entries=16)
    tool._cache["fresh"] = (96.0, "fresh")
    tool._cache["stale"] = (90.0, "stale")
    tool._cache["older"] = (70.0, "older")

    removed_entries = tool.invalidate_cache(older_than_seconds=8)

    assert removed_entries == 2
    assert list(tool._cache.keys()) == ["fresh"]


def test_invalidate_cache_can_remove_entries_younger_than_threshold(monkeypatch):
    """Young-age selector should evict entries below the provided age threshold."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    now = {"value": 100.0}
    monkeypatch.setattr("app.tools.web_search.time.monotonic", lambda: now["value"])

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=300, cache_max_entries=16)
    tool._cache["fresh"] = (99.0, "fresh")
    tool._cache["warm"] = (95.0, "warm")
    tool._cache["stale"] = (80.0, "stale")

    removed_entries = tool.invalidate_cache(younger_than_seconds=6)

    assert removed_entries == 2
    assert list(tool._cache.keys()) == ["stale"]


def test_invalidate_cache_can_remove_entries_by_status(monkeypatch):
    """Status selector should remove entries matching freshness classifications."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    now = {"value": 200.0}
    monkeypatch.setattr("app.tools.web_search.time.monotonic", lambda: now["value"])

    tool = DuckDuckGoSearchTool(
        cache_ttl_seconds=10,
        cache_max_entries=16,
        stale_cache_ttl_seconds=30,
    )
    tool._cache["active query"] = (195.0, "a")
    tool._cache["stale query"] = (180.0, "b")
    tool._cache["expired query"] = (150.0, "c")

    removed_entries = tool.invalidate_cache(status="expired")

    assert removed_entries == 1
    assert list(tool._cache.keys()) == ["active query", "stale query"]


def test_invalidate_cache_status_selector_supports_iterables(monkeypatch):
    """Status selector should support multiple statuses in one call."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    now = {"value": 200.0}
    monkeypatch.setattr("app.tools.web_search.time.monotonic", lambda: now["value"])

    tool = DuckDuckGoSearchTool(
        cache_ttl_seconds=10,
        cache_max_entries=16,
        stale_cache_ttl_seconds=30,
    )
    tool._cache["active query"] = (195.0, "a")
    tool._cache["stale query"] = (180.0, "b")
    tool._cache["expired query"] = (150.0, "c")

    removed_entries = tool.invalidate_cache(status=["ACTIVE", "stale_eligible"])

    assert removed_entries == 2
    assert list(tool._cache.keys()) == ["expired query"]


def test_invalidate_cache_rejects_invalid_status_selector(monkeypatch):
    """Status selector should reject unsupported cache-state values."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=60, cache_max_entries=16)

    with pytest.raises(
        ValueError,
        match="status must contain only: active, stale_eligible, expired, unbounded",
    ):
        tool.invalidate_cache(status="fresh")


def test_invalidate_cache_limit_caps_age_based_invalidation(monkeypatch):
    """limit should cap older-than invalidation using deterministic cache order."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    now = {"value": 100.0}
    monkeypatch.setattr("app.tools.web_search.time.monotonic", lambda: now["value"])

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=300, cache_max_entries=16)
    tool._cache["stale-one"] = (80.0, "payload-1")
    tool._cache["stale-two"] = (70.0, "payload-2")
    tool._cache["stale-three"] = (60.0, "payload-3")

    removed_entries = tool.invalidate_cache(older_than_seconds=5, limit=2)

    assert removed_entries == 2
    assert list(tool._cache.keys()) == ["stale-three"]


def test_invalidate_cache_limit_caps_full_cache_clear(monkeypatch):
    """limit should allow partial full-cache invalidation without selectors."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=300, cache_max_entries=16)

    assert tool._run("alpha") == "payload"
    assert tool._run("beta") == "payload"
    assert tool._run("gamma") == "payload"

    removed_entries = tool.invalidate_cache(limit=2)

    assert removed_entries == 2
    assert list(tool._cache.keys()) == ["gamma"]


def test_invalidate_cache_newest_first_prioritizes_recent_entries(monkeypatch):
    """newest_first should process most recent cache entries before limit capping."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=300, cache_max_entries=16)

    assert tool._run("alpha") == "payload"
    assert tool._run("beta") == "payload"
    assert tool._run("gamma") == "payload"

    removed_entries = tool.invalidate_cache(limit=2, newest_first=True)

    assert removed_entries == 2
    assert list(tool._cache.keys()) == ["alpha"]


def test_invalidate_cache_limit_respects_dry_run_without_deletion(monkeypatch):
    """dry_run with limit should count only limited matches and keep cache intact."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=300, cache_max_entries=16)

    assert tool._run("alpha one") == "payload"
    assert tool._run("alpha two") == "payload"
    assert tool._run("alpha three") == "payload"

    removed_entries = tool.invalidate_cache(prefix="alpha", limit=2, dry_run=True)

    assert removed_entries == 2
    assert list(tool._cache.keys()) == ["alpha one", "alpha two", "alpha three"]


def test_invalidate_cache_can_remove_multiple_explicit_queries(monkeypatch):
    """Multiple query invalidation should normalize inputs and de-duplicate keys."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=300, cache_max_entries=16)

    assert tool._run("alpha one") == "payload"
    assert tool._run("beta one") == "payload"
    assert tool._run("gamma one") == "payload"

    removed_entries = tool.invalidate_cache(
        queries=[" alpha\none ", "beta\tone", "alpha one"],
    )

    assert removed_entries == 2
    assert list(tool._cache.keys()) == ["gamma one"]


def test_invalidate_cache_rejects_invalid_queries_selector(monkeypatch):
    """Explicit query list selector must be an iterable of non-empty strings."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=300, cache_max_entries=16)

    with pytest.raises(
        ValueError,
        match="queries must be an iterable of non-empty strings",
    ):
        tool.invalidate_cache(queries="alpha")  # type: ignore[arg-type]

    with pytest.raises(
        ValueError,
        match="queries must be an iterable of non-empty strings",
    ):
        tool.invalidate_cache(queries=123)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="query must be a non-empty string"):
        tool.invalidate_cache(queries=["alpha", "   "])


def test_invalidate_cache_can_remove_entries_by_prefix(monkeypatch):
    """Prefix invalidation should remove all matching normalized query keys."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=300, cache_max_entries=16)

    assert tool._run("alpha one") == "payload"
    assert tool._run("alpha two") == "payload"
    assert tool._run("beta one") == "payload"

    removed_entries = tool.invalidate_cache(prefix="  alpha  ")

    assert removed_entries == 2
    assert list(tool._cache.keys()) == ["beta one"]


def test_invalidate_cache_can_remove_entries_by_suffix(monkeypatch):
    """Suffix invalidation should remove all matching normalized query keys."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=300, cache_max_entries=16)

    assert tool._run("weekly ai news") == "payload"
    assert tool._run("breaking ai news") == "payload"
    assert tool._run("weather seoul") == "payload"

    removed_entries = tool.invalidate_cache(suffix=" ai\nnews ")

    assert removed_entries == 2
    assert list(tool._cache.keys()) == ["weather seoul"]


def test_invalidate_cache_can_remove_entries_by_contains(monkeypatch):
    """Contains invalidation should remove keys containing normalized substrings."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=300, cache_max_entries=16)

    assert tool._run("weekly ai news") == "payload"
    assert tool._run("breaking ai update") == "payload"
    assert tool._run("weather seoul") == "payload"

    removed_entries = tool.invalidate_cache(contains=" ai\n")

    assert removed_entries == 2
    assert list(tool._cache.keys()) == ["weather seoul"]


def test_invalidate_cache_can_remove_entries_by_pattern(monkeypatch):
    """Pattern invalidation should support glob matching against query keys."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=300, cache_max_entries=16)

    assert tool._run("news ai") == "payload"
    assert tool._run("news robotics") == "payload"
    assert tool._run("weather seoul") == "payload"

    removed_entries = tool.invalidate_cache(pattern="news *")

    assert removed_entries == 2
    assert list(tool._cache.keys()) == ["weather seoul"]


def test_invalidate_cache_can_remove_entries_by_regex(monkeypatch):
    """Regex invalidation should support flexible normalized key matching."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=300, cache_max_entries=16)

    assert tool._run("news ai") == "payload"
    assert tool._run("news robotics") == "payload"
    assert tool._run("weather seoul") == "payload"

    removed_entries = tool.invalidate_cache(regex=r"^news\s")

    assert removed_entries == 2
    assert list(tool._cache.keys()) == ["weather seoul"]


def test_invalidate_cache_can_remove_entries_by_regex_with_flags(monkeypatch):
    """Regex invalidation should honor optional regex_flags selectors."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=300, cache_max_entries=16)

    assert tool._run("News AI") == "payload"
    assert tool._run("NEWS robotics") == "payload"
    assert tool._run("weather seoul") == "payload"

    removed_entries = tool.invalidate_cache(regex=r"^news\s", regex_flags="I")

    assert removed_entries == 2
    assert list(tool._cache.keys()) == ["weather seoul"]


def test_invalidate_cache_rejects_regex_flags_without_regex(monkeypatch):
    """regex_flags should be accepted only when regex selector is used."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=300, cache_max_entries=16)

    with pytest.raises(
        ValueError,
        match="regex_flags can only be used with regex selector",
    ):
        tool.invalidate_cache(regex_flags="i")


def test_invalidate_cache_rejects_invalid_regex_flags(monkeypatch):
    """regex_flags should reject unsupported flag tokens."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=300, cache_max_entries=16)

    with pytest.raises(
        ValueError,
        match="regex_flags must contain only supported flags: i, m, s, x",
    ):
        tool.invalidate_cache(regex=r"news", regex_flags="izq")


def test_invalidate_cache_rejects_invalid_regex_selector(monkeypatch):
    """Regex selector should fail fast on invalid patterns."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=300, cache_max_entries=16)

    with pytest.raises(
        ValueError,
        match="regex must be a valid regular expression",
    ):
        tool.invalidate_cache(regex="(")


def test_invalidate_cache_clears_full_cache_and_returns_removed_count(monkeypatch):
    """Calling invalidate_cache with no query should clear all entries."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=300, cache_max_entries=16)

    assert tool._run("alpha") == "payload"
    assert tool._run("beta") == "payload"

    removed_entries = tool.invalidate_cache()

    assert removed_entries == 2
    assert tool.get_cache_stats()["entries"] == 0


def test_invalidate_cache_dry_run_reports_matches_without_deletion(monkeypatch):
    """dry_run should count matches while preserving cache entries."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=300, cache_max_entries=16)

    assert tool._run("alpha one") == "payload"
    assert tool._run("beta one") == "payload"

    removed_entries = tool.invalidate_cache(prefix="alpha", dry_run=True)

    assert removed_entries == 1
    assert list(tool._cache.keys()) == ["alpha one", "beta one"]


def test_invalidate_cache_rejects_invalid_dry_run_selector(monkeypatch):
    """dry_run selector should accept only boolean values."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=300, cache_max_entries=16)

    with pytest.raises(ValueError, match="dry_run must be a boolean value"):
        tool.invalidate_cache(dry_run="true")  # type: ignore[arg-type]


def test_invalidate_cache_rejects_invalid_newest_first_selector(monkeypatch):
    """newest_first selector should accept only boolean values."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=300, cache_max_entries=16)

    with pytest.raises(ValueError, match="newest_first must be a boolean value"):
        tool.invalidate_cache(newest_first="true")  # type: ignore[arg-type]


def test_invalidate_cache_rejects_invalid_case_sensitive_selector(monkeypatch):
    """case_sensitive selector should accept only boolean values."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=300, cache_max_entries=16)

    with pytest.raises(ValueError, match="case_sensitive must be a boolean value"):
        tool.invalidate_cache(case_sensitive="false")  # type: ignore[arg-type]


def test_invalidate_cache_case_insensitive_prefix_matching(monkeypatch):
    """case_sensitive=False should match prefix selectors across case variants."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=300, cache_max_entries=16)

    assert tool._run("News AI") == "payload"
    assert tool._run("NEWS robotics") == "payload"
    assert tool._run("weather seoul") == "payload"

    removed_entries = tool.invalidate_cache(prefix="news", case_sensitive=False)

    assert removed_entries == 2
    assert list(tool._cache.keys()) == ["weather seoul"]


def test_invalidate_cache_case_insensitive_regex_matching(monkeypatch):
    """case_sensitive=False should apply ignore-case behavior for regex selectors."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=300, cache_max_entries=16)

    assert tool._run("News AI") == "payload"
    assert tool._run("NEWS robotics") == "payload"
    assert tool._run("weather seoul") == "payload"

    removed_entries = tool.invalidate_cache(
        regex=r"^news\s",
        case_sensitive=False,
    )

    assert removed_entries == 2
    assert list(tool._cache.keys()) == ["weather seoul"]


def test_list_cache_entries_reports_status_and_payload_metadata(monkeypatch):
    """Cache inspection should expose age/status and payload size diagnostics."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    now = {"value": 200.0}
    monkeypatch.setattr("app.tools.web_search.time.monotonic", lambda: now["value"])

    tool = DuckDuckGoSearchTool(
        cache_ttl_seconds=10,
        cache_max_entries=16,
        stale_cache_ttl_seconds=30,
    )

    tool._cache["active query"] = (195.0, "a")
    tool._cache["stale query"] = (180.0, "bb")
    tool._cache["expired query"] = (150.0, "ccc")

    assert tool.list_cache_entries() == [
        {
            "query": "active query",
            "age_seconds": 5.0,
            "status": "active",
            "payload_chars": 1,
        },
        {
            "query": "stale query",
            "age_seconds": 20.0,
            "status": "stale_eligible",
            "payload_chars": 2,
        },
        {
            "query": "expired query",
            "age_seconds": 50.0,
            "status": "expired",
            "payload_chars": 3,
        },
    ]


def test_list_cache_entries_supports_newest_first_and_limit(monkeypatch):
    """Cache inspection should support ordering and deterministic limit capping."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    now = {"value": 120.0}
    monkeypatch.setattr("app.tools.web_search.time.monotonic", lambda: now["value"])

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=60, cache_max_entries=16)
    tool._cache["alpha"] = (100.0, "a")
    tool._cache["beta"] = (101.0, "b")
    tool._cache["gamma"] = (102.0, "c")

    entries = tool.list_cache_entries(newest_first=True, limit=2)

    assert [entry["query"] for entry in entries] == ["gamma", "beta"]


def test_list_cache_entries_can_filter_by_status(monkeypatch):
    """Cache inspection should filter entries by freshness status when requested."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    now = {"value": 220.0}
    monkeypatch.setattr("app.tools.web_search.time.monotonic", lambda: now["value"])

    tool = DuckDuckGoSearchTool(
        cache_ttl_seconds=10,
        cache_max_entries=16,
        stale_cache_ttl_seconds=30,
    )
    tool._cache["active query"] = (215.0, "a")
    tool._cache["stale query"] = (200.0, "bb")
    tool._cache["expired query"] = (170.0, "ccc")

    entries = tool.list_cache_entries(status=["active", "stale_eligible"])

    assert [entry["query"] for entry in entries] == ["active query", "stale query"]


def test_list_cache_entries_can_filter_by_query_contains(monkeypatch):
    """Cache inspection should support case-insensitive query substring filters."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    now = {"value": 120.0}
    monkeypatch.setattr("app.tools.web_search.time.monotonic", lambda: now["value"])

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=60, cache_max_entries=16)
    tool._cache["Daily News AI"] = (100.0, "a")
    tool._cache["breaking news robotics"] = (101.0, "b")
    tool._cache["weather seoul"] = (102.0, "c")

    entries = tool.list_cache_entries(query_contains="NEWS", case_sensitive=False)

    assert [entry["query"] for entry in entries] == [
        "Daily News AI",
        "breaking news robotics",
    ]


def test_list_cache_entries_can_filter_by_age_range(monkeypatch):
    """Cache inspection should support minimum/maximum age filters."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    now = {"value": 500.0}
    monkeypatch.setattr("app.tools.web_search.time.monotonic", lambda: now["value"])

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=60, cache_max_entries=16)
    tool._cache["fresh"] = (498.0, "a")
    tool._cache["warm"] = (490.0, "b")
    tool._cache["old"] = (450.0, "c")

    entries = tool.list_cache_entries(min_age_seconds=5, max_age_seconds=20)

    assert [entry["query"] for entry in entries] == ["warm"]


def test_list_cache_entries_can_include_payload_previews(monkeypatch):
    """Cache inspection should optionally include truncated payload previews."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    now = {"value": 300.0}
    monkeypatch.setattr("app.tools.web_search.time.monotonic", lambda: now["value"])

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=60, cache_max_entries=16)
    tool._cache["alpha"] = (290.0, "1234567890")

    entries = tool.list_cache_entries(
        include_payload_preview=True,
        payload_preview_chars=4,
    )

    assert entries == [
        {
            "query": "alpha",
            "age_seconds": 10.0,
            "status": "active",
            "payload_chars": 10,
            "payload_preview": "1234",
            "payload_truncated": True,
        }
    ]


def test_list_cache_entries_can_include_full_payload_preview(monkeypatch):
    """Payload preview should include full text when preview limit is disabled."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    now = {"value": 300.0}
    monkeypatch.setattr("app.tools.web_search.time.monotonic", lambda: now["value"])

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=60, cache_max_entries=16)
    tool._cache["beta"] = (295.0, "hello")

    entries = tool.list_cache_entries(
        include_payload_preview=True,
        payload_preview_chars=None,
    )

    assert entries == [
        {
            "query": "beta",
            "age_seconds": 5.0,
            "status": "active",
            "payload_chars": 5,
            "payload_preview": "hello",
            "payload_truncated": False,
        }
    ]


def test_list_cache_entries_rejects_invalid_options(monkeypatch):
    """Cache inspection options should validate selectors and filter options."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=60, cache_max_entries=16)

    with pytest.raises(ValueError, match="newest_first must be a boolean value"):
        tool.list_cache_entries(newest_first="true")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="case_sensitive must be a boolean value"):
        tool.list_cache_entries(case_sensitive="false")  # type: ignore[arg-type]

    with pytest.raises(
        ValueError,
        match="include_payload_preview must be a boolean value",
    ):
        tool.list_cache_entries(include_payload_preview="true")  # type: ignore[arg-type]

    with pytest.raises(
        ValueError,
        match="payload_preview_chars must be a positive integer or None",
    ):
        tool.list_cache_entries(payload_preview_chars=0)

    with pytest.raises(
        ValueError,
        match="payload_preview_chars must be a positive integer or None",
    ):
        tool.list_cache_entries(payload_preview_chars=True)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="limit must be a positive integer"):
        tool.list_cache_entries(limit=0)

    with pytest.raises(ValueError, match="limit must be a positive integer"):
        tool.list_cache_entries(limit=True)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="limit must be a positive integer"):
        tool.list_cache_entries(limit=1.5)  # type: ignore[arg-type]

    with pytest.raises(
        ValueError,
        match="status must contain only: active, stale_eligible, expired, unbounded",
    ):
        tool.list_cache_entries(status="fresh")

    with pytest.raises(ValueError, match="query must be a non-empty string"):
        tool.list_cache_entries(query_contains="   ")

    with pytest.raises(
        ValueError,
        match="min_age_seconds must be a non-negative number",
    ):
        tool.list_cache_entries(min_age_seconds=-1)

    with pytest.raises(
        ValueError,
        match="min_age_seconds must be a non-negative number",
    ):
        tool.list_cache_entries(min_age_seconds=True)  # type: ignore[arg-type]

    with pytest.raises(
        ValueError,
        match="max_age_seconds must be a non-negative number",
    ):
        tool.list_cache_entries(max_age_seconds="10")  # type: ignore[arg-type]

    with pytest.raises(
        ValueError,
        match="min_age_seconds cannot be greater than max_age_seconds",
    ):
        tool.list_cache_entries(min_age_seconds=10, max_age_seconds=5)


def test_prune_cache_removes_entries_outside_retention_window(monkeypatch):
    """prune_cache should drop entries older than TTL/stale retention windows."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    now = {"value": 100.0}
    monkeypatch.setattr("app.tools.web_search.time.monotonic", lambda: now["value"])

    tool = DuckDuckGoSearchTool(
        cache_ttl_seconds=5,
        cache_max_entries=16,
        stale_cache_ttl_seconds=20,
    )

    tool._cache["fresh"] = (98.0, "fresh")
    tool._cache["stale"] = (90.0, "stale")
    tool._cache["expired"] = (70.0, "expired")

    assert tool.prune_cache() == 1
    assert list(tool._cache.keys()) == ["fresh", "stale"]


def test_get_cache_stats_reports_active_expired_and_stale_entries(monkeypatch):
    """Cache stats should expose active, expired, and stale-eligible counts."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    now = {"value": 200.0}
    monkeypatch.setattr("app.tools.web_search.time.monotonic", lambda: now["value"])

    tool = DuckDuckGoSearchTool(
        cache_ttl_seconds=10,
        cache_max_entries=16,
        stale_cache_ttl_seconds=30,
    )

    tool._cache["active"] = (195.0, "active")
    tool._cache["stale-eligible"] = (180.0, "stale")
    tool._cache["expired"] = (160.0, "expired")

    stats = tool.get_cache_stats()

    assert stats == {
        "enabled": True,
        "entries": 3,
        "max_entries": 16,
        "ttl_seconds": 10.0,
        "stale_ttl_seconds": 30.0,
        "retention_seconds": 30.0,
        "active_entries": 1,
        "expired_entries": 2,
        "stale_eligible_entries": 1,
        "cache_hits": 0,
        "cache_misses": 0,
        "cache_writes": 0,
        "stale_fallback_hits": 0,
        "hit_ratio": None,
    }


def test_get_cache_stats_tracks_hit_miss_write_and_hit_ratio(monkeypatch):
    """Cache stats should expose lookup/write counters and hit ratio."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=60, cache_max_entries=16)

    assert tool._run("alpha") == "payload"
    assert tool._run("alpha") == "payload"

    stats = tool.get_cache_stats()

    assert stats["cache_hits"] == 1
    assert stats["cache_misses"] == 1
    assert stats["cache_writes"] == 1
    assert stats["stale_fallback_hits"] == 0
    assert stats["hit_ratio"] == pytest.approx(0.5)


def test_cache_stats_tracks_stale_fallback_hits_and_can_reset_metrics(monkeypatch):
    """Stale fallback usage should be measurable and resettable."""
    priming_backend = _FakeSearchBackend(response="fresh snapshot")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: priming_backend,
    )

    now = {"value": 10.0}
    monkeypatch.setattr("app.tools.web_search.time.monotonic", lambda: now["value"])

    tool = DuckDuckGoSearchTool(
        cache_ttl_seconds=5,
        cache_max_entries=16,
        stale_cache_ttl_seconds=40,
    )

    assert tool._run("agent") == "fresh snapshot"

    now["value"] = 20.0
    tool._search = _FailingSearchBackend(message="still down")

    result = tool._run("agent")
    assert result.startswith("fresh snapshot")

    stats = tool.get_cache_stats()
    assert stats["cache_hits"] == 0
    assert stats["cache_misses"] == 2
    assert stats["cache_writes"] == 1
    assert stats["stale_fallback_hits"] == 1
    assert stats["hit_ratio"] == 0.0

    tool.reset_cache_metrics()
    reset_stats = tool.get_cache_stats()
    assert reset_stats["cache_hits"] == 0
    assert reset_stats["cache_misses"] == 0
    assert reset_stats["cache_writes"] == 0
    assert reset_stats["stale_fallback_hits"] == 0
    assert reset_stats["hit_ratio"] is None


def test_search_with_diagnostics_reports_fresh_search_source(monkeypatch):
    """Diagnostics should report fresh backend execution metadata."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(max_result_chars=None)

    diagnostics = tool.search_with_diagnostics("  agent\nquery  ")

    assert diagnostics["normalized_query"] == "agent query"
    assert diagnostics["source"] == "fresh_search"
    assert diagnostics["result"] == "payload"
    assert diagnostics["success"] is True
    assert diagnostics["cache_hit"] is False
    assert diagnostics["stale_fallback"] is False
    assert diagnostics["latency_ms"] >= 0


def test_search_with_diagnostics_reports_cache_hits(monkeypatch):
    """Repeated normalized queries should report cache-hit diagnostics."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=60, cache_max_entries=16)

    first = tool.search_with_diagnostics("agent")
    second = tool.search_with_diagnostics("agent")

    assert first["source"] == "fresh_search"
    assert second["source"] == "cache_hit"
    assert second["cache_hit"] is True
    assert second["success"] is True
    assert fake_backend.queries == ["agent"]


def test_search_with_diagnostics_reports_stale_fallback_source(monkeypatch):
    """Diagnostics should expose stale-cache fallback behavior on failures."""
    priming_backend = _FakeSearchBackend(response="fresh snapshot")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: priming_backend,
    )

    now = {"value": 10.0}
    monkeypatch.setattr("app.tools.web_search.time.monotonic", lambda: now["value"])

    tool = DuckDuckGoSearchTool(
        cache_ttl_seconds=5,
        cache_max_entries=16,
        stale_cache_ttl_seconds=40,
    )

    assert tool.search_with_diagnostics("agent")["source"] == "fresh_search"

    now["value"] = 20.0
    tool._search = _FailingSearchBackend(message="still down")

    diagnostics = tool.search_with_diagnostics("agent")

    assert diagnostics["source"] == "stale_cache_fallback"
    assert diagnostics["success"] is True
    assert diagnostics["cache_hit"] is False
    assert diagnostics["stale_fallback"] is True
    assert diagnostics["result"].startswith("fresh snapshot")


def test_search_with_diagnostics_reports_error_details(monkeypatch):
    """Validation failures should be surfaced with deterministic diagnostics."""
    fake_backend = _FakeSearchBackend(response="should not be used")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool()

    diagnostics = tool.search_with_diagnostics("   ")

    assert diagnostics["normalized_query"] is None
    assert diagnostics["source"] == "error"
    assert diagnostics["success"] is False
    assert diagnostics["cache_hit"] is False
    assert diagnostics["stale_fallback"] is False
    assert diagnostics["error"] == "query must be a non-empty string"
    assert diagnostics["result"] == "Search failed: query must be a non-empty string"
    assert fake_backend.queries == []


def test_search_many_returns_ordered_results(monkeypatch):
    """Batch search helper should return one result payload per input query."""
    fake_backend = _SequencedSearchBackend(
        ["alpha-result", "beta-result", "gamma-result"]
    )
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=None)

    results = tool.search_many(["alpha", "beta", "gamma"])

    assert results == ["alpha-result", "beta-result", "gamma-result"]
    assert fake_backend.queries == ["alpha", "beta", "gamma"]


def test_search_many_can_deduplicate_normalized_queries(monkeypatch):
    """deduplicate=True should avoid duplicate backend work in one batch."""
    fake_backend = _SequencedSearchBackend(["alpha-result", "beta-result"])
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=None)

    results = tool.search_many(
        [" alpha\none ", "alpha\tone", "beta"],
        deduplicate=True,
    )

    assert results == ["alpha-result", "alpha-result", "beta-result"]
    assert fake_backend.queries == ["alpha one", "beta"]


def test_search_many_deduplication_respects_cache_case_sensitivity(monkeypatch):
    """Batch deduplication should mirror cache_case_sensitive behavior."""
    fake_backend = _SequencedSearchBackend(
        [
            "sensitive-first",
            "sensitive-second",
            "insensitive-first",
            "insensitive-second",
        ]
    )
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    sensitive_tool = DuckDuckGoSearchTool(
        cache_ttl_seconds=None,
        cache_case_sensitive=True,
    )
    insensitive_tool = DuckDuckGoSearchTool(
        cache_ttl_seconds=None,
        cache_case_sensitive=False,
    )

    sensitive_results = sensitive_tool.search_many(
        ["News AI", "news ai"],
        deduplicate=True,
    )
    insensitive_results = insensitive_tool.search_many(
        ["News AI", "news ai"],
        deduplicate=True,
    )

    assert sensitive_results == ["sensitive-first", "sensitive-second"]
    assert insensitive_results == ["insensitive-first", "insensitive-first"]
    assert fake_backend.queries == ["News AI", "news ai", "News AI"]


def test_search_many_rejects_invalid_deduplicate_option(monkeypatch):
    """deduplicate option should accept only boolean values."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool()

    with pytest.raises(ValueError, match="deduplicate must be a boolean value"):
        tool.search_many(["alpha"], deduplicate="true")  # type: ignore[arg-type]


def test_search_many_with_diagnostics_can_deduplicate_normalized_queries(monkeypatch):
    """deduplicate=True should reuse diagnostics rows for normalized duplicates."""
    fake_backend = _SequencedSearchBackend(["alpha-result", "beta-result"])
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=None)

    diagnostics = tool.search_many_with_diagnostics(
        [" alpha\none ", "alpha\tone", "beta"],
        deduplicate=True,
    )

    assert [row["source"] for row in diagnostics["results"]] == [
        "fresh_search",
        "fresh_search",
        "fresh_search",
    ]
    assert diagnostics["results"][0]["deduplicated"] is False
    assert diagnostics["results"][0]["deduplicated_from_query"] is None
    assert diagnostics["results"][1]["deduplicated"] is True
    assert diagnostics["results"][1]["deduplicated_from_query"] == " alpha\none "
    assert diagnostics["results"][1]["latency_ms"] == 0.0

    assert diagnostics["summary"]["total_queries"] == 3
    assert diagnostics["summary"]["executed_queries"] == 2
    assert diagnostics["summary"]["deduplicated_results"] == 1
    assert diagnostics["summary"]["deduplication_rate"] == pytest.approx(1 / 3)
    assert fake_backend.queries == ["alpha one", "beta"]


def test_search_many_with_diagnostics_deduplication_respects_case_setting(
    monkeypatch,
):
    """Diagnostics deduplication should follow cache_case_sensitive setting."""
    fake_backend = _SequencedSearchBackend(
        [
            "sensitive-first",
            "sensitive-second",
            "insensitive-first",
            "insensitive-second",
        ]
    )
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    sensitive_tool = DuckDuckGoSearchTool(
        cache_ttl_seconds=None,
        cache_case_sensitive=True,
    )
    insensitive_tool = DuckDuckGoSearchTool(
        cache_ttl_seconds=None,
        cache_case_sensitive=False,
    )

    sensitive_diagnostics = sensitive_tool.search_many_with_diagnostics(
        ["News AI", "news ai"],
        deduplicate=True,
    )
    insensitive_diagnostics = insensitive_tool.search_many_with_diagnostics(
        ["News AI", "news ai"],
        deduplicate=True,
    )

    assert sensitive_diagnostics["summary"]["executed_queries"] == 2
    assert sensitive_diagnostics["summary"]["deduplicated_results"] == 0

    assert insensitive_diagnostics["summary"]["executed_queries"] == 1
    assert insensitive_diagnostics["summary"]["deduplicated_results"] == 1
    assert insensitive_diagnostics["results"][1]["deduplicated"] is True
    assert (
        insensitive_diagnostics["results"][1]["deduplicated_from_query"]
        == "News AI"
    )

    assert fake_backend.queries == ["News AI", "news ai", "News AI"]


def test_search_many_with_diagnostics_rejects_invalid_deduplicate_option(monkeypatch):
    """deduplicate option should accept only boolean values."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool()

    with pytest.raises(ValueError, match="deduplicate must be a boolean value"):
        tool.search_many_with_diagnostics(
            ["alpha"],
            deduplicate="true",  # type: ignore[arg-type]
        )


def test_search_many_with_diagnostics_reports_per_query_rows_and_summary(monkeypatch):
    """Batch diagnostics should include ordered rows and aggregate counters."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(cache_ttl_seconds=60, cache_max_entries=16)

    diagnostics = tool.search_many_with_diagnostics(["agent", "agent", "  "])

    assert [row["source"] for row in diagnostics["results"]] == [
        "fresh_search",
        "cache_hit",
        "error",
    ]
    assert diagnostics["summary"]["total_queries"] == 3
    assert diagnostics["summary"]["executed_queries"] == 3
    assert diagnostics["summary"]["deduplicated_results"] == 0
    assert diagnostics["summary"]["deduplication_rate"] == 0
    assert diagnostics["summary"]["successes"] == 2
    assert diagnostics["summary"]["errors"] == 1
    assert diagnostics["summary"]["fresh_searches"] == 1
    assert diagnostics["summary"]["cache_hits"] == 1
    assert diagnostics["summary"]["stale_fallbacks"] == 0
    assert diagnostics["summary"]["average_latency_ms"] >= 0
    assert diagnostics["summary"]["min_latency_ms"] >= 0
    assert diagnostics["summary"]["max_latency_ms"] >= 0
    assert (
        diagnostics["summary"]["min_latency_ms"]
        <= diagnostics["summary"]["median_latency_ms"]
        <= diagnostics["summary"]["p90_latency_ms"]
        <= diagnostics["summary"]["p95_latency_ms"]
        <= diagnostics["summary"]["p99_latency_ms"]
        <= diagnostics["summary"]["max_latency_ms"]
    )
    assert diagnostics["summary"]["success_rate"] == pytest.approx(2 / 3)
    assert diagnostics["summary"]["source_counts"] == {
        "fresh_search": 1,
        "cache_hit": 1,
        "stale_cache_fallback": 0,
        "error": 1,
    }


def test_search_many_with_diagnostics_reports_percentile_latencies(monkeypatch):
    """Batch diagnostics should expose deterministic percentile latencies."""
    fake_backend = _FakeSearchBackend(response="unused")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool()

    diagnostics_rows = iter(
        [
            {
                "query": "q1",
                "normalized_query": "q1",
                "result": "r1",
                "source": "fresh_search",
                "latency_ms": 10.0,
                "success": True,
                "cache_hit": False,
                "stale_fallback": False,
            },
            {
                "query": "q2",
                "normalized_query": "q2",
                "result": "r2",
                "source": "fresh_search",
                "latency_ms": 20.0,
                "success": True,
                "cache_hit": False,
                "stale_fallback": False,
            },
            {
                "query": "q3",
                "normalized_query": "q3",
                "result": "r3",
                "source": "cache_hit",
                "latency_ms": 30.0,
                "success": True,
                "cache_hit": True,
                "stale_fallback": False,
            },
            {
                "query": "q4",
                "normalized_query": "q4",
                "result": "r4",
                "source": "error",
                "latency_ms": 40.0,
                "success": False,
                "cache_hit": False,
                "stale_fallback": False,
                "error": "backend timeout",
            },
        ]
    )

    monkeypatch.setattr(
        DuckDuckGoSearchTool,
        "search_with_diagnostics",
        lambda self, _query: next(diagnostics_rows),
    )

    diagnostics = tool.search_many_with_diagnostics(["q1", "q2", "q3", "q4"])

    assert diagnostics["summary"]["median_latency_ms"] == pytest.approx(25.0)
    assert diagnostics["summary"]["p90_latency_ms"] == pytest.approx(37.0)
    assert diagnostics["summary"]["p95_latency_ms"] == pytest.approx(38.5)
    assert diagnostics["summary"]["p99_latency_ms"] == pytest.approx(39.7)


def test_calculate_percentile_rejects_invalid_arguments(monkeypatch):
    """Percentile helper should guard against empty values and bad ranges."""
    fake_backend = _FakeSearchBackend(response="unused")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool()

    with pytest.raises(
        ValueError,
        match="sorted_values must include at least one value",
    ):
        tool._calculate_percentile([], 50)

    with pytest.raises(ValueError, match="percentile must be between 0 and 100"):
        tool._calculate_percentile([1.0, 2.0], 101)


def test_search_many_with_diagnostics_rejects_invalid_query_batches(monkeypatch):
    """Batch diagnostics should validate query payloads eagerly."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool()

    with pytest.raises(
        ValueError,
        match="queries must be an iterable of query strings",
    ):
        tool.search_many_with_diagnostics("agent")  # type: ignore[arg-type]

    with pytest.raises(
        ValueError,
        match="queries must include at least one query",
    ):
        tool.search_many_with_diagnostics([])

    with pytest.raises(
        ValueError,
        match="queries must contain only string values",
    ):
        tool.search_many_with_diagnostics(["agent", 1])  # type: ignore[list-item]


def test_search_many_with_diagnostics_respects_max_batch_queries(monkeypatch):
    """Batch diagnostics should reject payloads above configured batch size."""
    fake_backend = _FakeSearchBackend(response="payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(max_batch_queries=2)

    with pytest.raises(
        ValueError,
        match=r"queries exceeds max_batch_queries \(3 > 2\)",
    ):
        tool.search_many_with_diagnostics(["alpha", "beta", "gamma"])

    assert fake_backend.queries == []


def test_run_rejects_overly_long_queries_without_backend_calls(monkeypatch):
    """Configured query-length limits should fail fast before backend calls."""
    fake_backend = _FakeSearchBackend(response="should not be used")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(max_query_length=12)

    result = tool._run("agentic workflow")

    assert result == "Search failed: query exceeds max_query_length (16 > 12)"
    assert fake_backend.queries == []


def test_run_rejects_blank_queries_without_backend_calls(monkeypatch):
    """Blank queries should return a deterministic validation error string."""
    fake_backend = _FakeSearchBackend(response="should not be used")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool()

    result = tool._run("   ")

    assert result == "Search failed: query must be a non-empty string"
    assert fake_backend.queries == []


def test_run_truncates_oversized_results(monkeypatch):
    """Configured max_result_chars should clip long payloads with suffix metadata."""
    fake_backend = _FakeSearchBackend(response="0123456789ABCDE")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(max_result_chars=10)

    result = tool._run("agent")

    assert result == "0123456789\n\n[truncated 5 characters]"


@pytest.mark.asyncio
async def test_arun_reuses_sync_implementation(monkeypatch):
    """Async path should reuse _run behavior for deterministic output."""
    fake_backend = _FakeSearchBackend(response="async payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(max_result_chars=None)

    result = await tool._arun(" async query ")

    assert result == "async payload"
    assert fake_backend.queries == ["async query"]
