"""Security utilities for authentication and authorization."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def create_access_token(
    data: dict,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode.update({"exp": expire, "type": "access"})

    return jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def create_refresh_token(data: dict) -> str:
    """Create a JWT refresh token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode.update({"exp": expire, "type": "refresh"})

    return jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def _normalize_required_claims(
    required_claims: Iterable[str] | None,
) -> tuple[str, ...]:
    """Normalize required-claim inputs used by ``decode_token``."""
    if required_claims is None:
        return ()

    normalized_claims: list[str] = []
    for claim in required_claims:
        if not isinstance(claim, str):
            raise TypeError("required_claims must contain only strings")

        normalized_claim = claim.strip()
        if not normalized_claim:
            raise ValueError("required_claims cannot contain blank values")

        normalized_claims.append(normalized_claim)

    return tuple(dict.fromkeys(normalized_claims))


def _normalize_required_claim_values(
    required_claim_values: Mapping[str, Any] | None,
) -> dict[str, tuple[Any, ...]]:
    """Normalize exact/allowlist claim-value requirements for ``decode_token``."""
    if required_claim_values is None:
        return {}

    if not isinstance(required_claim_values, Mapping):
        raise TypeError("required_claim_values must be a mapping")

    normalized_claim_values: dict[str, tuple[Any, ...]] = {}
    for claim_name, expected_value in required_claim_values.items():
        if not isinstance(claim_name, str):
            raise TypeError("required_claim_values keys must be strings")

        normalized_claim_name = claim_name.strip()
        if not normalized_claim_name:
            raise ValueError("required_claim_values cannot contain blank claim names")

        if isinstance(expected_value, (list, tuple, set, frozenset)):
            normalized_expected_values = tuple(expected_value)
            if not normalized_expected_values:
                raise ValueError(
                    "required_claim_values for claim "
                    f"'{normalized_claim_name}' cannot be an empty collection"
                )
        else:
            normalized_expected_values = (expected_value,)

        normalized_claim_values[normalized_claim_name] = normalized_expected_values

    return normalized_claim_values


def _normalize_expected_audiences(
    expected_audience: str | Iterable[str] | None,
) -> tuple[str, ...]:
    """Normalize expected audience requirements for ``decode_token``."""
    if expected_audience is None:
        return ()

    if isinstance(expected_audience, str):
        normalized_audience = expected_audience.strip()
        if not normalized_audience:
            raise ValueError("expected_audience cannot be blank")

        return (normalized_audience,)

    normalized_audiences: list[str] = []
    for audience in expected_audience:
        if not isinstance(audience, str):
            raise TypeError("expected_audience must contain only strings")

        normalized_audience = audience.strip()
        if not normalized_audience:
            raise ValueError("expected_audience cannot contain blank values")

        normalized_audiences.append(normalized_audience)

    if not normalized_audiences:
        raise ValueError("expected_audience cannot be an empty iterable")

    return tuple(dict.fromkeys(normalized_audiences))


def _extract_token_audiences(payload: Mapping[str, Any]) -> tuple[str, ...] | None:
    """Extract normalized token audiences from decoded payload."""
    audience_claim = payload.get("aud")
    if audience_claim is None:
        return None

    if isinstance(audience_claim, str):
        normalized_audience = audience_claim.strip()
        if not normalized_audience:
            return None

        return (normalized_audience,)

    if isinstance(audience_claim, (list, tuple, set, frozenset)):
        normalized_audiences: list[str] = []
        for audience in audience_claim:
            if not isinstance(audience, str):
                return None

            normalized_audience = audience.strip()
            if not normalized_audience:
                return None

            normalized_audiences.append(normalized_audience)

        if not normalized_audiences:
            return None

        return tuple(dict.fromkeys(normalized_audiences))

    return None


def decode_token(
    token: str,
    *,
    expected_type: str | None = None,
    expected_issuer: str | None = None,
    expected_audience: str | Iterable[str] | None = None,
    required_claims: Iterable[str] | None = None,
    required_claim_values: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Decode a JWT token with optional type/claim validation.

    Args:
        token: JWT token string.
        expected_type: Optional token ``type`` claim value to enforce.
        expected_issuer: Optional token ``iss`` claim value to enforce.
        expected_audience: Optional token ``aud`` claim value(s) to enforce.
            Accepts either a single audience string or an iterable of allowed
            audience values.
        required_claims: Optional claims that must be present and non-empty.
        required_claim_values: Optional claim value requirements. Values may
            be exact scalars or non-empty collections of allowed values.

    Returns:
        Decoded payload when valid, otherwise ``None``.
    """
    if expected_issuer is not None:
        if not isinstance(expected_issuer, str):
            raise TypeError("expected_issuer must be a string when provided")

        expected_issuer = expected_issuer.strip()
        if not expected_issuer:
            raise ValueError("expected_issuer cannot be blank")

    normalized_expected_audiences = _normalize_expected_audiences(expected_audience)
    normalized_required_claims = _normalize_required_claims(required_claims)
    normalized_required_claim_values = _normalize_required_claim_values(
        required_claim_values
    )

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_aud": False},
        )
    except JWTError:
        return None

    if expected_type is not None and payload.get("type") != expected_type:
        return None

    if expected_issuer is not None and payload.get("iss") != expected_issuer:
        return None

    if normalized_expected_audiences:
        token_audiences = _extract_token_audiences(payload)
        if token_audiences is None:
            return None

        if not set(token_audiences).intersection(normalized_expected_audiences):
            return None

    for claim in normalized_required_claims:
        claim_value = payload.get(claim)
        if claim_value is None:
            return None

        if isinstance(claim_value, str) and not claim_value.strip():
            return None

    for claim, expected_values in normalized_required_claim_values.items():
        claim_value = payload.get(claim)
        if claim_value is None or claim_value not in expected_values:
            return None

    return payload
