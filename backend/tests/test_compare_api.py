"""Tests for #209 Task Output Diff Viewer — GET /r/compare?a=&b=

Covers:
- HTML side-by-side diff for two completed tasks
- JSON diff output (?fmt=json)
- 404 when either token is missing/not-found
- 404 when a task is not yet completed
- Identical tasks → diff shows "identical"
- Cross-user tasks (tokens are public — both are accessible)
- Invalid UUID format → 404
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.models.task import Task as TaskModel, TaskStatus, TaskType
from app.models.user import User

# ── helpers ──────────────────────────────────────────────────────────────────


async def _make_user(db, email: str | None = None) -> User:
    u = User(id=uuid4(), email=email or f"u-{uuid4().hex[:6]}@x.com", is_active=True)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _make_task(
    db,
    user: User,
    prompt: str = "default prompt",
    content: str = "default result",
    status: TaskStatus = TaskStatus.COMPLETED,
    task_type: TaskType = TaskType.RESEARCH,
) -> TaskModel:
    t = TaskModel(
        id=uuid4(),
        user_id=user.id,
        prompt=prompt,
        task_type=task_type,
        status=status,
        result={"content": content, "title": f"Title: {prompt[:30]}"},
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


# ── HTML compare endpoint ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_compare_html_success(async_client: AsyncClient, db):
    user = await _make_user(db)
    task_a = await _make_task(db, user, prompt="Write a summary",
                              content="Line one\nLine two\nLine three")
    task_b = await _make_task(db, user, prompt="Write a detailed summary",
                              content="Line one\nLine two changed\nLine four")

    resp = await async_client.get(f"/api/v1/r/compare?a={task_a.id}&b={task_b.id}")
    assert resp.status_code == 200, resp.text
    body = resp.text
    assert "버전 A" in body
    assert "버전 B" in body
    assert "Line one" in body


@pytest.mark.asyncio
async def test_compare_html_identical(async_client: AsyncClient, db):
    user = await _make_user(db)
    same_content = "Exactly the same content\nLine two\nLine three"
    task_a = await _make_task(db, user, content=same_content)
    task_b = await _make_task(db, user, content=same_content)

    resp = await async_client.get(f"/api/v1/r/compare?a={task_a.id}&b={task_b.id}")
    assert resp.status_code == 200
    assert "차이가 없습니다" in resp.text


@pytest.mark.asyncio
async def test_compare_json_success(async_client: AsyncClient, db):
    user = await _make_user(db)
    task_a = await _make_task(db, user, content="Alpha\nBeta\nGamma")
    task_b = await _make_task(db, user, content="Alpha\nDelta\nGamma")

    resp = await async_client.get(
        f"/api/v1/r/compare?a={task_a.id}&b={task_b.id}&fmt=json"
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["task_a"]["id"] == str(task_a.id)
    assert data["task_b"]["id"] == str(task_b.id)
    assert "diff" in data
    assert "unified" in data["diff"]
    assert isinstance(data["diff"]["unified"], list)
    assert data["diff"]["identical"] is False


@pytest.mark.asyncio
async def test_compare_json_identical(async_client: AsyncClient, db):
    user = await _make_user(db)
    content = "Same line\nSame line 2"
    task_a = await _make_task(db, user, content=content)
    task_b = await _make_task(db, user, content=content)

    resp = await async_client.get(
        f"/api/v1/r/compare?a={task_a.id}&b={task_b.id}&fmt=json"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["diff"]["identical"] is True
    assert data["diff"]["unified"] == []


@pytest.mark.asyncio
async def test_compare_missing_token_a(async_client: AsyncClient, db):
    user = await _make_user(db)
    task_b = await _make_task(db, user)

    resp = await async_client.get(f"/api/v1/r/compare?a={uuid4()}&b={task_b.id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_compare_missing_token_b(async_client: AsyncClient, db):
    user = await _make_user(db)
    task_a = await _make_task(db, user)

    resp = await async_client.get(f"/api/v1/r/compare?a={task_a.id}&b={uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_compare_both_missing(async_client: AsyncClient):
    resp = await async_client.get(f"/api/v1/r/compare?a={uuid4()}&b={uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_compare_invalid_uuid_a(async_client: AsyncClient, db):
    user = await _make_user(db)
    task_b = await _make_task(db, user)

    resp = await async_client.get(f"/api/v1/r/compare?a=not-a-uuid&b={task_b.id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_compare_invalid_uuid_b(async_client: AsyncClient, db):
    user = await _make_user(db)
    task_a = await _make_task(db, user)

    resp = await async_client.get(f"/api/v1/r/compare?a={task_a.id}&b=not-a-uuid")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_compare_task_not_completed(async_client: AsyncClient, db):
    """If one task is not completed (e.g. still pending), it should be 404."""
    user = await _make_user(db)
    task_a = await _make_task(db, user, status=TaskStatus.PENDING)
    task_b = await _make_task(db, user, status=TaskStatus.COMPLETED)

    resp = await async_client.get(f"/api/v1/r/compare?a={task_a.id}&b={task_b.id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_compare_cross_user_tasks_are_public(async_client: AsyncClient, db):
    """Diff viewer is public — tasks from different users should both be accessible."""
    user_a = await _make_user(db)
    user_b = await _make_user(db)
    task_a = await _make_task(db, user_a, content="User A output")
    task_b = await _make_task(db, user_b, content="User B output")

    resp = await async_client.get(f"/api/v1/r/compare?a={task_a.id}&b={task_b.id}")
    assert resp.status_code == 200
    assert "User A output" in resp.text
    assert "User B output" in resp.text


@pytest.mark.asyncio
async def test_compare_missing_query_params(async_client: AsyncClient):
    """Both a and b are required."""
    resp = await async_client.get("/api/v1/r/compare")
    assert resp.status_code == 422  # FastAPI validation error


@pytest.mark.asyncio
async def test_compare_only_a_param(async_client: AsyncClient):
    resp = await async_client.get(f"/api/v1/r/compare?a={uuid4()}")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_compare_json_diff_contains_hunks(async_client: AsyncClient, db):
    """JSON diff unified output should contain +/- markers for changed lines."""
    user = await _make_user(db)
    task_a = await _make_task(db, user, content="Line A\nShared\nLine C")
    task_b = await _make_task(db, user, content="Line X\nShared\nLine Z")

    resp = await async_client.get(
        f"/api/v1/r/compare?a={task_a.id}&b={task_b.id}&fmt=json"
    )
    assert resp.status_code == 200
    diff_lines = resp.json()["diff"]["unified"]
    assert any(l.startswith("-") for l in diff_lines if not l.startswith("---")), diff_lines
    assert any(l.startswith("+") for l in diff_lines if not l.startswith("+++")), diff_lines


@pytest.mark.asyncio
async def test_compare_html_shows_both_prompts(async_client: AsyncClient, db):
    user = await _make_user(db)
    task_a = await _make_task(db, user, prompt="Prompt for task Alpha")
    task_b = await _make_task(db, user, prompt="Prompt for task Beta")

    resp = await async_client.get(f"/api/v1/r/compare?a={task_a.id}&b={task_b.id}")
    assert resp.status_code == 200
    body = resp.text
    assert "Prompt for task Alpha" in body
    assert "Prompt for task Beta" in body
