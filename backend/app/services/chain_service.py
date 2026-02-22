"""Service layer for Smart Task Chaining (#227).

Handles chain CRUD, execution orchestration, and output piping between steps.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.task import Task, TaskStatus, TaskType
from app.models.task_chain import (
    ChainStatus,
    ChainStep,
    StepStatus,
    TaskChain,
)
from app.schemas.chain import (
    ChainCreate,
    ChainStepUpdate,
    ChainUpdate,
)

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _render_prompt(template: str, previous_output: Optional[str]) -> str:
    """Replace {{previous_output}} placeholder with actual output."""
    if previous_output is None:
        # First step or no output — remove placeholder gracefully
        return template.replace("{{previous_output}}", "")
    return template.replace("{{previous_output}}", previous_output)


def _extract_output_summary(task: Task) -> str:
    """Extract a text summary from a completed task for piping to next step."""
    parts: list[str] = []

    if task.result:
        # Try common result keys
        for key in ("summary", "content", "text", "output", "data"):
            if key in task.result:
                val = task.result[key]
                if isinstance(val, str):
                    parts.append(val)
                else:
                    parts.append(json.dumps(val, ensure_ascii=False, default=str))
                break
        else:
            # Fallback: serialise the whole result
            parts.append(json.dumps(task.result, ensure_ascii=False, default=str))

    if task.document_url:
        parts.append(f"Document: {task.document_url}")

    return "\n".join(parts) if parts else "(no output)"


# ── CRUD ─────────────────────────────────────────────────────────────────────

async def create_chain(
    db: AsyncSession,
    user_id: UUID,
    data: ChainCreate,
) -> TaskChain:
    """Create a new task chain in DRAFT status."""
    chain = TaskChain(
        user_id=user_id,
        name=data.name,
        description=data.description,
        status=ChainStatus.DRAFT,
        chain_metadata=data.chain_metadata,
    )
    for idx, step_data in enumerate(data.steps):
        step = ChainStep(
            step_order=idx,
            prompt_template=step_data.prompt_template,
            task_type=step_data.task_type,
            status=StepStatus.PENDING,
            step_metadata=step_data.step_metadata,
        )
        chain.steps.append(step)
    db.add(chain)
    await db.flush()
    await db.refresh(chain, attribute_names=["steps"])
    return chain


async def get_chain(
    db: AsyncSession,
    chain_id: UUID,
    user_id: UUID,
) -> Optional[TaskChain]:
    """Fetch a chain with steps, belonging to user."""
    stmt = (
        select(TaskChain)
        .where(TaskChain.id == chain_id, TaskChain.user_id == user_id)
        .options(selectinload(TaskChain.steps))
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_chains(
    db: AsyncSession,
    user_id: UUID,
    *,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[TaskChain], int]:
    """List chains for a user with pagination."""
    count_stmt = (
        select(func.count())
        .select_from(TaskChain)
        .where(TaskChain.user_id == user_id)
    )
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(TaskChain)
        .where(TaskChain.user_id == user_id)
        .options(selectinload(TaskChain.steps))
        .order_by(TaskChain.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    chains = list(result.scalars().all())
    return chains, total


async def update_chain(
    db: AsyncSession,
    chain: TaskChain,
    data: ChainUpdate,
) -> TaskChain:
    """Update a DRAFT chain's metadata."""
    if chain.status != ChainStatus.DRAFT:
        raise ValueError("Only DRAFT chains can be edited")
    if data.name is not None:
        chain.name = data.name
    if data.description is not None:
        chain.description = data.description
    await db.flush()
    await db.refresh(chain, attribute_names=["steps"])
    return chain


async def delete_chain(db: AsyncSession, chain: TaskChain) -> None:
    """Delete a chain and its steps."""
    await db.delete(chain)
    await db.flush()


# ── Execution ────────────────────────────────────────────────────────────────

