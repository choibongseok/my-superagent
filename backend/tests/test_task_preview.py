"""Tests for #234 Interactive Task Preview.

Covers:
- Preview generation for all task types (docs, sheets, slides, research)
- Resource estimation (time, cost, tokens)
- Smart (LLM-powered) preview generation
- Prompt modification and re-preview
- LLM fallback to heuristic on failure
- Complexity scaling based on prompt length/keywords
- Preview caching, retrieval, expiry, and single-use consumption
- API endpoints: POST /preview, GET /preview/{id}, POST /preview/{id}/execute
- Notes generation (tips, warnings)
- Edge cases (unknown type, expired preview, double-execute)
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.services.task_preview import (
    PreviewResult,
    PreviewStep,
    TaskPreviewService,
    _estimate_complexity,
    _generate_notes,
    _generate_steps,
    _parse_llm_plan,
    _preview_store,
)


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def clear_preview_store():
    """Ensure clean preview store for each test."""
    _preview_store.clear()
    yield
    _preview_store.clear()


@pytest.fixture
def svc():
    return TaskPreviewService()


@pytest_asyncio.fixture
async def client(db):
    """Async HTTP client with DB override so routes see the test tables."""
    from app.main import app
    from app.core.database import get_db
    from tests.conftest import _override_get_db

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _make_user(db) -> "User":
    """Create and persist a test user, returning the instance."""
    from app.models.user import User

    user = User(
        id=uuid4(),
        email=f"test-{uuid4().hex[:8]}@example.com",
        full_name="Test User",
        google_id=f"g-{uuid4().hex[:8]}",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
def auth_headers():
    """Generate valid auth headers for testing."""
    from app.core.security import create_access_token

    token = create_access_token(data={"sub": str(uuid4())})
    return {"Authorization": f"Bearer {token}"}


# ── _estimate_complexity ──────────────────────────────────────────────


class TestEstimateComplexity:
    def test_short_prompt_base_multiplier(self):
        result = _estimate_complexity("Create a document")
        assert result == 1.0

    def test_medium_prompt_higher_multiplier(self):
        prompt = " ".join(["word"] * 50)
        result = _estimate_complexity(prompt)
        assert result == 1.2

    def test_long_prompt_highest_base(self):
        prompt = " ".join(["word"] * 120)
        result = _estimate_complexity(prompt)
        assert result >= 1.5

    def test_complex_keywords_boost(self):
        result = _estimate_complexity("Create a detailed comprehensive analysis with chart")
        assert result > 1.0  # keywords boost

    def test_max_cap_at_2(self):
        # Very long prompt + many keywords
        prompt = "detailed comprehensive compare analyze multiple chart graph table sections chapters " * 20
        result = _estimate_complexity(prompt)
        assert result <= 2.0


# ── _generate_steps ───────────────────────────────────────────────────


class TestGenerateSteps:
    def test_research_steps(self):
        steps = _generate_steps("AI trends", "research", None)
        assert len(steps) == 3
        assert steps[0].order == 1
        assert all(s.agent_type == "research" for s in steps)

    def test_docs_steps(self):
        steps = _generate_steps("Write report", "docs", {"title": "Q4 Report"})
        assert len(steps) == 3
        assert all(s.agent_type == "docs" for s in steps)
        assert "Q4 Report" in steps[0].description

    def test_sheets_steps_basic(self):
        steps = _generate_steps("Sales data", "sheets", None)
        assert len(steps) == 3  # no chart step
        assert all(s.agent_type == "sheets" for s in steps)

    def test_sheets_steps_with_chart(self):
        steps = _generate_steps("Sales data with chart visualization", "sheets", None)
        assert len(steps) == 4  # includes chart step
        chart_step = [s for s in steps if "chart" in s.description.lower()]
        assert len(chart_step) == 1

    def test_slides_steps(self):
        steps = _generate_steps("Quarterly review", "slides", {"title": "Q4 Deck"})
        assert len(steps) == 3
        assert all(s.agent_type == "slides" for s in steps)
        assert "Q4 Deck" in steps[0].description

    def test_steps_sequential_ordering(self):
        steps = _generate_steps("Test", "docs", None)
        orders = [s.order for s in steps]
        assert orders == sorted(orders)
        assert orders[0] == 1

    def test_unknown_type_returns_empty(self):
        steps = _generate_steps("Test", "unknown_type", None)
        assert steps == []


# ── _generate_notes ───────────────────────────────────────────────────


class TestGenerateNotes:
    def test_short_prompt_tip(self):
        notes = _generate_notes("Short", "docs")
        assert any("Tip" in n for n in notes)

    def test_long_prompt_complexity_warning(self):
        prompt = " ".join(["word"] * 100)
        notes = _generate_notes(prompt, "docs")
        assert any("Complex" in n or "longer" in n for n in notes)

    def test_research_citation_note(self):
        notes = _generate_notes("Research AI", "research")
        assert any("citation" in n.lower() or "cited" in n.lower() for n in notes)

    def test_docs_drive_note(self):
        notes = _generate_notes("Write a report about trends in AI and technology today", "docs")
        assert any("Google Drive" in n for n in notes)

    def test_sheets_drive_note(self):
        notes = _generate_notes("Create spreadsheet with columns for data analysis today", "sheets")
        assert any("Google Drive" in n for n in notes)

    def test_slides_drive_note(self):
        notes = _generate_notes("Create a presentation about quarterly sales and figures here", "slides")
        assert any("Google Drive" in n for n in notes)


# ── TaskPreviewService ────────────────────────────────────────────────


class TestTaskPreviewService:
    def test_generate_preview_docs(self, svc):
        preview = svc.generate_preview("Write a sales report", "docs")
        assert preview.preview_id
        assert preview.prompt == "Write a sales report"
        assert preview.task_type == "docs"
        assert len(preview.steps) > 0
        assert preview.output_format == "Google Docs Document"
        assert preview.estimated_time_seconds > 0
        assert preview.estimated_cost_usd > 0
        assert preview.estimated_tokens > 0

    def test_generate_preview_research(self, svc):
        preview = svc.generate_preview("AI ethics research", "research")
        assert preview.task_type == "research"
        assert preview.output_format == "Research Report (Markdown)"

    def test_generate_preview_sheets(self, svc):
        preview = svc.generate_preview("Budget spreadsheet", "sheets")
        assert preview.task_type == "sheets"
        assert preview.output_format == "Google Sheets Spreadsheet"

    def test_generate_preview_slides(self, svc):
        preview = svc.generate_preview("Team update deck", "slides")
        assert preview.task_type == "slides"
        assert preview.output_format == "Google Slides Presentation"

    def test_preview_cached(self, svc):
        preview = svc.generate_preview("Test", "docs")
        assert preview.preview_id in _preview_store

    def test_get_preview_returns_cached(self, svc):
        preview = svc.generate_preview("Test", "docs")
        retrieved = svc.get_preview(preview.preview_id)
        assert retrieved is not None
        assert retrieved.preview_id == preview.preview_id

    def test_get_preview_returns_none_for_unknown(self, svc):
        assert svc.get_preview("nonexistent-id") is None

    def test_consume_preview_removes_from_cache(self, svc):
        preview = svc.generate_preview("Test", "docs")
        pid = preview.preview_id
        consumed = svc.consume_preview(pid)
        assert consumed is not None
        assert consumed.preview_id == pid
        # Second consume should fail
        assert svc.consume_preview(pid) is None
        assert svc.get_preview(pid) is None

    def test_consume_nonexistent_returns_none(self, svc):
        assert svc.consume_preview("nope") is None

    def test_expired_preview_not_returned(self, svc):
        preview = svc.generate_preview("Test", "docs")
        pid = preview.preview_id
        # Manually expire
        expires_at, pv = _preview_store[pid]
        _preview_store[pid] = (time.time() - 1, pv)
        assert svc.get_preview(pid) is None

    def test_expired_preview_not_consumed(self, svc):
        preview = svc.generate_preview("Test", "docs")
        pid = preview.preview_id
        expires_at, pv = _preview_store[pid]
        _preview_store[pid] = (time.time() - 1, pv)
        assert svc.consume_preview(pid) is None

    def test_metadata_passed_through(self, svc):
        meta = {"title": "My Report"}
        preview = svc.generate_preview("Test", "docs", metadata=meta)
        assert preview.metadata == meta

    def test_complexity_affects_estimates(self, svc):
        simple = svc.generate_preview("Short task", "docs")
        complex_prompt = "Create a detailed comprehensive analysis comparing multiple data sources with charts and tables across sections"
        complex_ = svc.generate_preview(complex_prompt, "docs")
        assert complex_.estimated_time_seconds >= simple.estimated_time_seconds
        assert complex_.estimated_cost_usd >= simple.estimated_cost_usd

    def test_clear_store(self, svc):
        svc.generate_preview("Test", "docs")
        assert len(_preview_store) > 0
        TaskPreviewService.clear_store()
        assert len(_preview_store) == 0


# ── API Endpoints ─────────────────────────────────────────────────────


class TestPreviewEndpoints:

    @staticmethod
    async def _auth_headers(db):
        from app.core.security import create_access_token
        user = await _make_user(db)
        token = create_access_token(data={"sub": str(user.id)})
        return {"Authorization": f"Bearer {token}"}

    @pytest.mark.asyncio
    async def test_post_preview(self, client, db):
        headers = await self._auth_headers(db)
        resp = await client.post(
            "/api/v1/tasks/preview",
            json={"prompt": "Write quarterly report", "task_type": "docs"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "preview_id" in data
        assert data["task_type"] == "docs"
        assert data["output_format"] == "Google Docs Document"
        assert len(data["steps"]) > 0
        assert data["estimated_time_seconds"] > 0

    @pytest.mark.asyncio
    async def test_post_preview_research(self, client, db):
        headers = await self._auth_headers(db)
        resp = await client.post(
            "/api/v1/tasks/preview",
            json={"prompt": "Research renewable energy trends globally", "task_type": "research"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_type"] == "research"

    @pytest.mark.asyncio
    async def test_post_preview_with_metadata(self, client, db):
        headers = await self._auth_headers(db)
        resp = await client.post(
            "/api/v1/tasks/preview",
            json={
                "prompt": "Create budget tracking sheet",
                "task_type": "sheets",
                "metadata": {"title": "2026 Budget"},
            },
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["metadata"] == {"title": "2026 Budget"}

    @pytest.mark.asyncio
    async def test_get_preview_by_id(self, client, db):
        headers = await self._auth_headers(db)
        # Generate
        resp = await client.post(
            "/api/v1/tasks/preview",
            json={"prompt": "Test task", "task_type": "docs"},
            headers=headers,
        )
        preview_id = resp.json()["preview_id"]

        # Retrieve
        resp2 = await client.get(
            f"/api/v1/tasks/preview/{preview_id}",
            headers=headers,
        )
        assert resp2.status_code == 200
        assert resp2.json()["preview_id"] == preview_id

    @pytest.mark.asyncio
    async def test_get_preview_not_found(self, client, db):
        headers = await self._auth_headers(db)
        resp = await client.get(
            "/api/v1/tasks/preview/nonexistent-id",
            headers=headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_execute_preview_creates_task(self, client, db):
        headers = await self._auth_headers(db)
        # Generate preview
        resp = await client.post(
            "/api/v1/tasks/preview",
            json={"prompt": "Write a report", "task_type": "docs"},
            headers=headers,
        )
        preview_id = resp.json()["preview_id"]

        # Execute preview — Celery will fail (not running), task should still be created
        resp2 = await client.post(
            f"/api/v1/tasks/preview/{preview_id}/execute",
            headers=headers,
        )
        assert resp2.status_code == 201
        data = resp2.json()
        assert "id" in data
        assert data["prompt"] == "Write a report"

    @pytest.mark.asyncio
    async def test_execute_preview_single_use(self, client, db):
        headers = await self._auth_headers(db)
        # Generate
        resp = await client.post(
            "/api/v1/tasks/preview",
            json={"prompt": "Test", "task_type": "docs"},
            headers=headers,
        )
        preview_id = resp.json()["preview_id"]

        # First execute
        resp2 = await client.post(
            f"/api/v1/tasks/preview/{preview_id}/execute",
            headers=headers,
        )
        assert resp2.status_code == 201

        # Second execute should fail
        resp3 = await client.post(
            f"/api/v1/tasks/preview/{preview_id}/execute",
            headers=headers,
        )
        assert resp3.status_code == 404

    @pytest.mark.asyncio
    async def test_execute_nonexistent_preview(self, client, db):
        headers = await self._auth_headers(db)
        resp = await client.post(
            "/api/v1/tasks/preview/does-not-exist/execute",
            headers=headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_preview_requires_auth(self, client):
        resp = await client.post(
            "/api/v1/tasks/preview",
            json={"prompt": "Test", "task_type": "docs"},
        )
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_preview_validates_prompt(self, client, db):
        headers = await self._auth_headers(db)
        resp = await client.post(
            "/api/v1/tasks/preview",
            json={"prompt": "", "task_type": "docs"},
            headers=headers,
        )
        assert resp.status_code == 422  # validation error

    @pytest.mark.asyncio
    async def test_preview_all_task_types(self, client, db):
        headers = await self._auth_headers(db)
        for task_type in ["research", "docs", "sheets", "slides"]:
            resp = await client.post(
                "/api/v1/tasks/preview",
                json={"prompt": f"Test {task_type} preview", "task_type": task_type},
                headers=headers,
            )
            assert resp.status_code == 200, f"Failed for task_type={task_type}"
            data = resp.json()
            assert data["task_type"] == task_type
            assert len(data["steps"]) >= 1


# ── Smart Preview Tests ──────────────────────────────────────────────


class TestParseLLMPlan:
    """Tests for _parse_llm_plan helper."""

    def test_parse_valid_json(self):
        raw = '{"steps": [{"order": 1, "description": "Research", "agent_type": "research", "detail": "Search web"}], "estimated_time_seconds": 45, "estimated_tokens": 3000, "notes": ["Tip: be specific"]}'
        result = _parse_llm_plan(raw, "research")
        assert len(result["steps"]) == 1
        assert result["steps"][0].description == "Research"
        assert result["estimated_time_seconds"] == 45
        assert result["notes"] == ["Tip: be specific"]

    def test_parse_json_with_markdown_fences(self):
        raw = '```json\n{"steps": [{"order": 1, "description": "Step one", "agent_type": "docs"}]}\n```'
        result = _parse_llm_plan(raw, "docs")
        assert len(result["steps"]) == 1
        assert result["steps"][0].description == "Step one"

    def test_parse_missing_fields_uses_defaults(self):
        raw = '{"steps": [{}]}'
        result = _parse_llm_plan(raw, "sheets")
        assert len(result["steps"]) == 1
        assert result["steps"][0].order == 1
        assert result["steps"][0].description == "Step 1"
        assert result["steps"][0].agent_type == "sheets"

    def test_parse_empty_steps(self):
        raw = '{"steps": []}'
        result = _parse_llm_plan(raw, "docs")
        assert result["steps"] == []

    def test_parse_invalid_json_raises(self):
        with pytest.raises(Exception):
            _parse_llm_plan("not json at all", "docs")


class TestSmartPreview:
    """Tests for LLM-powered smart preview generation."""

    @pytest.fixture(autouse=True)
    def _clear(self):
        TaskPreviewService.clear_store()
        yield
        TaskPreviewService.clear_store()

    @pytest.mark.asyncio
    async def test_smart_preview_with_llm(self):
        svc = TaskPreviewService()

        async def mock_llm(system_prompt, user_prompt):
            return '{"steps": [{"order": 1, "description": "Analyze sales data", "agent_type": "sheets", "detail": "Parse Q4 numbers"}], "estimated_time_seconds": 20, "estimated_tokens": 1500, "notes": ["Focus on Q4"]}'

        result = await svc.generate_smart_preview(
            prompt="Create Q4 sales report",
            task_type="sheets",
            llm_caller=mock_llm,
        )
        assert result.smart is True
        assert len(result.steps) == 1
        assert result.steps[0].description == "Analyze sales data"
        assert result.estimated_time_seconds == 20
        assert result.notes == ["Focus on Q4"]

    @pytest.mark.asyncio
    async def test_smart_preview_fallback_on_no_caller(self):
        svc = TaskPreviewService()
        result = await svc.generate_smart_preview(
            prompt="Create a doc",
            task_type="docs",
            llm_caller=None,
        )
        assert result.smart is False
        assert len(result.steps) >= 1

    @pytest.mark.asyncio
    async def test_smart_preview_fallback_on_llm_error(self):
        svc = TaskPreviewService()

        async def bad_llm(system_prompt, user_prompt):
            raise RuntimeError("API down")

        result = await svc.generate_smart_preview(
            prompt="Create a doc",
            task_type="docs",
            llm_caller=bad_llm,
        )
        assert result.smart is False
        assert len(result.steps) >= 1

    @pytest.mark.asyncio
    async def test_smart_preview_fallback_on_bad_json(self):
        svc = TaskPreviewService()

        async def bad_json_llm(system_prompt, user_prompt):
            return "I can't generate JSON right now, sorry!"

        result = await svc.generate_smart_preview(
            prompt="Create a doc",
            task_type="docs",
            llm_caller=bad_json_llm,
        )
        assert result.smart is False

    @pytest.mark.asyncio
    async def test_smart_preview_cached(self):
        svc = TaskPreviewService()

        async def mock_llm(system_prompt, user_prompt):
            return '{"steps": [{"order": 1, "description": "Do it", "agent_type": "docs"}]}'

        result = await svc.generate_smart_preview("Test", "docs", llm_caller=mock_llm)
        retrieved = svc.get_preview(result.preview_id)
        assert retrieved is not None
        assert retrieved.smart is True


class TestModifyPreview:
    """Tests for preview prompt modification."""

    @pytest.fixture(autouse=True)
    def _clear(self):
        TaskPreviewService.clear_store()
        yield
        TaskPreviewService.clear_store()

    def test_modify_preview_heuristic(self):
        svc = TaskPreviewService()
        original = svc.generate_preview("Create a doc about cats", "docs")
        old_id = original.preview_id

        modified = svc.modify_preview(old_id, "Create a doc about dogs")
        assert modified is not None
        assert modified.prompt == "Create a doc about dogs"
        assert modified.original_prompt == "Create a doc about cats"
        assert modified.preview_id != old_id

        # Old preview consumed
        assert svc.get_preview(old_id) is None

    def test_modify_nonexistent_preview(self):
        svc = TaskPreviewService()
        result = svc.modify_preview("nonexistent-id", "New prompt")
        assert result is None

    def test_modify_preserves_task_type(self):
        svc = TaskPreviewService()
        original = svc.generate_preview("Research AI trends", "research")
        modified = svc.modify_preview(original.preview_id, "Research ML trends")
        assert modified.task_type == "research"

    def test_modify_with_new_metadata(self):
        svc = TaskPreviewService()
        original = svc.generate_preview("Create doc", "docs", metadata={"title": "Old"})
        modified = svc.modify_preview(
            original.preview_id, "Create doc v2",
            metadata={"title": "New"},
        )
        assert modified.metadata == {"title": "New"}

    @pytest.mark.asyncio
    async def test_modify_preview_smart(self):
        svc = TaskPreviewService()
        original = svc.generate_preview("Create a doc about cats", "docs")

        async def mock_llm(system_prompt, user_prompt):
            return '{"steps": [{"order": 1, "description": "Write about dogs", "agent_type": "docs", "detail": "Canine content"}]}'

        modified = await svc.modify_preview_smart(
            original.preview_id, "Create a doc about dogs",
            llm_caller=mock_llm,
        )
        assert modified is not None
        assert modified.smart is True
        assert modified.original_prompt == "Create a doc about cats"
        assert modified.steps[0].description == "Write about dogs"

    @pytest.mark.asyncio
    async def test_modify_smart_nonexistent(self):
        svc = TaskPreviewService()
        result = await svc.modify_preview_smart("nope", "New prompt")
        assert result is None


class TestPreviewAPIEnhancements:
    """Tests for the enhanced preview API endpoints (smart + modify)."""

    @staticmethod
    async def _auth_headers(db):
        """Create a test user and return auth headers."""
        from app.core.security import create_access_token
        user = await _make_user(db)
        token = create_access_token(data={"sub": str(user.id)})
        return {"Authorization": f"Bearer {token}"}

    @pytest.mark.asyncio
    async def test_preview_smart_flag_in_response(self, client, db):
        headers = await self._auth_headers(db)
        # Default (non-smart) preview
        resp = await client.post(
            "/api/v1/tasks/preview",
            json={"prompt": "Test doc", "task_type": "docs"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["smart"] is False
        assert data["original_prompt"] is None

    @pytest.mark.asyncio
    async def test_modify_preview_endpoint(self, client, db):
        headers = await self._auth_headers(db)

        # Create a preview first
        resp = await client.post(
            "/api/v1/tasks/preview",
            json={"prompt": "Original prompt", "task_type": "docs"},
            headers=headers,
        )
        assert resp.status_code == 200
        preview_id = resp.json()["preview_id"]

        # Modify it
        resp2 = await client.put(
            f"/api/v1/tasks/preview/{preview_id}",
            json={"prompt": "Modified prompt"},
            headers=headers,
        )
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["prompt"] == "Modified prompt"
        assert data["original_prompt"] == "Original prompt"
        assert data["preview_id"] != preview_id

    @pytest.mark.asyncio
    async def test_modify_expired_preview_404(self, client, db):
        headers = await self._auth_headers(db)
        resp = await client.put(
            "/api/v1/tasks/preview/nonexistent-id",
            json={"prompt": "Whatever"},
            headers=headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_modify_then_execute(self, client, db):
        headers = await self._auth_headers(db)

        # Create → modify → execute
        resp = await client.post(
            "/api/v1/tasks/preview",
            json={"prompt": "Original", "task_type": "research"},
            headers=headers,
        )
        pid1 = resp.json()["preview_id"]

        resp2 = await client.put(
            f"/api/v1/tasks/preview/{pid1}",
            json={"prompt": "Refined research query"},
            headers=headers,
        )
        pid2 = resp2.json()["preview_id"]

        # Execute the modified preview
        resp3 = await client.post(
            f"/api/v1/tasks/preview/{pid2}/execute",
            headers=headers,
        )
        assert resp3.status_code == 201
        task = resp3.json()
        assert task["prompt"] == "Refined research query"
