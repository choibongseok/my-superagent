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
) -> dict[str, Any]:
    """Detailed status endpoint with optional service filtering."""
    selected_services = _parse_requested_services(services)
    payload: dict[str, Any] = {
        "status": "operational",
        "services": {
            service_name: _SERVICE_STATUSES[service_name]
            for service_name in selected_services
        },
    }

    if include_uptime:
        payload["uptime_seconds"] = round(_uptime_seconds(), 3)

    return payload
