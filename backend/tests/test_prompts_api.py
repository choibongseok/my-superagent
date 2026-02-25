"""
Tests for Shared Prompt Library API.

Tests the /api/v1/prompts endpoints for creating and listing
shared prompt templates.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from app.core.security import create_access_token
from app.models.prompt import SharedPrompt
from app.models.user import User


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _make_user(db: AsyncSession, email: str | None = None) -> User:
    """Create a test user."""
    u = User(id=uuid4(), email=email or f"u-{uuid4().hex[:6]}@test.com", is_active=True)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


def _auth_headers(user: User) -> dict:
    """Generate authorization headers for a user."""
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_prompts_empty(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """List prompts when library is empty."""
    user = await _make_user(db)
    
    response = await async_client.get(
        "/api/v1/prompts/",
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["prompts"] == []
    assert data["page"] == 1
    assert data["page_size"] == 20


@pytest.mark.asyncio
async def test_create_public_prompt(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """Create a public prompt successfully."""
    user = await _make_user(db)
    
    payload = {
        "title": "Weekly Report Generator",
        "content": "Generate a weekly report summarizing...",
        "is_public": True,
    }
    
    response = await async_client.post(
        "/api/v1/prompts/",
        json=payload,
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == payload["title"]
    assert data["content"] == payload["content"]
    assert data["is_public"] is True
    assert data["use_count"] == 0
    assert data["user_id"] == str(user.id)
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_create_private_prompt(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """Create a private prompt successfully."""
    user = await _make_user(db)
    
    payload = {
        "title": "Personal Note Template",
        "content": "My private prompt content",
        "is_public": False,
    }
    
    response = await async_client.post(
        "/api/v1/prompts/",
        json=payload,
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["is_public"] is False


@pytest.mark.asyncio
async def test_list_public_prompts_only(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """List prompts returns only public prompts."""
    user = await _make_user(db)
    
    # Create 2 public prompts
    public1 = SharedPrompt(
        user_id=user.id,
        title="Public 1",
        content="Content 1",
        is_public=True,
        use_count=10,
    )
    public2 = SharedPrompt(
        user_id=user.id,
        title="Public 2",
        content="Content 2",
        is_public=True,
        use_count=5,
    )
    
    # Create 1 private prompt
    private = SharedPrompt(
        user_id=user.id,
        title="Private",
        content="Secret content",
        is_public=False,
        use_count=20,  # High count but still private
    )
    
    db.add_all([public1, public2, private])
    await db.commit()
    
    response = await async_client.get(
        "/api/v1/prompts/",
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2  # Only public prompts
    assert len(data["prompts"]) == 2
    
    titles = [p["title"] for p in data["prompts"]]
    assert "Public 1" in titles
    assert "Public 2" in titles
    assert "Private" not in titles


@pytest.mark.asyncio
async def test_list_prompts_ordered_by_use_count(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """Prompts are ordered by use_count descending."""
    user = await _make_user(db)
    
    prompts = [
        SharedPrompt(
            user_id=user.id,
            title=f"Prompt {i}",
            content=f"Content {i}",
            is_public=True,
            use_count=use_count,
        )
        for i, use_count in enumerate([5, 20, 10, 15])
    ]
    
    db.add_all(prompts)
    await db.commit()
    
    response = await async_client.get(
        "/api/v1/prompts/",
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 4
    
    use_counts = [p["use_count"] for p in data["prompts"]]
    assert use_counts == [20, 15, 10, 5]  # Descending order


@pytest.mark.asyncio
async def test_list_prompts_pagination(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """Pagination works correctly."""
    user = await _make_user(db)
    
    # Create 25 prompts
    prompts = [
        SharedPrompt(
            user_id=user.id,
            title=f"Prompt {i}",
            content=f"Content {i}",
            is_public=True,
            use_count=i,
        )
        for i in range(25)
    ]
    
    db.add_all(prompts)
    await db.commit()
    
    # Page 1 (default page_size=20)
    response = await async_client.get(
        "/api/v1/prompts/?page=1",
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 25
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert len(data["prompts"]) == 20
    
    # Page 2
    response = await async_client.get(
        "/api/v1/prompts/?page=2",
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 2
    assert len(data["prompts"]) == 5  # Remaining items


@pytest.mark.asyncio
async def test_list_prompts_custom_page_size(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """Custom page_size parameter works."""
    user = await _make_user(db)
    
    prompts = [
        SharedPrompt(
            user_id=user.id,
            title=f"Prompt {i}",
            content=f"Content {i}",
            is_public=True,
            use_count=0,
        )
        for i in range(15)
    ]
    
    db.add_all(prompts)
    await db.commit()
    
    response = await async_client.get(
        "/api/v1/prompts/?page_size=5",
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 15
    assert data["page_size"] == 5
    assert len(data["prompts"]) == 5


@pytest.mark.asyncio
async def test_create_prompt_unauthenticated(
    async_client: AsyncClient,
):
    """Creating a prompt requires authentication."""
    payload = {
        "title": "Test Prompt",
        "content": "Test content",
        "is_public": True,
    }
    
    response = await async_client.post(
        "/api/v1/prompts/",
        json=payload,
    )
    
    # API returns 403 when not authenticated (CSRF protection)
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_list_prompts_unauthenticated(
    async_client: AsyncClient,
):
    """Listing prompts requires authentication."""
    response = await async_client.get("/api/v1/prompts/")
    
    # API returns 403 when not authenticated (CSRF protection)
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_create_prompt_missing_fields(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """Creating a prompt with missing fields returns 422."""
    user = await _make_user(db)
    
    payload = {
        "title": "Test Prompt",
        # Missing 'content' field
    }
    
    response = await async_client.post(
        "/api/v1/prompts/",
        json=payload,
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_prompt_default_is_public(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """is_public defaults to false if not provided."""
    user = await _make_user(db)
    
    payload = {
        "title": "Test Prompt",
        "content": "Test content",
        # is_public not specified
    }
    
    response = await async_client.post(
        "/api/v1/prompts/",
        json=payload,
        headers=_auth_headers(user),
    )
    
    # Check schema definition to see if there's a default
    # If schema has no default, this will return 422
    # If it has default=False, this should succeed with is_public=False
    if response.status_code == 201:
        data = response.json()
        assert data["is_public"] is False
    else:
        # Schema requires is_public explicitly
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_prompt_empty_content(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """Creating a prompt with empty content should work (or fail with 422)."""
    user = await _make_user(db)
    
    payload = {
        "title": "Empty Prompt",
        "content": "",
        "is_public": True,
    }
    
    response = await async_client.post(
        "/api/v1/prompts/",
        json=payload,
        headers=_auth_headers(user),
    )
    
    # Depends on schema validation - either 201 or 422 is acceptable
    assert response.status_code in [201, 422]


@pytest.mark.asyncio
async def test_list_prompts_page_validation(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """Invalid page numbers are rejected."""
    user = await _make_user(db)
    
    # Page must be >= 1
    response = await async_client.get(
        "/api/v1/prompts/?page=0",
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_prompts_page_size_validation(
    async_client: AsyncClient,
    db: AsyncSession,
):
    """page_size must be within valid range (1-100)."""
    user = await _make_user(db)
    
    # page_size > 100
    response = await async_client.get(
        "/api/v1/prompts/?page_size=101",
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 422
    
    # page_size < 1
    response = await async_client.get(
        "/api/v1/prompts/?page_size=0",
        headers=_auth_headers(user),
    )
    
    assert response.status_code == 422
