"""Tests for #220 Magic Link Guest Access — anonymous 1-click re-run.

Covers:
  - Happy path: POST /r/{token}/try creates a new guest task (202)
  - Rate limiting: max+1 try returns 429
  - Invalid/missing token returns 404
  - Expired share link returns 410
  - All task types (docs, sheets, slides, research)
  - Celery failure → task marked failed but still 202
  - Response schema (task_id, signup_url, tries_remaining, etc.)
  - Config defaults
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.cache import cache
from app.models.task import Task as TaskModel, TaskStatus, TaskType
from app.models.user import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_user(db, email: str | None = None) -> User:
    u = User(id=uuid4(), email=email or f"guest-{uuid4().hex[:6]}@test.com", is_active=True)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _make_shared_task(
    db,
    user: User,
    prompt: str = "Summarize Q4 earnings",
    content: str = "Q4 revenue grew 18% YoY",
    task_type: TaskType = TaskType.DOCS,
    expires_at: datetime | None = None,
) -> TaskModel:
    share_token = uuid4()
    t = TaskModel(
        id=uuid4(),
        user_id=user.id,
        prompt=prompt,
        task_type=task_type,
        status=TaskStatus.COMPLETED,
        result={"content": content, "title": f"Title: {prompt[:30]}"},
        share_token=share_token,
        expires_at=expires_at,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMagicLinkTry:
    """POST /r/{share_token}/try endpoint."""

    @pytest.mark.asyncio
    async def test_try_creates_guest_task_202(self, async_client: AsyncClient, db):
        """Happy path: POST /r/{token}/try → 202 with task_id."""
        user = await _make_user(db)
        task = await _make_shared_task(db, user)

        mock_celery = MagicMock()
        mock_celery.id = "celery-guest-001"

        with patch("app.agents.celery_app.process_docs_task") as mock_docs:
            mock_docs.apply_async = MagicMock(return_value=mock_celery)
            resp = await async_client.post(f"/api/v1/r/{task.share_token}/try")

        assert resp.status_code == 202, resp.text
        data = resp.json()
        assert "task_id" in data
        assert data["task_type"] == "docs"
        assert data["original_prompt"] == task.prompt[:200]
        assert "signup_url" in data
        assert "ref=magic_link" in data["signup_url"]
        assert str(task.share_token) in data["signup_url"]
        mock_docs.apply_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_try_research_type(self, async_client: AsyncClient, db):
        """Research task dispatches to process_research_task."""
        user = await _make_user(db)
        task = await _make_shared_task(db, user, task_type=TaskType.RESEARCH)

        mock_celery = MagicMock()
        mock_celery.id = "celery-research-001"

        with patch("app.agents.celery_app.process_research_task") as mock_rt:
            mock_rt.apply_async = MagicMock(return_value=mock_celery)
            resp = await async_client.post(f"/api/v1/r/{task.share_token}/try")

        assert resp.status_code == 202
        assert resp.json()["task_type"] == "research"
        mock_rt.apply_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_try_sheets_type(self, async_client: AsyncClient, db):
        user = await _make_user(db)
        task = await _make_shared_task(db, user, task_type=TaskType.SHEETS)

        mock_celery = MagicMock()
        mock_celery.id = "celery-sheets-001"

        with patch("app.agents.celery_app.process_sheets_task") as mock_st:
            mock_st.apply_async = MagicMock(return_value=mock_celery)
            resp = await async_client.post(f"/api/v1/r/{task.share_token}/try")

        assert resp.status_code == 202
        assert resp.json()["task_type"] == "sheets"

    @pytest.mark.asyncio
    async def test_try_slides_type(self, async_client: AsyncClient, db):
        user = await _make_user(db)
        task = await _make_shared_task(db, user, task_type=TaskType.SLIDES)

        mock_celery = MagicMock()
        mock_celery.id = "celery-slides-001"

        with patch("app.agents.celery_app.process_slides_task") as mock_sl:
            mock_sl.apply_async = MagicMock(return_value=mock_celery)
            resp = await async_client.post(f"/api/v1/r/{task.share_token}/try")

        assert resp.status_code == 202
        assert resp.json()["task_type"] == "slides"

    @pytest.mark.asyncio
    async def test_invalid_uuid_returns_404(self, async_client: AsyncClient):
        resp = await async_client.post("/api/v1/r/not-a-uuid/try")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_nonexistent_token_returns_404(self, async_client: AsyncClient):
        fake = uuid4()
        resp = await async_client.post(f"/api/v1/r/{fake}/try")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_expired_link_returns_410(self, async_client: AsyncClient, db):
        user = await _make_user(db)
        task = await _make_shared_task(
            db, user,
            expires_at=datetime.now(tz=timezone.utc) - timedelta(hours=1),
        )
        resp = await async_client.post(f"/api/v1/r/{task.share_token}/try")
        assert resp.status_code == 410

    @pytest.mark.asyncio
    async def test_celery_failure_still_returns_202(self, async_client: AsyncClient, db):
        """If Celery dispatch fails, endpoint still returns 202 (task recorded as failed)."""
        user = await _make_user(db)
        task = await _make_shared_task(db, user)

        with patch("app.agents.celery_app.process_docs_task") as mock_docs:
            mock_docs.apply_async = MagicMock(side_effect=ConnectionError("Redis down"))
            resp = await async_client.post(f"/api/v1/r/{task.share_token}/try")

        assert resp.status_code == 202


class TestMagicLinkRateLimit:
    """IP-based rate limiting for guest access."""

    @pytest.mark.asyncio
    async def test_rate_limit_after_max_tries(self, async_client: AsyncClient, db):
        """After ANONYMOUS_MAX_TRIES_PER_IP tries, returns 429."""
        user = await _make_user(db)
        task = await _make_shared_task(db, user)

        mock_celery = MagicMock()
        mock_celery.id = "celery-rl"

        # Provide an in-memory store so that the cache-backed rate limiter
        # actually increments between requests (no Redis in tests).
        _mem: dict[str, Any] = {}

        async def _fake_get(key: str):
            return _mem.get(key)

        async def _fake_set(key: str, value, ttl=None):
            _mem[key] = value
            return True

        with (
            patch("app.agents.celery_app.process_docs_task") as mock_docs,
            patch.object(cache, "get", side_effect=_fake_get),
            patch.object(cache, "set", side_effect=_fake_set),
        ):
            mock_docs.apply_async = MagicMock(return_value=mock_celery)

            # Use 3 tries (default max)
            for i in range(3):
                r = await async_client.post(f"/api/v1/r/{task.share_token}/try")
                assert r.status_code == 202, f"Try {i+1} failed: {r.text}"

            # 4th try should be rate limited
            r = await async_client.post(f"/api/v1/r/{task.share_token}/try")
            assert r.status_code == 429
            assert "Daily limit" in r.json()["detail"]
            assert "Sign up" in r.json()["detail"]


class TestMagicLinkConfig:
    """Configuration defaults."""

    def test_default_config_values(self):
        from app.core.config import Settings
        s = Settings()
        assert s.ANONYMOUS_MAX_TRIES_PER_IP == 3
        assert s.ANONYMOUS_DAILY_BUDGET_USD == 5.0
        assert s.ANONYMOUS_RESULT_TTL_SECONDS == 1800
