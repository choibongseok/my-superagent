import json

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
    monkeypatch.setattr(
        BaseAgent, "_init_memory", lambda *args, **kwargs: _DummyMemory()
    )


@pytest.fixture
def fake_slides_service():
    captured = {}

    class _Presentations:
        def create(self, body=None):
            captured["op"] = "create"
            captured["create_body"] = body
            return self

        def batchUpdate(self, presentationId=None, body=None):
            captured["op"] = "batch_update"
            captured["batch_update_kwargs"] = {
                "presentationId": presentationId,
                "body": body,
            }
            return self

        def get(self, presentationId=None):
            captured["op"] = "get"
            captured["get_presentation_id"] = presentationId
            return self

        def execute(self):
            op = captured.get("op")

            if op == "create":
                return {"presentationId": "pres-123"}

            if op == "batch_update":
                return {"replies": [{"createSlide": {"objectId": "slide-1"}}]}

            return {
                "presentationId": "pres-123",
                "slides": [
                    {
                        "objectId": "slide-1",
                        "slideProperties": {
                            "notesPage": {"objectId": "notes-1", "pageElements": []}
                        },
                    },
                    {
                        "objectId": "slide-2",
                        "slideProperties": {
                            "notesPage": {"objectId": "notes-2", "pageElements": []}
                        },
                    },
                ],
                "pageSize": {
                    "width": {"magnitude": 720},
                    "height": {"magnitude": 540},
                },
            }

    class _Service:
        def __init__(self):
            self.captured = captured

        def presentations(self):
            return _Presentations()

    return _Service()


def test_slides_agent_tools_created_with_credentials(monkeypatch, fake_slides_service):
    monkeypatch.setattr(
        "app.agents.slides_agent.build", lambda *args, **kwargs: fake_slides_service
    )

    credentials = object()
    agent = SlidesAgent(user_id="u1", session_id="s1", credentials=credentials)
    tools = agent._create_tools()
    names = {t.name for t in tools}

    assert agent.credentials is credentials
    assert {
        "create_presentation",
        "add_slide",
        "insert_text",
        "insert_image",
        "apply_theme",
        "add_speaker_notes",
    }.issubset(names)


def test_slides_apply_theme_supports_named_theme_colors(
    monkeypatch, fake_slides_service
):
    monkeypatch.setattr(
        "app.agents.slides_agent.build", lambda *args, **kwargs: fake_slides_service
    )

    agent = SlidesAgent(user_id="u1", session_id="s1", credentials=object())
    tools = {t.name: t for t in agent._create_tools()}

    result = tools["apply_theme"].run(
        json.dumps({"presentation_id": "pres-123", "theme_id": "teal"})
    )

    assert "Successfully applied teal theme" in result

    requests = fake_slides_service.captured["batch_update_kwargs"]["body"]["requests"]
    assert len(requests) == 2

    for request in requests:
        color = request["updatePageProperties"]["pageProperties"]["pageBackgroundFill"][
            "solidFill"
        ]["color"]["rgbColor"]
        assert color == {"red": 0.0, "green": 0.7, "blue": 0.7}


def test_slides_apply_theme_supports_hex_theme_colors(monkeypatch, fake_slides_service):
    monkeypatch.setattr(
        "app.agents.slides_agent.build", lambda *args, **kwargs: fake_slides_service
    )

    agent = SlidesAgent(user_id="u1", session_id="s1", credentials=object())
    tools = {t.name: t for t in agent._create_tools()}

    result = tools["apply_theme"].run(
        json.dumps({"presentation_id": "pres-123", "theme_id": "#FF8000"})
    )

    assert "Successfully applied #FF8000 theme" in result

    color = fake_slides_service.captured["batch_update_kwargs"]["body"]["requests"][0][
        "updatePageProperties"
    ]["pageProperties"]["pageBackgroundFill"]["solidFill"]["color"]["rgbColor"]
    assert color["red"] == pytest.approx(1.0)
    assert color["green"] == pytest.approx(128 / 255)
    assert color["blue"] == pytest.approx(0.0)


def test_slides_apply_theme_rejects_invalid_theme(monkeypatch, fake_slides_service):
    monkeypatch.setattr(
        "app.agents.slides_agent.build", lambda *args, **kwargs: fake_slides_service
    )

    agent = SlidesAgent(user_id="u1", session_id="s1", credentials=object())
    tools = {t.name: t for t in agent._create_tools()}

    result = tools["apply_theme"].run(
        json.dumps({"presentation_id": "pres-123", "theme_id": "not-a-theme"})
    )

    assert "Error applying theme: Unsupported theme" in result
    assert "batch_update_kwargs" not in fake_slides_service.captured


def test_slides_tool_returns_error_without_credentials():
    agent = SlidesAgent(user_id="u1", session_id="s1", credentials=None)
    tools = {t.name: t for t in agent._create_tools()}

    result = tools["create_presentation"].run("My Deck")

    assert "Missing credentials" in result
