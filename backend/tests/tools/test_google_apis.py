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
    "variable_order,expected_placeholders",
    [
        ("asc", ["{{alpha}}", "{{middle}}", "{{zeta}}"]),
        ("desc", ["{{zeta}}", "{{middle}}", "{{alpha}}"]),
    ],
)
def test_replace_template_variables_supports_variable_order_sorting(
    docs_api,
    variable_order,
    expected_placeholders,
):
    """Template replacements can be sorted deterministically by placeholder name."""
    api, mocked_service = docs_api

    api.replace_template_variables(
        "doc-order",
        {
            "zeta": "last",
            "alpha": "first",
            "middle": "middle",
        },
        variable_order=variable_order,
    )

    requests = mocked_service.documents.return_value.batchUpdate.call_args.kwargs[
        "body"
    ]["requests"]
    assert [
        request["replaceAllText"]["containsText"]["text"] for request in requests
    ] == expected_placeholders


@pytest.mark.parametrize("variable_order", [None, "", "random", 1])
def test_replace_template_variables_rejects_invalid_variable_order(
    docs_api, variable_order
):
    """variable_order should only accept input/asc/desc strings."""
    api, mocked_service = docs_api

    with pytest.raises(
        ValueError, match="variable_order must be one of: input, asc, desc"
    ):
        api.replace_template_variables(
            "doc-invalid-order",
            {"name": "AgentHQ"},
            variable_order=variable_order,  # type: ignore[arg-type]
        )

    mocked_service.documents.return_value.batchUpdate.assert_not_called()


def test_replace_template_variables_supports_custom_value_serializer(docs_api):
    """Custom value serializers should transform non-None replacements."""
    api, mocked_service = docs_api

    serializer_inputs: list[object] = []

    def serialize(value: object) -> object:
        serializer_inputs.append(value)
        if isinstance(value, bool):
            return "YES" if value else "NO"
        if isinstance(value, float):
            return f"{value:.1%}"
        return value

    api.replace_template_variables(
        "doc-serializer",
        {
            "enabled": True,
            "ratio": 0.125,
            "notes": None,
        },
        value_serializer=serialize,
    )

    assert serializer_inputs == [True, 0.125]
    mocked_service.documents.return_value.batchUpdate.assert_called_once_with(
        documentId="doc-serializer",
        body={
            "requests": [
                {
                    "replaceAllText": {
                        "containsText": {
                            "text": "{{enabled}}",
                            "matchCase": True,
                        },
                        "replaceText": "YES",
                    }
                },
                {
                    "replaceAllText": {
                        "containsText": {
                            "text": "{{ratio}}",
                            "matchCase": True,
                        },
                        "replaceText": "12.5%",
                    }
                },
                {
                    "replaceAllText": {
                        "containsText": {
                            "text": "{{notes}}",
                            "matchCase": True,
                        },
                        "replaceText": "",
                    }
                },
            ]
        },
    )


def test_replace_template_variables_allows_serializer_to_return_none(docs_api):
    """Serializer results of None should map to empty replacement strings."""
    api, mocked_service = docs_api

    api.replace_template_variables(
        "doc-serializer-none",
        {
            "optional": "value",
        },
        value_serializer=lambda _: None,
    )

    mocked_service.documents.return_value.batchUpdate.assert_called_once_with(
        documentId="doc-serializer-none",
        body={
            "requests": [
                {
                    "replaceAllText": {
                        "containsText": {
                            "text": "{{optional}}",
                            "matchCase": True,
                        },
                        "replaceText": "",
                    }
                }
            ]
        },
    )


def test_replace_template_variables_rejects_invalid_value_serializer(docs_api):
    """value_serializer should be optional but callable when provided."""
    api, mocked_service = docs_api

    with pytest.raises(
        ValueError,
        match="value_serializer must be callable when provided",
    ):
        api.replace_template_variables(
            "doc-invalid-serializer",
            {"name": "AgentHQ"},
            value_serializer="serialize",  # type: ignore[arg-type]
        )

    mocked_service.documents.return_value.batchUpdate.assert_not_called()


