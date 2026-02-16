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


def test_run_normalizes_query_and_returns_backend_results(monkeypatch):
    """_run should trim query whitespace before delegating to backend."""
    fake_backend = _FakeSearchBackend(response="result payload")
    monkeypatch.setattr(
        "app.tools.web_search.DuckDuckGoSearchRun",
        lambda: fake_backend,
    )

    tool = DuckDuckGoSearchTool(max_result_chars=None)

    result = tool._run("  agentic workflow  ")

    assert result == "result payload"
    assert fake_backend.queries == ["agentic workflow"]


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
