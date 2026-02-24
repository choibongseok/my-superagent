"""Multi-tenancy isolation tests for workspaces."""

import pytest
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import MemberRole, WorkspaceMember
from app.models.task import Task, TaskStatus, TaskType
from app.models.chat import Chat


@pytest.mark.asyncio
async def test_workspace_task_isolation(db: AsyncSession):
    """Test that tasks are isolated by workspace."""
    
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
    
    # Create two workspaces
    workspace1 = Workspace(
        name="Workspace 1",
        description="First workspace",
        owner_id=user1.id,
        max_members=10
    )
    workspace2 = Workspace(
        name="Workspace 2",
        description="Second workspace",
        owner_id=user2.id,
        max_members=10
    )
    
    db.add(workspace1)
    db.add(workspace2)
    await db.flush()
    
    # Add members
    member1 = WorkspaceMember(
        workspace_id=workspace1.id,
        user_id=user1.id,
        role=MemberRole.OWNER.value
    )
    member2 = WorkspaceMember(
        workspace_id=workspace2.id,
        user_id=user2.id,
        role=MemberRole.OWNER.value
    )
    
    db.add(member1)
    db.add(member2)
    await db.flush()
    
    # Create tasks in different workspaces
    task1 = Task(
        user_id=user1.id,
        workspace_id=workspace1.id,
        prompt="Task in workspace 1",
        task_type=TaskType.DOCS,
        status=TaskStatus.PENDING
    )
    task2 = Task(
        user_id=user2.id,
        workspace_id=workspace2.id,
        prompt="Task in workspace 2",
        task_type=TaskType.SHEETS,
        status=TaskStatus.PENDING
    )
    task3 = Task(
        user_id=user1.id,
        workspace_id=None,  # Personal task
        prompt="Personal task",
        task_type=TaskType.SLIDES,
        status=TaskStatus.PENDING
    )
    
    db.add(task1)
    db.add(task2)
    db.add(task3)
    await db.commit()
    
    # Query workspace 1 tasks
    result = await db.execute(
        select(Task).where(Task.workspace_id == workspace1.id)
    )
    workspace1_tasks = result.scalars().all()
    
    assert len(workspace1_tasks) == 1
    assert workspace1_tasks[0].id == task1.id
    
    # Query workspace 2 tasks
    result = await db.execute(
        select(Task).where(Task.workspace_id == workspace2.id)
    )
    workspace2_tasks = result.scalars().all()
    
    assert len(workspace2_tasks) == 1
    assert workspace2_tasks[0].id == task2.id
    
    # Query personal tasks (workspace_id is None)
    result = await db.execute(
        select(Task).where(Task.workspace_id.is_(None))
    )
    personal_tasks = result.scalars().all()
    
    assert len(personal_tasks) == 1
    assert personal_tasks[0].id == task3.id


