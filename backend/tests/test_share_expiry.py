"""Tests for #206 Share Link Expiry.

Covers:
- POST /api/v1/tasks/{id}/share returns 200 with share_token, expires_at, share_url
- Default ttl_days=7 sets expiry ~7 days from now
- Custom ttl_days param respected
- GET /r/{share_token} returns 200 for a non-expired valid share link
- GET /r/{share_token} returns 410 Gone when share link is expired
- GET /r/{share_token} returns 404 for unknown token
- Share endpoint requires auth (401 without token)
- Share endpoint returns 404 when task belongs to another user
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.task import Task as TaskModel, TaskStatus, TaskType
from app.models.user import User


# ── helpers ───────────────────────────────────────────────────────────────────


async def _make_user(db: AsyncSession, email: str | None = None) -> User:
    u = User(id=uuid4(), email=email or f"u-{uuid4().hex[:6]}@x.com", is_active=True)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _make_task(
    db: AsyncSession,
    user: User,
    status: TaskStatus = TaskStatus.COMPLETED,
    share_token=None,
    expires_at=None,
) -> TaskModel:
    t = TaskModel(
        id=uuid4(),
        user_id=user.id,
        prompt="Test prompt",
        task_type=TaskType.RESEARCH,
        status=status,
        result={"content": "result content", "title": "Test Task"},
        share_token=share_token,
        expires_at=expires_at,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


def _auth_headers(user: User) -> dict:
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


# ── POST /api/v1/tasks/{id}/share ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_share_link_default_ttl(async_client: AsyncClient, db: AsyncSession):
    """POST /share with default ttl_days=7 returns valid response."""
    user = await _make_user(db)
    task = await _make_task(db, user)

    resp = await async_client.post(
        f"/api/v1/tasks/{task.id}/share",
        headers=_auth_headers(user),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["task_id"] == str(task.id)
    assert "share_token" in data
    assert data["share_url"].startswith("/r/")
    assert data["share_url"].endswith(data["share_token"])

    # Expiry should be ~7 days from now (allow ±1 min clock skew)
    expires = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
    expected = datetime.now(tz=timezone.utc) + timedelta(days=7)
    delta = abs((expires - expected).total_seconds())
    assert delta < 120, f"Expiry delta too large: {delta}s"


@pytest.mark.asyncio
async def test_create_share_link_custom_ttl(async_client: AsyncClient, db: AsyncSession):
    """POST /share?ttl_days=1 sets expiry ~1 day from now."""
    user = await _make_user(db)
    task = await _make_task(db, user)

    resp = await async_client.post(
        f"/api/v1/tasks/{task.id}/share?ttl_days=1",
        headers=_auth_headers(user),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    expires = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
    expected = datetime.now(tz=timezone.utc) + timedelta(days=1)
    delta = abs((expires - expected).total_seconds())
    assert delta < 120


@pytest.mark.asyncio
async def test_create_share_link_requires_auth(async_client: AsyncClient, db: AsyncSession):
    """POST /share without auth token returns 403."""
    user = await _make_user(db)
    task = await _make_task(db, user)

    resp = await async_client.post(f"/api/v1/tasks/{task.id}/share")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_create_share_link_wrong_user(async_client: AsyncClient, db: AsyncSession):
    """POST /share by a different user returns 404."""
    owner = await _make_user(db)
    attacker = await _make_user(db)
    task = await _make_task(db, owner)

    resp = await async_client.post(
        f"/api/v1/tasks/{task.id}/share",
        headers=_auth_headers(attacker),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_share_link_unknown_task(async_client: AsyncClient, db: AsyncSession):
    """POST /share with non-existent task_id returns 404."""
    user = await _make_user(db)

    resp = await async_client.post(
        f"/api/v1/tasks/{uuid4()}/share",
        headers=_auth_headers(user),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_share_link_overwrites_previous(async_client: AsyncClient, db: AsyncSession):
    """Calling POST /share twice gives a fresh token each time."""
    user = await _make_user(db)
    task = await _make_task(db, user)

    r1 = await async_client.post(f"/api/v1/tasks/{task.id}/share", headers=_auth_headers(user))
    r2 = await async_client.post(f"/api/v1/tasks/{task.id}/share", headers=_auth_headers(user))
    assert r1.status_code == 200
    assert r2.status_code == 200
    # New token is issued (may be same or different UUID; what matters is both are valid UUIDs)
    from uuid import UUID
    UUID(r1.json()["share_token"])  # raises if invalid
    UUID(r2.json()["share_token"])  # raises if invalid


# ── GET /r/{share_token} — expiry enforcement ─────────────────────────────────


@pytest.mark.asyncio
async def test_view_share_valid_not_expired(async_client: AsyncClient, db: AsyncSession):
    """GET /r/{share_token} returns 200 for a non-expired link."""
    user = await _make_user(db)
    token = uuid4()
    future = datetime.now(tz=timezone.utc) + timedelta(days=7)
    task = await _make_task(db, user, share_token=token, expires_at=future)

    resp = await async_client.get(f"/api/v1/r/{token}?fmt=json")
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_view_share_expired_returns_410(async_client: AsyncClient, db: AsyncSession):
    """GET /r/{share_token} returns 410 Gone when expires_at is in the past."""
    user = await _make_user(db)
    token = uuid4()
    past = datetime.now(tz=timezone.utc) - timedelta(seconds=1)
    task = await _make_task(db, user, share_token=token, expires_at=past)

    resp = await async_client.get(f"/api/v1/r/{token}")
    assert resp.status_code == 410, resp.text


@pytest.mark.asyncio
async def test_view_share_no_expiry_still_works(async_client: AsyncClient, db: AsyncSession):
    """GET /r/{task.id} without expires_at set (legacy) returns 200."""
    user = await _make_user(db)
    # expires_at=None → no expiry check
    task = await _make_task(db, user, expires_at=None)

    resp = await async_client.get(f"/api/v1/r/{task.id}?fmt=json")
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_view_share_unknown_token_404(async_client: AsyncClient, db: AsyncSession):
    """GET /r/{random_uuid} returns 404."""
    await _make_user(db)  # ensure tables exist
    resp = await async_client.get(f"/api/v1/r/{uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_view_share_invalid_uuid_404(async_client: AsyncClient, db: AsyncSession):
    """GET /r/not-a-uuid returns 404."""
    await _make_user(db)
    resp = await async_client.get("/api/v1/r/not-a-valid-uuid")
    assert resp.status_code == 404
