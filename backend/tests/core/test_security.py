"""Tests for JWT helpers in app.core.security."""

from __future__ import annotations

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
