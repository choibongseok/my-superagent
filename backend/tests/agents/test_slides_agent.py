import pytest

from app.agents.base import BaseAgent
from app.agents.slides_agent import SlidesAgent


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


@pytest.fixture(autouse=True)
def _patch_base_agent(monkeypatch):
    monkeypatch.setattr(BaseAgent, "_create_llm", lambda *args, **kwargs: object())
    monkeypatch.setattr(BaseAgent, "_init_memory", lambda *args, **kwargs: _DummyMemory())


@pytest.fixture
def fake_slides_service():
    class _Presentations:
        def create(self, body=None):
            return self

        def batchUpdate(self, presentationId=None, body=None):
            return self

        def get(self, presentationId=None):
            return self

        def execute(self):
            return {
                "presentationId": "pres-123",
                "slides": [{"objectId": "slide-1", "slideProperties": {"notesPage": {"objectId": "notes-1", "pageElements": []}}}],
                "pageSize": {
                    "width": {"magnitude": 720},
                    "height": {"magnitude": 540},
                },
                "replies": [{"createSlide": {"objectId": "slide-1"}}],
            }

    class _Service:
        def presentations(self):
            return _Presentations()

    return _Service()


def test_slides_agent_tools_created_with_credentials(monkeypatch, fake_slides_service):
    monkeypatch.setattr("app.agents.slides_agent.build", lambda *args, **kwargs: fake_slides_service)

    credentials = object()
    agent = SlidesAgent(user_id="u1", session_id="s1", credentials=credentials)
    tools = agent._create_tools()
    names = {t.name for t in tools}

    assert agent.credentials is credentials
    assert {"create_presentation", "add_slide", "insert_text", "insert_image", "apply_theme", "add_speaker_notes"}.issubset(names)


def test_slides_tool_returns_error_without_credentials():
    agent = SlidesAgent(user_id="u1", session_id="s1", credentials=None)
    tools = {t.name: t for t in agent._create_tools()}

    result = tools["create_presentation"].run("My Deck")

    assert "Missing credentials" in result
