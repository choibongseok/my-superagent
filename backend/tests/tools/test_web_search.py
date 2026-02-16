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
    }


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
