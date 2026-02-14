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


@pytest.fixture(autouse=True)
def _patch_base_agent(monkeypatch):
    monkeypatch.setattr(BaseAgent, "_create_llm", lambda *args, **kwargs: object())
    monkeypatch.setattr(BaseAgent, "_init_memory", lambda *args, **kwargs: _DummyMemory())


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
