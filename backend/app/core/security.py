"""Security utilities for authentication and authorization."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta
import re
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


_SCOPE_SPLIT_PATTERN = re.compile(r"[,\s]+")


def _split_scope_tokens(raw_scopes: str) -> tuple[str, ...]:
    """Split scope strings into normalized scope tokens."""
    normalized_scope_string = raw_scopes.strip()
    if not normalized_scope_string:
        return ()

    scopes = tuple(
        token for token in _SCOPE_SPLIT_PATTERN.split(normalized_scope_string) if token
    )
    if not scopes:
        return ()

    return tuple(dict.fromkeys(scopes))


def _normalize_required_scopes(
    required_scopes: str | Iterable[str] | None,
) -> tuple[str, ...]:
    """Normalize required scope inputs used by ``decode_token``."""
    if required_scopes is None:
        return ()

    if isinstance(required_scopes, str):
        normalized_scopes = _split_scope_tokens(required_scopes)
        if not normalized_scopes:
            raise ValueError("required_scopes cannot be blank")

        return normalized_scopes

    normalized_scopes: list[str] = []
    for scope in required_scopes:
        if not isinstance(scope, str):
            raise TypeError("required_scopes must contain only strings")

        scope_tokens = _split_scope_tokens(scope)
        if not scope_tokens:
            raise ValueError("required_scopes cannot contain blank values")

        normalized_scopes.extend(scope_tokens)

    if not normalized_scopes:
        raise ValueError("required_scopes cannot be an empty iterable")

    return tuple(dict.fromkeys(normalized_scopes))


def _normalize_scope_claim_name(scope_claim: str) -> str:
    """Normalize optional scope-claim names for ``decode_token``."""
    if not isinstance(scope_claim, str):
        raise TypeError("scope_claim must be a string")

    normalized_scope_claim = scope_claim.strip()
    if not normalized_scope_claim:
        raise ValueError("scope_claim cannot be blank")

    return normalized_scope_claim


def _extract_token_scopes(
    payload: Mapping[str, Any],
    scope_claim: str,
) -> tuple[str, ...] | None:
    """Extract normalized token scopes from decoded payload."""
    claim_value = payload.get(scope_claim)
    if claim_value is None:
        return None

    if isinstance(claim_value, str):
        token_scopes = _split_scope_tokens(claim_value)
        return token_scopes or None

    if isinstance(claim_value, (list, tuple, set, frozenset)):
        normalized_scopes: list[str] = []
        for item in claim_value:
            if not isinstance(item, str):
                return None

            scope_tokens = _split_scope_tokens(item)
            if not scope_tokens:
                return None

            normalized_scopes.extend(scope_tokens)

        if not normalized_scopes:
            return None

        return tuple(dict.fromkeys(normalized_scopes))

    return None


def _normalize_expected_subjects(
    expected_subject: str | Iterable[str] | None,
) -> tuple[str, ...]:
    """Normalize expected subject requirements for ``decode_token``."""
    if expected_subject is None:
        return ()

    if isinstance(expected_subject, str):
        normalized_subject = expected_subject.strip()
        if not normalized_subject:
            raise ValueError("expected_subject cannot be blank")

        return (normalized_subject,)

    normalized_subjects: list[str] = []
    for subject in expected_subject:
        if not isinstance(subject, str):
            raise TypeError("expected_subject must contain only strings")

        normalized_subject = subject.strip()
        if not normalized_subject:
            raise ValueError("expected_subject cannot contain blank values")

        normalized_subjects.append(normalized_subject)

    if not normalized_subjects:
        raise ValueError("expected_subject cannot be an empty iterable")

    return tuple(dict.fromkeys(normalized_subjects))


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


def _normalize_leeway_seconds(leeway_seconds: int | float | None) -> float:
    """Normalize optional JWT leeway seconds for clock-skew tolerance."""
    if leeway_seconds is None:
        return 0.0

    if isinstance(leeway_seconds, bool) or not isinstance(leeway_seconds, (int, float)):
        raise TypeError("leeway_seconds must be a numeric value")

    normalized_leeway = float(leeway_seconds)
    if normalized_leeway < 0:
        raise ValueError("leeway_seconds must be greater than or equal to 0")

    return normalized_leeway


def decode_token(
    token: str,
    *,
    expected_type: str | None = None,
    expected_subject: str | Iterable[str] | None = None,
    expected_issuer: str | None = None,
    expected_audience: str | Iterable[str] | None = None,
    required_claims: Iterable[str] | None = None,
    required_claim_values: Mapping[str, Any] | None = None,
    required_scopes: str | Iterable[str] | None = None,
    scope_claim: str = "scope",
    match_any_scopes: bool = False,
    leeway_seconds: int | float | None = None,
) -> dict[str, Any] | None:
    """Decode a JWT token with optional type/claim validation.

    Args:
        token: JWT token string.
        expected_type: Optional token ``type`` claim value to enforce.
        expected_subject: Optional token ``sub`` claim value(s) to enforce.
            Accepts either a single subject string or an iterable of allowed
            subject values.
        expected_issuer: Optional token ``iss`` claim value to enforce.
        expected_audience: Optional token ``aud`` claim value(s) to enforce.
            Accepts either a single audience string or an iterable of allowed
            audience values.
        required_claims: Optional claims that must be present and non-empty.
        required_claim_values: Optional claim value requirements. Values may
            be exact scalars or non-empty collections of allowed values.
        required_scopes: Optional OAuth-style scope requirements. Accepts a
            scope string (space/comma-delimited) or iterable of scope strings.
        scope_claim: Token claim name containing scopes. Defaults to
            ``"scope"``.
        match_any_scopes: Scope matching mode. ``False`` (default) requires
            every ``required_scopes`` entry to be present. ``True`` requires
            at least one matching scope.
        leeway_seconds: Optional expiration/not-before clock-skew tolerance
            applied during JWT decode.

    Returns:
        Decoded payload when valid, otherwise ``None``.
    """
    if expected_issuer is not None:
        if not isinstance(expected_issuer, str):
            raise TypeError("expected_issuer must be a string when provided")

        expected_issuer = expected_issuer.strip()
        if not expected_issuer:
            raise ValueError("expected_issuer cannot be blank")

    if not isinstance(match_any_scopes, bool):
        raise TypeError("match_any_scopes must be a boolean")

    normalized_expected_subjects = _normalize_expected_subjects(expected_subject)
    normalized_expected_audiences = _normalize_expected_audiences(expected_audience)
    normalized_required_claims = _normalize_required_claims(required_claims)
    normalized_required_claim_values = _normalize_required_claim_values(
        required_claim_values
    )
    normalized_required_scopes = _normalize_required_scopes(required_scopes)
    normalized_scope_claim = _normalize_scope_claim_name(scope_claim)
    normalized_leeway_seconds = _normalize_leeway_seconds(leeway_seconds)

    decode_options: dict[str, Any] = {"verify_aud": False}
    if normalized_leeway_seconds > 0:
        decode_options["leeway"] = normalized_leeway_seconds

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options=decode_options,
        )
    except JWTError:
        return None

    if expected_type is not None and payload.get("type") != expected_type:
        return None

    if normalized_expected_subjects:
        subject_claim = payload.get("sub")
        if not isinstance(subject_claim, str):
            return None

        normalized_subject_claim = subject_claim.strip()
        if not normalized_subject_claim:
            return None

        if normalized_subject_claim not in normalized_expected_subjects:
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

    if normalized_required_scopes:
        token_scopes = _extract_token_scopes(payload, normalized_scope_claim)
        if token_scopes is None:
            return None

        token_scope_set = set(token_scopes)
        required_scope_set = set(normalized_required_scopes)

        if match_any_scopes:
            if token_scope_set.isdisjoint(required_scope_set):
                return None
        elif not required_scope_set.issubset(token_scope_set):
            return None

    return payload