def test_replace_template_variables_can_flatten_nested_mappings(docs_api):
    """Nested mappings should be flattened into dotted placeholder names."""
    api, mocked_service = docs_api

    api.replace_template_variables(
        "doc-flat",
        {
            "customer": {
                "name": "Ada",
                "account": {
                    "tier": "pro",
                },
            },
            "summary": "ready",
        },
        flatten_nested_variables=True,
    )

    mocked_service.documents.return_value.batchUpdate.assert_called_once_with(
        documentId="doc-flat",
        body={
            "requests": [
                {
                    "replaceAllText": {
                        "containsText": {
                            "text": "{{customer.name}}",
                            "matchCase": True,
                        },
                        "replaceText": "Ada",
                    }
                },
                {
                    "replaceAllText": {
                        "containsText": {
                            "text": "{{customer.account.tier}}",
                            "matchCase": True,
                        },
                        "replaceText": "pro",
                    }
                },
                {
                    "replaceAllText": {
                        "containsText": {
                            "text": "{{summary}}",
                            "matchCase": True,
                        },
                        "replaceText": "ready",
                    }
                },
            ]
        },
    )


def test_replace_template_variables_flattening_honors_custom_separator(docs_api):
    """Flattened key separators should be configurable for placeholder naming."""
    api, mocked_service = docs_api

    api.replace_template_variables(
        "doc-flat-sep",
        {
            "user": {
                "name": "Grace",
            }
        },
        flatten_nested_variables=True,
        nested_key_separator="__",
    )

    mocked_service.documents.return_value.batchUpdate.assert_called_once_with(
        documentId="doc-flat-sep",
        body={
            "requests": [
                {
                    "replaceAllText": {
                        "containsText": {
                            "text": "{{user__name}}",
                            "matchCase": True,
                        },
                        "replaceText": "Grace",
                    }
                }
            ]
        },
    )


def test_replace_template_variables_can_flatten_nested_sequences(docs_api):
    """Nested list/tuple values can be flattened into indexed placeholders."""
    api, mocked_service = docs_api

    api.replace_template_variables(
        "doc-flat-sequences",
        {
            "milestones": ["draft", "review"],
            "team": {
                "members": [
                    {"name": "Ada"},
                    {"name": "Grace"},
                ]
            },
        },
        flatten_nested_variables=True,
        flatten_nested_sequences=True,
    )

    mocked_service.documents.return_value.batchUpdate.assert_called_once_with(
        documentId="doc-flat-sequences",
        body={
            "requests": [
                {
                    "replaceAllText": {
                        "containsText": {
                            "text": "{{milestones.0}}",
                            "matchCase": True,
                        },
                        "replaceText": "draft",
                    }
                },
                {
                    "replaceAllText": {
                        "containsText": {
                            "text": "{{milestones.1}}",
                            "matchCase": True,
                        },
                        "replaceText": "review",
                    }
                },
                {
                    "replaceAllText": {
                        "containsText": {
                            "text": "{{team.members.0.name}}",
                            "matchCase": True,
                        },
                        "replaceText": "Ada",
                    }
                },
                {
                    "replaceAllText": {
                        "containsText": {
                            "text": "{{team.members.1.name}}",
                            "matchCase": True,
                        },
                        "replaceText": "Grace",
                    }
                },
            ]
        },
    )


def test_replace_template_variables_keeps_sequences_as_single_value_by_default(
    docs_api,
):
    """Sequence flattening is opt-in to preserve legacy placeholder behavior."""
    api, mocked_service = docs_api

    api.replace_template_variables(
        "doc-flat-sequences-default",
        {
            "milestones": ["draft", "review"],
        },
        flatten_nested_variables=True,
    )

    mocked_service.documents.return_value.batchUpdate.assert_called_once_with(
        documentId="doc-flat-sequences-default",
        body={
            "requests": [
                {
                    "replaceAllText": {
                        "containsText": {
                            "text": "{{milestones}}",
                            "matchCase": True,
                        },
                        "replaceText": "['draft', 'review']",
                    }
                }
            ]
        },
    )


