"""Test workspace task access control fixes."""

import pytest
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import MemberRole, WorkspaceMember
from app.models.task import Task, TaskStatus, TaskType
from app.api.v1.tasks import _get_task_with_access_check
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_get_task_with_access_check_owner(db: AsyncSession):
    """Test that task owner can access their own task."""
    
    # Create user and task
    user = User(
        email="owner@example.com",
        full_name="Owner",
        google_id="google_owner",
        is_active=True
    )
    
    db.add(user)
    await db.flush()
    
    task = Task(
        user_id=user.id,
        prompt="Test task",
        task_type=TaskType.DOCS,
        status=TaskStatus.PENDING
    )
    
    db.add(task)
    await db.commit()
    
    # Owner should be able to access
    result = await _get_task_with_access_check(task.id, user, db)
    assert result.id == task.id


@pytest.mark.asyncio
async def test_get_task_with_access_check_workspace_member(db: AsyncSession):
    """Test that workspace members can access tasks created by other members."""
    
    # Create two users
    user1 = User(
        email="user1@example.com",
        full_name="User One",
        google_id="google_user1",
        is_active=True
    )
    user2 = User(
        email="user2@example.com",
        full_name="User Two",
        google_id="google_user2",
        is_active=True
    )
    
    db.add(user1)
    db.add(user2)
    await db.flush()
    
    # Create workspace
    workspace = Workspace(
        name="Shared Workspace",
        description="Test workspace",
        owner_id=user1.id,
        max_members=10
    )
    
    db.add(workspace)
    await db.flush()
    
    # Add both users as members
    member1 = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=user1.id,
        role=MemberRole.OWNER.value
    )
    member2 = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=user2.id,
        role=MemberRole.MEMBER.value
    )
    
    db.add(member1)
    db.add(member2)
    await db.flush()
    
    # User1 creates a task in the workspace
    task = Task(
        user_id=user1.id,
        workspace_id=workspace.id,
        prompt="Workspace task",
        task_type=TaskType.SHEETS,
        status=TaskStatus.COMPLETED
    )
    
    db.add(task)
    await db.commit()
    
    # User2 (workspace member) should be able to access user1's task
    result = await _get_task_with_access_check(task.id, user2, db)
    assert result.id == task.id
    assert result.workspace_id == workspace.id


@pytest.mark.asyncio
async def test_get_task_with_access_check_non_member_denied(db: AsyncSession):
    """Test that non-workspace members cannot access workspace tasks."""
    
    # Create two users
    user1 = User(
        email="member@example.com",
        full_name="Member",
        google_id="google_member",
        is_active=True
    )
    user2 = User(
        email="outsider@example.com",
        full_name="Outsider",
        google_id="google_outsider",
        is_active=True
    )
    
    db.add(user1)
    db.add(user2)
    await db.flush()
    
    # Create workspace
    workspace = Workspace(
        name="Private Workspace",
        description="Test workspace",
        owner_id=user1.id,
        max_members=10
    )
    
    db.add(workspace)
    await db.flush()
    
    # Add only user1 as member
    member1 = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=user1.id,
        role=MemberRole.OWNER.value
    )
    
    db.add(member1)
    await db.flush()
    
    # User1 creates a task in the workspace
    task = Task(
        user_id=user1.id,
        workspace_id=workspace.id,
        prompt="Private workspace task",
        task_type=TaskType.SLIDES,
        status=TaskStatus.COMPLETED
    )
    
    db.add(task)
    await db.commit()
    
    # User2 (not a member) should NOT be able to access
    with pytest.raises(HTTPException) as exc_info:
        await _get_task_with_access_check(task.id, user2, db)
    
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_task_with_access_check_personal_task_isolation(db: AsyncSession):
    """Test that personal tasks (no workspace) are isolated to the owner."""
    
    # Create two users
    user1 = User(
        email="user1@example.com",
        full_name="User One",
        google_id="google_user1_iso",
        is_active=True
    )
    user2 = User(
        email="user2@example.com",
        full_name="User Two",
        google_id="google_user2_iso",
        is_active=True
    )
    
    db.add(user1)
    db.add(user2)
    await db.flush()
    
    # User1 creates a personal task (no workspace_id)
    task = Task(
        user_id=user1.id,
        workspace_id=None,
        prompt="Personal task",
        task_type=TaskType.DOCS,
        status=TaskStatus.PENDING
    )
    
    db.add(task)
    await db.commit()
    
    # User1 can access their own task
    result = await _get_task_with_access_check(task.id, user1, db)
    assert result.id == task.id
    
    # User2 cannot access user1's personal task
    with pytest.raises(HTTPException) as exc_info:
        await _get_task_with_access_check(task.id, user2, db)
    
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_task_with_access_check_nonexistent_task(db: AsyncSession):
    """Test that accessing a nonexistent task returns 404."""
    
    user = User(
        email="user@example.com",
        full_name="User",
        google_id="google_user_404",
        is_active=True
    )
    
    db.add(user)
    await db.commit()
    
    # Try to access a task that doesn't exist
    fake_task_id = uuid4()
    
    with pytest.raises(HTTPException) as exc_info:
        await _get_task_with_access_check(fake_task_id, user, db)
    
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_retry_task_preserves_workspace_id(db: AsyncSession):
    """Test that retrying a workspace task preserves workspace_id."""
    
    # Create user and workspace
    user = User(
        email="user@example.com",
        full_name="User",
        google_id="google_user_retry",
        is_active=True
    )
    
    db.add(user)
    await db.flush()
    
    workspace = Workspace(
        name="Test Workspace",
        description="Test",
        owner_id=user.id,
        max_members=10
    )
    
    db.add(workspace)
    await db.flush()
    
    member = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=user.id,
        role=MemberRole.OWNER.value
    )
    
    db.add(member)
    await db.flush()
    
    # Create a failed task with workspace_id
    original_task = Task(
        user_id=user.id,
        workspace_id=workspace.id,
        prompt="Test task",
        task_type=TaskType.DOCS,
        status=TaskStatus.FAILED,
        error_message="Test error"
    )
    
    db.add(original_task)
    await db.commit()
    
    # Import here to avoid circular import
    from app.api.v1.tasks import _build_task_kwargs
    from app.models.task import Task as TaskModel
    
    # Simulate retry logic
    retry_metadata = {"retry_depth": 1, "retry_of": str(original_task.id)}
    
    task_kwargs = _build_task_kwargs(
        user_id=user.id,
        prompt=original_task.prompt,
        task_type=original_task.task_type,
        metadata=retry_metadata,
        workspace_id=original_task.workspace_id,
    )
    
    retry_task_obj = TaskModel(**task_kwargs)
    db.add(retry_task_obj)
    await db.commit()
    await db.refresh(retry_task_obj)
    
    # Verify workspace_id is preserved
    assert retry_task_obj.workspace_id == workspace.id
    assert retry_task_obj.workspace_id == original_task.workspace_id
