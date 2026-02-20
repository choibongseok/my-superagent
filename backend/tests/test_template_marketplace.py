"""Tests for Phase 5 Feature — Template Marketplace discovery endpoint."""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.template import Template
from app.models.user import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(email: str) -> User:
    return User(id=uuid4(), email=email, is_active=True)


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token({"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


async def _create_template(
    db: AsyncSession,
    user: User,
    *,
    name: str,
    category: str = "research",
    is_public: bool = True,
    is_official: bool = False,
    is_featured: bool = False,
    usage_count: int = 0,
    rating: float = 0.0,
    description: str | None = None,
) -> Template:
    template = Template(
        id=uuid4(),
        name=name,
        description=description,
        category=category,
        tags=None,
        author_id=user.id,
        prompt_template="Create {topic}",
        is_public=is_public,
        is_official=is_official,
        is_featured=is_featured,
        usage_count=usage_count,
        rating=rating,
        rating_count=3,
    )
    db.add(template)
    return template


# ---------------------------------------------------------------------------
# Marketplace endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_marketplace_exposes_public_templates_only(db: AsyncSession, async_client: AsyncClient):
    """Only public templates should be listed in marketplace."""
    owner = _make_user("marketplace-owner@example.com")
    db.add(owner)

    await _create_template(
        db,
        owner,
        name="Public Slow",
        is_public=True,
        usage_count=1,
        rating=4.2,
    )
    await _create_template(
        db,
        owner,
        name="Public Fast",
        is_public=True,
        usage_count=10,
        rating=4.5,
    )
    await _create_template(
        db,
        owner,
        name="Private Hidden",
        is_public=False,
        usage_count=100,
        rating=5.0,
    )
    await db.commit()

    resp = await async_client.get(
        "/api/v1/templates/marketplace",
        headers=_auth_headers(owner),
    )

    assert resp.status_code == 200
    payload = resp.json()

    assert payload["total"] == 2
    names = [item["name"] for item in payload["templates"]]
    assert names == ["Public Fast", "Public Slow"]


@pytest.mark.asyncio
async def test_marketplace_filters_featured_templates(db: AsyncSession, async_client: AsyncClient):
    """`featured=true` should return only featured templates."""
    owner = _make_user("marketplace-featured@example.com")
    db.add(owner)

    await _create_template(db, owner, name="Feature One", is_featured=True)
    await _create_template(db, owner, name="Regular One", is_featured=False)
    await db.commit()

    resp = await async_client.get(
        "/api/v1/templates/marketplace?featured=true",
        headers=_auth_headers(owner),
    )

    assert resp.status_code == 200
    payload = resp.json()

    assert payload["total"] == 1
    assert payload["templates"][0]["name"] == "Feature One"
    assert payload["templates"][0]["is_featured"] is True


@pytest.mark.asyncio
async def test_marketplace_searches_and_filters_by_category(db: AsyncSession, async_client: AsyncClient):
    """Query + category filters should narrow marketplace results."""
    owner = _make_user("marketplace-search@example.com")
    db.add(owner)

    await _create_template(
        db,
        owner,
        name="Docs Mastery",
        category="docs",
        usage_count=3,
        rating=3.9,
    )
    await _create_template(
        db,
        owner,
        name="Sheets Mastery",
        category="sheets",
        usage_count=5,
        rating=4.9,
    )
    await db.commit()

    resp = await async_client.get(
        "/api/v1/templates/marketplace?query=mastery&category=docs",
        headers=_auth_headers(owner),
    )

    assert resp.status_code == 200
    payload = resp.json()

    assert payload["total"] == 1
    assert payload["templates"][0]["name"] == "Docs Mastery"
    assert payload["templates"][0]["category"] == "docs"
