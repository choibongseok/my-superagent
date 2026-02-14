import json

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
    captured = {}

    class _SheetsValues:
        def update(self, **kwargs):
            captured["values_op"] = "update"
            captured["update_kwargs"] = kwargs
            return self

        def append(self, **kwargs):
            captured["values_op"] = "append"
            captured["append_kwargs"] = kwargs
            return self

        def get(self, **kwargs):
            captured["values_op"] = "get"
            captured["get_kwargs"] = kwargs
            return self

        def execute(self):
            op = captured.get("values_op")
            if op == "append":
                return {
                    "updates": {
                        "updatedRows": 2,
                        "updatedCells": 4,
                        "updatedRange": "Sheet1!A3:B4",
                    }
                }

            if op == "get":
                return {"values": [["A", "B"], [1, 2]]}

            return {"updatedCells": 4, "updatedRows": 2}

    class _Spreadsheets:
        def create(self, body=None):
            captured["sheets_op"] = "create"
            captured["create_body"] = body
            return self

        def get(self, spreadsheetId=None):
            captured["sheets_op"] = "get"
            captured["get_spreadsheet_id"] = spreadsheetId
            return self

        def values(self):
            return _SheetsValues()

        def batchUpdate(self, spreadsheetId=None, body=None):
            captured["sheets_op"] = "batchUpdate"
            captured["batch_update_kwargs"] = {
                "spreadsheetId": spreadsheetId,
                "body": body,
            }
            return self

        def execute(self):
            op = captured.get("sheets_op")
            if op == "create":
                return {
                    "spreadsheetId": "sheet-123",
                    "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/sheet-123/edit",
                    "sheets": [{"properties": {"sheetId": 1, "title": "Sheet1"}}],
                }

            if op == "get":
                return {
                    "sheets": [{"properties": {"sheetId": 1, "title": "Sheet1"}}],
                }

            return {
                "replies": [{"addChart": {"chart": {"chartId": 99}}}],
            }

    class _Service:
        def __init__(self):
            self.captured = captured

        def spreadsheets(self):
            return _Spreadsheets()

    return _Service()


def test_sheets_agent_tools_created_with_credentials(monkeypatch, fake_sheets_service):
    monkeypatch.setattr(
        "app.agents.sheets_agent.build", lambda *args, **kwargs: fake_sheets_service
    )

    credentials = object()
    agent = SheetsAgent(user_id="u1", session_id="s1", credentials=credentials)
    tools = agent._create_tools()
    names = {t.name for t in tools}

    assert agent.credentials is credentials
    assert {
        "create_spreadsheet",
        "write_data",
        "append_data",
        "read_data",
        "format_cells",
        "create_chart",
    }.issubset(names)


def test_sheets_append_data_uses_google_values_append(monkeypatch, fake_sheets_service):
    monkeypatch.setattr(
        "app.agents.sheets_agent.build", lambda *args, **kwargs: fake_sheets_service
    )

    agent = SheetsAgent(user_id="u1", session_id="s1", credentials=object())
    tools = {t.name: t for t in agent._create_tools()}

    result = tools["append_data"].run(
        json.dumps(
            {
                "spreadsheet_id": "sheet-123",
                "range_name": "Sheet1!A:B",
                "values": [["Task", "Owner"], ["Deploy", "AgentHQ"]],
                "value_input_option": "RAW",
                "insert_data_option": "OVERWRITE",
            }
        )
    )

    assert "Successfully appended 2 rows (4 cells) to Sheet1!A3:B4" in result
    assert fake_sheets_service.captured["append_kwargs"] == {
        "spreadsheetId": "sheet-123",
        "range": "Sheet1!A:B",
        "valueInputOption": "RAW",
        "insertDataOption": "OVERWRITE",
        "body": {"values": [["Task", "Owner"], ["Deploy", "AgentHQ"]]},
    }


def test_sheets_tool_returns_error_without_credentials():
    agent = SheetsAgent(user_id="u1", session_id="s1", credentials=None)
    tools = {t.name: t for t in agent._create_tools()}

    create_result = tools["create_spreadsheet"].run("My Sheet")
    append_result = tools["append_data"].run(
        json.dumps(
            {
                "spreadsheet_id": "sheet-123",
                "range_name": "Sheet1!A:B",
                "values": [["A", "B"]],
            }
        )
    )

    assert "Missing credentials" in create_result
    assert "Missing credentials" in append_result
