"""Tests for #228 Quality Score Badge.

Covers:
- Auto-QA trigger on task completion (qa_auto service)
- QA badge rendering on share links (HTML + JSON)
- Edge cases: no text output, duplicate QA, low scores
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.qa_auto import _extract_text_from_result, auto_qa_on_completion
from app.api.v1.share import _qa_badge_html, _qa_json


# ---------------------------------------------------------------------------
# _extract_text_from_result
# ---------------------------------------------------------------------------

class TestExtractText:
    def test_none_result(self):
        assert _extract_text_from_result(None) is None

    def test_empty_dict(self):
        assert _extract_text_from_result({}) is None

    def test_content_key(self):
        assert _extract_text_from_result({"content": "Hello world"}) == "Hello world"

    def test_summary_key(self):
        assert _extract_text_from_result({"summary": "A summary"}) == "A summary"

    def test_text_key(self):
        assert _extract_text_from_result({"text": "Some text"}) == "Some text"

    def test_findings_list_strings(self):
        result = _extract_text_from_result({"findings": ["One", "Two"]})
        assert result == "One\n\nTwo"

    def test_findings_list_dicts(self):
        result = _extract_text_from_result({
            "findings": [{"content": "Finding A"}, {"text": "Finding B"}]
        })
        assert "Finding A" in result
        assert "Finding B" in result

    def test_priority_content_over_summary(self):
        result = _extract_text_from_result({"content": "Content", "summary": "Summary"})
        assert result == "Content"

    def test_whitespace_only_skipped(self):
        assert _extract_text_from_result({"content": "   "}) is None

    def test_non_dict(self):
        assert _extract_text_from_result("just a string") is None


# ---------------------------------------------------------------------------
# _qa_badge_html
# ---------------------------------------------------------------------------

class TestQaBadgeHtml:
    def test_none_returns_empty(self):
        assert _qa_badge_html(None) == ""

    def test_high_score_badge(self):
        qa = MagicMock()
        qa.overall_score = 92.5
        qa.get_grade.return_value = "A"
        qa.needs_improvement.return_value = False
        result = _qa_badge_html(qa)
        assert "qa-A" in result
        assert "92.5" in result
        assert "qa-tip" not in result

    def test_low_score_badge_with_tip(self):
        qa = MagicMock()
        qa.overall_score = 55.0
        qa.get_grade.return_value = "F"
        qa.needs_improvement.return_value = True
        qa.auto_fix_suggestions = {"suggestions": [
            {"suggestion": "Add source citations.", "category": "fact_check", "priority": "high"}
        ]}
        result = _qa_badge_html(qa)
        assert "qa-F" in result
        assert "55.0" in result
        assert "qa-tip" in result
        assert "Add source citations" in result

    def test_low_score_no_suggestions(self):
        qa = MagicMock()
        qa.overall_score = 60.0
        qa.get_grade.return_value = "D"
        qa.needs_improvement.return_value = True
        qa.auto_fix_suggestions = {}
        result = _qa_badge_html(qa)
        assert "qa-D" in result
        assert "qa-tip" in result
        assert "구조, 문법, 출처" in result  # fallback tip


# ---------------------------------------------------------------------------
# _qa_json
# ---------------------------------------------------------------------------

class TestQaJson:
    def test_none_returns_none(self):
        assert _qa_json(None) is None

    def test_serializes_scores(self):
        qa = MagicMock()
        qa.overall_score = 82.3
        qa.get_grade.return_value = "B"
        qa.grammar_score = 90.0
        qa.structure_score = 80.0
        qa.readability_score = 75.0
        qa.completeness_score = 85.0
        qa.fact_check_score = 70.0
        qa.confidence_level = "medium"
        result = _qa_json(qa)
        assert result["overall_score"] == 82.3
        assert result["grade"] == "B"
        assert result["scores"]["grammar"] == 90.0
        assert result["confidence"] == "medium"


# ---------------------------------------------------------------------------
# auto_qa_on_completion (async)
# ---------------------------------------------------------------------------

class TestAutoQaOnCompletion:
    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        return db

    @pytest.fixture
    def completed_task(self):
        task = MagicMock()
        task.id = uuid4()
        task.status = MagicMock()
        task.status.value = "completed"
        task.prompt = "Write a report about AI trends in 2026"
        task.task_type = MagicMock()
        task.task_type.value = "research"
        task.result = {
            "content": (
                "# AI Trends Report 2026\n\n"
                "## Introduction\n"
                "Artificial intelligence continues to evolve rapidly. "
                "This report covers the major trends.\n\n"
                "## Key Findings\n"
                "1. Large language models are becoming more efficient.\n"
                "2. Edge AI deployment is increasing.\n"
                "3. Multimodal AI is mainstream.\n\n"
                "## Conclusion\n"
                "The AI landscape in 2026 shows strong growth across all sectors."
            )
        }
        return task

    @pytest.mark.asyncio
    async def test_runs_qa_and_persists(self, mock_db, completed_task):
        """Auto-QA should run validation and add a QAResult to the DB."""
        task_id = completed_task.id

        # Mock DB: task lookup returns our task
        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = completed_task
        # Mock DB: no existing QA result
        qa_check_result = MagicMock()
        qa_check_result.scalar_one_or_none.return_value = None

        mock_db.execute = AsyncMock(side_effect=[task_result, qa_check_result])
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        result = await auto_qa_on_completion(mock_db, task_id)

        assert result is not None
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

        # Check the QAResult that was added
        added_row = mock_db.add.call_args[0][0]
        assert added_row.task_id == task_id
        assert added_row.overall_score > 0
        assert added_row.validator_version is not None

    @pytest.mark.asyncio
    async def test_skips_if_qa_exists(self, mock_db, completed_task):
        """Auto-QA should skip if the task already has a QA result."""
        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = completed_task
        existing_qa = MagicMock()
        existing_qa.scalar_one_or_none.return_value = uuid4()  # existing QA id

        mock_db.execute = AsyncMock(side_effect=[task_result, existing_qa])

        result = await auto_qa_on_completion(mock_db, completed_task.id)
        assert result is None
        mock_db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_if_no_text(self, mock_db, completed_task):
        """Auto-QA should skip if task has no meaningful text output."""
        completed_task.result = {"status": "ok"}  # no content/text/summary

        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = completed_task
        qa_check_result = MagicMock()
        qa_check_result.scalar_one_or_none.return_value = None

        mock_db.execute = AsyncMock(side_effect=[task_result, qa_check_result])

        result = await auto_qa_on_completion(mock_db, completed_task.id)
        assert result is None

    @pytest.mark.asyncio
    async def test_skips_failed_task(self, mock_db):
        """Auto-QA should skip tasks that aren't completed."""
        task = MagicMock()
        task.id = uuid4()
        task.status = MagicMock()
        task.status.value = "failed"

        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = task
        mock_db.execute = AsyncMock(return_value=task_result)

        result = await auto_qa_on_completion(mock_db, task.id)
        assert result is None

    @pytest.mark.asyncio
    async def test_swallows_exceptions(self, mock_db):
        """Auto-QA should never raise — errors are logged and swallowed."""
        mock_db.execute = AsyncMock(side_effect=RuntimeError("DB exploded"))
        result = await auto_qa_on_completion(mock_db, uuid4())
        assert result is None  # no exception raised

    @pytest.mark.asyncio
    async def test_skips_task_not_found(self, mock_db):
        """Auto-QA should handle missing task gracefully."""
        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=task_result)

        result = await auto_qa_on_completion(mock_db, uuid4())
        assert result is None


# ---------------------------------------------------------------------------
# Share endpoint integration — QA badge in HTML
# ---------------------------------------------------------------------------

class TestShareQaBadgeIntegration:
    """Test that share viewer includes QA badge when available."""

    def test_viewer_html_template_has_qa_placeholder(self):
        """The VIEWER_HTML template must contain {qa_badge} placeholder."""
        from app.api.v1.share import VIEWER_HTML
        assert "{qa_badge}" in VIEWER_HTML

    def test_badge_grades(self):
        """Each grade gets the correct CSS class."""
        for grade, score in [("A", 95), ("B", 85), ("C", 75), ("D", 65), ("F", 45)]:
            qa = MagicMock()
            qa.overall_score = score
            qa.get_grade.return_value = grade
            qa.needs_improvement.return_value = score < 70
            qa.auto_fix_suggestions = {}
            html = _qa_badge_html(qa)
            assert f"qa-{grade}" in html
