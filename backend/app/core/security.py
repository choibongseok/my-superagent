"""Security utilities for authentication and authorization."""

from __future__ import annotations

from collections.abc import Iterable
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


def decode_token(
    token: str,
    *,
    expected_type: str | None = None,
    required_claims: Iterable[str] | None = None,
) -> dict[str, Any] | None:
    """Decode a JWT token with optional type/claim validation.

    Args:
        token: JWT token string.
        expected_type: Optional token ``type`` claim value to enforce.
        required_claims: Optional claims that must be present and non-empty.

    Returns:
        Decoded payload when valid, otherwise ``None``.
    """
    normalized_required_claims = _normalize_required_claims(required_claims)

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
    except JWTError:
        return None

    if expected_type is not None and payload.get("type") != expected_type:
        return None

    for claim in normalized_required_claims:
        claim_value = payload.get(claim)
        if claim_value is None:
            return None

        if isinstance(claim_value, str) and not claim_value.strip():
            return None

    return payload
