"""Comprehensive tests for Chats API endpoints.

Uses real test database with proper JWT authentication.
"""

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from datetime import datetime, timedelta, UTC
from uuid import uuid4
import jwt

from app.main import app
from app.core.config import settings
from app.models.chat import Chat
from app.models.message import Message
from app.models.user import User
from sqlalchemy import select


@pytest.fixture
def client():
    """FastAPI test client (sync)"""
    return TestClient(app)


@pytest_asyncio.fixture
async def test_user(db):
    """Create a test user in the database."""
    user = User(
        id=uuid4(),
        email="chatuser@test.com",
        full_name="Chat User",
        google_id="google_test_id",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_user):
    """Generate valid JWT token for test user."""
    payload = {
        "sub": str(test_user.id),
        "email": test_user.email,
        "exp": datetime.now(UTC) + timedelta(hours=1),
        "type": "access",
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def test_chat(db, test_user):
    """Create a test chat in the database."""
    chat = Chat(
        id=uuid4(),
        title="Test Chat",
        user_id=test_user.id,
    )
    db.add(chat)
    await db.commit()
    await db.refresh(chat)
    return chat


@pytest_asyncio.fixture
async def test_chat_with_messages(db, test_user):
    """Create a test chat with messages in the database."""
    chat = Chat(
        id=uuid4(),
        title="Chat with Messages",
        user_id=test_user.id,
    )
    db.add(chat)
    await db.commit()
    await db.refresh(chat)
    
    # Add messages
    messages = [
        Message(
            id=uuid4(),
            chat_id=chat.id,
            role="user",
            content="Hello, how are you?",
        ),
        Message(
            id=uuid4(),
            chat_id=chat.id,
            role="assistant",
            content="I'm doing well, thank you!",
        ),
        Message(
            id=uuid4(),
            chat_id=chat.id,
            role="user",
            content="Can you help me with something?",
        ),
    ]
    
    for msg in messages:
        db.add(msg)
    
    await db.commit()
    
    # Refresh to load relationships
    await db.refresh(chat)
    
    return chat


class TestCreateChat:
    """Tests for POST /api/v1/chats endpoint."""

    @pytest.mark.asyncio
    async def test_create_chat_success(self, client, db, test_user, auth_headers):
        """Test successful chat creation."""
        response = client.post(
            "/api/v1/chats",
            json={"title": "My New Chat"},
            headers=auth_headers,
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "My New Chat"
        assert data["user_id"] == str(test_user.id)
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

    @pytest.mark.asyncio
    async def test_create_chat_with_empty_title(self, client, db, test_user, auth_headers):
        """Test chat creation with empty title."""
        response = client.post(
            "/api/v1/chats",
            json={"title": ""},
            headers=auth_headers,
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == ""

    def test_create_chat_unauthorized(self, client):
        """Test chat creation without authentication."""
        response = client.post(
            "/api/v1/chats",
            json={"title": "Unauthorized Chat"},
        )
        
        assert response.status_code in [401, 403]


class TestListChats:
    """Tests for GET /api/v1/chats endpoint."""

    @pytest.mark.asyncio
    async def test_list_chats_empty(self, client, db, test_user, auth_headers):
        """Test listing chats when user has none."""
        response = client.get("/api/v1/chats", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["chats"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_chats_with_data(self, client, db, test_user, test_chat, auth_headers):
        """Test listing chats with existing data."""
        # Create additional chats
        chats = [
            Chat(title=f"Chat {i}", user_id=test_user.id)
            for i in range(3)
        ]
        for chat in chats:
            db.add(chat)
        await db.commit()
        
        response = client.get("/api/v1/chats", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["chats"]) == 4  # test_chat + 3 new chats
        assert data["total"] == 4

    @pytest.mark.asyncio
    async def test_list_chats_pagination(self, client, db, test_user, auth_headers):
        """Test chat list pagination."""
        # Create 10 chats
        chats = [
            Chat(title=f"Chat {i}", user_id=test_user.id)
            for i in range(10)
        ]
        for chat in chats:
            db.add(chat)
        await db.commit()
        
        # Get first page
        response = client.get("/api/v1/chats?skip=0&limit=5", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["chats"]) == 5
        assert data["total"] == 10
        
        # Get second page
        response = client.get("/api/v1/chats?skip=5&limit=5", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["chats"]) == 5
        assert data["total"] == 10

    @pytest.mark.asyncio
    async def test_list_chats_user_isolation(self, client, db, test_user, test_chat, auth_headers):
        """Test that users only see their own chats."""
        # Create another user and their chat
        other_user = User(
            id=uuid4(),
            email="other@test.com",
            google_id="google_other_id",
            full_name="Other User",
        )
        db.add(other_user)
        await db.commit()
        
        other_chat = Chat(
            title="Other User's Chat",
            user_id=other_user.id,
        )
        db.add(other_chat)
        await db.commit()
        
        response = client.get("/api/v1/chats", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        # Should only see test_chat, not other_chat
        assert data["total"] == 1
        assert data["chats"][0]["title"] == "Test Chat"

    def test_list_chats_unauthorized(self, client):
        """Test listing chats without authentication."""
        response = client.get("/api/v1/chats")
        assert response.status_code in [401, 403]


class TestGetChat:
    """Tests for GET /api/v1/chats/{chat_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_chat_success(self, client, db, test_user, test_chat, auth_headers):
        """Test successful chat retrieval."""
        response = client.get(f"/api/v1/chats/{test_chat.id}", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_chat.id)
        assert data["title"] == test_chat.title

    @pytest.mark.asyncio
    async def test_get_chat_with_messages(self, client, db, test_user, test_chat_with_messages, auth_headers):
        """Test retrieving chat with messages."""
        response = client.get(f"/api/v1/chats/{test_chat_with_messages.id}", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 3
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][0]["content"] == "Hello, how are you?"

    @pytest.mark.asyncio
    async def test_get_chat_not_found(self, client, db, test_user, auth_headers):
        """Test retrieving non-existent chat."""
        fake_id = uuid4()
        response = client.get(f"/api/v1/chats/{fake_id}", headers=auth_headers)
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_chat_wrong_user(self, client, db, test_user, test_chat, auth_headers):
        """Test retrieving another user's chat (returns 404 to hide existence)."""
        # Create another user
        other_user = User(
            id=uuid4(),
            email="hacker@test.com",
            google_id="google_other_id",
            full_name="Hacker User",
        )
        db.add(other_user)
        await db.commit()
        
        # Generate token for other user
        payload = {
            "sub": str(other_user.id),
            "email": other_user.email,
            "exp": datetime.now(UTC) + timedelta(hours=1),
            "type": "access",
        }
        other_token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
        other_headers = {"Authorization": f"Bearer {other_token}"}
        
        response = client.get(f"/api/v1/chats/{test_chat.id}", headers=other_headers)
        
        # Should return 404 (not 403) to avoid leaking existence
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_chat_invalid_uuid(self, client, db, test_user, auth_headers):
        """Test retrieving chat with invalid UUID."""
        response = client.get("/api/v1/chats/not-a-uuid", headers=auth_headers)
        assert response.status_code == 422

    def test_get_chat_unauthorized(self, client, test_chat):
        """Test retrieving chat without authentication."""
        response = client.get(f"/api/v1/chats/{test_chat.id}")
        assert response.status_code in [401, 403]


class TestUpdateChat:
    """Tests for PATCH /api/v1/chats/{chat_id} endpoint."""

    @pytest.mark.asyncio
    async def test_update_chat_title(self, client, db, test_user, test_chat, auth_headers):
        """Test updating chat title."""
        response = client.patch(
            f"/api/v1/chats/{test_chat.id}",
            json={"title": "Updated Title"},
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Title"

    @pytest.mark.asyncio
    async def test_update_chat_empty_title(self, client, db, test_user, test_chat, auth_headers):
        """Test updating chat with empty title."""
        response = client.patch(
            f"/api/v1/chats/{test_chat.id}",
            json={"title": ""},
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == ""

    @pytest.mark.asyncio
    async def test_update_chat_no_changes(self, client, db, test_user, test_chat, auth_headers):
        """Test updating chat with no changes."""
        response = client.patch(
            f"/api/v1/chats/{test_chat.id}",
            json={},
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == test_chat.title

    @pytest.mark.asyncio
    async def test_update_chat_not_found(self, client, db, test_user, auth_headers):
        """Test updating non-existent chat."""
        fake_id = uuid4()
        response = client.patch(
            f"/api/v1/chats/{fake_id}",
            json={"title": "New Title"},
            headers=auth_headers,
        )
        
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_chat_wrong_user(self, client, db, test_user, test_chat, auth_headers):
        """Test updating another user's chat."""
        # Create another user
        other_user = User(
            id=uuid4(),
            email="attacker@test.com",
            google_id="google_other_id",
            full_name="Attacker",
        )
        db.add(other_user)
        await db.commit()
        
        # Generate token for other user
        payload = {
            "sub": str(other_user.id),
            "email": other_user.email,
            "exp": datetime.now(UTC) + timedelta(hours=1),
            "type": "access",
        }
        other_token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
        other_headers = {"Authorization": f"Bearer {other_token}"}
        
        response = client.patch(
            f"/api/v1/chats/{test_chat.id}",
            json={"title": "Hacked Title"},
            headers=other_headers,
        )
        
        assert response.status_code == 404

    def test_update_chat_unauthorized(self, client, test_chat):
        """Test updating chat without authentication."""
        response = client.patch(
            f"/api/v1/chats/{test_chat.id}",
            json={"title": "No Auth"},
        )
        assert response.status_code in [401, 403]


class TestDeleteChat:
    """Tests for DELETE /api/v1/chats/{chat_id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_chat_success(self, client, db, test_user, test_chat, auth_headers):
        """Test successful chat deletion."""
        chat_id = test_chat.id
        
        response = client.delete(f"/api/v1/chats/{chat_id}", headers=auth_headers)
        
        assert response.status_code == 204
        
        # Verify chat is deleted
        result = await db.execute(select(Chat).where(Chat.id == chat_id))
        deleted_chat = result.scalar_one_or_none()
        assert deleted_chat is None

    @pytest.mark.asyncio
    async def test_delete_chat_not_found(self, client, db, test_user, auth_headers):
        """Test deleting non-existent chat."""
        fake_id = uuid4()
        response = client.delete(f"/api/v1/chats/{fake_id}", headers=auth_headers)
        
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_chat_wrong_user(self, client, db, test_user, test_chat, auth_headers):
        """Test deleting another user's chat."""
        # Create another user
        other_user = User(
            id=uuid4(),
            email="badactor@test.com",
            google_id="google_other_id",
            full_name="Bad Actor",
        )
        db.add(other_user)
        await db.commit()
        
        # Generate token for other user
        payload = {
            "sub": str(other_user.id),
            "email": other_user.email,
            "exp": datetime.now(UTC) + timedelta(hours=1),
            "type": "access",
        }
        other_token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
        other_headers = {"Authorization": f"Bearer {other_token}"}
        
        response = client.delete(f"/api/v1/chats/{test_chat.id}", headers=other_headers)
        
        assert response.status_code == 404
        
        # Verify chat still exists
        result = await db.execute(select(Chat).where(Chat.id == test_chat.id))
        existing_chat = result.scalar_one_or_none()
        assert existing_chat is not None

    @pytest.mark.asyncio
    async def test_delete_chat_with_messages(self, client, db, test_user, test_chat_with_messages, auth_headers):
        """Test deleting chat with messages (cascade)."""
        chat_id = test_chat_with_messages.id
        
        response = client.delete(f"/api/v1/chats/{chat_id}", headers=auth_headers)
        
        assert response.status_code == 204
        
        # Verify chat and messages are deleted
        result = await db.execute(select(Chat).where(Chat.id == chat_id))
        assert result.scalar_one_or_none() is None
        
        result = await db.execute(select(Message).where(Message.chat_id == chat_id))
        messages = result.scalars().all()
        assert len(messages) == 0  # Should be cascade deleted

    def test_delete_chat_unauthorized(self, client, test_chat):
        """Test deleting chat without authentication."""
        response = client.delete(f"/api/v1/chats/{test_chat.id}")
        assert response.status_code in [401, 403]


class TestChatEdgeCases:
    """Edge case and integration tests."""

    @pytest.mark.asyncio
    async def test_chat_long_title(self, client, db, test_user, auth_headers):
        """Test creating chat with very long title."""
        long_title = "A" * 10000
        
        response = client.post(
            "/api/v1/chats",
            json={"title": long_title},
            headers=auth_headers,
        )
        
        assert response.status_code == 201
        data = response.json()
        assert len(data["title"]) == 10000

    @pytest.mark.asyncio
    async def test_chat_special_characters(self, client, db, test_user, auth_headers):
        """Test creating chat with special characters in title."""
        special_title = "🚀 Test Chat with émojis & spëcial chars: <script>alert('xss')</script>"
        
        response = client.post(
            "/api/v1/chats",
            json={"title": special_title},
            headers=auth_headers,
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == special_title
