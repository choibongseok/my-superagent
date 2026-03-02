"""Tests for admin rate limit management endpoints."""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.main import app
from backend.app.models.user import User
from backend.app.models.rate_limit_override import RateLimitOverride
from backend.app.core.security import create_access_token


@pytest.fixture
def admin_user(db: Session) -> User:
    """Create an admin user for testing."""
    user = User(
        id=uuid4(),
        email="admin@test.com",
        full_name="Admin User",
        is_active=True,
        is_admin=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def regular_user(db: Session) -> User:
    """Create a regular user for testing."""
    user = User(
        id=uuid4(),
        email="user@test.com",
        full_name="Regular User",
        is_active=True,
        is_admin=False
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin_token(admin_user: User) -> str:
    """Create an access token for the admin user."""
    return create_access_token(str(admin_user.id))


@pytest.fixture
def user_token(regular_user: User) -> str:
    """Create an access token for the regular user."""
    return create_access_token(str(regular_user.id))


@pytest.fixture
def client() -> TestClient:
    """Create a test client."""
    return TestClient(app)


class TestRateLimitOverrideModel:
    """Tests for RateLimitOverride model."""
    
    def test_create_override(self, db: Session, admin_user: User, regular_user: User):
        """Test creating a rate limit override."""
        override = RateLimitOverride(
            user_id=regular_user.id,
            endpoint_pattern="/api/v1/tasks/*",
            custom_limit=500,
            created_by=admin_user.id,
            reason="VIP user"
        )
        db.add(override)
        db.commit()
        db.refresh(override)
        
        assert override.id is not None
        assert override.user_id == regular_user.id
        assert override.custom_limit == 500
        assert override.is_active()
    
    def test_override_is_active(self, db: Session, admin_user: User, regular_user: User):
        """Test checking if override is active."""
        # Active override (no expiry)
        override1 = RateLimitOverride(
            user_id=regular_user.id,
            endpoint_pattern="*",
            custom_limit=1000,
            created_by=admin_user.id
        )
        assert override1.is_active()
        
        # Active override (future expiry)
        override2 = RateLimitOverride(
            user_id=regular_user.id,
            endpoint_pattern="*",
            custom_limit=1000,
            expires_at=datetime.utcnow() + timedelta(hours=1),
            created_by=admin_user.id
        )
        assert override2.is_active()
        
        # Expired override
        override3 = RateLimitOverride(
            user_id=regular_user.id,
            endpoint_pattern="*",
            custom_limit=1000,
            expires_at=datetime.utcnow() - timedelta(hours=1),
            created_by=admin_user.id
        )
        assert not override3.is_active()
    
    def test_matches_endpoint(self, db: Session, admin_user: User, regular_user: User):
        """Test endpoint pattern matching."""
        override = RateLimitOverride(
            user_id=regular_user.id,
            endpoint_pattern="/api/v1/tasks/*",
            custom_limit=100,
            created_by=admin_user.id
        )
        
        # Should match
        assert override.matches_endpoint("/api/v1/tasks/create")
        assert override.matches_endpoint("/api/v1/tasks/list")
        assert override.matches_endpoint("/api/v1/tasks/123/status")
        
        # Should not match
        assert not override.matches_endpoint("/api/v1/agents/research")
        assert not override.matches_endpoint("/api/v2/tasks/create")
    
    def test_wildcard_pattern(self, db: Session, admin_user: User, regular_user: User):
        """Test wildcard pattern matching."""
        override = RateLimitOverride(
            user_id=regular_user.id,
            endpoint_pattern="*",
            custom_limit=100,
            created_by=admin_user.id
        )
        
        # Should match everything
        assert override.matches_endpoint("/api/v1/tasks/create")
        assert override.matches_endpoint("/api/v1/agents/research")
        assert override.matches_endpoint("/any/endpoint")
    
    def test_exact_pattern(self, db: Session, admin_user: User, regular_user: User):
        """Test exact pattern matching."""
        override = RateLimitOverride(
            user_id=regular_user.id,
            endpoint_pattern="/api/v1/tasks/create",
            custom_limit=100,
            created_by=admin_user.id
        )
        
        # Should only match exact endpoint
        assert override.matches_endpoint("/api/v1/tasks/create")
        assert not override.matches_endpoint("/api/v1/tasks/list")
        assert not override.matches_endpoint("/api/v1/tasks/create/123")


class TestAdminRateLimitEndpoints:
    """Tests for admin rate limit management endpoints."""
    
    def test_list_overrides_as_admin(
        self, 
        client: TestClient, 
        db: Session, 
        admin_user: User, 
        regular_user: User,
        admin_token: str
    ):
        """Test listing overrides as admin."""
        # Create some overrides
        override1 = RateLimitOverride(
            user_id=regular_user.id,
            endpoint_pattern="/api/v1/tasks/*",
            custom_limit=500,
            created_by=admin_user.id
        )
        override2 = RateLimitOverride(
            user_id=regular_user.id,
            endpoint_pattern="*",
            custom_limit=1000,
            expires_at=datetime.utcnow() + timedelta(hours=1),
            created_by=admin_user.id
        )
        db.add_all([override1, override2])
        db.commit()
        
        # List overrides
        response = client.get(
            "/api/v1/admin/rate-limits",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        overrides = response.json()
        assert len(overrides) >= 2
    
    def test_list_overrides_as_regular_user(
        self, 
        client: TestClient, 
        user_token: str
    ):
        """Test listing overrides as regular user (should fail)."""
        response = client.get(
            "/api/v1/admin/rate-limits",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        
        assert response.status_code == 403
    
    def test_create_override_as_admin(
        self,
        client: TestClient,
        db: Session,
        admin_user: User,
        regular_user: User,
        admin_token: str
    ):
        """Test creating an override as admin."""
        override_data = {
            "user_id": str(regular_user.id),
            "endpoint_pattern": "/api/v1/tasks/*",
            "custom_limit": 500,
            "reason": "VIP user needs higher limits"
        }
        
        response = client.post(
            "/api/v1/admin/rate-limits",
            json=override_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["user_id"] == str(regular_user.id)
        assert data["endpoint_pattern"] == "/api/v1/tasks/*"
        assert data["custom_limit"] == 500
        assert data["is_active"] is True
    
    def test_create_override_with_expiry(
        self,
        client: TestClient,
        db: Session,
        admin_user: User,
        regular_user: User,
        admin_token: str
    ):
        """Test creating a temporary override."""
        expires_at = (datetime.utcnow() + timedelta(hours=24)).isoformat()
        
        override_data = {
            "user_id": str(regular_user.id),
            "endpoint_pattern": "*",
            "custom_limit": 2000,
            "expires_at": expires_at,
            "reason": "Temporary high limit for testing"
        }
        
        response = client.post(
            "/api/v1/admin/rate-limits",
            json=override_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["expires_at"] is not None
    
    def test_create_duplicate_override(
        self,
        client: TestClient,
        db: Session,
        admin_user: User,
        regular_user: User,
        admin_token: str
    ):
        """Test creating a duplicate override (should fail)."""
        # Create first override
        override = RateLimitOverride(
            user_id=regular_user.id,
            endpoint_pattern="/api/v1/tasks/*",
            custom_limit=500,
            created_by=admin_user.id
        )
        db.add(override)
        db.commit()
        
        # Try to create duplicate
        override_data = {
            "user_id": str(regular_user.id),
            "endpoint_pattern": "/api/v1/tasks/*",
            "custom_limit": 1000
        }
        
        response = client.post(
            "/api/v1/admin/rate-limits",
            json=override_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 409
    
    def test_update_override(
        self,
        client: TestClient,
        db: Session,
        admin_user: User,
        regular_user: User,
        admin_token: str
    ):
        """Test updating an existing override."""
        # Create override
        override = RateLimitOverride(
            user_id=regular_user.id,
            endpoint_pattern="/api/v1/tasks/*",
            custom_limit=500,
            created_by=admin_user.id
        )
        db.add(override)
        db.commit()
        db.refresh(override)
        
        # Update override
        update_data = {
            "custom_limit": 1000,
            "reason": "Increased limit for production usage"
        }
        
        response = client.patch(
            f"/api/v1/admin/rate-limits/{override.id}",
            json=update_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["custom_limit"] == 1000
        assert data["reason"] == "Increased limit for production usage"
    
    def test_delete_override(
        self,
        client: TestClient,
        db: Session,
        admin_user: User,
        regular_user: User,
        admin_token: str
    ):
        """Test deleting an override."""
        # Create override
        override = RateLimitOverride(
            user_id=regular_user.id,
            endpoint_pattern="/api/v1/tasks/*",
            custom_limit=500,
            created_by=admin_user.id
        )
        db.add(override)
        db.commit()
        db.refresh(override)
        
        # Delete override
        response = client.delete(
            f"/api/v1/admin/rate-limits/{override.id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 204
        
        # Verify it's deleted
        db.expire_all()
        deleted = db.query(RateLimitOverride).filter(
            RateLimitOverride.id == override.id
        ).first()
        assert deleted is None
    
    def test_get_single_override(
        self,
        client: TestClient,
        db: Session,
        admin_user: User,
        regular_user: User,
        admin_token: str
    ):
        """Test getting a single override by ID."""
        override = RateLimitOverride(
            user_id=regular_user.id,
            endpoint_pattern="/api/v1/tasks/*",
            custom_limit=500,
            created_by=admin_user.id,
            reason="Testing"
        )
        db.add(override)
        db.commit()
        db.refresh(override)
        
        response = client.get(
            f"/api/v1/admin/rate-limits/{override.id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == override.id
        assert data["custom_limit"] == 500


class TestRateLimitMiddlewareOverrides:
    """Tests for rate limit middleware with overrides."""
    
    def test_middleware_uses_override(
        self,
        client: TestClient,
        db: Session,
        admin_user: User,
        regular_user: User,
        user_token: str
    ):
        """Test that middleware uses database overrides."""
        # Create an override with very low limit for testing
        override = RateLimitOverride(
            user_id=regular_user.id,
            endpoint_pattern="/api/v1/tasks/*",
            custom_limit=5,  # Very low for easy testing
            created_by=admin_user.id
        )
        db.add(override)
        db.commit()
        
        # Make requests up to the override limit
        headers = {"Authorization": f"Bearer {user_token}"}
        
        for i in range(5):
            response = client.get("/api/v1/tasks", headers=headers)
            # Should succeed within limit
            assert response.status_code != 429
        
        # Next request should be rate limited
        response = client.get("/api/v1/tasks", headers=headers)
        assert response.status_code == 429
    
    def test_expired_override_not_used(
        self,
        client: TestClient,
        db: Session,
        admin_user: User,
        regular_user: User,
        user_token: str
    ):
        """Test that expired overrides are not used."""
        # Create an expired override
        override = RateLimitOverride(
            user_id=regular_user.id,
            endpoint_pattern="/api/v1/tasks/*",
            custom_limit=5,
            expires_at=datetime.utcnow() - timedelta(hours=1),  # Expired
            created_by=admin_user.id
        )
        db.add(override)
        db.commit()
        
        # Should use default limit, not expired override
        # (This would require more setup to test properly with actual rate limiting)
        headers = {"Authorization": f"Bearer {user_token}"}
        response = client.get("/api/v1/tasks", headers=headers)
        
        # Should not use the expired override's low limit
        assert response.headers.get("X-RateLimit-Limit") != "5"
