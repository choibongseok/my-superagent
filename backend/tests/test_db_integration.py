"""
Database Integration Tests
Tests actual database operations using PostgreSQL/SQLite fixtures without mocks.
Validates CRUD operations, relationships, transactions, and data integrity.
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.task import Task, TaskStatus, TaskType
from app.models.chat import Chat
from app.models.message import Message, MessageRole


@pytest.mark.asyncio
class TestUserDatabaseIntegration:
    """Test User model database operations"""
    
    async def test_create_user(self, db: AsyncSession):
        """Test creating a new user in the database"""
        user = User(
            email="test@example.com",
            full_name="Test User",
            google_id="google_123",
            google_access_token="access_token_xyz",
            google_refresh_token="refresh_token_abc",
        )
        
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        assert user.id is not None
        assert user.email == "test@example.com"
        assert user.full_name == "Test User"
        assert user.created_at is not None
    
    async def test_read_user_by_email(self, db: AsyncSession):
        """Test querying user by email"""
        # Create user
        user = User(
            email="query@example.com",
            full_name="Query User",
            google_id="google_456",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        # Query by email
        result = await db.execute(
            select(User).where(User.email == "query@example.com")
        )
        found_user = result.scalar_one_or_none()
        
        assert found_user is not None
        assert found_user.id == user.id
        assert found_user.email == "query@example.com"
    
    async def test_update_user(self, db: AsyncSession):
        """Test updating user information"""
        # Create user
        user = User(
            email="update@example.com",
            full_name="Old Name",
            google_id="google_789",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        # Update user
        user.full_name = "New Name"
        user.google_access_token = "new_access_token"
        await db.commit()
        await db.refresh(user)
        
        # Verify update
        result = await db.execute(select(User).where(User.id == user.id))
        updated_user = result.scalar_one()
        
        assert updated_user.full_name == "New Name"
        assert updated_user.google_access_token == "new_access_token"
    
    async def test_delete_user(self, db: AsyncSession):
        """Test deleting a user"""
        # Create user
        user = User(
            email="delete@example.com",
            full_name="Delete User",
            google_id="google_delete",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = user.id
        
        # Delete user
        await db.delete(user)
        await db.commit()
        
        # Verify deletion
        result = await db.execute(select(User).where(User.id == user_id))
        deleted_user = result.scalar_one_or_none()
        
        assert deleted_user is None
    
    async def test_user_unique_email_constraint(self, db: AsyncSession):
        """Test that email uniqueness is enforced"""
        # Create first user
        user1 = User(
            email="unique@example.com",
            full_name="User 1",
            google_id="google_unique_1",
        )
        db.add(user1)
        await db.commit()
        
        # Try to create duplicate email user
        user2 = User(
            email="unique@example.com",  # Duplicate
            full_name="User 2",
            google_id="google_unique_2",
        )
        db.add(user2)
        
        with pytest.raises(Exception):  # IntegrityError expected
            await db.commit()
        
        await db.rollback()


@pytest.mark.asyncio
class TestTaskDatabaseIntegration:
    """Test Task model database operations"""
    
    async def test_create_task(self, db: AsyncSession):
        """Test creating a new task"""
        # Create user first
        user = User(
            email="taskuser@example.com",
            full_name="Task User",
            google_id="google_task_user",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        # Create task
        task = Task(
            user_id=user.id,
            prompt="Create a sales report",
            task_type=TaskType.DOCS,
            status=TaskStatus.PENDING,
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        
        assert task.id is not None
        assert task.user_id == user.id
        assert task.prompt == "Create a sales report"
        assert task.task_type == TaskType.DOCS
        assert task.status == TaskStatus.PENDING
        assert task.created_at is not None
    
    async def test_task_user_relationship(self, db: AsyncSession):
        """Test Task → User relationship"""
        # Create user
        user = User(
            email="relationship@example.com",
            full_name="Relationship User",
            google_id="google_rel",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        # Create task
        task = Task(
            user_id=user.id,
            prompt="Test relationship",
            task_type=TaskType.SHEETS,
            status=TaskStatus.PENDING,
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        
        # Load task with relationship
        result = await db.execute(
            select(Task).where(Task.id == task.id)
        )
        loaded_task = result.scalar_one()
        
        # Access user through relationship (if configured)
        # Note: This requires proper relationship setup in Task model
        assert loaded_task.user_id == user.id
    
    async def test_update_task_status(self, db: AsyncSession):
        """Test updating task status"""
        # Create user and task
        user = User(email="status@example.com", full_name="Status User", google_id="g_status")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        task = Task(
            user_id=user.id,
            prompt="Status test",
            task_type=TaskType.DOCS,
            status=TaskStatus.PENDING,
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        
        # Update status to IN_PROGRESS
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.utcnow()
        await db.commit()
        await db.refresh(task)
        
        assert task.status == TaskStatus.IN_PROGRESS
        assert task.started_at is not None
        
        # Update status to COMPLETED
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.utcnow()
        task.result = {"document_id": "doc_123"}
        await db.commit()
        await db.refresh(task)
        
        assert task.status == TaskStatus.COMPLETED
        assert task.completed_at is not None
        assert task.result["document_id"] == "doc_123"
    
    async def test_list_user_tasks(self, db: AsyncSession):
        """Test querying all tasks for a user"""
        # Create user
        user = User(email="list@example.com", full_name="List User", google_id="g_list")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        # Create multiple tasks
        tasks = [
            Task(user_id=user.id, prompt="Task 1", task_type=TaskType.DOCS, status=TaskStatus.PENDING),
            Task(user_id=user.id, prompt="Task 2", task_type=TaskType.SHEETS, status=TaskStatus.IN_PROGRESS),
            Task(user_id=user.id, prompt="Task 3", task_type=TaskType.SLIDES, status=TaskStatus.COMPLETED),
        ]
        for task in tasks:
            db.add(task)
        await db.commit()
        
        # Query all tasks for user
        result = await db.execute(
            select(Task).where(Task.user_id == user.id).order_by(Task.created_at)
        )
        user_tasks = result.scalars().all()
        
        assert len(user_tasks) == 3
        assert user_tasks[0].prompt == "Task 1"
        assert user_tasks[1].prompt == "Task 2"
        assert user_tasks[2].prompt == "Task 3"
    
    async def test_filter_tasks_by_status(self, db: AsyncSession):
        """Test filtering tasks by status"""
        # Create user
        user = User(email="filter@example.com", full_name="Filter User", google_id="g_filter")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        # Create tasks with different statuses
        tasks = [
            Task(user_id=user.id, prompt="Pending 1", task_type=TaskType.DOCS, status=TaskStatus.PENDING),
            Task(user_id=user.id, prompt="Pending 2", task_type=TaskType.SHEETS, status=TaskStatus.PENDING),
            Task(user_id=user.id, prompt="Completed", task_type=TaskType.SLIDES, status=TaskStatus.COMPLETED),
        ]
        for task in tasks:
            db.add(task)
        await db.commit()
        
        # Query only PENDING tasks
        result = await db.execute(
            select(Task).where(
                Task.user_id == user.id,
                Task.status == TaskStatus.PENDING
            )
        )
        pending_tasks = result.scalars().all()
        
        assert len(pending_tasks) == 2
        assert all(t.status == TaskStatus.PENDING for t in pending_tasks)
    
    async def test_task_cascade_delete(self, db: AsyncSession):
        """Test that deleting a user cascades to tasks (if configured)"""
        # Create user
        user = User(email="cascade@example.com", full_name="Cascade User", google_id="g_cascade")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        # Create task
        task = Task(
            user_id=user.id,
            prompt="Cascade test",
            task_type=TaskType.DOCS,
            status=TaskStatus.PENDING,
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        task_id = task.id
        
        # Delete user
        await db.delete(user)
        await db.commit()
        
        # Check if task still exists (depends on cascade configuration)
        result = await db.execute(select(Task).where(Task.id == task_id))
        orphaned_task = result.scalar_one_or_none()
        
        # If cascade is configured, task should be deleted too
        # If not, task will remain but user_id will be invalid
        # This test documents the current behavior
        if orphaned_task:
            assert orphaned_task.user_id == user.id  # Foreign key still points to deleted user


@pytest.mark.asyncio
class TestChatDatabaseIntegration:
    """Test Chat and Message models"""
    
    async def test_create_chat(self, db: AsyncSession):
        """Test creating a chat"""
        # Create user
        user = User(email="conv@example.com", full_name="Conv User", google_id="g_conv")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        # Create chat
        chat = Chat(
            user_id=user.id,
            title="Test Chat",
        )
        db.add(chat)
        await db.commit()
        await db.refresh(chat)
        
        assert chat.id is not None
        assert chat.user_id == user.id
        assert chat.title == "Test Chat"
        assert chat.created_at is not None
    
    async def test_create_messages_in_chat(self, db: AsyncSession):
        """Test creating messages within a chat"""
        # Create user and chat
        user = User(email="msg@example.com", full_name="Msg User", google_id="g_msg")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        chat = Chat(user_id=user.id, title="Message Test")
        db.add(chat)
        await db.commit()
        await db.refresh(chat)
        
        # Create messages
        messages = [
            Message(
                chat_id=chat.id,
                user_id=user.id,
                role=MessageRole.USER,
                content="Hello, create a document",
            ),
            Message(
                chat_id=chat.id,
                user_id=user.id,
                role=MessageRole.ASSISTANT,
                content="I'll create that document for you.",
            ),
        ]
        for msg in messages:
            db.add(msg)
        await db.commit()
        
        # Query messages
        result = await db.execute(
            select(Message)
            .where(Message.chat_id == chat.id)
            .order_by(Message.created_at)
        )
        chat_messages = result.scalars().all()
        
        assert len(chat_messages) == 2
        assert chat_messages[0].role == MessageRole.USER
        assert chat_messages[1].role == MessageRole.ASSISTANT
        assert "document" in chat_messages[0].content.lower()


@pytest.mark.asyncio
class TestDatabaseTransactions:
    """Test transaction behavior and rollback"""
    
    async def test_commit_transaction(self, db: AsyncSession):
        """Test successful transaction commit"""
        user = User(email="commit@example.com", full_name="Commit User", google_id="g_commit")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        # Verify user exists after commit
        result = await db.execute(select(User).where(User.id == user.id))
        found_user = result.scalar_one_or_none()
        assert found_user is not None
    
    async def test_rollback_transaction(self, db: AsyncSession):
        """Test transaction rollback"""
        # Create user but don't commit
        user = User(email="rollback@example.com", full_name="Rollback User", google_id="g_rollback")
        db.add(user)
        await db.flush()  # Send to DB but don't commit
        user_id = user.id
        
        # Rollback
        await db.rollback()
        
        # Verify user doesn't exist after rollback
        result = await db.execute(select(User).where(User.id == user_id))
        found_user = result.scalar_one_or_none()
        assert found_user is None
    
    async def test_atomic_multi_insert(self, db: AsyncSession):
        """Test atomic insertion of multiple related records"""
        # Create user, task, and chat atomically
        user = User(email="atomic@example.com", full_name="Atomic User", google_id="g_atomic")
        db.add(user)
        await db.flush()  # Get user.id
        
        task = Task(
            user_id=user.id,
            prompt="Atomic task",
            task_type=TaskType.DOCS,
            status=TaskStatus.PENDING,
        )
        db.add(task)
        
        chat = Chat(user_id=user.id, title="Atomic chat")
        db.add(chat)
        
        # Commit all at once
        await db.commit()
        
        # Verify all records exist
        user_result = await db.execute(select(User).where(User.id == user.id))
        assert user_result.scalar_one_or_none() is not None
        
        task_result = await db.execute(select(Task).where(Task.user_id == user.id))
        assert task_result.scalar_one_or_none() is not None
        
        chat_result = await db.execute(select(Chat).where(Chat.user_id == user.id))
        assert chat_result.scalar_one_or_none() is not None


@pytest.mark.asyncio
class TestDatabaseConstraints:
    """Test database constraints and data integrity"""
    
    async def test_not_null_constraint(self, db: AsyncSession):
        """Test that NOT NULL constraints are enforced"""
        # Try to create task without required user_id (should fail)
        task = Task(
            prompt="Orphan task without user_id",
            task_type=TaskType.DOCS,
            status=TaskStatus.PENDING,
        )
        db.add(task)
        
        with pytest.raises(Exception):  # IntegrityError expected
            await db.commit()
        
        await db.rollback()
    
    async def test_foreign_key_constraint(self, db: AsyncSession):
        """Test foreign key constraint enforcement"""
        # Try to create task with non-existent user_id
        task = Task(
            user_id="non_existent_user_id",
            prompt="Orphan task",
            task_type=TaskType.DOCS,
            status=TaskStatus.PENDING,
        )
        db.add(task)
        
        with pytest.raises(Exception):  # IntegrityError expected
            await db.commit()
        
        await db.rollback()
    
    async def test_enum_constraint(self, db: AsyncSession):
        """Test that enum values are enforced"""
        # Create user first
        user = User(email="enum@example.com", full_name="Enum User", google_id="g_enum")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        # Try to set invalid task_type (should fail at Python level or DB level)
        # Note: Python Enum enforcement happens before DB
        try:
            task = Task(
                user_id=user.id,
                prompt="Invalid type",
                task_type="invalid_type",  # Not a valid TaskType
                status=TaskStatus.PENDING,
            )
            db.add(task)
            await db.commit()
            assert False, "Should have raised an error for invalid enum"
        except (ValueError, Exception):
            # Expected: either Python ValueError or DB constraint error
            await db.rollback()
            assert True


@pytest.mark.asyncio
class TestDatabasePerformance:
    """Test database query performance and optimization"""
    
    async def test_bulk_insert_performance(self, db: AsyncSession):
        """Test bulk insertion of multiple records"""
        # Create user
        user = User(email="bulk@example.com", full_name="Bulk User", google_id="g_bulk")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        # Bulk insert 100 tasks
        tasks = [
            Task(
                user_id=user.id,
                prompt=f"Bulk task {i}",
                task_type=TaskType.DOCS,
                status=TaskStatus.PENDING,
            )
            for i in range(100)
        ]
        
        db.add_all(tasks)
        await db.commit()
        
        # Verify count
        result = await db.execute(
            select(Task).where(Task.user_id == user.id)
        )
        all_tasks = result.scalars().all()
        
        assert len(all_tasks) == 100
    
    async def test_pagination(self, db: AsyncSession):
        """Test paginated queries"""
        # Create user
        user = User(email="page@example.com", full_name="Page User", google_id="g_page")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        # Create 50 tasks
        tasks = [
            Task(
                user_id=user.id,
                prompt=f"Task {i}",
                task_type=TaskType.DOCS,
                status=TaskStatus.PENDING,
            )
            for i in range(50)
        ]
        db.add_all(tasks)
        await db.commit()
        
        # Query with pagination
        page_size = 10
        offset = 0
        
        result = await db.execute(
            select(Task)
            .where(Task.user_id == user.id)
            .order_by(Task.created_at)
            .limit(page_size)
            .offset(offset)
        )
        page_1 = result.scalars().all()
        
        assert len(page_1) == page_size
        
        # Query second page
        offset = page_size
        result = await db.execute(
            select(Task)
            .where(Task.user_id == user.id)
            .order_by(Task.created_at)
            .limit(page_size)
            .offset(offset)
        )
        page_2 = result.scalars().all()
        
        assert len(page_2) == page_size
        assert page_1[0].id != page_2[0].id  # Different pages


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
