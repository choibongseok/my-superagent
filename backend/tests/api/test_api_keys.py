"""Tests for API key management."""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select

from app.models.api_key import ApiKey
from app.models.api_key_usage import ApiKeyUsage
from app.models.user import User


@pytest.mark.asyncio
class TestApiKeyManagement:
    """Test API key CRUD operations."""
    
    async def test_create_api_key(self, async_client: AsyncClient, test_user_token: str):
        """Test creating a new API key."""
        response = await async_client.post(
            "/api/v1/api-keys",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={
                "name": "Test API Key",
                "scopes": ["read", "write"],
                "expires_in_days": 30
            }
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        
        assert data["name"] == "Test API Key"
        assert set(data["scopes"]) == {"read", "write"}
        assert data["is_active"] is True
        assert "api_key" in data  # Actual key is returned
        assert data["api_key"].startswith("ahq_")
        assert data["key_prefix"] == data["api_key"][:8]
    
    async def test_create_api_key_invalid_scopes(
        self, async_client: AsyncClient, test_user_token: str
    ):
        """Test creating API key with invalid scopes."""
        response = await async_client.post(
            "/api/v1/api-keys",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={
                "name": "Invalid Key",
                "scopes": ["invalid_scope"]
            }
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid scopes" in response.json()["detail"]
    
    async def test_create_api_key_admin_scope_non_admin(
        self, async_client: AsyncClient, test_user_token: str
    ):
        """Test non-admin user cannot create admin-scoped keys."""
        response = await async_client.post(
            "/api/v1/api-keys",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={
                "name": "Admin Key",
                "scopes": ["admin"]
            }
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "administrator" in response.json()["detail"].lower()
    
    async def test_list_api_keys(
        self, async_client: AsyncClient, test_user_token: str, db_session
    ):
        """Test listing user's API keys."""
        # Create some keys first
        for i in range(3):
            await async_client.post(
                "/api/v1/api-keys",
                headers={"Authorization": f"Bearer {test_user_token}"},
                json={"name": f"Key {i}", "scopes": ["read"]}
            )
        
        # List keys
        response = await async_client.get(
            "/api/v1/api-keys",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) >= 3
        assert all("api_key" not in key for key in data)  # Actual key not in list
    
    async def test_list_api_keys_include_inactive(
        self, async_client: AsyncClient, test_user_token: str, db_session
    ):
        """Test listing includes inactive keys when requested."""
        # Create and deactivate a key
        create_response = await async_client.post(
            "/api/v1/api-keys",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={"name": "Inactive Key", "scopes": ["read"]}
        )
        key_id = create_response.json()["id"]
        
        await async_client.patch(
            f"/api/v1/api-keys/{key_id}",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={"is_active": False}
        )
        
        # List without inactive
        response = await async_client.get(
            "/api/v1/api-keys",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert not any(key["id"] == key_id for key in response.json())
        
        # List with inactive
        response = await async_client.get(
            "/api/v1/api-keys?include_inactive=true",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert any(key["id"] == key_id for key in response.json())
    
    async def test_get_api_key(
        self, async_client: AsyncClient, test_user_token: str
    ):
        """Test getting a specific API key."""
        # Create key
        create_response = await async_client.post(
            "/api/v1/api-keys",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={"name": "Get Test", "scopes": ["read"]}
        )
        key_id = create_response.json()["id"]
        
        # Get key
        response = await async_client.get(
            f"/api/v1/api-keys/{key_id}",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == key_id
        assert data["name"] == "Get Test"
        assert "api_key" not in data  # Actual key not returned
    
    async def test_get_api_key_not_found(
        self, async_client: AsyncClient, test_user_token: str
    ):
        """Test getting non-existent API key."""
        response = await async_client.get(
            f"/api/v1/api-keys/{uuid4()}",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    async def test_update_api_key(
        self, async_client: AsyncClient, test_user_token: str
    ):
        """Test updating an API key."""
        # Create key
        create_response = await async_client.post(
            "/api/v1/api-keys",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={"name": "Update Test", "scopes": ["read"]}
        )
        key_id = create_response.json()["id"]
        
        # Update key
        response = await async_client.patch(
            f"/api/v1/api-keys/{key_id}",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={
                "name": "Updated Name",
                "scopes": ["read", "write"],
                "is_active": False
            }
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "Updated Name"
        assert set(data["scopes"]) == {"read", "write"}
        assert data["is_active"] is False
    
    async def test_delete_api_key(
        self, async_client: AsyncClient, test_user_token: str, db_session
    ):
        """Test deleting an API key."""
        # Create key
        create_response = await async_client.post(
            "/api/v1/api-keys",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={"name": "Delete Test", "scopes": ["read"]}
        )
        key_id = create_response.json()["id"]
        
        # Delete key
        response = await async_client.delete(
            f"/api/v1/api-keys/{key_id}",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        
        assert response.status_code == status.HTTP_204_NO_CONTENT
        
        # Verify deleted
        response = await async_client.get(
            f"/api/v1/api-keys/{key_id}",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    async def test_rotate_api_key(
        self, async_client: AsyncClient, test_user_token: str
    ):
        """Test rotating an API key."""
        # Create key
        create_response = await async_client.post(
            "/api/v1/api-keys",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={"name": "Rotate Test", "scopes": ["read"]}
        )
        key_id = create_response.json()["id"]
        old_key = create_response.json()["api_key"]
        
        # Rotate key
        response = await async_client.post(
            f"/api/v1/api-keys/{key_id}/rotate",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        new_key = data["api_key"]
        
        assert new_key != old_key
        assert new_key.startswith("ahq_")
        assert data["usage_count"] == 0  # Reset on rotation
        assert data["last_used_at"] is None


@pytest.mark.asyncio
class TestApiKeyAuthentication:
    """Test API key authentication."""
    
    async def test_authenticate_with_api_key(
        self, async_client: AsyncClient, test_user_token: str
    ):
        """Test authenticating with an API key."""
        # Create key
        create_response = await async_client.post(
            "/api/v1/api-keys",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={"name": "Auth Test", "scopes": ["read", "write"]}
        )
        api_key = create_response.json()["api_key"]
        
        # Use API key to access endpoint
        response = await async_client.get(
            "/api/v1/health",
            headers={"X-API-Key": api_key}
        )
        
        assert response.status_code == status.HTTP_200_OK
    
    async def test_authenticate_with_invalid_api_key(
        self, async_client: AsyncClient
    ):
        """Test authentication fails with invalid API key."""
        response = await async_client.get(
            "/api/v1/tasks",
            headers={"X-API-Key": "ahq_invalidkey123"}
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    async def test_authenticate_with_expired_api_key(
        self, async_client: AsyncClient, test_user_token: str, db_session
    ):
        """Test authentication fails with expired API key."""
        # Create key that expires in 1 second
        create_response = await async_client.post(
            "/api/v1/api-keys",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={
                "name": "Expired Key",
                "scopes": ["read"],
                "expires_in_days": 1
            }
        )
        key_id = create_response.json()["id"]
        api_key = create_response.json()["api_key"]
        
        # Manually expire the key
        query = select(ApiKey).where(ApiKey.id == key_id)
        result = await db_session.execute(query)
        db_key = result.scalar_one()
        db_key.expires_at = datetime.utcnow() - timedelta(hours=1)
        await db_session.commit()
        
        # Try to use expired key
        response = await async_client.get(
            "/api/v1/health",
            headers={"X-API-Key": api_key}
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    async def test_authenticate_with_inactive_api_key(
        self, async_client: AsyncClient, test_user_token: str
    ):
        """Test authentication fails with inactive API key."""
        # Create and deactivate key
        create_response = await async_client.post(
            "/api/v1/api-keys",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={"name": "Inactive Key", "scopes": ["read"]}
        )
        key_id = create_response.json()["id"]
        api_key = create_response.json()["api_key"]
        
        await async_client.patch(
            f"/api/v1/api-keys/{key_id}",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={"is_active": False}
        )
        
        # Try to use inactive key
        response = await async_client.get(
            "/api/v1/health",
            headers={"X-API-Key": api_key}
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
class TestApiKeyUsageTracking:
    """Test API key usage tracking and analytics."""
    
    async def test_usage_count_increments(
        self, async_client: AsyncClient, test_user_token: str
    ):
        """Test usage count increments with each request."""
        # Create key
        create_response = await async_client.post(
            "/api/v1/api-keys",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={"name": "Usage Test", "scopes": ["read"]}
        )
        key_id = create_response.json()["id"]
        api_key = create_response.json()["api_key"]
        
        # Make several requests
        for _ in range(5):
            await async_client.get(
                "/api/v1/health",
                headers={"X-API-Key": api_key}
            )
        
        # Check usage count
        response = await async_client.get(
            f"/api/v1/api-keys/{key_id}",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        
        assert response.json()["usage_count"] >= 5
    
    async def test_last_used_at_updates(
        self, async_client: AsyncClient, test_user_token: str
    ):
        """Test last_used_at timestamp updates."""
        # Create key
        create_response = await async_client.post(
            "/api/v1/api-keys",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={"name": "Timestamp Test", "scopes": ["read"]}
        )
        key_id = create_response.json()["id"]
        api_key = create_response.json()["api_key"]
        
        # Use the key
        await async_client.get(
            "/api/v1/health",
            headers={"X-API-Key": api_key}
        )
        
        # Check last_used_at
        response = await async_client.get(
            f"/api/v1/api-keys/{key_id}",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        
        assert response.json()["last_used_at"] is not None
    
    async def test_get_api_key_stats(
        self, async_client: AsyncClient, test_user_token: str
    ):
        """Test getting API key usage statistics."""
        # Create key
        create_response = await async_client.post(
            "/api/v1/api-keys",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={"name": "Stats Test", "scopes": ["read", "write"]}
        )
        key_id = create_response.json()["id"]
        api_key = create_response.json()["api_key"]
        
        # Make some requests
        await async_client.get("/api/v1/health", headers={"X-API-Key": api_key})
        await async_client.get("/api/v1/health", headers={"X-API-Key": api_key})
        await async_client.get("/api/v1/tasks", headers={"X-API-Key": api_key})
        
        # Get stats
        response = await async_client.get(
            f"/api/v1/api-keys/{key_id}/stats",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data["total_requests"] >= 3
        assert "/api/v1/health" in data["requests_by_endpoint"]
        assert data["last_24h_requests"] >= 3


@pytest.mark.asyncio
class TestApiKeyScopesAndPermissions:
    """Test API key scopes and permission checks."""
    
    async def test_admin_key_creation_requires_admin(
        self, async_client: AsyncClient, test_user_token: str, db_session
    ):
        """Test that admin-scoped keys can only be created by admins."""
        response = await async_client.post(
            "/api/v1/api-keys",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={
                "name": "Admin Key",
                "scopes": ["admin"]
            }
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
