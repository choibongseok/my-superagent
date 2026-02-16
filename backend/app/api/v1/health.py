"""Health check endpoints."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

_SERVICE_STATUSES: dict[str, str] = {
    "api": "healthy",
    "database": "healthy",
    "redis": "healthy",
}
_START_TIME_MONOTONIC = time.monotonic()

_HEALTHY_STATUS_VALUES = {"healthy", "ok", "operational", "up"}
_DEGRADED_STATUS_VALUES = {"degraded", "warning", "limited", "partial"}
_UNHEALTHY_STATUS_VALUES = {
    "unhealthy",
    "down",
    "failed",
    "error",
    "critical",
    "offline",
}

_STATUS_FILTER_ALIASES: dict[str, str] = {
    "healthy": "healthy",
    "ok": "healthy",
    "operational": "healthy",
    "up": "healthy",
    "degraded": "degraded",
    "warning": "degraded",
    "limited": "degraded",
    "partial": "degraded",
    "unhealthy": "unhealthy",
    "down": "unhealthy",
    "failed": "unhealthy",
    "error": "unhealthy",
    "critical": "unhealthy",
    "offline": "unhealthy",
    "unknown": "unknown",
}


def _uptime_seconds() -> float:
    """Return process uptime in seconds based on monotonic clock."""
    return max(0.0, time.monotonic() - _START_TIME_MONOTONIC)


def _current_timestamp_utc() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.fromtimestamp(time.time(), tz=timezone.utc).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")


def _parse_requested_services(raw_services: str | None) -> list[str]:
    """Parse and validate optional comma-delimited service filters."""
    if raw_services is None:
        return list(_SERVICE_STATUSES)

    normalized_services = [
        service.strip().lower()
        for service in raw_services.split(",")
        if service.strip()
    ]
    if not normalized_services:
        raise HTTPException(
            status_code=400,
            detail="services must include at least one service name",
        )

    requested_services = list(dict.fromkeys(normalized_services))
    unknown_services = [
        service for service in requested_services if service not in _SERVICE_STATUSES
    ]
    if unknown_services:
        unknown_list = ", ".join(unknown_services)
        supported_list = ", ".join(sorted(_SERVICE_STATUSES))
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown services: {unknown_list}. "
                f"Supported services: {supported_list}."
            ),
        )

    return requested_services


def _classify_service_status(raw_status: str) -> str:
    """Normalize one raw status value into a summary category."""
    normalized_status = str(raw_status).strip().lower()

    if normalized_status in _HEALTHY_STATUS_VALUES:
        return "healthy"
    if normalized_status in _DEGRADED_STATUS_VALUES:
        return "degraded"
    if normalized_status in _UNHEALTHY_STATUS_VALUES:
        return "unhealthy"

    return "unknown"


def _build_service_summary(service_statuses: dict[str, str]) -> dict[str, int]:
    """Build status-category counts for the selected service statuses."""
    summary = {
        "total": len(service_statuses),
        "healthy": 0,
        "degraded": 0,
        "unhealthy": 0,
        "unknown": 0,
    }

    for raw_status in service_statuses.values():
        summary[_classify_service_status(raw_status)] += 1

    return summary


def _parse_status_filter(raw_status_filter: str | None) -> set[str] | None:
    """Parse optional comma-delimited status-category filters."""
    if raw_status_filter is None:
        return None

    normalized_tokens = [
        token.strip().lower() for token in raw_status_filter.split(",") if token.strip()
    ]
    if not normalized_tokens:
        raise HTTPException(
            status_code=400,
            detail="status_filter must include at least one status category",
        )

    normalized_categories: set[str] = set()
    unknown_tokens: list[str] = []

    for token in normalized_tokens:
        normalized_category = _STATUS_FILTER_ALIASES.get(token)
        if normalized_category is None:
            unknown_tokens.append(token)
            continue

        normalized_categories.add(normalized_category)

    if unknown_tokens:
        unknown_list = ", ".join(sorted(dict.fromkeys(unknown_tokens)))
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown status_filter values: {unknown_list}. "
                "Supported categories: healthy, degraded, unhealthy, unknown."
            ),
        )

    return normalized_categories


def _filter_service_statuses_by_category(
    service_statuses: dict[str, str],
    *,
    allowed_categories: set[str] | None,
) -> dict[str, str]:
    """Filter service statuses by normalized health categories."""
    if allowed_categories is None:
        return service_statuses

    return {
        service_name: raw_status
        for service_name, raw_status in service_statuses.items()
        if _classify_service_status(raw_status) in allowed_categories
    }


def _build_service_categories(service_statuses: dict[str, str]) -> dict[str, str]:
    """Build normalized health categories for each selected service."""
    return {
        service_name: _classify_service_status(raw_status)
        for service_name, raw_status in service_statuses.items()
    }


def _derive_overall_status(summary: dict[str, int]) -> str:
    """Derive aggregate service health from category counts."""
    if summary["total"] == 0:
        return "unknown"

    if summary["unhealthy"] > 0:
        return "degraded"
    if summary["degraded"] > 0:
        return "degraded"
    if summary["unknown"] > 0:
        return "unknown"
    return "operational"


@router.get("/ping")
async def ping(
    include_uptime: bool = Query(
        default=False,
        description="Include process uptime in the ping payload",
    ),
    include_timestamp: bool = Query(
        default=False,
        description="Include current UTC timestamp in ISO-8601 format",
    ),
) -> dict[str, Any]:
    """Simple ping endpoint with optional uptime and timestamp diagnostics."""
    payload: dict[str, Any] = {"message": "pong"}
    if include_uptime:
        payload["uptime_seconds"] = round(_uptime_seconds(), 3)

    if include_timestamp:
        payload["timestamp_utc"] = _current_timestamp_utc()

    return payload


@router.get("/status")
async def status(
    services: str
    | None = Query(
        default=None,
        description="Comma-delimited service filter (e.g., api,redis)",
    ),
    include_uptime: bool = Query(
        default=False,
        description="Include process uptime in the status payload",
    ),
    include_timestamp: bool = Query(
        default=False,
        description="Include current UTC timestamp in ISO-8601 format",
    ),
    include_summary: bool = Query(
        default=False,
        description="Include categorized service-health summary counts",
    ),
    include_categories: bool = Query(
        default=False,
        description="Include normalized health category per selected service",
    ),
    status_filter: str
    | None = Query(
        default=None,
        description=(
            "Optional comma-delimited status categories to include "
            "(healthy,degraded,unhealthy,unknown)"
        ),
    ),
) -> dict[str, Any]:
    """Detailed status endpoint with optional service filtering."""
    selected_services = _parse_requested_services(services)
    selected_statuses = {
        service_name: _SERVICE_STATUSES[service_name]
        for service_name in selected_services
    }
    selected_statuses = _filter_service_statuses_by_category(
        selected_statuses,
        allowed_categories=_parse_status_filter(status_filter),
    )
    service_summary = _build_service_summary(selected_statuses)

    payload: dict[str, Any] = {
        "status": _derive_overall_status(service_summary),
        "services": selected_statuses,
    }

    if include_categories:
        payload["service_categories"] = _build_service_categories(selected_statuses)

    if include_summary:
        payload["summary"] = service_summary

    if include_uptime:
        payload["uptime_seconds"] = round(_uptime_seconds(), 3)

    if include_timestamp:
        payload["timestamp_utc"] = _current_timestamp_utc()

    return payload