@pytest.mark.asyncio
async def test_shared_workspace_tasks(db: AsyncSession):
    """Test that workspace members can access shared tasks."""
    
    # Create two users
    user1 = User(
        email="owner@example.com",
        full_name="Owner",
        google_id="google_owner",
        is_active=True
    )
    user2 = User(
        email="member@example.com",
        full_name="Member",
        google_id="google_member",
        is_active=True
    )
    
    db.add(user1)
    db.add(user2)
    await db.flush()
    
    # Create workspace
    workspace = Workspace(
        name="Shared Workspace",
        description="Collaborative workspace",
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
    
    # Create tasks by different users in the same workspace
    task1 = Task(
        user_id=user1.id,
        workspace_id=workspace.id,
        prompt="Task by owner",
        task_type=TaskType.DOCS,
        status=TaskStatus.COMPLETED
    )
    task2 = Task(
        user_id=user2.id,
        workspace_id=workspace.id,
        prompt="Task by member",
        task_type=TaskType.SHEETS,
        status=TaskStatus.COMPLETED
    )
    
    db.add(task1)
    db.add(task2)
    await db.commit()
    
    # Query all workspace tasks
    result = await db.execute(
        select(Task).where(Task.workspace_id == workspace.id)
    )
    workspace_tasks = result.scalars().all()
    
    assert len(workspace_tasks) == 2
    
    # Verify members can see all workspace tasks
    result = await db.execute(
        select(WorkspaceMember.user_id)
        .where(WorkspaceMember.workspace_id == workspace.id)
    )
    member_ids = [row[0] for row in result.all()]
    
    assert user1.id in member_ids
    assert user2.id in member_ids


@pytest.mark.asyncio
async def test_workspace_chat_isolation(db: AsyncSession):
    """Test that chats are isolated by workspace."""
    
    # Create user
    user = User(
        email="chatuser@example.com",
        full_name="Chat User",
        google_id="google_chatuser",
        is_active=True
    )
    
    db.add(user)
    await db.flush()
    
    # Create workspace
    workspace = Workspace(
        name="Chat Workspace",
        description="Workspace for chats",
        owner_id=user.id,
        max_members=10
    )
    
    db.add(workspace)
    await db.flush()
    
    # Create chats
    chat1 = Chat(
        title="Workspace Chat",
        user_id=user.id,
        workspace_id=workspace.id
    )
    chat2 = Chat(
        title="Personal Chat",
        user_id=user.id,
        workspace_id=None
    )
    
    db.add(chat1)
    db.add(chat2)
    await db.commit()
    
    # Query workspace chats
    result = await db.execute(
        select(Chat).where(Chat.workspace_id == workspace.id)
    )
    workspace_chats = result.scalars().all()
    
    assert len(workspace_chats) == 1
    assert workspace_chats[0].title == "Workspace Chat"
    
    # Query personal chats
    result = await db.execute(
        select(Chat).where(Chat.workspace_id.is_(None))
    )
    personal_chats = result.scalars().all()
    
    assert len(personal_chats) == 1
    assert personal_chats[0].title == "Personal Chat"


@pytest.mark.asyncio
async def test_workspace_member_permissions(db: AsyncSession):
    """Test workspace member permission hierarchy."""
    
    # Create user
    user = User(
        email="permuser@example.com",
        full_name="Permission User",
        google_id="google_permuser",
        is_active=True
    )
    
    db.add(user)
    await db.flush()
    
    # Create workspace
    workspace = Workspace(
        name="Permission Workspace",
        description="Testing permissions",
        owner_id=user.id,
        max_members=10
    )
    
    db.add(workspace)
    await db.flush()
    
    # Test different roles
    roles = [
        (MemberRole.OWNER, MemberRole.ADMIN, True),
        (MemberRole.OWNER, MemberRole.MEMBER, True),
        (MemberRole.ADMIN, MemberRole.OWNER, False),
        (MemberRole.ADMIN, MemberRole.MEMBER, True),
        (MemberRole.MEMBER, MemberRole.ADMIN, False),
        (MemberRole.MEMBER, MemberRole.VIEWER, True),
        (MemberRole.VIEWER, MemberRole.MEMBER, False),
    ]
    
    for current_role, required_role, should_pass in roles:
        member = WorkspaceMember(
            workspace_id=workspace.id,
            user_id=user.id,
            role=current_role.value
        )
        
        has_permission = member.has_permission(required_role)
        assert has_permission == should_pass, \
            f"{current_role.value} -> {required_role.value}: expected {should_pass}, got {has_permission}"


@pytest.mark.asyncio
async def test_workspace_capacity_limit(db: AsyncSession):
    """Test workspace member capacity enforcement."""
    
    # Create owner
    owner = User(
        email="owner@example.com",
        full_name="Owner",
        google_id="google_owner_cap",
        is_active=True
    )
    
    db.add(owner)
    await db.flush()
    
    # Create workspace with limited capacity
    workspace = Workspace(
        name="Limited Workspace",
        description="Testing capacity",
        owner_id=owner.id,
        max_members=2  # Only 2 members allowed
    )
    
    db.add(workspace)
    await db.flush()
    
    # Add owner as member
    owner_member = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=owner.id,
        role=MemberRole.OWNER.value
    )
    
    db.add(owner_member)
    await db.flush()
    
    # Add second member (should succeed)
    user2 = User(
        email="user2@example.com",
        full_name="User 2",
        google_id="google_user2_cap",
        is_active=True
    )
    
    db.add(user2)
    await db.flush()
    
    member2 = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=user2.id,
        role=MemberRole.MEMBER.value
    )
    
    db.add(member2)
    await db.commit()
    
    # Verify member count
    result = await db.execute(
        select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace.id)
    )
    members = result.scalars().all()
    
    assert len(members) == 2
    assert len(members) <= workspace.max_members
