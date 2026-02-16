"""Health check endpoints."""

from __future__ import annotations

import time
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


def _uptime_seconds() -> float:
    """Return process uptime in seconds based on monotonic clock."""
    return max(0.0, time.monotonic() - _START_TIME_MONOTONIC)


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
        normalized_status = str(raw_status).strip().lower()

        if normalized_status in _HEALTHY_STATUS_VALUES:
            summary["healthy"] += 1
        elif normalized_status in _DEGRADED_STATUS_VALUES:
            summary["degraded"] += 1
        elif normalized_status in _UNHEALTHY_STATUS_VALUES:
            summary["unhealthy"] += 1
        else:
            summary["unknown"] += 1

    return summary


def _derive_overall_status(summary: dict[str, int]) -> str:
    """Derive aggregate service health from category counts."""
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
) -> dict[str, Any]:
    """Simple ping endpoint with optional uptime diagnostics."""
    payload: dict[str, Any] = {"message": "pong"}
    if include_uptime:
        payload["uptime_seconds"] = round(_uptime_seconds(), 3)

    return payload


@router.get("/status")
async def status(
    services: str | None = Query(
        default=None,
        description="Comma-delimited service filter (e.g., api,redis)",
    ),
    include_uptime: bool = Query(
        default=False,
        description="Include process uptime in the status payload",
    ),
    include_summary: bool = Query(
        default=False,
        description="Include categorized service-health summary counts",
    ),
) -> dict[str, Any]:
    """Detailed status endpoint with optional service filtering."""
    selected_services = _parse_requested_services(services)
    selected_statuses = {
        service_name: _SERVICE_STATUSES[service_name]
        for service_name in selected_services
    }
    service_summary = _build_service_summary(selected_statuses)

    payload: dict[str, Any] = {
        "status": _derive_overall_status(service_summary),
        "services": selected_statuses,
    }

    if include_summary:
        payload["summary"] = service_summary

    if include_uptime:
        payload["uptime_seconds"] = round(_uptime_seconds(), 3)

    return payload
