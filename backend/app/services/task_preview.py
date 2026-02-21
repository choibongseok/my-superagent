"""Interactive Task Preview (#234).

Generates a lightweight execution plan preview *before* running a task,
letting users confirm, modify, or cancel.  Saves API costs and avoids
re-executions caused by mismatched expectations.

Previews are stored in a TTL-bound in-memory cache (10 minutes) keyed by
a random preview_id.  A confirmed preview can be executed via the
``/tasks/preview/{preview_id}/execute`` endpoint.

Usage::

    from app.services.task_preview import TaskPreviewService

    svc = TaskPreviewService()
    preview = await svc.generate_preview("Create sales Q4 report", "docs")
    # preview.preview_id, preview.steps, preview.estimated_*
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

# Preview TTL in seconds (10 minutes)
_PREVIEW_TTL = 600

# In-memory preview store: {preview_id: (expires_at, PreviewResult)}
_preview_store: Dict[str, tuple[float, "PreviewResult"]] = {}


@dataclass
class PreviewStep:
    """A single planned step in the preview."""

    order: int
    description: str
    agent_type: str
    detail: str = ""


@dataclass
class PreviewResult:
    """Full preview result returned to the client."""

    preview_id: str
    prompt: str
    task_type: str
    steps: List[PreviewStep]
    output_format: str  # e.g. "Google Docs", "Google Sheets"
    estimated_time_seconds: int
    estimated_cost_usd: float
    estimated_tokens: int
    notes: List[str] = field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = None
    created_at: float = field(default_factory=time.time)
    smart: bool = False
    original_prompt: Optional[str] = None


# Agent-type to output format mapping
_OUTPUT_FORMATS = {
    "research": "Research Report (Markdown)",
    "docs": "Google Docs Document",
    "sheets": "Google Sheets Spreadsheet",
    "slides": "Google Slides Presentation",
}

# Base resource estimates per agent type
_TIME_BASE = {"research": 30, "docs": 20, "sheets": 15, "slides": 25}
_COST_BASE = {"research": 0.02, "docs": 0.03, "sheets": 0.02, "slides": 0.03}
_TOKEN_BASE = {"research": 2000, "docs": 3000, "sheets": 1500, "slides": 2500}


def _estimate_complexity(prompt: str) -> float:
    """Heuristic complexity multiplier based on prompt length and keywords."""
    words = len(prompt.split())
    if words > 100:
        multiplier = 1.5
    elif words > 40:
        multiplier = 1.2
    else:
        multiplier = 1.0

    # Boost for keywords suggesting more work
    complex_keywords = [
        "detailed", "comprehensive", "compare", "analyze", "multiple",
        "chart", "graph", "table", "sections", "chapters",
    ]
    keyword_hits = sum(1 for kw in complex_keywords if kw in prompt.lower())
    multiplier += keyword_hits * 0.1

    return min(multiplier, 2.0)


def _generate_steps(prompt: str, task_type: str, metadata: Optional[Dict[str, Any]]) -> List[PreviewStep]:
    """Generate deterministic preview steps based on task type and prompt analysis."""
    steps: List[PreviewStep] = []
    order = 1

    if task_type == "research":
        steps.append(PreviewStep(
            order=order, description="Search and gather relevant sources",
            agent_type="research", detail="Web search using provided query terms",
        ))
        order += 1
        steps.append(PreviewStep(
            order=order, description="Analyze and cross-reference sources",
            agent_type="research", detail="Extract key findings and verify facts",
        ))
        order += 1
        steps.append(PreviewStep(
            order=order, description="Compile research report with citations",
            agent_type="research", detail="Structured report with APA-style citations",
        ))

    elif task_type == "docs":
        title = "document"
        if metadata and isinstance(metadata, dict):
            title = metadata.get("title", metadata.get("document_title", "document"))
        steps.append(PreviewStep(
            order=order, description=f'Create document structure for "{title}"',
            agent_type="docs", detail="Outline sections based on prompt",
        ))
        order += 1
        steps.append(PreviewStep(
            order=order, description="Generate content for each section",
            agent_type="docs", detail="AI-written content following specified tone and style",
        ))
        order += 1
        steps.append(PreviewStep(
            order=order, description="Format and finalize Google Docs document",
            agent_type="docs", detail="Apply formatting, headings, and layout",
        ))

    elif task_type == "sheets":
        title = "spreadsheet"
        if metadata and isinstance(metadata, dict):
            title = metadata.get("title", metadata.get("sheet_title", "spreadsheet"))
        steps.append(PreviewStep(
            order=order, description=f'Design data structure for "{title}"',
            agent_type="sheets", detail="Define columns, data types, and layout",
        ))
        order += 1
        steps.append(PreviewStep(
            order=order, description="Populate spreadsheet with data",
            agent_type="sheets", detail="Fill cells with generated or extracted data",
        ))
        order += 1

        # Add chart step if prompt mentions visualization
        viz_keywords = ["chart", "graph", "visual", "plot", "diagram"]
        if any(kw in prompt.lower() for kw in viz_keywords):
            steps.append(PreviewStep(
                order=order, description="Add charts and visualizations",
                agent_type="sheets", detail="Create charts based on data patterns",
            ))
            order += 1

        steps.append(PreviewStep(
            order=order, description="Format and finalize Google Sheets",
            agent_type="sheets", detail="Apply cell formatting, borders, and conditional rules",
        ))

    elif task_type == "slides":
        title = "presentation"
        if metadata and isinstance(metadata, dict):
            title = metadata.get("title", metadata.get("deck_title", "presentation"))
        steps.append(PreviewStep(
            order=order, description=f'Plan slide outline for "{title}"',
            agent_type="slides", detail="Determine slide count and structure",
        ))
        order += 1
        steps.append(PreviewStep(
            order=order, description="Generate slide content",
            agent_type="slides", detail="Create text, bullet points, and speaker notes",
        ))
        order += 1
        steps.append(PreviewStep(
            order=order, description="Apply design and layout",
            agent_type="slides", detail="Choose theme, add visual elements, format text",
        ))

    return steps


def _generate_notes(prompt: str, task_type: str) -> List[str]:
    """Generate helpful notes/warnings for the preview."""
    notes: List[str] = []

    if len(prompt.split()) < 10:
        notes.append("💡 Tip: A more detailed prompt will produce better results.")

    if task_type == "research":
        notes.append("🔍 Sources will be automatically cited in APA format.")
    elif task_type == "docs":
        notes.append("📝 The document will be created in your Google Drive.")
    elif task_type == "sheets":
        notes.append("📊 The spreadsheet will be created in your Google Drive.")
    elif task_type == "slides":
        notes.append("🎨 The presentation will be created in your Google Drive.")

    if len(prompt.split()) > 80:
        notes.append("⚡ Complex prompt detected — execution may take longer than estimated.")

    return notes


class TaskPreviewService:
    """Generate and manage task execution previews."""

    def generate_preview(
        self,
        prompt: str,
        task_type: str,
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
    ) -> PreviewResult:
        """Generate a preview for the given task without executing it.

        This is intentionally synchronous and fast — no LLM calls.
        Uses heuristic analysis of the prompt to produce a deterministic
        preview plan.
        """
        self._evict_expired()

        complexity = _estimate_complexity(prompt)
        steps = _generate_steps(prompt, task_type, metadata)
        notes = _generate_notes(prompt, task_type)

        base_time = _TIME_BASE.get(task_type, 30)
        base_cost = _COST_BASE.get(task_type, 0.02)
        base_tokens = _TOKEN_BASE.get(task_type, 2000)

        # Scale by number of steps and complexity
        step_count = len(steps)
        estimated_time = int(base_time * complexity * max(step_count / 3, 1))
        estimated_cost = round(base_cost * complexity * max(step_count / 3, 1), 4)
        estimated_tokens = int(base_tokens * complexity * max(step_count / 3, 1))

        preview = PreviewResult(
            preview_id=str(uuid4()),
            prompt=prompt,
            task_type=task_type,
            steps=steps,
            output_format=_OUTPUT_FORMATS.get(task_type, "Unknown"),
            estimated_time_seconds=estimated_time,
            estimated_cost_usd=estimated_cost,
            estimated_tokens=estimated_tokens,
            notes=notes,
            metadata=metadata,
        )

        # Cache the preview
        expires_at = time.time() + _PREVIEW_TTL
        _preview_store[preview.preview_id] = (expires_at, preview)

        logger.info(
            "Preview generated: %s (%s, %d steps, ~%ds, ~$%.4f)",
            preview.preview_id,
            task_type,
            step_count,
            estimated_time,
            estimated_cost,
        )

        return preview

    def get_preview(self, preview_id: str) -> Optional[PreviewResult]:
        """Retrieve a cached preview by ID, or None if expired/missing."""
        self._evict_expired()
        entry = _preview_store.get(preview_id)
        if entry is None:
            return None
        expires_at, preview = entry
        if time.time() > expires_at:
            _preview_store.pop(preview_id, None)
            return None
        return preview

    def consume_preview(self, preview_id: str) -> Optional[PreviewResult]:
        """Retrieve and remove a cached preview (single-use execution)."""
        self._evict_expired()
        entry = _preview_store.pop(preview_id, None)
        if entry is None:
            return None
        expires_at, preview = entry
        if time.time() > expires_at:
            return None
        return preview

    @staticmethod
    def _evict_expired() -> None:
        """Remove expired entries from the preview store."""
        now = time.time()
        expired_keys = [
            key for key, (expires_at, _) in _preview_store.items()
            if now > expires_at
        ]
        for key in expired_keys:
            _preview_store.pop(key, None)

    async def generate_smart_preview(
        self,
        prompt: str,
        task_type: str,
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        llm_caller: Optional[Callable] = None,
    ) -> PreviewResult:
        """Generate a preview using an LLM for contextual step descriptions.

        Falls back to heuristic preview if the LLM call fails.

        Parameters
        ----------
        llm_caller:
            An async callable ``(system_prompt, user_prompt) -> str`` that
            wraps the actual LLM invocation.  Injected to keep this service
            independent of LangChain imports.  When *None*, falls back to
            heuristic generation.
        """
        self._evict_expired()

        if llm_caller is None:
            logger.info("No llm_caller provided for smart preview — falling back to heuristic")
            result = self.generate_preview(prompt, task_type, metadata, user_id)
            result.smart = False
            return result

        system_prompt = (
            "You are a task planning assistant. Given a user request and task type, "
            "generate an execution plan as a JSON array of steps.\n\n"
            "Each step must have: order (int), description (string), agent_type (string), "
            "detail (string with specifics).\n\n"
            "Also include: estimated_time_seconds (int), estimated_tokens (int), "
            "notes (array of helpful tips).\n\n"
            "Return ONLY valid JSON with keys: steps, estimated_time_seconds, "
            "estimated_tokens, notes."
        )
        user_prompt = (
            f"Task type: {task_type}\n"
            f"User request: {prompt}\n"
            f"Metadata: {json.dumps(metadata) if metadata else 'none'}\n\n"
            "Generate a detailed execution plan."
        )

        try:
            raw = await llm_caller(system_prompt, user_prompt)
            plan = _parse_llm_plan(raw, task_type)
        except Exception:
            logger.warning("Smart preview LLM call failed — falling back to heuristic", exc_info=True)
            result = self.generate_preview(prompt, task_type, metadata, user_id)
            result.smart = False
            return result

        complexity = _estimate_complexity(prompt)
        base_cost = _COST_BASE.get(task_type, 0.02)
        step_count = len(plan["steps"])

        preview = PreviewResult(
            preview_id=str(uuid4()),
            prompt=prompt,
            task_type=task_type,
            steps=plan["steps"],
            output_format=_OUTPUT_FORMATS.get(task_type, "Unknown"),
            estimated_time_seconds=plan.get("estimated_time_seconds", int(30 * complexity)),
            estimated_cost_usd=round(base_cost * complexity * max(step_count / 3, 1), 4),
            estimated_tokens=plan.get("estimated_tokens", int(2000 * complexity)),
            notes=plan.get("notes", []),
            metadata=metadata,
            smart=True,
        )

        expires_at = time.time() + _PREVIEW_TTL
        _preview_store[preview.preview_id] = (expires_at, preview)

        logger.info(
            "Smart preview generated: %s (%s, %d steps)",
            preview.preview_id, task_type, step_count,
        )
        return preview

    def modify_preview(
        self,
        preview_id: str,
        new_prompt: str,
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
    ) -> Optional[PreviewResult]:
        """Modify the prompt of an existing preview and regenerate (heuristic).

        Returns a new preview with the modified prompt and a reference to
        the original prompt.  The old preview is consumed.
        """
        old = self.consume_preview(preview_id)
        if old is None:
            return None

        new_preview = self.generate_preview(
            prompt=new_prompt,
            task_type=old.task_type,
            metadata=metadata if metadata is not None else old.metadata,
            user_id=user_id,
        )
        new_preview.original_prompt = old.prompt
        return new_preview

    async def modify_preview_smart(
        self,
        preview_id: str,
        new_prompt: str,
        llm_caller: Optional[Callable] = None,
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
    ) -> Optional[PreviewResult]:
        """Modify + regenerate using LLM-powered preview."""
        old = self.consume_preview(preview_id)
        if old is None:
            return None

        new_preview = await self.generate_smart_preview(
            prompt=new_prompt,
            task_type=old.task_type,
            metadata=metadata if metadata is not None else old.metadata,
            user_id=user_id,
            llm_caller=llm_caller,
        )
        new_preview.original_prompt = old.prompt
        return new_preview

    @staticmethod
    def clear_store() -> None:
        """Clear all previews (for testing)."""
        _preview_store.clear()


def _parse_llm_plan(raw: str, task_type: str) -> Dict[str, Any]:
    """Parse LLM response into a structured plan dict.

    Handles JSON possibly wrapped in markdown code fences.
    """
    # Strip markdown fences
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    data = json.loads(cleaned)

    steps: List[PreviewStep] = []
    for i, s in enumerate(data.get("steps", []), start=1):
        steps.append(PreviewStep(
            order=s.get("order", i),
            description=s.get("description", f"Step {i}"),
            agent_type=s.get("agent_type", task_type),
            detail=s.get("detail", ""),
        ))

    return {
        "steps": steps,
        "estimated_time_seconds": data.get("estimated_time_seconds"),
        "estimated_tokens": data.get("estimated_tokens"),
        "notes": data.get("notes", []),
    }
