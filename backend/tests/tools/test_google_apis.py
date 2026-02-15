"""Tests for Google Workspace API helpers."""

from unittest.mock import MagicMock

import pytest

from app.tools.google_apis import GoogleDocsAPI


@pytest.fixture
def docs_api(monkeypatch):
    """Create a GoogleDocsAPI instance with a mocked Google service."""
    mocked_service = MagicMock()
    mocked_service.documents.return_value.batchUpdate.return_value.execute.return_value = {
        "replies": [{}, {}],
    }

    build_mock = MagicMock(return_value=mocked_service)
    monkeypatch.setattr("app.tools.google_apis.build", build_mock)

    credentials = MagicMock()
    api = GoogleDocsAPI(credentials)

    build_mock.assert_called_once_with("docs", "v1", credentials=credentials)
    return api, mocked_service


def test_replace_template_variables_builds_batch_update_requests(docs_api):
    """Template replacements should be mapped to replaceAllText requests."""
    api, mocked_service = docs_api

    result = api.replace_template_variables(
        "doc-123",
        {
            "name": "AgentHQ",
            "date": "2026-02-15",
        },
    )

    assert result == {"replies": [{}, {}]}

    mocked_service.documents.return_value.batchUpdate.assert_called_once_with(
        documentId="doc-123",
        body={
            "requests": [
                {
                    "replaceAllText": {
                        "containsText": {"text": "{{name}}", "matchCase": True},
                        "replaceText": "AgentHQ",
                    }
                },
                {
                    "replaceAllText": {
                        "containsText": {"text": "{{date}}", "matchCase": True},
                        "replaceText": "2026-02-15",
                    }
                },
            ]
        },
    )


def test_replace_template_variables_supports_custom_delimiters_and_value_coercion(
    docs_api,
):
    """Custom delimiters and non-string replacement values should be supported."""
    api, mocked_service = docs_api

    api.replace_template_variables(
        "doc-456",
        {
            " count ": 3,
            "notes": None,
        },
        placeholder_prefix="<<",
        placeholder_suffix=">>",
        match_case=False,
    )

    mocked_service.documents.return_value.batchUpdate.assert_called_once_with(
        documentId="doc-456",
        body={
            "requests": [
                {
                    "replaceAllText": {
                        "containsText": {"text": "<<count>>", "matchCase": False},
                        "replaceText": "3",
                    }
                },
                {
                    "replaceAllText": {
                        "containsText": {"text": "<<notes>>", "matchCase": False},
                        "replaceText": "",
                    }
                },
            ]
        },
    )


@pytest.mark.parametrize(
    "variables,error",
    [
        ([], "variables must be a mapping of placeholder names"),
        ({}, "variables must include at least one placeholder"),
    ],
)
def test_replace_template_variables_validates_variables_payload(
    docs_api,
    variables,
    error,
):
    """Replacement variables should require a non-empty mapping payload."""
    api, mocked_service = docs_api

    with pytest.raises(ValueError, match=error):
        api.replace_template_variables("doc-789", variables)  # type: ignore[arg-type]

    mocked_service.documents.return_value.batchUpdate.assert_not_called()


def test_replace_template_variables_rejects_invalid_keys_and_match_case(docs_api):
    """Variable keys must be non-empty strings and match_case must be boolean."""
    api, mocked_service = docs_api

    with pytest.raises(ValueError, match="variables keys must be non-empty strings"):
        api.replace_template_variables("doc-1", {"": "x"})

    with pytest.raises(ValueError, match="variables keys must be non-empty strings"):
        api.replace_template_variables("doc-1", {1: "x"})  # type: ignore[dict-item]

    with pytest.raises(ValueError, match="match_case must be a boolean"):
        api.replace_template_variables(
            "doc-1",
            {"name": "AgentHQ"},
            match_case="yes",  # type: ignore[arg-type]
        )

    mocked_service.documents.return_value.batchUpdate.assert_not_called()


@pytest.mark.parametrize(
    "field,value",
    [
        ("placeholder_prefix", " "),
        ("placeholder_suffix", ""),
        ("placeholder_prefix", 123),
    ],
)
def test_replace_template_variables_rejects_invalid_placeholder_tokens(
    docs_api,
    field,
    value,
):
    """Placeholder prefix/suffix should be non-empty strings."""
    api, mocked_service = docs_api

    kwargs = {"placeholder_prefix": "{{", "placeholder_suffix": "}}"}
    kwargs[field] = value

    with pytest.raises(ValueError, match=f"{field} must be a non-empty string"):
        api.replace_template_variables("doc-2", {"name": "AgentHQ"}, **kwargs)

    mocked_service.documents.return_value.batchUpdate.assert_not_called()
