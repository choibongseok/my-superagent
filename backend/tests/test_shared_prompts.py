"""Tests for #208 Shared Prompt Library — GET/POST /api/v1/prompts."""

from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.prompt import SharedPrompt
from app.models.user import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(email: str = "prompt@example.com") -> User:
    return User(
        id=uuid4(),
        email=email,
        full_name="Prompt User",
        is_active=True,
    )


def _make_token(user: User) -> str:
    return create_access_token({"sub": str(user.id)})


# ---------------------------------------------------------------------------
# Async client fixture
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def async_client(db: AsyncSession):
    app.dependency_overrides[get_db] = lambda: (yield db)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /api/v1/prompts — create
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_public_prompt(db: AsyncSession, async_client: AsyncClient):
    """A user can create a public shared prompt."""
    user = _make_user()
    db.add(user)
    await db.commit()

    token = _make_token(user)

    resp = await async_client.post(
        "/api/v1/prompts/",
        json={"title": "GPT Haiku", "content": "Write a haiku about {topic}.", "is_public": True},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["title"] == "GPT Haiku"
    assert data["content"] == "Write a haiku about {topic}."
    assert data["is_public"] is True
    assert data["use_count"] == 0
    assert data["user_id"] == str(user.id)
    assert "id" in data


@pytest.mark.asyncio
async def test_create_private_prompt(db: AsyncSession, async_client: AsyncClient):
    """A user can create a private prompt (not visible to others)."""
    user = _make_user(email="private@example.com")
    db.add(user)
    await db.commit()

    token = _make_token(user)

    resp = await async_client.post(
        "/api/v1/prompts/",
        json={"title": "Secret Prompt", "content": "Top secret content", "is_public": False},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 201
    assert resp.json()["is_public"] is False


@pytest.mark.asyncio
async def test_create_prompt_defaults_to_private(db: AsyncSession, async_client: AsyncClient):
    """Omitting is_public should default to False."""
    user = _make_user(email="default@example.com")
    db.add(user)
    await db.commit()

    token = _make_token(user)

    resp = await async_client.post(
        "/api/v1/prompts/",
        json={"title": "Default Visibility", "content": "Some content"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 201
    assert resp.json()["is_public"] is False


@pytest.mark.asyncio
async def test_create_prompt_requires_auth(db: AsyncSession, async_client: AsyncClient):
    """Creating a prompt without auth must fail."""
    resp = await async_client.post(
        "/api/v1/prompts/",
        json={"title": "No Auth", "content": "Should fail"},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_create_prompt_rejects_empty_title(db: AsyncSession, async_client: AsyncClient):
    """Empty title must fail validation."""
    user = _make_user(email="val@example.com")
    db.add(user)
    await db.commit()

    token = _make_token(user)

    resp = await async_client.post(
        "/api/v1/prompts/",
        json={"title": "", "content": "Some content"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_prompt_rejects_empty_content(db: AsyncSession, async_client: AsyncClient):
    """Empty content must fail validation."""
    user = _make_user(email="val2@example.com")
    db.add(user)
    await db.commit()

    token = _make_token(user)

    resp = await async_client.post(
        "/api/v1/prompts/",
        json={"title": "Title OK", "content": ""},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/prompts — list public
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_public_prompts_empty(db: AsyncSession, async_client: AsyncClient):
    """With no prompts, the list should be empty."""
    user = _make_user(email="list@example.com")
    db.add(user)
    await db.commit()

    token = _make_token(user)

    resp = await async_client.get(
        "/api/v1/prompts/",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["prompts"] == []


@pytest.mark.asyncio
async def test_list_public_prompts_returns_only_public(db: AsyncSession, async_client: AsyncClient):
    """Private prompts must NOT appear in the public listing."""
    user = _make_user(email="mix@example.com")
    db.add(user)
    await db.commit()

    public_prompt = SharedPrompt(
        id=uuid4(),
        user_id=user.id,
        title="Public One",
        content="Public content",
        is_public=True,
        use_count=0,
    )
    private_prompt = SharedPrompt(
        id=uuid4(),
        user_id=user.id,
        title="Private One",
        content="Private content",
        is_public=False,
        use_count=0,
    )
    db.add(public_prompt)
    db.add(private_prompt)
    await db.commit()

    token = _make_token(user)

    resp = await async_client.get(
        "/api/v1/prompts/",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    titles = [p["title"] for p in data["prompts"]]
    assert "Public One" in titles
    assert "Private One" not in titles


@pytest.mark.asyncio
async def test_list_public_prompts_sorted_by_use_count(db: AsyncSession, async_client: AsyncClient):
    """Public prompts should be ordered by use_count descending."""
    user = _make_user(email="sorted@example.com")
    db.add(user)
    await db.commit()

    for title, count in [("Low", 1), ("High", 100), ("Mid", 50)]:
        db.add(SharedPrompt(
            id=uuid4(),
            user_id=user.id,
            title=title,
            content="Content",
            is_public=True,
            use_count=count,
        ))
    await db.commit()

    token = _make_token(user)

    resp = await async_client.get(
        "/api/v1/prompts/",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    titles = [p["title"] for p in resp.json()["prompts"]]
    assert titles == ["High", "Mid", "Low"]


@pytest.mark.asyncio
async def test_list_public_prompts_pagination(db: AsyncSession, async_client: AsyncClient):
    """Pagination parameters should limit results correctly."""
    user = _make_user(email="page@example.com")
    db.add(user)
    await db.commit()

    for i in range(5):
        db.add(SharedPrompt(
            id=uuid4(),
            user_id=user.id,
            title=f"Prompt {i}",
            content="x",
            is_public=True,
            use_count=i,
        ))
    await db.commit()

    token = _make_token(user)

    resp = await async_client.get(
        "/api/v1/prompts/?page=1&page_size=2",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 5
    assert len(data["prompts"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 2


@pytest.mark.asyncio
async def test_list_prompts_requires_auth(db: AsyncSession, async_client: AsyncClient):
    """Listing prompts without auth must fail."""
    resp = await async_client.get("/api/v1/prompts/")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_response_schema_fields(db: AsyncSession, async_client: AsyncClient):
    """Each prompt in the list should have all expected schema fields."""
    user = _make_user(email="schema@example.com")
    db.add(user)
    await db.commit()

    db.add(SharedPrompt(
        id=uuid4(),
        user_id=user.id,
        title="Schema Check",
        content="Check fields",
        is_public=True,
        use_count=7,
    ))
    await db.commit()

    token = _make_token(user)

    resp = await async_client.get(
        "/api/v1/prompts/",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    prompt = resp.json()["prompts"][0]
    for field in ("id", "user_id", "title", "content", "is_public", "use_count", "created_at", "updated_at"):
        assert field in prompt, f"Missing field: {field}"
