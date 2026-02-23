"""Tests for Workspace Trust Ring dashboard endpoint (#259)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.task import Task, TaskStatus, TaskType
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import MemberRole, WorkspaceMember


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _user(email: str) -> User:
    return User(id=uuid4(), email=email, is_active=True)


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token({"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


async def _create_workspace(db: AsyncSession, owner: User, name: str = "Trust Ring") -> Workspace:
    workspace = Workspace(
        id=uuid4(),
        name=name,
        owner_id=owner.id,
        max_members=20,
    )
    db.add(workspace)

    db.add(
        WorkspaceMember(
            id=uuid4(),
            workspace_id=workspace.id,
            user_id=owner.id,
            role=MemberRole.OWNER.value,
        )
    )
    await db.flush()
    return workspace


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workspace_trust_ring_aggregates_multi_member_data(
    db: AsyncSession,
    async_client: AsyncClient,
):
    owner = _user("trust-owner@example.com")
    member = _user("trust-member@example.com")
    db.add_all([owner, member])

    workspace = await _create_workspace(db, owner)

    # Add a second member.
    db.add(
        WorkspaceMember(
            id=uuid4(),
            workspace_id=workspace.id,
            user_id=member.id,
            role=MemberRole.MEMBER.value,
        )
    )

    now = datetime.now(timezone.utc)

    # Owner tasks
    db.add(
        Task(
            id=uuid4(),
            user_id=owner.id,
            prompt="Completed research",
            task_type=TaskType.RESEARCH,
            status=TaskStatus.COMPLETED,
            created_at=now - timedelta(hours=2),
            completed_at=now - timedelta(hours=2) + timedelta(minutes=3),
        )
    )
    db.add(
        Task(
            id=uuid4(),
            user_id=owner.id,
            prompt="Failed research",
            task_type=TaskType.RESEARCH,
            status=TaskStatus.FAILED,
            error_message="Google API error: spreadsheet not found",
            created_at=now - timedelta(hours=1),
        )
    )

    # Member tasks
    db.add(
        Task(
            id=uuid4(),
            user_id=member.id,
            prompt="Member failed task",
            task_type=TaskType.SHEETS,
            status=TaskStatus.FAILED,
            error_message="Permission denied for spreadsheet",
            created_at=now - timedelta(minutes=90),
        )
    )
    db.add(
        Task(
            id=uuid4(),
            user_id=member.id,
            prompt="Pending sheets",
            task_type=TaskType.SHEETS,
            status=TaskStatus.PENDING,
            created_at=now - timedelta(minutes=20),
        )
    )

    await db.commit()

    response = await async_client.get(
        f"/api/v1/workspaces/{workspace.id}/trust-ring",
        headers=_auth_headers(owner),
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["workspace_id"] == str(workspace.id)
    assert payload["workspace_name"] == "Trust Ring"
    assert payload["total_tasks"] == 4
    assert payload["completed_tasks"] == 1
    assert payload["failed_tasks"] == 2
    assert payload["pending_tasks"] == 1
    assert payload["in_progress_tasks"] == 0
    assert payload["cancelled_tasks"] == 0
    assert payload["avg_completion_time_seconds"] > 0
    assert payload["trust_score"] < 100
    assert payload["stability_score"] <= 100
    assert payload["speed_score"] <= 100
    assert payload["repeatability_score"] <= 100

    assert set(payload["failure_categories"].keys()) == {"google_api", "permission"}
    assert len(payload["member_health"]) == 2
    by_email = {row["user_email"]: row for row in payload["member_health"]}
    assert by_email[owner.email]["completed_tasks"] == 1
    assert by_email[member.email]["failed_tasks"] == 1


@pytest.mark.asyncio
async def test_workspace_trust_ring_for_non_member_is_forbidden(
    db: AsyncSession,
    async_client: AsyncClient,
):
    owner = _user("owner-only@example.com")
    outsider = _user("outsider@example.com")
    db.add_all([owner, outsider])

    workspace = await _create_workspace(db, owner)
    await db.commit()

    response = await async_client.get(
        f"/api/v1/workspaces/{workspace.id}/trust-ring",
        headers=_auth_headers(outsider),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Not a member of this workspace"