def test_replace_template_variables_requires_nested_flattening_for_sequences(
    docs_api,
):
    """Sequence flattening requires flatten_nested_variables to be enabled."""
    api, mocked_service = docs_api

    with pytest.raises(
        ValueError,
        match="flatten_nested_sequences requires flatten_nested_variables=True",
    ):
        api.replace_template_variables(
            "doc-invalid-sequence-flatten",
            {"milestones": ["draft", "review"]},
            flatten_nested_sequences=True,
        )

    mocked_service.documents.return_value.batchUpdate.assert_not_called()


def test_replace_template_variables_rejects_duplicate_flattened_keys(docs_api):
    """Flattening should reject ambiguous placeholder collisions."""
    api, mocked_service = docs_api

    with pytest.raises(
        ValueError,
        match="flattened variables contain duplicate placeholder keys",
    ):
        api.replace_template_variables(
            "doc-collision",
            {
                "user.name": "Ada",
                "user": {
                    "name": "Grace",
                },
            },
            flatten_nested_variables=True,
        )

    mocked_service.documents.return_value.batchUpdate.assert_not_called()


@pytest.mark.parametrize("flatten_nested_variables", [None, "yes", 1])
def test_replace_template_variables_rejects_invalid_flatten_nested_variables(
    docs_api,
    flatten_nested_variables,
):
    """flatten_nested_variables must be explicitly provided as a boolean."""
    api, mocked_service = docs_api

    with pytest.raises(
        ValueError,
        match="flatten_nested_variables must be a boolean",
    ):
        api.replace_template_variables(
            "doc-invalid-flat",
            {"name": "AgentHQ"},
            flatten_nested_variables=flatten_nested_variables,  # type: ignore[arg-type]
        )

    mocked_service.documents.return_value.batchUpdate.assert_not_called()


@pytest.mark.parametrize("flatten_nested_sequences", [None, "yes", 1])
def test_replace_template_variables_rejects_invalid_flatten_nested_sequences(
    docs_api,
    flatten_nested_sequences,
):
    """flatten_nested_sequences must be explicitly provided as a boolean."""
    api, mocked_service = docs_api

    with pytest.raises(
        ValueError,
        match="flatten_nested_sequences must be a boolean",
    ):
        api.replace_template_variables(
            "doc-invalid-flat-sequences",
            {"name": "AgentHQ"},
            flatten_nested_sequences=flatten_nested_sequences,  # type: ignore[arg-type]
        )

    mocked_service.documents.return_value.batchUpdate.assert_not_called()


@pytest.mark.parametrize("nested_key_separator", [None, "", "   ", 123])
def test_replace_template_variables_rejects_invalid_nested_key_separator(
    docs_api,
    nested_key_separator,
):
    """nested_key_separator must be a non-empty string when provided."""
    api, mocked_service = docs_api

    with pytest.raises(
        ValueError,
        match="nested_key_separator must be a non-empty string",
    ):
        api.replace_template_variables(
            "doc-invalid-separator",
            {"name": "AgentHQ"},
            nested_key_separator=nested_key_separator,  # type: ignore[arg-type]
        )

    mocked_service.documents.return_value.batchUpdate.assert_not_called()


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


def test_replace_template_variables_chunks_requests_when_batch_limit_is_set(docs_api):
    """Large replacement payloads should be split into multiple batchUpdate calls."""
    api, mocked_service = docs_api
    batch_update = mocked_service.documents.return_value.batchUpdate
    batch_update.return_value.execute.side_effect = [
        {"replies": [{"batch": 1}]},
        {"replies": [{"batch": 2}]},
    ]

    result = api.replace_template_variables(
        "doc-3",
        {
            "first": "one",
            "second": "two",
            "third": "three",
        },
        max_requests_per_batch=2,
    )

    assert batch_update.call_count == 2
    assert batch_update.call_args_list[0].kwargs == {
        "documentId": "doc-3",
        "body": {
            "requests": [
                {
                    "replaceAllText": {
                        "containsText": {"text": "{{first}}", "matchCase": True},
                        "replaceText": "one",
                    }
                },
                {
                    "replaceAllText": {
                        "containsText": {"text": "{{second}}", "matchCase": True},
                        "replaceText": "two",
                    }
                },
            ]
        },
    }
    assert batch_update.call_args_list[1].kwargs == {
        "documentId": "doc-3",
        "body": {
            "requests": [
                {
                    "replaceAllText": {
                        "containsText": {"text": "{{third}}", "matchCase": True},
                        "replaceText": "three",
                    }
                }
            ]
        },
    }

    assert result == {
        "batchCount": 2,
        "requestCount": 3,
        "batchResponses": [
            {"replies": [{"batch": 1}]},
            {"replies": [{"batch": 2}]},
        ],
        "replies": [{"batch": 1}, {"batch": 2}],
    }


