"""Tests for JWT helpers in app.core.security."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
)


def test_decode_token_accepts_expected_access_type() -> None:
    token = create_access_token({"sub": "user-123", "scope": "chat:read"})

    payload = decode_token(token, expected_type="access")

    assert payload is not None
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"


def test_decode_token_rejects_type_mismatch() -> None:
    refresh_token = create_refresh_token({"sub": "user-123"})

    assert decode_token(refresh_token, expected_type="access") is None


def test_decode_token_accepts_expected_type_allowlist_match() -> None:
    token = create_access_token({"sub": "user-123"})

    payload = decode_token(token, expected_type=["refresh", "access"])

    assert payload is not None
    assert payload["type"] == "access"


def test_decode_token_validates_expected_type_input() -> None:
    token = create_access_token({"sub": "user-123"})

    with pytest.raises(ValueError, match="expected_type cannot be blank"):
        decode_token(token, expected_type="   ")

    with pytest.raises(ValueError, match="expected_type cannot be an empty iterable"):
        decode_token(token, expected_type=[])

    with pytest.raises(TypeError, match="expected_type must contain only strings"):
        decode_token(token, expected_type=["access", 123])

    with pytest.raises(ValueError, match="expected_type cannot contain blank values"):
        decode_token(token, expected_type=["access", "   "])


def test_decode_token_accepts_expected_subject_string_match() -> None:
    token = create_access_token({"sub": "user-123"})

    payload = decode_token(token, expected_subject="user-123")

    assert payload is not None
    assert payload["sub"] == "user-123"


def test_decode_token_accepts_expected_subject_allowlist_match() -> None:
    token = create_access_token({"sub": "user-123"})

    payload = decode_token(
        token,
        expected_subject=("user-456", "user-123"),
    )

    assert payload is not None


def test_decode_token_rejects_missing_or_mismatched_expected_subject() -> None:
    token = create_access_token({"sub": "user-123"})

    assert decode_token(token, expected_subject="user-999") is None
    assert (
        decode_token(
            create_access_token({"scope": "chat:read"}),
            expected_subject="user-123",
        )
        is None
    )


def test_decode_token_validates_expected_subject_input() -> None:
    token = create_access_token({"sub": "user-123"})

    with pytest.raises(ValueError, match="expected_subject cannot be blank"):
        decode_token(token, expected_subject="   ")

    with pytest.raises(
        ValueError,
        match="expected_subject cannot be an empty iterable",
    ):
        decode_token(token, expected_subject=[])

    with pytest.raises(
        TypeError,
        match="expected_subject must contain only strings",
    ):
        decode_token(token, expected_subject=["user-123", 123])

    with pytest.raises(
        ValueError,
        match="expected_subject cannot contain blank values",
    ):
        decode_token(token, expected_subject=["user-123", "   "])


def test_decode_token_rejects_missing_required_claim() -> None:
    token_without_sub = create_access_token({"scope": "chat:read"})

    assert decode_token(token_without_sub, required_claims=("sub",)) is None


def test_decode_token_rejects_blank_required_string_claim() -> None:
    token_with_blank_subject = create_access_token({"sub": "   "})

    assert decode_token(token_with_blank_subject, required_claims=("sub",)) is None


def test_decode_token_validates_required_claims_input() -> None:
    token = create_access_token({"sub": "user-123"})

    with pytest.raises(TypeError, match="required_claims must contain only strings"):
        decode_token(token, required_claims=("sub", 1))  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="required_claims cannot contain blank values"):
        decode_token(token, required_claims=("sub", "  "))


def test_decode_token_accepts_required_claim_values_exact_match() -> None:
    token = create_access_token({"sub": "user-123", "scope": "chat:read"})

    payload = decode_token(
        token,
        required_claim_values={"scope": "chat:read"},
    )

    assert payload is not None
    assert payload["scope"] == "chat:read"


def test_decode_token_accepts_required_claim_values_allowlist_match() -> None:
    token = create_access_token({"sub": "user-123", "role": "editor"})

    payload = decode_token(
        token,
        required_claim_values={"role": ("admin", "editor")},
    )

    assert payload is not None
    assert payload["role"] == "editor"


def test_decode_token_accepts_required_claim_values_for_collection_claims() -> None:
    token = create_access_token(
        {
            "sub": "user-123",
            "roles": ["viewer", "editor"],
        }
    )

    payload = decode_token(
        token,
        required_claim_values={"roles": ("admin", "editor")},
    )

    assert payload is not None
    assert payload["roles"] == ["viewer", "editor"]


def test_decode_token_rejects_required_claim_values_when_collection_claim_misses() -> (
    None
):
    token = create_access_token(
        {
            "sub": "user-123",
            "roles": ["viewer", "reader"],
        }
    )

    assert (
        decode_token(
            token,
            required_claim_values={"roles": ("admin", "editor")},
        )
        is None
    )


def test_decode_token_rejects_missing_or_mismatched_required_claim_values() -> None:
    token = create_access_token({"sub": "user-123", "scope": "chat:read"})

    assert (
        decode_token(
            token,
            required_claim_values={"scope": "chat:write"},
        )
        is None
    )
    assert (
        decode_token(
            token,
            required_claim_values={"aud": "api://agenthq"},
        )
        is None
    )


def test_decode_token_validates_required_claim_values_input() -> None:
    token = create_access_token({"sub": "user-123", "scope": "chat:read"})

    with pytest.raises(TypeError, match="required_claim_values must be a mapping"):
        decode_token(
            token,
            required_claim_values=[("scope", "chat:read")],  # type: ignore[arg-type]
        )

    with pytest.raises(
        TypeError,
        match="required_claim_values keys must be strings",
    ):
        decode_token(
            token,
            required_claim_values={1: "chat:read"},  # type: ignore[dict-item]
        )

    with pytest.raises(
        ValueError,
        match="required_claim_values cannot contain blank claim names",
    ):
        decode_token(token, required_claim_values={"   ": "chat:read"})

    with pytest.raises(
        ValueError,
        match="cannot be an empty collection",
    ):
        decode_token(token, required_claim_values={"scope": []})


def test_decode_token_accepts_expected_issuer() -> None:
    token = create_access_token({"sub": "user-123", "iss": "agenthq-auth"})

    payload = decode_token(token, expected_issuer="agenthq-auth")

    assert payload is not None
    assert payload["iss"] == "agenthq-auth"


def test_decode_token_rejects_missing_or_mismatched_expected_issuer() -> None:
    token = create_access_token({"sub": "user-123", "iss": "agenthq-auth"})

    assert decode_token(token, expected_issuer="other-issuer") is None
    assert (
        decode_token(
            create_access_token({"sub": "user-123"}), expected_issuer="agenthq-auth"
        )
        is None
    )


def test_decode_token_validates_expected_issuer_input() -> None:
    token = create_access_token({"sub": "user-123", "iss": "agenthq-auth"})

    with pytest.raises(TypeError, match="expected_issuer must be a string"):
        decode_token(token, expected_issuer=123)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="expected_issuer cannot be blank"):
        decode_token(token, expected_issuer="   ")


def test_decode_token_accepts_expected_audience_string_match() -> None:
    token = create_access_token({"sub": "user-123", "aud": "api://agenthq"})

    payload = decode_token(token, expected_audience="api://agenthq")

    assert payload is not None
    assert payload["aud"] == "api://agenthq"


def test_decode_token_accepts_expected_audience_allowlist_match() -> None:
    token = create_access_token(
        {
            "sub": "user-123",
            "aud": ["api://agenthq", "api://analytics"],
        }
    )

    payload = decode_token(
        token,
        expected_audience=("api://other", "api://analytics"),
    )

    assert payload is not None


def test_decode_token_rejects_missing_or_mismatched_expected_audience() -> None:
    token = create_access_token({"sub": "user-123", "aud": "api://agenthq"})

    assert decode_token(token, expected_audience="api://other") is None
    assert (
        decode_token(
            create_access_token({"sub": "user-123"}),
            expected_audience="api://agenthq",
        )
        is None
    )


def test_decode_token_rejects_invalid_token_audience_payload_shape() -> None:
    token_with_invalid_audience = create_access_token(
        {"sub": "user-123", "aud": ["api://agenthq", 42]}
    )

    assert (
        decode_token(token_with_invalid_audience, expected_audience="api://agenthq")
        is None
    )


def test_decode_token_validates_expected_audience_input() -> None:
    token = create_access_token({"sub": "user-123", "aud": "api://agenthq"})

    with pytest.raises(ValueError, match="expected_audience cannot be blank"):
        decode_token(token, expected_audience="   ")

    with pytest.raises(
        ValueError, match="expected_audience cannot be an empty iterable"
    ):
        decode_token(token, expected_audience=[])

    with pytest.raises(
        TypeError,
        match="expected_audience must contain only strings",
    ):
        decode_token(token, expected_audience=["api://agenthq", 123])

    with pytest.raises(
        ValueError,
        match="expected_audience cannot contain blank values",
    ):
        decode_token(token, expected_audience=["api://agenthq", "   "])


def test_decode_token_accepts_required_scopes_all_match() -> None:
    token = create_access_token(
        {
            "sub": "user-123",
            "scope": "chat:read profile:view offline_access",
        }
    )

    payload = decode_token(
        token,
        required_scopes=["chat:read", "profile:view"],
    )

    assert payload is not None


def test_decode_token_accepts_required_scopes_with_match_any_mode() -> None:
    token = create_access_token(
        {
            "sub": "user-123",
            "scope": ["chat:read", "analytics:view"],
        }
    )

    payload = decode_token(
        token,
        required_scopes=["chat:write", "analytics:view"],
        match_any_scopes=True,
    )

    assert payload is not None


def test_decode_token_rejects_missing_required_scopes() -> None:
    token = create_access_token({"sub": "user-123", "scope": "chat:read"})

    assert decode_token(token, required_scopes=["chat:read", "chat:write"]) is None


def test_decode_token_supports_custom_scope_claim_name() -> None:
    token = create_access_token(
        {
            "sub": "user-123",
            "scp": "chat:read,chat:write",
        }
    )

    payload = decode_token(
        token,
        required_scopes="chat:write",
        scope_claim="scp",
    )

    assert payload is not None


def test_decode_token_rejects_invalid_scope_claim_payload_shape() -> None:
    token = create_access_token(
        {
            "sub": "user-123",
            "scope": ["chat:read", 42],
        }
    )

    assert decode_token(token, required_scopes="chat:read") is None


def test_decode_token_validates_scope_requirement_inputs() -> None:
    token = create_access_token({"sub": "user-123", "scope": "chat:read"})

    with pytest.raises(ValueError, match="required_scopes cannot be blank"):
        decode_token(token, required_scopes="   ")

    with pytest.raises(ValueError, match="required_scopes cannot be an empty iterable"):
        decode_token(token, required_scopes=[])

    with pytest.raises(TypeError, match="required_scopes must contain only strings"):
        decode_token(token, required_scopes=["chat:read", 123])

    with pytest.raises(TypeError, match="scope_claim must be a string"):
        decode_token(token, required_scopes="chat:read", scope_claim=123)

    with pytest.raises(ValueError, match="scope_claim cannot be blank"):
        decode_token(token, required_scopes="chat:read", scope_claim="   ")

    with pytest.raises(TypeError, match="match_any_scopes must be a boolean"):
        decode_token(token, required_scopes="chat:read", match_any_scopes="yes")


def test_decode_token_rejects_expired_tokens_without_leeway() -> None:
    token = create_access_token(
        {"sub": "user-123"},
        expires_delta=timedelta(seconds=-1),
    )

    assert decode_token(token, expected_subject="user-123") is None


def test_decode_token_accepts_expired_tokens_with_leeway() -> None:
    token = create_access_token(
        {"sub": "user-123"},
        expires_delta=timedelta(seconds=-1),
    )

    payload = decode_token(
        token,
        expected_subject="user-123",
        leeway_seconds=5,
    )

    assert payload is not None
    assert payload["sub"] == "user-123"


def test_create_access_token_adds_iat_claim_by_default() -> None:
    token = create_access_token({"sub": "user-123"})

    payload = decode_token(token, expected_subject="user-123")

    assert payload is not None
    assert isinstance(payload.get("iat"), (int, float))


def test_decode_token_accepts_tokens_within_max_age_window() -> None:
    token = create_access_token({"sub": "user-123"})

    payload = decode_token(
        token,
        expected_subject="user-123",
        max_age_seconds=60,
    )

    assert payload is not None
    assert payload["sub"] == "user-123"


def test_decode_token_rejects_tokens_older_than_max_age() -> None:
    token = create_access_token(
        {
            "sub": "user-123",
            "iat": datetime.utcnow() - timedelta(minutes=10),
        },
        expires_delta=timedelta(minutes=30),
    )

    assert (
        decode_token(
            token,
            expected_subject="user-123",
            max_age_seconds=60,
        )
        is None
    )


def test_decode_token_validates_max_age_seconds_input() -> None:
    token = create_access_token({"sub": "user-123"})

    with pytest.raises(TypeError, match="max_age_seconds must be a numeric value"):
        decode_token(token, max_age_seconds="60")  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="max_age_seconds must be a numeric value"):
        decode_token(token, max_age_seconds=True)  # type: ignore[arg-type]

    with pytest.raises(
        ValueError,
        match="max_age_seconds must be greater than or equal to 0",
    ):
        decode_token(token, max_age_seconds=-1)


def test_decode_token_validates_leeway_seconds_input() -> None:
    token = create_access_token({"sub": "user-123"})

    with pytest.raises(TypeError, match="leeway_seconds must be a numeric value"):
        decode_token(token, leeway_seconds="5")  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="leeway_seconds must be a numeric value"):
        decode_token(token, leeway_seconds=True)  # type: ignore[arg-type]

    with pytest.raises(
        ValueError,
        match="leeway_seconds must be greater than or equal to 0",
    ):
        decode_token(token, leeway_seconds=-1)
