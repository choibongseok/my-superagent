"""Security utilities for authentication and authorization."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta
from fnmatch import fnmatchcase
import re
import time
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

    issued_at = datetime.utcnow()

    if expires_delta:
        expire = issued_at + expires_delta
    else:
        expire = issued_at + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.setdefault("iat", issued_at)
    to_encode.update({"exp": expire, "type": "access"})

    return jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def create_refresh_token(data: dict) -> str:
    """Create a JWT refresh token."""
    to_encode = data.copy()
    issued_at = datetime.utcnow()
    expire = issued_at + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode.setdefault("iat", issued_at)
    to_encode.update({"exp": expire, "type": "refresh"})

    return jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def _normalize_expected_types(
    expected_type: str | Iterable[str] | None,
) -> tuple[str, ...]:
    """Normalize expected token type requirements for ``decode_token``."""
    if expected_type is None:
        return ()

    if isinstance(expected_type, str):
        normalized_expected_type = expected_type.strip()
        if not normalized_expected_type:
            raise ValueError("expected_type cannot be blank")

        return (normalized_expected_type,)

    normalized_expected_types: list[str] = []
    for token_type in expected_type:
        if not isinstance(token_type, str):
            raise TypeError("expected_type must contain only strings")

        normalized_token_type = token_type.strip()
        if not normalized_token_type:
            raise ValueError("expected_type cannot contain blank values")

        normalized_expected_types.append(normalized_token_type)

    if not normalized_expected_types:
        raise ValueError("expected_type cannot be an empty iterable")

    return tuple(dict.fromkeys(normalized_expected_types))


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


def _normalize_required_claim_patterns(
    required_claim_patterns: Mapping[str, str | re.Pattern[str]] | None,
) -> dict[str, re.Pattern[str]]:
    """Normalize regex-based claim requirements for ``decode_token``."""
    if required_claim_patterns is None:
        return {}

    if not isinstance(required_claim_patterns, Mapping):
        raise TypeError("required_claim_patterns must be a mapping")

    normalized_patterns: dict[str, re.Pattern[str]] = {}
    for claim_name, pattern_value in required_claim_patterns.items():
        if not isinstance(claim_name, str):
            raise TypeError("required_claim_patterns keys must be strings")

        normalized_claim_name = claim_name.strip()
        if not normalized_claim_name:
            raise ValueError("required_claim_patterns cannot contain blank claim names")

        if isinstance(pattern_value, re.Pattern):
            compiled_pattern = pattern_value
        elif isinstance(pattern_value, str):
            normalized_pattern = pattern_value.strip()
            if not normalized_pattern:
                raise ValueError(
                    "required_claim_patterns values cannot be blank patterns"
                )

            try:
                compiled_pattern = re.compile(normalized_pattern)
            except re.error as exc:
                raise ValueError(
                    "required_claim_patterns contains an invalid regex pattern"
                ) from exc
        else:
            raise TypeError(
                "required_claim_patterns values must be regex patterns or pattern strings"
            )

        normalized_patterns[normalized_claim_name] = compiled_pattern

    return normalized_patterns


def _claim_value_matches_expected_values(
    claim_value: Any,
    expected_values: tuple[Any, ...],
) -> bool:
    """Return whether decoded claim values satisfy expected scalar/allowlist values.

    Scalar claims require an exact match against at least one expected value.
    Collection claims (list/tuple/set/frozenset) match when any contained
    value matches at least one expected value.
    """
    if isinstance(claim_value, (list, tuple, set, frozenset)):
        for candidate_value in claim_value:
            if any(
                candidate_value == expected_value for expected_value in expected_values
            ):
                return True
        return False

    return any(claim_value == expected_value for expected_value in expected_values)


def _resolve_claim_value(
    payload: Mapping[str, Any],
    claim_name: str,
) -> tuple[bool, Any]:
    """Resolve claim values using exact names or dotted nested claim paths.

    Exact key matches take priority. When direct lookup fails, dotted claim
    names (for example ``"context.tenant.id"``) are resolved against nested
    mapping values.

    Returns:
        ``(True, value)`` when the claim is present, otherwise ``(False, None)``.
    """
    if claim_name in payload:
        return True, payload[claim_name]

    if "." not in claim_name:
        return False, None

    current_value: Any = payload
    for segment in claim_name.split("."):
        if segment == "" or not isinstance(current_value, Mapping):
            return False, None

        if segment not in current_value:
            return False, None

        current_value = current_value[segment]

    return True, current_value


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


def _scope_requirement_matches(
    required_scope: str,
    token_scope_set: set[str],
) -> bool:
    """Return whether one required scope is satisfied by token scopes.

    Required scopes support glob patterns (for example, ``"chat:*"``).
    """
    if any(token in required_scope for token in "*?["):
        return any(
            fnmatchcase(token_scope, required_scope) for token_scope in token_scope_set
        )

    return required_scope in token_scope_set


def _normalize_scope_claim_name(scope_claim: str) -> str:
    """Normalize optional scope-claim names for ``decode_token``."""
    if not isinstance(scope_claim, str):
        raise TypeError("scope_claim must be a string")

    normalized_scope_claim = scope_claim.strip()
    if not normalized_scope_claim:
        raise ValueError("scope_claim cannot be blank")

    return normalized_scope_claim


def _normalize_scope_claim_fallbacks(
    scope_claim_fallbacks: str | Iterable[str] | None,
) -> tuple[str, ...]:
    """Normalize optional scope-claim fallback names for ``decode_token``."""
    if scope_claim_fallbacks is None:
        return ()

    if isinstance(scope_claim_fallbacks, str):
        return (_normalize_scope_claim_name(scope_claim_fallbacks),)

    normalized_scope_claims: list[str] = []
    for scope_claim in scope_claim_fallbacks:
        if not isinstance(scope_claim, str):
            raise TypeError("scope_claim_fallbacks must contain only strings")

        normalized_scope_claim = scope_claim.strip()
        if not normalized_scope_claim:
            raise ValueError("scope_claim_fallbacks cannot contain blank values")

        normalized_scope_claims.append(normalized_scope_claim)

    if not normalized_scope_claims:
        raise ValueError("scope_claim_fallbacks cannot be an empty iterable")

    return tuple(dict.fromkeys(normalized_scope_claims))


def _extract_token_scopes_from_claim_value(
    claim_value: Any,
) -> tuple[str, ...] | None:
    """Extract normalized token scopes from one decoded claim value."""
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


def _extract_token_scopes(
    payload: Mapping[str, Any],
    scope_claim: str,
) -> tuple[str, ...] | None:
    """Extract normalized token scopes from one decoded payload claim."""
    claim_exists, claim_value = _resolve_claim_value(payload, scope_claim)
    if not claim_exists:
        return None

    return _extract_token_scopes_from_claim_value(claim_value)


def _extract_token_scopes_with_fallbacks(
    payload: Mapping[str, Any],
    scope_claims: tuple[str, ...],
) -> tuple[str, ...] | None:
    """Extract token scopes from one of multiple scope claims in order.

    Claims are checked left-to-right. Missing claims are skipped. If a claim is
    present but malformed, extraction fails immediately to avoid silently
    accepting malformed payloads.
    """
    for scope_claim in scope_claims:
        claim_exists, claim_value = _resolve_claim_value(payload, scope_claim)
        if not claim_exists:
            continue

        return _extract_token_scopes_from_claim_value(claim_value)

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


def _normalize_expected_jtis(
    expected_jti: str | Iterable[str] | None,
) -> tuple[str, ...]:
    """Normalize expected token ID requirements for ``decode_token``."""
    if expected_jti is None:
        return ()

    if isinstance(expected_jti, str):
        normalized_jti = expected_jti.strip()
        if not normalized_jti:
            raise ValueError("expected_jti cannot be blank")

        return (normalized_jti,)

    normalized_jtis: list[str] = []
    for jti in expected_jti:
        if not isinstance(jti, str):
            raise TypeError("expected_jti must contain only strings")

        normalized_jti = jti.strip()
        if not normalized_jti:
            raise ValueError("expected_jti cannot contain blank values")

        normalized_jtis.append(normalized_jti)

    if not normalized_jtis:
        raise ValueError("expected_jti cannot be an empty iterable")

    return tuple(dict.fromkeys(normalized_jtis))


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


def _audience_requirement_matches(required_audience: str, token_audience: str) -> bool:
    """Return whether a token audience satisfies one audience requirement.

    Required audience values support glob patterns (for example,
    ``"api://agenthq-*"``).
    """
    if any(token in required_audience for token in "*?["):
        return fnmatchcase(token_audience, required_audience)

    return token_audience == required_audience


def _normalize_expected_issuers(
    expected_issuer: str | Iterable[str] | None,
) -> tuple[str, ...]:
    """Normalize expected issuer requirements for ``decode_token``."""
    if expected_issuer is None:
        return ()

    if isinstance(expected_issuer, str):
        normalized_issuer = expected_issuer.strip()
        if not normalized_issuer:
            raise ValueError("expected_issuer cannot be blank")

        return (normalized_issuer,)

    try:
        issuer_values = iter(expected_issuer)
    except TypeError as exc:
        raise TypeError(
            "expected_issuer must be a string or iterable of strings"
        ) from exc

    normalized_issuers: list[str] = []
    for issuer in issuer_values:
        if not isinstance(issuer, str):
            raise TypeError("expected_issuer must contain only strings")

        normalized_issuer = issuer.strip()
        if not normalized_issuer:
            raise ValueError("expected_issuer cannot contain blank values")

        normalized_issuers.append(normalized_issuer)

    if not normalized_issuers:
        raise ValueError("expected_issuer cannot be an empty iterable")

    return tuple(dict.fromkeys(normalized_issuers))


def _issuer_requirement_matches(required_issuer: str, token_issuer: str) -> bool:
    """Return whether a token issuer satisfies one issuer requirement.

    Required issuer values support glob patterns (for example,
    ``"agenthq-*"``).
    """
    if any(token in required_issuer for token in "*?["):
        return fnmatchcase(token_issuer, required_issuer)

    return token_issuer == required_issuer


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


def _normalize_max_age_seconds(max_age_seconds: int | float | None) -> float | None:
    """Normalize optional token max-age constraints for ``decode_token``."""
    if max_age_seconds is None:
        return None

    if isinstance(max_age_seconds, bool) or not isinstance(
        max_age_seconds,
        (int, float),
    ):
        raise TypeError("max_age_seconds must be a numeric value")

    normalized_max_age = float(max_age_seconds)
    if normalized_max_age < 0:
        raise ValueError("max_age_seconds must be greater than or equal to 0")

    return normalized_max_age


def _normalize_max_future_iat_seconds(
    max_future_iat_seconds: int | float | None,
) -> float | None:
    """Normalize optional future-``iat`` tolerance for ``decode_token``."""
    if max_future_iat_seconds is None:
        return None

    if isinstance(max_future_iat_seconds, bool) or not isinstance(
        max_future_iat_seconds,
        (int, float),
    ):
        raise TypeError("max_future_iat_seconds must be a numeric value")

    normalized_max_future_iat = float(max_future_iat_seconds)
    if normalized_max_future_iat < 0:
        raise ValueError(
            "max_future_iat_seconds must be greater than or equal to 0"
        )

    return normalized_max_future_iat


def _extract_issued_at_timestamp(payload: Mapping[str, Any]) -> float | None:
    """Extract normalized ``iat`` timestamps from decoded token payloads."""
    issued_at_claim = payload.get("iat")
    if issued_at_claim is None or isinstance(issued_at_claim, bool):
        return None

    if isinstance(issued_at_claim, datetime):
        issued_at = issued_at_claim.timestamp()
    else:
        try:
            issued_at = float(issued_at_claim)
        except (TypeError, ValueError):
            return None

    if issued_at < 0:
        return None

    return issued_at


def decode_token(
    token: str,
    *,
    expected_type: str | Iterable[str] | None = None,
    expected_subject: str | Iterable[str] | None = None,
    expected_jti: str | Iterable[str] | None = None,
    expected_issuer: str | Iterable[str] | None = None,
    expected_audience: str | Iterable[str] | None = None,
    required_claims: Iterable[str] | None = None,
    required_claim_values: Mapping[str, Any] | None = None,
    required_claim_patterns: Mapping[str, str | re.Pattern[str]] | None = None,
    required_scopes: str | Iterable[str] | None = None,
    scope_claim: str = "scope",
    scope_claim_fallbacks: str | Iterable[str] | None = None,
    match_any_scopes: bool = False,
    leeway_seconds: int | float | None = None,
    max_age_seconds: int | float | None = None,
    max_future_iat_seconds: int | float | None = None,
) -> dict[str, Any] | None:
    """Decode a JWT token with optional type/claim validation.

    Args:
        token: JWT token string.
        expected_type: Optional token ``type`` claim value(s) to enforce.
            Accepts either a single type string or an iterable of allowed
            type values.
        expected_subject: Optional token ``sub`` claim value(s) to enforce.
            Accepts either a single subject string or an iterable of allowed
            subject values.
        expected_jti: Optional token ``jti`` claim value(s) to enforce.
            Accepts either a single token ID string or an iterable of allowed
            token IDs.
        expected_issuer: Optional token ``iss`` claim value(s) to enforce.
            Accepts either a single issuer string or an iterable of allowed
            issuer values. Issuer requirements support glob patterns
            (for example, ``"agenthq-*"``).
        expected_audience: Optional token ``aud`` claim value(s) to enforce.
            Accepts either a single audience string or an iterable of allowed
            audience values. Audience requirements support glob patterns
            (for example, ``"api://agenthq-*"``).
        required_claims: Optional claims that must be present and non-empty.
            Claim names can use dotted paths (for example,
            ``"context.tenant_id"``) to validate nested payload fields.
        required_claim_values: Optional claim value requirements. Values may
            be exact scalars or non-empty collections of allowed values.
            Claim names can use dotted paths to target nested payload fields.
            When the token claim itself is a collection, validation passes if
            any claim entry matches an allowed value.
        required_claim_patterns: Optional regex requirements for string-based
            claims. Claim names can use dotted paths to target nested payload
            fields. Values may be regex pattern strings or compiled
            ``re.Pattern`` instances. String claims must satisfy
            ``pattern.fullmatch(claim_value)``, and collection claims pass when
            any contained string fully matches.
        required_scopes: Optional OAuth-style scope requirements. Accepts a
            scope string (space/comma-delimited) or iterable of scope strings.
            Required scope values support glob patterns (for example,
            ``"chat:*"``).
        scope_claim: Primary token claim name containing scopes.
            Defaults to ``"scope"``. Supports dotted claim paths
            (for example, ``"context.auth.scope"``).
        scope_claim_fallbacks: Optional fallback claim name(s) checked in
            order when ``scope_claim`` is missing (for example, ``"scp"`` or
            ``"realm.scope"``). If a selected claim exists but has an invalid
            payload shape, decoding fails.
        match_any_scopes: Scope matching mode. ``False`` (default) requires
            every ``required_scopes`` entry to be present. ``True`` requires
            at least one matching scope.
        leeway_seconds: Optional expiration/not-before clock-skew tolerance
            applied during JWT decode.
        max_age_seconds: Optional freshness constraint based on ``iat`` claim.
            When provided, tokens older than this many seconds are rejected.
        max_future_iat_seconds: Optional upper bound (seconds) for how far
            the token ``iat`` claim may be in the future relative to current
            time. Useful when freshness checks are not enabled but future
            issuance timestamps should still be rejected.

    Returns:
        Decoded payload when valid, otherwise ``None``.
    """
    if not isinstance(match_any_scopes, bool):
        raise TypeError("match_any_scopes must be a boolean")

    normalized_expected_types = _normalize_expected_types(expected_type)
    normalized_expected_subjects = _normalize_expected_subjects(expected_subject)
    normalized_expected_jtis = _normalize_expected_jtis(expected_jti)
    normalized_expected_issuers = _normalize_expected_issuers(expected_issuer)
    normalized_expected_audiences = _normalize_expected_audiences(expected_audience)
    normalized_required_claims = _normalize_required_claims(required_claims)
    normalized_required_claim_values = _normalize_required_claim_values(
        required_claim_values
    )
    normalized_required_claim_patterns = _normalize_required_claim_patterns(
        required_claim_patterns
    )
    normalized_required_scopes = _normalize_required_scopes(required_scopes)
    normalized_scope_claim = _normalize_scope_claim_name(scope_claim)
    normalized_scope_claim_fallbacks = _normalize_scope_claim_fallbacks(
        scope_claim_fallbacks
    )
    normalized_scope_claims = tuple(
        dict.fromkeys((normalized_scope_claim, *normalized_scope_claim_fallbacks))
    )
    normalized_leeway_seconds = _normalize_leeway_seconds(leeway_seconds)
    normalized_max_age_seconds = _normalize_max_age_seconds(max_age_seconds)
    normalized_max_future_iat_seconds = _normalize_max_future_iat_seconds(
        max_future_iat_seconds
    )

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

    if normalized_expected_types:
        token_type = payload.get("type")
        if not isinstance(token_type, str):
            return None

        normalized_token_type = token_type.strip()
        if not normalized_token_type:
            return None

        if normalized_token_type not in normalized_expected_types:
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

    if normalized_expected_jtis:
        token_id_claim = payload.get("jti")
        if not isinstance(token_id_claim, str):
            return None

        normalized_token_id_claim = token_id_claim.strip()
        if not normalized_token_id_claim:
            return None

        if normalized_token_id_claim not in normalized_expected_jtis:
            return None

    if normalized_expected_issuers:
        token_issuer = payload.get("iss")
        if not isinstance(token_issuer, str):
            return None

        normalized_token_issuer = token_issuer.strip()
        if not normalized_token_issuer:
            return None

        if not any(
            _issuer_requirement_matches(required_issuer, normalized_token_issuer)
            for required_issuer in normalized_expected_issuers
        ):
            return None

    if normalized_expected_audiences:
        token_audiences = _extract_token_audiences(payload)
        if token_audiences is None:
            return None

        if not any(
            _audience_requirement_matches(required_audience, token_audience)
            for required_audience in normalized_expected_audiences
            for token_audience in token_audiences
        ):
            return None

    for claim in normalized_required_claims:
        claim_exists, claim_value = _resolve_claim_value(payload, claim)
        if not claim_exists or claim_value is None:
            return None

        if isinstance(claim_value, str) and not claim_value.strip():
            return None

    for claim, expected_values in normalized_required_claim_values.items():
        claim_exists, claim_value = _resolve_claim_value(payload, claim)
        if not claim_exists or claim_value is None:
            return None

        if not _claim_value_matches_expected_values(claim_value, expected_values):
            return None

    for claim, pattern in normalized_required_claim_patterns.items():
        claim_exists, claim_value = _resolve_claim_value(payload, claim)
        if not claim_exists or claim_value is None:
            return None

        if isinstance(claim_value, str):
            candidate_values = [claim_value]
        elif isinstance(claim_value, (list, tuple, set, frozenset)):
            if not all(isinstance(item, str) for item in claim_value):
                return None
            candidate_values = list(claim_value)
        else:
            return None

        if not any(
            pattern.fullmatch(candidate_value) for candidate_value in candidate_values
        ):
            return None

    if normalized_required_scopes:
        token_scopes = _extract_token_scopes_with_fallbacks(
            payload,
            normalized_scope_claims,
        )
        if token_scopes is None:
            return None

        token_scope_set = set(token_scopes)

        if match_any_scopes:
            if not any(
                _scope_requirement_matches(required_scope, token_scope_set)
                for required_scope in normalized_required_scopes
            ):
                return None
        elif not all(
            _scope_requirement_matches(required_scope, token_scope_set)
            for required_scope in normalized_required_scopes
        ):
            return None

    if (
        normalized_max_age_seconds is not None
        or normalized_max_future_iat_seconds is not None
    ):
        issued_at = _extract_issued_at_timestamp(payload)
        if issued_at is None:
            return None

        now_timestamp = time.time()
        allowed_future_iat_seconds = normalized_leeway_seconds
        if normalized_max_future_iat_seconds is not None:
            allowed_future_iat_seconds += normalized_max_future_iat_seconds

        if issued_at > (now_timestamp + allowed_future_iat_seconds):
            return None

        if normalized_max_age_seconds is not None:
            token_age = now_timestamp - issued_at
            if token_age > (normalized_max_age_seconds + normalized_leeway_seconds):
                return None

    return payload