async def start_chain(
    db: AsyncSession,
    chain: TaskChain,
) -> TaskChain:
    """Start executing a chain from step 0 (or resume from current)."""
    if chain.status in (ChainStatus.COMPLETED, ChainStatus.CANCELLED):
        raise ValueError(f"Cannot start a {chain.status.value} chain")

    if chain.status == ChainStatus.DRAFT or chain.status == ChainStatus.PENDING:
        chain.status = ChainStatus.RUNNING
        chain.current_step_index = 0
        chain.started_at = datetime.now(timezone.utc)

    elif chain.status == ChainStatus.PAUSED:
        chain.status = ChainStatus.RUNNING

    elif chain.status == ChainStatus.FAILED:
        # Retry from the failed step
        chain.status = ChainStatus.RUNNING

    # Start the current step
    await _execute_current_step(db, chain)
    await db.flush()
    await db.refresh(chain, attribute_names=["steps"])
    return chain


async def advance_chain(
    db: AsyncSession,
    chain: TaskChain,
    completed_task: Task,
) -> TaskChain:
    """Called when a step's task completes. Advances the chain.

    This should be called by the task completion webhook/callback.
    """
    if chain.status != ChainStatus.RUNNING:
        return chain

    steps = sorted(chain.steps, key=lambda s: s.step_order)
    current_step = steps[chain.current_step_index]

    if completed_task.status == TaskStatus.FAILED:
        current_step.status = StepStatus.FAILED
        current_step.error_message = completed_task.error_message
        current_step.completed_at = datetime.now(timezone.utc)
        chain.status = ChainStatus.FAILED
        await db.flush()
        await db.refresh(chain, attribute_names=["steps"])
        return chain

    # Mark step as completed
    current_step.status = StepStatus.COMPLETED
    current_step.completed_at = datetime.now(timezone.utc)
    current_step.output_summary = _extract_output_summary(completed_task)

    # Move to next step
    next_index = chain.current_step_index + 1
    if next_index >= len(steps):
        # Chain complete!
        chain.status = ChainStatus.COMPLETED
        chain.completed_at = datetime.now(timezone.utc)
    else:
        chain.current_step_index = next_index
        await _execute_current_step(db, chain)

    await db.flush()
    await db.refresh(chain, attribute_names=["steps"])
    return chain


async def cancel_chain(
    db: AsyncSession,
    chain: TaskChain,
) -> TaskChain:
    """Cancel a running chain."""
    if chain.status in (ChainStatus.COMPLETED, ChainStatus.CANCELLED):
        raise ValueError(f"Cannot cancel a {chain.status.value} chain")
    chain.status = ChainStatus.CANCELLED

    # Mark pending steps as skipped
    for step in chain.steps:
        if step.status == StepStatus.PENDING:
            step.status = StepStatus.SKIPPED

    await db.flush()
    await db.refresh(chain, attribute_names=["steps"])
    return chain


# ── Internal step execution ──────────────────────────────────────────────────

async def _execute_current_step(
    db: AsyncSession,
    chain: TaskChain,
) -> None:
    """Create a Task for the current step and mark it as running."""
    steps = sorted(chain.steps, key=lambda s: s.step_order)
    step = steps[chain.current_step_index]

    # Get previous step's output (if any)
    previous_output: Optional[str] = None
    if chain.current_step_index > 0:
        prev_step = steps[chain.current_step_index - 1]
        previous_output = prev_step.output_summary

    # Render the prompt
    resolved = _render_prompt(step.prompt_template, previous_output)
    step.resolved_prompt = resolved
    step.status = StepStatus.RUNNING
    step.started_at = datetime.now(timezone.utc)

    # Create the actual task
    task = Task(
        user_id=chain.user_id,
        prompt=resolved,
        task_type=step.task_type,
        status=TaskStatus.PENDING,
        task_metadata={
            "chain_id": str(chain.id),
            "chain_step_id": str(step.id),
            "chain_step_order": step.step_order,
        },
    )
    db.add(task)
    await db.flush()
    step.task_id = task.id

    logger.info(
        "Chain %s step %d started → Task %s (%s)",
        chain.id,
        step.step_order,
        task.id,
        step.task_type.value,
    )
