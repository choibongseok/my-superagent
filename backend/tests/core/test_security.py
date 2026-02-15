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