def test_replace_template_variables_allows_unbounded_single_batch_requests(docs_api):
    """Passing None as batch size should submit all replacements in one call."""
    api, mocked_service = docs_api

    api.replace_template_variables(
        "doc-4",
        {
            "first": "one",
            "second": "two",
            "third": "three",
        },
        max_requests_per_batch=None,
    )

    mocked_service.documents.return_value.batchUpdate.assert_called_once_with(
        documentId="doc-4",
        body={
            "requests": [
                {
                    "replaceAllText": {
                        "containsText": {"text": "{{first}}", "matchCase": True},
                        "replaceText": "one",
                    }
                },
                {
                    "replaceAllText": {
                        "containsText": {"text": "{{second}}", "matchCase": True},
                        "replaceText": "two",
                    }
                },
                {
                    "replaceAllText": {
                        "containsText": {"text": "{{third}}", "matchCase": True},
                        "replaceText": "three",
                    }
                },
            ]
        },
    )


@pytest.mark.parametrize("max_requests_per_batch", [0, -1, True, 1.5, "2"])
def test_replace_template_variables_rejects_invalid_batch_limits(
    docs_api,
    max_requests_per_batch,
):
    """Batch-size configuration should accept only positive integers or None."""
    api, mocked_service = docs_api

    with pytest.raises(
        ValueError,
        match="max_requests_per_batch must be a positive integer or None",
    ):
        api.replace_template_variables(
            "doc-5",
            {"name": "AgentHQ"},
            max_requests_per_batch=max_requests_per_batch,  # type: ignore[arg-type]
        )

    mocked_service.documents.return_value.batchUpdate.assert_not_called()


def test_replace_template_variables_dry_run_returns_batched_preview_payload(
    docs_api,
):
    """Dry-run mode should return generated requests without calling Google APIs."""
    api, mocked_service = docs_api

    result = api.replace_template_variables(
        "doc-preview",
        {
            "first": "one",
            "second": "two",
            "third": "three",
        },
        max_requests_per_batch=2,
        dry_run=True,
    )

    assert result == {
        "dryRun": True,
        "documentId": "doc-preview",
        "requestCount": 3,
        "batchCount": 2,
        "requestBatches": [
            {
                "requests": [
                    {
                        "replaceAllText": {
                            "containsText": {
                                "text": "{{first}}",
                                "matchCase": True,
                            },
                            "replaceText": "one",
                        }
                    },
                    {
                        "replaceAllText": {
                            "containsText": {
                                "text": "{{second}}",
                                "matchCase": True,
                            },
                            "replaceText": "two",
                        }
                    },
                ]
            },
            {
                "requests": [
                    {
                        "replaceAllText": {
                            "containsText": {
                                "text": "{{third}}",
                                "matchCase": True,
                            },
                            "replaceText": "three",
                        }
                    }
                ]
            },
        ],
    }

    mocked_service.documents.return_value.batchUpdate.assert_not_called()


@pytest.mark.parametrize("dry_run", [None, "yes", 1])
def test_replace_template_variables_rejects_invalid_dry_run_flags(
    docs_api,
    dry_run,
):
    """dry_run must be explicitly provided as a boolean."""
    api, mocked_service = docs_api

    with pytest.raises(ValueError, match="dry_run must be a boolean"):
        api.replace_template_variables(
            "doc-6",
            {"name": "AgentHQ"},
            dry_run=dry_run,  # type: ignore[arg-type]
        )

    mocked_service.documents.return_value.batchUpdate.assert_not_called()


