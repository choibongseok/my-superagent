import pytest

from app.agents.base import BaseAgent
from app.agents.sheets_agent import SheetsAgent


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
def fake_sheets_service():
    class _SheetsValues:
        def update(self, **kwargs):
            return self

        def get(self, **kwargs):
            return self

        def execute(self):
            return {"updatedCells": 4, "values": [["A", "B"], [1, 2]]}

    class _Spreadsheets:
        def create(self, body=None):
            return self

        def get(self, spreadsheetId=None):
            return self

        def values(self):
            return _SheetsValues()

        def batchUpdate(self, spreadsheetId=None, body=None):
            return self

        def execute(self):
            return {
                "spreadsheetId": "sheet-123",
                "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/sheet-123/edit",
                "sheets": [{"properties": {"sheetId": 1, "title": "Sheet1"}}],
                "replies": [{"addChart": {"chart": {"chartId": 99}}}],
            }

    class _Service:
        def spreadsheets(self):
            return _Spreadsheets()

    return _Service()


def test_sheets_agent_tools_created_with_credentials(monkeypatch, fake_sheets_service):
    monkeypatch.setattr("app.agents.sheets_agent.build", lambda *args, **kwargs: fake_sheets_service)

    credentials = object()
    agent = SheetsAgent(user_id="u1", session_id="s1", credentials=credentials)
    tools = agent._create_tools()
    names = {t.name for t in tools}

    assert agent.credentials is credentials
    assert {"create_spreadsheet", "write_data", "read_data", "format_cells", "create_chart"}.issubset(names)


def test_sheets_tool_returns_error_without_credentials():
    agent = SheetsAgent(user_id="u1", session_id="s1", credentials=None)
    tools = {t.name: t for t in agent._create_tools()}

    result = tools["create_spreadsheet"].run("My Sheet")

    assert "Missing credentials" in result
