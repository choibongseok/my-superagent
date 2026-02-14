from unittest.mock import AsyncMock

import pytest

from app.agents.base import BaseAgent
from app.agents.docs_agent import DocsAgent


class _DummyMemory:
    langchain_memory = None

    def add_user_message(self, _):
        pass

    def add_ai_message(self, _):
        pass

    def get_context(self):
        return ""

    def clear(self):
        pass


class _DummyResearchAgent:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class _FakeDocsAPI:
    def __init__(self, _credentials):
        self.created_titles = []
        self.inserted_payloads = []

    def create_document(self, title):
        self.created_titles.append(title)
        return "doc-123"

    def insert_text(self, doc_id, content):
        self.inserted_payloads.append((doc_id, content))

    def get_document_url(self, doc_id):
        return f"https://docs.google.com/document/d/{doc_id}"


@pytest.fixture(autouse=True)
def _patch_base_agent(monkeypatch):
    monkeypatch.setattr(BaseAgent, "_create_llm", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        BaseAgent, "_init_memory", lambda *args, **kwargs: _DummyMemory()
    )


def test_docs_agent_preserves_credentials(monkeypatch):
    docs_api_instance = object()
    credentials = object()
    observed = {}

    monkeypatch.setattr("app.agents.docs_agent.ResearchAgent", _DummyResearchAgent)

    def _fake_google_docs_api(creds):
        observed["credentials"] = creds
        return docs_api_instance

    monkeypatch.setattr("app.agents.docs_agent.GoogleDocsAPI", _fake_google_docs_api)

    agent = DocsAgent(user_id="u1", session_id="s1", credentials=credentials)

    assert observed["credentials"] is credentials
    assert agent.credentials is credentials
    assert agent.docs_api is docs_api_instance


def test_docs_agent_without_credentials_skips_docs_api(monkeypatch):
    monkeypatch.setattr("app.agents.docs_agent.ResearchAgent", _DummyResearchAgent)

    def _should_not_be_called(_):
        raise AssertionError("GoogleDocsAPI should not be initialized without creds")

    monkeypatch.setattr("app.agents.docs_agent.GoogleDocsAPI", _should_not_be_called)

    agent = DocsAgent(user_id="u1", session_id="s1", credentials=None)

    assert agent.credentials is None
    assert agent.docs_api is None


def test_docs_agent_extracts_outline_and_content_metrics(monkeypatch):
    monkeypatch.setattr("app.agents.docs_agent.ResearchAgent", _DummyResearchAgent)

    agent = DocsAgent(user_id="u1", session_id="s1", credentials=None)

    content = """# Weekly Report

## Highlights
1. Revenue Growth
1.1 Enterprise Segment
본문 문장입니다.
"""

    assert agent._extract_outline(content) == [
        {"level": 1, "title": "Weekly Report"},
        {"level": 2, "title": "Highlights"},
        {"level": 1, "title": "Revenue Growth", "section": "1"},
        {"level": 2, "title": "Enterprise Segment", "section": "1.1"},
    ]

    metrics = agent._build_content_metrics(content)
    assert metrics["heading_count"] == 4
    assert metrics["word_count"] > 0
    assert metrics["line_count"] == 5
    assert metrics["estimated_read_time_minutes"] == 1


@pytest.mark.asyncio
async def test_create_document_without_docs_api_returns_outline_and_metrics(
    monkeypatch,
):
    monkeypatch.setattr("app.agents.docs_agent.ResearchAgent", _DummyResearchAgent)

    agent = DocsAgent(user_id="u1", session_id="s1", credentials=None)
    generated_content = """# Product Update

## Launch Summary
The launch exceeded engagement goals.
"""
    agent.run = AsyncMock(return_value={"success": True, "output": generated_content})

    result = await agent.create_document(
        title="Product Update",
        prompt="Write a launch summary",
        include_research=False,
    )

    assert result["success"] is True
    assert result["content"] == generated_content
    assert result["citations"] == []
    assert result["outline"] == [
        {"level": 1, "title": "Product Update"},
        {"level": 2, "title": "Launch Summary"},
    ]
    assert result["content_metrics"]["heading_count"] == 2
    assert result["content_metrics"]["estimated_read_time_minutes"] == 1


@pytest.mark.asyncio
async def test_create_document_with_docs_api_includes_enriched_metadata(monkeypatch):
    monkeypatch.setattr("app.agents.docs_agent.ResearchAgent", _DummyResearchAgent)
    monkeypatch.setattr("app.agents.docs_agent.GoogleDocsAPI", _FakeDocsAPI)

    agent = DocsAgent(user_id="u1", session_id="s1", credentials=object())
    generated_content = """1. Executive Summary
1.1 KPI Snapshot
Performance remained strong.
"""
    agent.run = AsyncMock(return_value={"success": True, "output": generated_content})

    result = await agent.create_document(
        title="KPI Review",
        prompt="Summarize KPI status",
        include_research=False,
    )

    assert result["success"] is True
    assert result["document_id"] == "doc-123"
    assert result["document_url"].endswith("doc-123")
    assert result["outline"] == [
        {"level": 1, "title": "Executive Summary", "section": "1"},
        {"level": 2, "title": "KPI Snapshot", "section": "1.1"},
    ]
    assert result["content_metrics"]["heading_count"] == 2
    assert result["content_metrics"]["estimated_read_time_minutes"] == 1
    assert agent.docs_api.created_titles == ["KPI Review"]
    assert agent.docs_api.inserted_payloads == [("doc-123", generated_content)]