def test_replace_template_variables_skip_none_values_omits_none_replacements(docs_api):
    """skip_none_values should exclude None-valued placeholders from requests."""
    api, mocked_service = docs_api

    result = api.replace_template_variables(
        "doc-7",
        {
            "name": "AgentHQ",
            "optional_note": None,
        },
        skip_none_values=True,
    )

    assert result == {"replies": [{}, {}]}
    mocked_service.documents.return_value.batchUpdate.assert_called_once_with(
        documentId="doc-7",
        body={
            "requests": [
                {
                    "replaceAllText": {
                        "containsText": {"text": "{{name}}", "matchCase": True},
                        "replaceText": "AgentHQ",
                    }
                }
            ]
        },
    )


def test_replace_template_variables_skip_none_values_short_circuits_empty_requests(
    docs_api,
):
    """All-None payloads should return deterministic no-op metadata."""
    api, mocked_service = docs_api

    result = api.replace_template_variables(
        "doc-8",
        {
            "optional_a": None,
            "optional_b": None,
        },
        skip_none_values=True,
    )

    assert result == {
        "documentId": "doc-8",
        "requestCount": 0,
        "batchCount": 0,
        "batchResponses": [],
        "replies": [],
    }
    mocked_service.documents.return_value.batchUpdate.assert_not_called()


@pytest.mark.parametrize("skip_none_values", [None, "yes", 1])
def test_replace_template_variables_rejects_invalid_skip_none_values_flags(
    docs_api,
    skip_none_values,
):
    """skip_none_values must be explicitly provided as a boolean."""
    api, mocked_service = docs_api

    with pytest.raises(ValueError, match="skip_none_values must be a boolean"):
        api.replace_template_variables(
            "doc-9",
            {"name": "AgentHQ"},
            skip_none_values=skip_none_values,  # type: ignore[arg-type]
        )

    mocked_service.documents.return_value.batchUpdate.assert_not_called()


def test_replace_template_variables_skip_blank_values_omits_blank_strings(docs_api):
    """skip_blank_values should exclude empty/whitespace-only string replacements."""
    api, mocked_service = docs_api

    result = api.replace_template_variables(
        "doc-10",
        {
            "name": "AgentHQ",
            "empty": "",
            "spaces": "   ",
            "count": 3,
        },
        skip_blank_values=True,
    )

    assert result == {"replies": [{}, {}]}
    mocked_service.documents.return_value.batchUpdate.assert_called_once_with(
        documentId="doc-10",
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
                        "containsText": {"text": "{{count}}", "matchCase": True},
                        "replaceText": "3",
                    }
                },
            ]
        },
    )


def test_replace_template_variables_skip_blank_values_short_circuits_empty_requests(
    docs_api,
):
    """All-blank string payloads should return deterministic no-op metadata."""
    api, mocked_service = docs_api

    result = api.replace_template_variables(
        "doc-11",
        {
            "optional_a": "",
            "optional_b": "  ",
        },
        skip_blank_values=True,
    )

    assert result == {
        "documentId": "doc-11",
        "requestCount": 0,
        "batchCount": 0,
        "batchResponses": [],
        "replies": [],
    }
    mocked_service.documents.return_value.batchUpdate.assert_not_called()


@pytest.mark.parametrize("skip_blank_values", [None, "yes", 1])
def test_replace_template_variables_rejects_invalid_skip_blank_values_flags(
    docs_api,
    skip_blank_values,
):
    """skip_blank_values must be explicitly provided as a boolean."""
    api, mocked_service = docs_api

    with pytest.raises(ValueError, match="skip_blank_values must be a boolean"):
        api.replace_template_variables(
            "doc-12",
            {"name": "AgentHQ"},
            skip_blank_values=skip_blank_values,  # type: ignore[arg-type]
        )

    mocked_service.documents.return_value.batchUpdate.assert_not_called()
