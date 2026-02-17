"""Rate limiting middleware using Token Bucket algorithm."""

import math
import re
import time
from collections.abc import Iterable
from fnmatch import fnmatchcase
from typing import Callable, Mapping, Optional

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.cache import cache
from app.core.config import settings


class TokenBucket:
    """Token Bucket rate limiter."""

    STATE_TTL_SECONDS = 3600

    def __init__(self, capacity: int, refill_rate: float):
        """
        Initialize token bucket.

        Args:
            capacity: Maximum tokens in bucket
            refill_rate: Tokens added per second
        """
        if isinstance(capacity, bool) or capacity <= 0:
            raise ValueError("capacity must be greater than 0")
        if refill_rate <= 0:
            raise ValueError("refill_rate must be greater than 0")

        self.capacity = capacity
        self.refill_rate = refill_rate

    @staticmethod
    def _validate_tokens(tokens: int) -> int:
        """Validate requested token count for bucket operations."""
        if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens <= 0:
            raise ValueError("tokens must be a positive integer")
        return tokens

    async def _load_bucket(self, key: str, *, now: float) -> dict[str, float]:
        """Load and refill a bucket state for the provided key."""
        bucket_data = await cache.get(f"rate_limit:{key}")
        if not bucket_data:
            return {
                "tokens": float(self.capacity),
                "last_refill": now,
            }

        previous_tokens = float(bucket_data.get("tokens", self.capacity))
        previous_refill = float(bucket_data.get("last_refill", now))
        elapsed = max(0.0, now - previous_refill)
        refill_amount = elapsed * self.refill_rate
        current_tokens = min(self.capacity, previous_tokens + refill_amount)

        return {
            "tokens": current_tokens,
            "last_refill": now,
        }

    async def consume(self, key: str, tokens: int = 1) -> bool:
        """
        Try to consume tokens from bucket.

        Args:
            key: Bucket key (user_id or IP)
            tokens: Number of tokens to consume

        Returns:
            True if tokens consumed, False if rate limited
        """
        requested_tokens = self._validate_tokens(tokens)
        now = time.time()
        bucket_data = await self._load_bucket(key, now=now)

        if requested_tokens > self.capacity or bucket_data["tokens"] < requested_tokens:
            await cache.set(
                f"rate_limit:{key}",
                bucket_data,
                ttl=self.STATE_TTL_SECONDS,
            )
            return False

        bucket_data["tokens"] -= requested_tokens

        await cache.set(
            f"rate_limit:{key}",
            bucket_data,
            ttl=self.STATE_TTL_SECONDS,
        )
        return True

    async def get_remaining(self, key: str) -> float:
        """
        Get remaining tokens in bucket.

        Args:
            key: Bucket key

        Returns:
            Number of remaining tokens
        """
        bucket_data = await self._load_bucket(key, now=time.time())
        return bucket_data["tokens"]

    async def get_retry_after(self, key: str, tokens: int = 1) -> float:
        """Return seconds until ``tokens`` can be consumed."""
        requested_tokens = self._validate_tokens(tokens)
        if requested_tokens > self.capacity:
            return math.inf

        bucket_data = await self._load_bucket(key, now=time.time())
        deficit = requested_tokens - bucket_data["tokens"]
        if deficit <= 0:
            return 0.0

        return deficit / self.refill_rate


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware for API rate limiting."""

    def __init__(
        self,
        app,
        requests_per_minute: int = 60,
        burst_size: Optional[int] = None,
        request_costs: Optional[Mapping[str, int]] = None,
        path_request_costs: Optional[Mapping[str, int]] = None,
        exclude_paths: Optional[Iterable[str]] = None,
        exclude_methods: Optional[Iterable[str]] = None,
        client_id_header: Optional[str | Iterable[str]] = None,
        exclude_client_ids: Optional[Iterable[str]] = None,
        exclude_user_agents: Optional[Iterable[str]] = None,
    ):
        """
        Initialize rate limit middleware.

        Args:
            app: FastAPI application
            requests_per_minute: Sustained request rate
            burst_size: Maximum burst requests (defaults to 2x rate)
            request_costs: Optional per-method token costs (e.g. {"POST": 2}).
                Use "*" as a wildcard fallback for methods not explicitly listed.
            path_request_costs: Optional per-path token costs where keys are
                exact paths (e.g. ``"/api/v1/tasks"``), prefix patterns
                (e.g. ``"/api/v1/tasks/*"``), or glob patterns
                (e.g. ``"/api/*/tasks/*/events"``). Rules may optionally be
                scoped to an HTTP method using ``"METHOD /path"`` syntax.
            exclude_paths: Optional custom path exclusion rules. Supports
                exact paths, prefix rules, glob patterns, and method-scoped
                rules such as ``"POST /admin/*"``.
            exclude_methods: Optional HTTP methods that should bypass
                rate limiting entirely (for example ``["OPTIONS"]`` for
                CORS preflight requests).
            client_id_header: Optional HTTP header name (or ordered list of
                header names) used to identify clients for bucket isolation
                (e.g. ``"X-API-Key"`` or
                ``["X-API-Key", "X-Client-ID"]``). When configured and
                present on a request, the first non-empty header value takes
                precedence over ``request.state.user_id`` and IP-based
                identification.
            exclude_client_ids: Optional client-id selectors that bypass
                rate limiting entirely. Selectors support exact matches and
                glob patterns against normalized client IDs such as
                ``"header:internal-*"``, ``"user:admin"``, or
                ``"ip:10.0.*"``.
            exclude_user_agents: Optional user-agent selectors that bypass
                rate limiting. Selectors support exact matches and glob
                patterns (case-insensitive), for example
                ``"kube-probe/*"`` or ``"internal-healthcheck"``.
        """
        super().__init__(app)

        if isinstance(requests_per_minute, bool) or requests_per_minute <= 0:
            raise ValueError("requests_per_minute must be greater than 0")

        resolved_burst_size = burst_size or (requests_per_minute * 2)
        if isinstance(resolved_burst_size, bool) or resolved_burst_size <= 0:
            raise ValueError("burst_size must be greater than 0")

        self.requests_per_minute = requests_per_minute
        self.burst_size = resolved_burst_size
        self.request_costs = self._normalize_request_costs(request_costs)
        self.path_request_costs = self._normalize_path_request_costs(path_request_costs)
        self.exclude_methods = self._normalize_exclude_methods(exclude_methods)
        self.client_id_headers = self._normalize_client_id_headers(client_id_header)
        self.exclude_client_ids = self._normalize_exclude_client_ids(exclude_client_ids)
        self.exclude_user_agents = self._normalize_exclude_user_agents(
            exclude_user_agents
        )
        # Backward-compatible alias for callers that still access this attribute.
        self.client_id_header = (
            self.client_id_headers[0] if self.client_id_headers else None
        )

        # Token bucket: refills at requests_per_minute rate
        # Max capacity: burst_size
        self.bucket = TokenBucket(
            capacity=self.burst_size,
            refill_rate=requests_per_minute / 60.0,  # Convert to per-second
        )

        # Built-in exclusions for service metadata routes.
        self.exclude_paths = {
            "/health",
            "/",
            "/docs",
            "/redoc",
            "/openapi.json",
        }
        self.exclude_path_rules = self._normalize_exclude_paths(exclude_paths)

    @staticmethod
    def _normalize_client_id_headers(
        client_id_header: Optional[str | Iterable[str]],
    ) -> tuple[str, ...]:
        """Normalize optional header names used for rate-limit identity keys."""
        if client_id_header is None:
            return ()

        if isinstance(client_id_header, str):
            normalized_header = client_id_header.strip()
            if not normalized_header:
                raise ValueError(
                    "client_id_header must be a non-empty string or iterable of non-empty strings"
                )

            return (normalized_header,)

        try:
            raw_headers = list(client_id_header)
        except TypeError as exc:
            raise ValueError(
                "client_id_header must be a non-empty string or iterable of non-empty strings"
            ) from exc

        if not raw_headers:
            raise ValueError(
                "client_id_header must be a non-empty string or iterable of non-empty strings"
            )

        normalized_headers: list[str] = []
        for raw_header in raw_headers:
            if not isinstance(raw_header, str) or not raw_header.strip():
                raise ValueError(
                    "client_id_header must contain only non-empty header strings"
                )

            normalized_header = raw_header.strip()
            if normalized_header not in normalized_headers:
                normalized_headers.append(normalized_header)

        if not normalized_headers:
            raise ValueError(
                "client_id_header must be a non-empty string or iterable of non-empty strings"
            )

        return tuple(normalized_headers)

    @staticmethod
    def _normalize_exclude_methods(
        exclude_methods: Optional[Iterable[str]],
    ) -> set[str]:
        """Normalize optional HTTP methods that bypass rate limiting."""
        if exclude_methods is None:
            return set()

        normalized_methods: set[str] = set()
        for raw_method in exclude_methods:
            if not isinstance(raw_method, str) or not raw_method.strip():
                raise ValueError(
                    "exclude_methods must contain non-empty HTTP method strings"
                )

            normalized_method = raw_method.strip().upper()
            if not re.fullmatch(r"[A-Z]+", normalized_method):
                raise ValueError(
                    "exclude_methods must contain alphabetic HTTP method strings"
                )

            normalized_methods.add(normalized_method)

        return normalized_methods

    @staticmethod
    def _normalize_exclude_client_ids(
        exclude_client_ids: Optional[Iterable[str]],
    ) -> tuple[str, ...]:
        """Normalize optional client-id bypass selectors."""
        if exclude_client_ids is None:
            return ()

        normalized_patterns: list[str] = []
        for raw_pattern in exclude_client_ids:
            if not isinstance(raw_pattern, str) or not raw_pattern.strip():
                raise ValueError(
                    "exclude_client_ids must contain non-empty client-id selectors"
                )

            normalized_pattern = raw_pattern.strip()
            if normalized_pattern not in normalized_patterns:
                normalized_patterns.append(normalized_pattern)

        return tuple(normalized_patterns)

    @staticmethod
    def _normalize_exclude_user_agents(
        exclude_user_agents: Optional[Iterable[str]],
    ) -> tuple[str, ...]:
        """Normalize optional user-agent bypass selectors."""
        if exclude_user_agents is None:
            return ()

        normalized_patterns: list[str] = []
        for raw_pattern in exclude_user_agents:
            if not isinstance(raw_pattern, str) or not raw_pattern.strip():
                raise ValueError(
                    "exclude_user_agents must contain non-empty user-agent selectors"
                )

            normalized_pattern = raw_pattern.strip().lower()
            if normalized_pattern not in normalized_patterns:
                normalized_patterns.append(normalized_pattern)

        return tuple(normalized_patterns)

    def _normalize_request_costs(
        self,
        request_costs: Optional[Mapping[str, int]],
    ) -> dict[str, int]:
        """Normalize and validate optional HTTP method token costs."""
        if request_costs is None:
            return {}

        normalized_costs: dict[str, int] = {}
        for method, cost in request_costs.items():
            if not isinstance(method, str) or not method.strip():
                raise ValueError("request_costs keys must be non-empty method strings")

            normalized_method = method.strip().upper()
            if normalized_method != "*" and not re.fullmatch(
                r"[A-Z]+",
                normalized_method,
            ):
                raise ValueError(
                    "request_costs keys must be alphabetic HTTP methods or '*'"
                )

            if isinstance(cost, bool) or not isinstance(cost, int) or cost <= 0:
                raise ValueError(
                    "request_costs values must be positive integer token costs"
                )
            if cost > self.burst_size:
                raise ValueError("request_costs values cannot exceed burst_size")

            normalized_costs[normalized_method] = cost

        return normalized_costs

    @staticmethod
    def _split_path_request_cost_pattern(
        path_pattern: str,
    ) -> tuple[Optional[str], str]:
        """Split optional METHOD prefixes from path request-cost patterns."""
        normalized_pattern = path_pattern.strip()
        parts = normalized_pattern.split(None, 1)
        if (
            len(parts) == 2
            and parts[1].startswith("/")
            and not parts[0].startswith("/")
        ):
            method = parts[0].strip().upper()
            if not re.fullmatch(r"[A-Z]+", method):
                raise ValueError(
                    "path_request_costs method prefix must be alphabetic (e.g. 'GET /path')"
                )
            return method, parts[1].strip()

        return None, normalized_pattern

    def _normalize_path_request_costs(
        self,
        path_request_costs: Optional[Mapping[str, int]],
    ) -> dict[tuple[Optional[str], str], int]:
        """Normalize and validate optional exact/prefix/glob token costs."""
        if path_request_costs is None:
            return {}

        normalized_path_costs: dict[tuple[Optional[str], str], int] = {}
        for raw_pattern, cost in path_request_costs.items():
            if not isinstance(raw_pattern, str) or not raw_pattern.strip():
                raise ValueError(
                    "path_request_costs keys must be non-empty path pattern strings"
                )

            method, path_pattern = self._split_path_request_cost_pattern(raw_pattern)

            normalized_pattern = path_pattern
            if normalized_pattern.endswith("*"):
                normalized_pattern = normalized_pattern[:-1]

            if not normalized_pattern.startswith("/"):
                raise ValueError(
                    "path_request_costs keys must start with '/' and use optional wildcard patterns"
                )

            if isinstance(cost, bool) or not isinstance(cost, int) or cost <= 0:
                raise ValueError(
                    "path_request_costs values must be positive integer token costs"
                )
            if cost > self.burst_size:
                raise ValueError("path_request_costs values cannot exceed burst_size")

            normalized_path_costs[(method, path_pattern)] = cost

        return normalized_path_costs

    def _normalize_exclude_paths(
        self,
        exclude_paths: Optional[Iterable[str]],
    ) -> list[tuple[Optional[str], str]]:
        """Normalize optional custom path exclusions.

        Supports exact paths (``"/path"``), prefix rules (``"/path/*"``),
        glob rules (``"/path/*/events"``), and optional method scoping
        (``"GET /path"``, ``"POST /path/*"``).
        """
        if exclude_paths is None:
            return []

        normalized_rules: list[tuple[Optional[str], str]] = []
        for raw_pattern in exclude_paths:
            if not isinstance(raw_pattern, str) or not raw_pattern.strip():
                raise ValueError(
                    "exclude_paths must contain non-empty path pattern strings"
                )

            method, path_pattern = self._split_path_request_cost_pattern(raw_pattern)
            normalized_pattern = (
                path_pattern[:-1] if path_pattern.endswith("*") else path_pattern
            )

            if not normalized_pattern.startswith("/"):
                raise ValueError(
                    "exclude_paths entries must start with '/' and use optional wildcard patterns"
                )

            normalized_rules.append((method, path_pattern))

        return normalized_rules

    @staticmethod
    def _contains_glob_wildcards(pattern: str) -> bool:
        """Return whether ``pattern`` includes glob wildcard syntax."""
        return any(token in pattern for token in ("*", "?", "["))

    @classmethod
    def _is_simple_prefix_pattern(cls, pattern: str) -> bool:
        """Return whether ``pattern`` is a prefix rule like ``/path/*``."""
        return pattern.endswith("*") and not cls._contains_glob_wildcards(pattern[:-1])

    @classmethod
    def _path_matches_rule(cls, path: str, pattern: str) -> bool:
        """Return ``True`` when ``path`` matches exact, prefix, or glob rule."""
        if not cls._contains_glob_wildcards(pattern):
            return path == pattern

        if cls._is_simple_prefix_pattern(pattern):
            return path.startswith(pattern[:-1])

        return fnmatchcase(path, pattern)

    @classmethod
    def _path_rule_specificity(cls, pattern: str) -> tuple[int, int, int]:
        """Return sortable specificity tuple for path matching precedence."""
        if not cls._contains_glob_wildcards(pattern):
            return (3, len(pattern), 0)

        if cls._is_simple_prefix_pattern(pattern):
            return (2, len(pattern) - 1, 0)

        wildcard_count = sum(pattern.count(token) for token in ("*", "?", "["))
        literal_chars = len(pattern) - wildcard_count
        return (1, literal_chars, -wildcard_count)

    def _is_excluded_path(self, request: Request) -> bool:
        """Return whether current request should bypass rate limiting."""
        method = request.method.upper()
        if method in self.exclude_methods:
            return True

        path = request.url.path
        if path in self.exclude_paths:
            return True

        for rule_method, pattern in self.exclude_path_rules:
            if rule_method not in (None, method):
                continue
            if self._path_matches_rule(path, pattern):
                return True

        return False

    def _is_excluded_user_agent(self, request: Request) -> bool:
        """Return whether request user-agent matches bypass selectors."""
        if not self.exclude_user_agents:
            return False

        user_agent = request.headers.get("User-Agent")
        if user_agent is None:
            return False

        normalized_user_agent = user_agent.strip().lower()
        if not normalized_user_agent:
            return False

        return any(
            fnmatchcase(normalized_user_agent, pattern)
            for pattern in self.exclude_user_agents
        )

    @classmethod
    def _extract_ip_from_x_forwarded_for(cls, forwarded_for: str) -> Optional[str]:
        """Extract first valid client IP from ``X-Forwarded-For`` values."""
        for raw_ip in forwarded_for.split(","):
            normalized_ip = cls._normalize_forwarded_for_value(raw_ip)
            if normalized_ip:
                return normalized_ip

        return None

    @staticmethod
    def _normalize_forwarded_for_value(value: str) -> Optional[str]:
        """Normalize RFC 7239 ``for`` values into bare client IP/host values."""
        candidate = value.strip().strip('"')
        if not candidate:
            return None

        lowered_candidate = candidate.lower()
        # RFC 7239 permits "unknown" and obfuscated identifiers. Skip both.
        if lowered_candidate == "unknown" or candidate.startswith("_"):
            return None

        if candidate.startswith("["):
            end_bracket = candidate.find("]")
            if end_bracket > 1:
                return candidate[1:end_bracket]

        if candidate.count(":") == 1:
            host, _, port = candidate.partition(":")
            if host and port.isdigit():
                return host

        return candidate

    @classmethod
    def _extract_ip_from_forwarded_header(cls, forwarded: str) -> Optional[str]:
        """Extract first valid client IP/host from RFC 7239 ``Forwarded``."""
        for entry in forwarded.split(","):
            for parameter in entry.split(";"):
                key, separator, value = parameter.partition("=")
                if separator != "=" or key.strip().lower() != "for":
                    continue

                normalized_value = cls._normalize_forwarded_for_value(value)
                if normalized_value:
                    return normalized_value

        return None

    @classmethod
    def _extract_client_ip(cls, request: Request) -> str:
        """Resolve best-effort client IP from common proxy forwarding headers."""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            xff_ip = cls._extract_ip_from_x_forwarded_for(forwarded_for)
            if xff_ip:
                return xff_ip

        forwarded = request.headers.get("Forwarded")
        if forwarded:
            forwarded_ip = cls._extract_ip_from_forwarded_header(forwarded)
            if forwarded_ip:
                return forwarded_ip

        x_real_ip = request.headers.get("X-Real-IP")
        if x_real_ip and x_real_ip.strip():
            return x_real_ip.strip()

        return request.client.host if request.client else "unknown"

    def _get_client_id(self, request: Request) -> str:
        """
        Get client identifier for rate limiting.

        Args:
            request: HTTP request

        Returns:
            Client identifier (user_id or IP address)
        """
        # Prefer explicit client identity headers when configured.
        if self.client_id_headers:
            for header_name in self.client_id_headers:
                client_header_value = request.headers.get(header_name)
                if client_header_value is None:
                    continue

                normalized_client_header_value = client_header_value.strip()
                if normalized_client_header_value:
                    return f"header:{normalized_client_header_value}"

        # Try to get user ID from request state (set by auth middleware)
        if hasattr(request.state, "user_id"):
            return f"user:{request.state.user_id}"

        client_ip = self._extract_client_ip(request)
        return f"ip:{client_ip}"

    def _is_excluded_client_id(self, client_id: str) -> bool:
        """Return whether one normalized client ID bypasses rate limiting."""
        return any(
            fnmatchcase(client_id, selector) for selector in self.exclude_client_ids
        )

    def _resolve_path_request_cost(
        self,
        path: str,
        *,
        method: Optional[str],
    ) -> Optional[int]:
        """Resolve path request cost for one method scope (or generic scope)."""
        best_cost: int | None = None
        best_specificity: tuple[int, int, int] | None = None

        for (rule_method, pattern), cost in self.path_request_costs.items():
            if rule_method != method:
                continue
            if not self._path_matches_rule(path, pattern):
                continue

            specificity = self._path_rule_specificity(pattern)
            if best_specificity is None or specificity > best_specificity:
                best_specificity = specificity
                best_cost = cost

        return best_cost

    def _get_request_cost(self, request: Request) -> int:
        """Resolve token cost for path-specific rules and HTTP method."""
        path = request.url.path
        method = request.method.upper()

        # Method-specific path rules take highest precedence.
        method_scoped_cost = self._resolve_path_request_cost(path, method=method)
        if method_scoped_cost is not None:
            return method_scoped_cost

        # Fallback to method-agnostic path rules.
        generic_cost = self._resolve_path_request_cost(path, method=None)
        if generic_cost is not None:
            return generic_cost

        if method in self.request_costs:
            return self.request_costs[method]

        if "*" in self.request_costs:
            return self.request_costs["*"]

        return 1

    def _build_rate_limit_headers(
        self,
        *,
        remaining: int,
        request_cost: int,
        reset_after: int,
        retry_after: Optional[int] = None,
    ) -> dict[str, str]:
        """Build legacy and RFC 9333-style rate-limit response headers."""
        safe_remaining = max(0, remaining)
        safe_reset_after = max(0, reset_after)

        headers = {
            "X-RateLimit-Limit": str(self.burst_size),
            "X-RateLimit-Remaining": str(safe_remaining),
            "X-RateLimit-Reset": str(int(time.time()) + safe_reset_after),
            "X-RateLimit-Reset-After": str(safe_reset_after),
            "X-RateLimit-Request-Cost": str(request_cost),
            "RateLimit-Limit": str(self.burst_size),
            "RateLimit-Remaining": str(safe_remaining),
            "RateLimit-Reset": str(safe_reset_after),
            "RateLimit-Policy": f"{self.burst_size};w=60",
        }

        if retry_after is not None:
            headers["Retry-After"] = str(max(0, retry_after))

        return headers

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request with rate limiting.

        Args:
            request: HTTP request
            call_next: Next middleware/route handler

        Returns:
            HTTP response
        """
        # Skip rate limiting for excluded paths/user agents
        if self._is_excluded_path(request) or self._is_excluded_user_agent(request):
            return await call_next(request)

        # Get client identifier and method-specific token cost
        client_id = self._get_client_id(request)
        if self._is_excluded_client_id(client_id):
            return await call_next(request)

        request_cost = self._get_request_cost(request)

        # Try to consume token budget for this request
        allowed = await self.bucket.consume(client_id, tokens=request_cost)

        if not allowed:
            # Rate limited
            retry_after_seconds = await self.bucket.get_retry_after(
                client_id,
                tokens=request_cost,
            )
            retry_after = (
                max(1, math.ceil(retry_after_seconds))
                if math.isfinite(retry_after_seconds)
                else 3600
            )

            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "Too many requests. Please try again later.",
                    "retry_after": retry_after,
                },
                headers=self._build_rate_limit_headers(
                    remaining=0,
                    request_cost=request_cost,
                    reset_after=retry_after,
                    retry_after=retry_after,
                ),
            )

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        remaining = await self.bucket.get_remaining(client_id)
        retry_after_seconds = await self.bucket.get_retry_after(client_id)
        reset_after = (
            max(0, math.ceil(retry_after_seconds))
            if math.isfinite(retry_after_seconds)
            else 3600
        )

        for header_name, header_value in self._build_rate_limit_headers(
            remaining=int(remaining),
            request_cost=request_cost,
            reset_after=reset_after,
        ).items():
            response.headers[header_name] = header_value

        return response


def get_rate_limit_middleware(
    requests_per_minute: Optional[int] = None,
    burst_size: Optional[int] = None,
    request_costs: Optional[Mapping[str, int]] = None,
    path_request_costs: Optional[Mapping[str, int]] = None,
    exclude_paths: Optional[Iterable[str]] = None,
    exclude_methods: Optional[Iterable[str]] = None,
    client_id_header: Optional[str | Iterable[str]] = None,
    exclude_client_ids: Optional[Iterable[str]] = None,
    exclude_user_agents: Optional[Iterable[str]] = None,
):
    """
    Create rate limit middleware factory.

    Args:
        requests_per_minute: Request rate limit (defaults to settings)
        burst_size: Optional token bucket capacity override. When ``None``,
            ``RateLimitMiddleware`` defaults to ``requests_per_minute * 2``.
        request_costs: Optional per-method token costs (supports "*" wildcard fallback)
        path_request_costs: Optional exact/prefix path token costs
        exclude_paths: Optional exact/prefix/method-scoped exclusion rules
        exclude_methods: Optional HTTP methods that bypass rate limiting
        client_id_header: Optional HTTP header name (or ordered header list)
            used for client identity
        exclude_client_ids: Optional exact/glob selectors that bypass
            rate limiting for matching client IDs
        exclude_user_agents: Optional exact/glob selectors that bypass
            rate limiting for matching user-agent headers

    Returns:
        Callable middleware factory compatible with ``add_middleware``
    """
    rpm = requests_per_minute or settings.RATE_LIMIT_PER_MINUTE

    return lambda app: RateLimitMiddleware(
        app,
        requests_per_minute=rpm,
        burst_size=burst_size,
        request_costs=request_costs,
        path_request_costs=path_request_costs,
        exclude_paths=exclude_paths,
        exclude_methods=exclude_methods,
        client_id_header=client_id_header,
        exclude_client_ids=exclude_client_ids,
        exclude_user_agents=exclude_user_agents,
    )
