"""Tests for #227 Smart Task Chaining — /api/v1/chains endpoints.

Covers:
  - CRUD operations (create, list, get, update, delete)
  - Chain execution (start, cancel, retry)
  - Authorization (cannot access other user's chains)
  - Validation (empty steps, bad status transitions)
  - Pagination
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.task import TaskType
from app.models.task_chain import ChainStatus, StepStatus, TaskChain, ChainStep
from app.models.user import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(email: str = "chain@example.com") -> User:
    return User(
        id=uuid4(),
        email=email,
        full_name="Chain User",
        is_active=True,
    )


def _make_token(user: User) -> str:
    return create_access_token({"sub": str(user.id)})


def _chain_payload(
    name: str = "Research → Docs",
    steps: list | None = None,
) -> dict:
    """Build a valid ChainCreate JSON payload."""
    if steps is None:
        steps = [
            {
                "prompt_template": "Research AI trends in 2026",
                "task_type": "research",
            },
            {
                "prompt_template": "Write a report based on: {{previous_output}}",
                "task_type": "docs",
            },
        ]
    return {"name": name, "steps": steps}


# ---------------------------------------------------------------------------
# Fixture
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
# CREATE
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_chain_success(db: AsyncSession, async_client: AsyncClient):
    """POST /chains with valid payload creates a DRAFT chain."""
    user = _make_user()
    db.add(user)
    await db.commit()
    token = _make_token(user)

    resp = await async_client.post(
        "/api/v1/chains",
        json=_chain_payload(),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "Research → Docs"
    assert data["status"] == "draft"
    assert len(data["steps"]) == 2
    assert data["steps"][0]["task_type"] == "research"
    assert data["steps"][1]["task_type"] == "docs"
    assert data["steps"][0]["status"] == "pending"


@pytest.mark.asyncio
async def test_create_chain_with_description(db: AsyncSession, async_client: AsyncClient):
    """Chain with optional description and metadata."""
    user = _make_user()
    db.add(user)
    await db.commit()
    token = _make_token(user)

    payload = _chain_payload()
    payload["description"] = "Full pipeline from research to document"
    payload["chain_metadata"] = {"project": "Q1 report"}

    resp = await async_client.post(
        "/api/v1/chains",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["description"] == "Full pipeline from research to document"
    assert data["chain_metadata"] == {"project": "Q1 report"}


@pytest.mark.asyncio
async def test_create_chain_empty_steps_rejected(db: AsyncSession, async_client: AsyncClient):
    """Cannot create a chain with 0 steps."""
    user = _make_user()
    db.add(user)
    await db.commit()
    token = _make_token(user)

    resp = await async_client.post(
        "/api/v1/chains",
        json={"name": "Empty", "steps": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_chain_single_step(db: AsyncSession, async_client: AsyncClient):
    """A single-step chain is valid."""
    user = _make_user()
    db.add(user)
    await db.commit()
    token = _make_token(user)

    payload = _chain_payload(
        name="Single step",
        steps=[{"prompt_template": "Just research", "task_type": "research"}],
    )
    resp = await async_client.post(
        "/api/v1/chains",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert len(resp.json()["steps"]) == 1


@pytest.mark.asyncio
async def test_create_chain_no_auth(async_client: AsyncClient):
    """Request without auth token is rejected."""
    resp = await async_client.post(
        "/api/v1/chains",
        json=_chain_payload(),
    )
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_chains_empty(db: AsyncSession, async_client: AsyncClient):
    """No chains → empty list, total 0."""
    user = _make_user()
    db.add(user)
    await db.commit()
    token = _make_token(user)

    resp = await async_client.get(
        "/api/v1/chains",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["chains"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_chains_returns_user_chains(db: AsyncSession, async_client: AsyncClient):
    """List returns chains belonging to the current user only."""
    user = _make_user()
    other = _make_user("other@example.com")
    db.add_all([user, other])
    await db.commit()

    # Create chain for user
    chain = TaskChain(
        id=uuid4(), user_id=user.id, name="My chain",
        status=ChainStatus.DRAFT, current_step_index=0,
    )
    step = ChainStep(
        id=uuid4(), chain_id=chain.id, step_order=0,
        prompt_template="test", task_type=TaskType.RESEARCH,
        status=StepStatus.PENDING,
    )
    chain.steps.append(step)

    # Create chain for other user
    other_chain = TaskChain(
        id=uuid4(), user_id=other.id, name="Other chain",
        status=ChainStatus.DRAFT, current_step_index=0,
    )
    other_step = ChainStep(
        id=uuid4(), chain_id=other_chain.id, step_order=0,
        prompt_template="other", task_type=TaskType.RESEARCH,
        status=StepStatus.PENDING,
    )
    other_chain.steps.append(other_step)

    db.add_all([chain, other_chain])
    await db.commit()

    token = _make_token(user)
    resp = await async_client.get(
        "/api/v1/chains",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["chains"][0]["name"] == "My chain"


@pytest.mark.asyncio
async def test_list_chains_pagination(db: AsyncSession, async_client: AsyncClient):
    """Pagination via offset and limit."""
    user = _make_user()
    db.add(user)
    await db.commit()

    for i in range(5):
        chain = TaskChain(
            id=uuid4(), user_id=user.id, name=f"Chain {i}",
            status=ChainStatus.DRAFT, current_step_index=0,
        )
        step = ChainStep(
            id=uuid4(), chain_id=chain.id, step_order=0,
            prompt_template="test", task_type=TaskType.RESEARCH,
            status=StepStatus.PENDING,
        )
        chain.steps.append(step)
        db.add(chain)
    await db.commit()

    token = _make_token(user)

    resp = await async_client.get(
        "/api/v1/chains?offset=0&limit=2",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 5
    assert len(data["chains"]) == 2

    resp2 = await async_client.get(
        "/api/v1/chains?offset=4&limit=10",
        headers={"Authorization": f"Bearer {token}"},
    )
    data2 = resp2.json()
    assert len(data2["chains"]) == 1


# ---------------------------------------------------------------------------
# GET
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_chain_success(db: AsyncSession, async_client: AsyncClient):
    """Fetch a specific chain by ID."""
    user = _make_user()
    db.add(user)
    await db.commit()

    chain = TaskChain(
        id=uuid4(), user_id=user.id, name="My chain",
        status=ChainStatus.DRAFT, current_step_index=0,
    )
    step = ChainStep(
        id=uuid4(), chain_id=chain.id, step_order=0,
        prompt_template="Research AI", task_type=TaskType.RESEARCH,
        status=StepStatus.PENDING,
    )
    chain.steps.append(step)
    db.add(chain)
    await db.commit()

    token = _make_token(user)
    resp = await async_client.get(
        f"/api/v1/chains/{chain.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(chain.id)
    assert data["name"] == "My chain"
    assert len(data["steps"]) == 1


@pytest.mark.asyncio
async def test_get_chain_not_found(db: AsyncSession, async_client: AsyncClient):
    """404 for non-existent chain."""
    user = _make_user()
    db.add(user)
    await db.commit()
    token = _make_token(user)

    resp = await async_client.get(
        f"/api/v1/chains/{uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_chain_other_user_forbidden(db: AsyncSession, async_client: AsyncClient):
    """Cannot access another user's chain (returns 404 for security)."""
    user = _make_user()
    other = _make_user("other@example.com")
    db.add_all([user, other])
    await db.commit()

    chain = TaskChain(
        id=uuid4(), user_id=other.id, name="Other's chain",
        status=ChainStatus.DRAFT, current_step_index=0,
    )
    step = ChainStep(
        id=uuid4(), chain_id=chain.id, step_order=0,
        prompt_template="test", task_type=TaskType.RESEARCH,
        status=StepStatus.PENDING,
    )
    chain.steps.append(step)
    db.add(chain)
    await db.commit()

    token = _make_token(user)
    resp = await async_client.get(
        f"/api/v1/chains/{chain.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_chain_name(db: AsyncSession, async_client: AsyncClient):
    """PATCH updates name on a DRAFT chain."""
    user = _make_user()
    db.add(user)
    await db.commit()

    chain = TaskChain(
        id=uuid4(), user_id=user.id, name="Old name",
        status=ChainStatus.DRAFT, current_step_index=0,
    )
    step = ChainStep(
        id=uuid4(), chain_id=chain.id, step_order=0,
        prompt_template="test", task_type=TaskType.RESEARCH,
        status=StepStatus.PENDING,
    )
    chain.steps.append(step)
    db.add(chain)
    await db.commit()

    token = _make_token(user)
    resp = await async_client.patch(
        f"/api/v1/chains/{chain.id}",
        json={"name": "New name"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "New name"


@pytest.mark.asyncio
async def test_update_running_chain_rejected(db: AsyncSession, async_client: AsyncClient):
    """Cannot update a RUNNING chain."""
    user = _make_user()
    db.add(user)
    await db.commit()

    chain = TaskChain(
        id=uuid4(), user_id=user.id, name="Running",
        status=ChainStatus.RUNNING, current_step_index=0,
    )
    step = ChainStep(
        id=uuid4(), chain_id=chain.id, step_order=0,
        prompt_template="test", task_type=TaskType.RESEARCH,
        status=StepStatus.RUNNING,
    )
    chain.steps.append(step)
    db.add(chain)
    await db.commit()

    token = _make_token(user)
    resp = await async_client.patch(
        f"/api/v1/chains/{chain.id}",
        json={"name": "Updated"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_chain_success(db: AsyncSession, async_client: AsyncClient):
    """DELETE removes chain and steps."""
    user = _make_user()
    db.add(user)
    await db.commit()

    chain = TaskChain(
        id=uuid4(), user_id=user.id, name="To delete",
        status=ChainStatus.DRAFT, current_step_index=0,
    )
    step = ChainStep(
        id=uuid4(), chain_id=chain.id, step_order=0,
        prompt_template="test", task_type=TaskType.RESEARCH,
        status=StepStatus.PENDING,
    )
    chain.steps.append(step)
    db.add(chain)
    await db.commit()

    token = _make_token(user)
    resp = await async_client.delete(
        f"/api/v1/chains/{chain.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204

    # Confirm gone
    resp2 = await async_client.get(
        f"/api/v1/chains/{chain.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_chain(db: AsyncSession, async_client: AsyncClient):
    """DELETE returns 404 for unknown ID."""
    user = _make_user()
    db.add(user)
    await db.commit()
    token = _make_token(user)

    resp = await async_client.delete(
        f"/api/v1/chains/{uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# START
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_start_chain_draft(db: AsyncSession, async_client: AsyncClient):
    """Starting a DRAFT chain moves it to RUNNING."""
    user = _make_user()
    db.add(user)
    await db.commit()

    chain = TaskChain(
        id=uuid4(), user_id=user.id, name="Draft chain",
        status=ChainStatus.DRAFT, current_step_index=0,
    )
    step = ChainStep(
        id=uuid4(), chain_id=chain.id, step_order=0,
        prompt_template="Research something", task_type=TaskType.RESEARCH,
        status=StepStatus.PENDING,
    )
    chain.steps.append(step)
    db.add(chain)
    await db.commit()

    token = _make_token(user)
    resp = await async_client.post(
        f"/api/v1/chains/{chain.id}/start",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["steps"][0]["status"] == "running"


@pytest.mark.asyncio
async def test_start_completed_chain_rejected(db: AsyncSession, async_client: AsyncClient):
    """Cannot start an already COMPLETED chain."""
    user = _make_user()
    db.add(user)
    await db.commit()

    chain = TaskChain(
        id=uuid4(), user_id=user.id, name="Done chain",
        status=ChainStatus.COMPLETED, current_step_index=0,
    )
    step = ChainStep(
        id=uuid4(), chain_id=chain.id, step_order=0,
        prompt_template="test", task_type=TaskType.RESEARCH,
        status=StepStatus.COMPLETED,
    )
    chain.steps.append(step)
    db.add(chain)
    await db.commit()

    token = _make_token(user)
    resp = await async_client.post(
        f"/api/v1/chains/{chain.id}/start",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# CANCEL
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cancel_running_chain(db: AsyncSession, async_client: AsyncClient):
    """Cancelling a RUNNING chain marks it CANCELLED; pending steps SKIPPED."""
    user = _make_user()
    db.add(user)
    await db.commit()

    chain = TaskChain(
        id=uuid4(), user_id=user.id, name="Running",
        status=ChainStatus.RUNNING, current_step_index=0,
    )
    step0 = ChainStep(
        id=uuid4(), chain_id=chain.id, step_order=0,
        prompt_template="Step A", task_type=TaskType.RESEARCH,
        status=StepStatus.RUNNING,
    )
    step1 = ChainStep(
        id=uuid4(), chain_id=chain.id, step_order=1,
        prompt_template="Step B", task_type=TaskType.DOCS,
        status=StepStatus.PENDING,
    )
    chain.steps.extend([step0, step1])
    db.add(chain)
    await db.commit()

    token = _make_token(user)
    resp = await async_client.post(
        f"/api/v1/chains/{chain.id}/cancel",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "cancelled"
    # Pending step 1 should be SKIPPED
    assert data["steps"][1]["status"] == "skipped"


@pytest.mark.asyncio
async def test_cancel_completed_chain_rejected(db: AsyncSession, async_client: AsyncClient):
    """Cannot cancel an already completed chain."""
    user = _make_user()
    db.add(user)
    await db.commit()

    chain = TaskChain(
        id=uuid4(), user_id=user.id, name="Done",
        status=ChainStatus.COMPLETED, current_step_index=0,
    )
    step = ChainStep(
        id=uuid4(), chain_id=chain.id, step_order=0,
        prompt_template="test", task_type=TaskType.RESEARCH,
        status=StepStatus.COMPLETED,
    )
    chain.steps.append(step)
    db.add(chain)
    await db.commit()

    token = _make_token(user)
    resp = await async_client.post(
        f"/api/v1/chains/{chain.id}/cancel",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# RETRY
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_failed_chain(db: AsyncSession, async_client: AsyncClient):
    """Retrying a FAILED chain restarts it from the failed step."""
    user = _make_user()
    db.add(user)
    await db.commit()

    chain = TaskChain(
        id=uuid4(), user_id=user.id, name="Failed chain",
        status=ChainStatus.FAILED, current_step_index=1,
    )
    step0 = ChainStep(
        id=uuid4(), chain_id=chain.id, step_order=0,
        prompt_template="Step A", task_type=TaskType.RESEARCH,
        status=StepStatus.COMPLETED,
        output_summary="AI trends data",
    )
    step1 = ChainStep(
        id=uuid4(), chain_id=chain.id, step_order=1,
        prompt_template="Write report on: {{previous_output}}",
        task_type=TaskType.DOCS,
        status=StepStatus.FAILED,
        error_message="LLM timeout",
    )
    chain.steps.extend([step0, step1])
    db.add(chain)
    await db.commit()

    token = _make_token(user)
    resp = await async_client.post(
        f"/api/v1/chains/{chain.id}/retry",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"


@pytest.mark.asyncio
async def test_retry_non_failed_chain_rejected(db: AsyncSession, async_client: AsyncClient):
    """Cannot retry a chain that isn't in FAILED state."""
    user = _make_user()
    db.add(user)
    await db.commit()

    chain = TaskChain(
        id=uuid4(), user_id=user.id, name="Draft",
        status=ChainStatus.DRAFT, current_step_index=0,
    )
    step = ChainStep(
        id=uuid4(), chain_id=chain.id, step_order=0,
        prompt_template="test", task_type=TaskType.RESEARCH,
        status=StepStatus.PENDING,
    )
    chain.steps.append(step)
    db.add(chain)
    await db.commit()

    token = _make_token(user)
    resp = await async_client.post(
        f"/api/v1/chains/{chain.id}/retry",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Create via API → Fetch → Start (integration)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_lifecycle_create_list_start_cancel(
    db: AsyncSession, async_client: AsyncClient
):
    """Full lifecycle: create → list → get → start → cancel."""
    user = _make_user()
    db.add(user)
    await db.commit()
    token = _make_token(user)
    headers = {"Authorization": f"Bearer {token}"}

    # Create
    resp = await async_client.post(
        "/api/v1/chains",
        json=_chain_payload(name="Lifecycle test"),
        headers=headers,
    )
    assert resp.status_code == 201
    chain_id = resp.json()["id"]

    # List
    resp = await async_client.get("/api/v1/chains", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 1

    # Get
    resp = await async_client.get(f"/api/v1/chains/{chain_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "draft"

    # Start
    resp = await async_client.post(f"/api/v1/chains/{chain_id}/start", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"

    # Cancel
    resp = await async_client.post(f"/api/v1/chains/{chain_id}/cancel", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


# ---------------------------------------------------------------------------
# Multi-step chain with step_metadata
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_chain_with_step_metadata(
    db: AsyncSession, async_client: AsyncClient
):
    """Steps can carry arbitrary metadata."""
    user = _make_user()
    db.add(user)
    await db.commit()
    token = _make_token(user)

    payload = _chain_payload(
        name="With metadata",
        steps=[
            {
                "prompt_template": "Research market data",
                "task_type": "research",
                "step_metadata": {"source": "web"},
            },
            {
                "prompt_template": "Create spreadsheet from: {{previous_output}}",
                "task_type": "sheets",
                "step_metadata": {"chart_type": "bar"},
            },
            {
                "prompt_template": "Create slides from: {{previous_output}}",
                "task_type": "slides",
                "step_metadata": {"theme": "corporate"},
            },
        ],
    )

    resp = await async_client.post(
        "/api/v1/chains",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert len(data["steps"]) == 3
    assert data["steps"][0]["step_metadata"] == {"source": "web"}
    assert data["steps"][1]["step_metadata"] == {"chart_type": "bar"}
    assert data["steps"][2]["step_metadata"] == {"theme": "corporate"}
