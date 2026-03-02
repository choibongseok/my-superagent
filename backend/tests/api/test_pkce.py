"""Tests for PKCE OAuth implementation."""

import base64
import hashlib
import secrets
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.pkce_challenge import PKCEChallenge
from app.models.user import User
from app.services.pkce_service import PKCEService


class TestPKCEService:
    """Test PKCE service functions."""
    
    def test_generate_code_verifier(self):
        """Test code verifier generation."""
        verifier = PKCEService.generate_code_verifier()
        
        # Should be 128 characters
        assert len(verifier) == 128
        
        # Should be URL-safe
        assert all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_' for c in verifier)
        
        # Should be different on each call
        verifier2 = PKCEService.generate_code_verifier()
        assert verifier != verifier2
    
    def test_generate_code_verifier_custom_length(self):
        """Test code verifier generation with custom length."""
        verifier = PKCEService.generate_code_verifier(length=64)
        assert len(verifier) == 64
    
    def test_generate_code_verifier_invalid_length(self):
        """Test code verifier generation with invalid length."""
        with pytest.raises(ValueError):
            PKCEService.generate_code_verifier(length=42)  # Too short
        
        with pytest.raises(ValueError):
            PKCEService.generate_code_verifier(length=200)  # Too long
    
    def test_generate_code_challenge_s256(self):
        """Test code challenge generation with S256 method."""
        verifier = "test_verifier_123"
        challenge = PKCEService.generate_code_challenge(verifier, method="S256")
        
        # Manually compute expected challenge
        sha256_hash = hashlib.sha256(verifier.encode('utf-8')).digest()
        expected_challenge = base64.urlsafe_b64encode(sha256_hash).decode('utf-8').rstrip('=')
        
        assert challenge == expected_challenge
    
    def test_generate_code_challenge_plain(self):
        """Test code challenge generation with plain method."""
        verifier = "test_verifier_123"
        challenge = PKCEService.generate_code_challenge(verifier, method="plain")
        
        # Plain method: challenge = verifier
        assert challenge == verifier
    
    def test_generate_code_challenge_invalid_method(self):
        """Test code challenge generation with invalid method."""
        with pytest.raises(ValueError):
            PKCEService.generate_code_challenge("verifier", method="invalid")
    
    @pytest.mark.asyncio
    async def test_store_challenge(self, db_session):
        """Test storing PKCE challenge."""
        state = secrets.token_urlsafe(32)
        code_challenge = "test_challenge"
        redirect_uri = "https://example.com/callback"
        
        challenge = await PKCEService.store_challenge(
            db=db_session,
            state=state,
            code_challenge=code_challenge,
            code_challenge_method="S256",
            redirect_uri=redirect_uri,
        )
        
        assert challenge.state == state
        assert challenge.code_challenge == code_challenge
        assert challenge.code_challenge_method == "S256"
        assert challenge.redirect_uri == redirect_uri
        assert challenge.used is False
        assert challenge.expires_at > datetime.utcnow()
    
    @pytest.mark.asyncio
    async def test_verify_challenge_success(self, db_session):
        """Test successful challenge verification."""
        # Generate verifier and challenge
        verifier = PKCEService.generate_code_verifier()
        challenge_str = PKCEService.generate_code_challenge(verifier, method="S256")
        
        state = secrets.token_urlsafe(32)
        redirect_uri = "https://example.com/callback"
        
        # Store challenge
        await PKCEService.store_challenge(
            db=db_session,
            state=state,
            code_challenge=challenge_str,
            code_challenge_method="S256",
            redirect_uri=redirect_uri,
        )
        
        # Verify challenge
        result = await PKCEService.verify_challenge(
            db=db_session,
            state=state,
            code_verifier=verifier,
        )
        
        assert result.state == state
        assert result.used is True
        assert result.used_at is not None
    
    @pytest.mark.asyncio
    async def test_verify_challenge_invalid_verifier(self, db_session):
        """Test challenge verification with invalid verifier."""
        verifier = PKCEService.generate_code_verifier()
        challenge_str = PKCEService.generate_code_challenge(verifier, method="S256")
        
        state = secrets.token_urlsafe(32)
        redirect_uri = "https://example.com/callback"
        
        # Store challenge
        await PKCEService.store_challenge(
            db=db_session,
            state=state,
            code_challenge=challenge_str,
            code_challenge_method="S256",
            redirect_uri=redirect_uri,
        )
        
        # Try to verify with wrong verifier
        wrong_verifier = PKCEService.generate_code_verifier()
        
        with pytest.raises(Exception):  # Should raise HTTPException
            await PKCEService.verify_challenge(
                db=db_session,
                state=state,
                code_verifier=wrong_verifier,
            )
    
    @pytest.mark.asyncio
    async def test_verify_challenge_expired(self, db_session):
        """Test challenge verification with expired challenge."""
        verifier = PKCEService.generate_code_verifier()
        challenge_str = PKCEService.generate_code_challenge(verifier, method="S256")
        
        state = secrets.token_urlsafe(32)
        redirect_uri = "https://example.com/callback"
        
        # Store challenge with past expiration
        challenge = PKCEChallenge(
            state=state,
            code_challenge=challenge_str,
            code_challenge_method="S256",
            redirect_uri=redirect_uri,
            expires_at=datetime.utcnow() - timedelta(minutes=1),  # Expired
        )
        db_session.add(challenge)
        await db_session.commit()
        
        # Try to verify expired challenge
        with pytest.raises(Exception):  # Should raise HTTPException
            await PKCEService.verify_challenge(
                db=db_session,
                state=state,
                code_verifier=verifier,
            )
    
    @pytest.mark.asyncio
    async def test_verify_challenge_reuse_protection(self, db_session):
        """Test that used challenges cannot be reused."""
        verifier = PKCEService.generate_code_verifier()
        challenge_str = PKCEService.generate_code_challenge(verifier, method="S256")
        
        state = secrets.token_urlsafe(32)
        redirect_uri = "https://example.com/callback"
        
        # Store challenge
        await PKCEService.store_challenge(
            db=db_session,
            state=state,
            code_challenge=challenge_str,
            code_challenge_method="S256",
            redirect_uri=redirect_uri,
        )
        
        # Verify once (should succeed)
        await PKCEService.verify_challenge(
            db=db_session,
            state=state,
            code_verifier=verifier,
        )
        
        # Try to verify again (should fail)
        with pytest.raises(Exception):  # Should raise HTTPException
            await PKCEService.verify_challenge(
                db=db_session,
                state=state,
                code_verifier=verifier,
            )
    
    @pytest.mark.asyncio
    async def test_cleanup_expired_challenges(self, db_session):
        """Test cleanup of expired challenges."""
        # Create expired challenge
        expired_challenge = PKCEChallenge(
            state="expired_state",
            code_challenge="expired_challenge",
            code_challenge_method="S256",
            redirect_uri="https://example.com/callback",
            expires_at=datetime.utcnow() - timedelta(minutes=1),
        )
        db_session.add(expired_challenge)
        
        # Create valid challenge
        valid_challenge = PKCEChallenge(
            state="valid_state",
            code_challenge="valid_challenge",
            code_challenge_method="S256",
            redirect_uri="https://example.com/callback",
            expires_at=datetime.utcnow() + timedelta(minutes=10),
        )
        db_session.add(valid_challenge)
        
        await db_session.commit()
        
        # Cleanup expired
        deleted_count = await PKCEService.cleanup_expired_challenges(db_session)
        
        assert deleted_count == 1
        
        # Verify expired is gone, valid remains
        result = await db_session.execute(
            select(PKCEChallenge).where(PKCEChallenge.state == "expired_state")
        )
        assert result.scalar_one_or_none() is None
        
        result = await db_session.execute(
            select(PKCEChallenge).where(PKCEChallenge.state == "valid_state")
        )
        assert result.scalar_one_or_none() is not None


class TestPKCEEndpoints:
    """Test PKCE API endpoints."""
    
    @pytest.mark.asyncio
    async def test_get_pkce_status(self, async_client: AsyncClient):
        """Test PKCE status endpoint."""
        response = await async_client.get("/api/v1/pkce/status")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["enabled"] is True
        assert "google" in data["supported_providers"]
        assert "S256" in data["supported_methods"]
        assert "plain" in data["supported_methods"]
    
    @pytest.mark.asyncio
    async def test_pkce_authorize_google(self, async_client: AsyncClient):
        """Test PKCE authorization endpoint for Google."""
        verifier = PKCEService.generate_code_verifier()
        challenge = PKCEService.generate_code_challenge(verifier, method="S256")
        
        response = await async_client.post(
            "/api/v1/pkce/authorize",
            json={
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "redirect_uri": "https://example.com/callback",
                "provider": "google",
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "auth_url" in data
        assert "state" in data
        assert "accounts.google.com" in data["auth_url"]
        assert challenge in data["auth_url"]
        assert "code_challenge_method=S256" in data["auth_url"]
    
    @pytest.mark.asyncio
    async def test_pkce_authorize_invalid_method(self, async_client: AsyncClient):
        """Test PKCE authorization with invalid challenge method."""
        response = await async_client.post(
            "/api/v1/pkce/authorize",
            json={
                "code_challenge": "test_challenge",
                "code_challenge_method": "invalid",
                "redirect_uri": "https://example.com/callback",
                "provider": "google",
            },
        )
        
        assert response.status_code == 400
        assert "code_challenge_method" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_pkce_authorize_unsupported_provider(self, async_client: AsyncClient):
        """Test PKCE authorization with unsupported provider."""
        verifier = PKCEService.generate_code_verifier()
        challenge = PKCEService.generate_code_challenge(verifier, method="S256")
        
        response = await async_client.post(
            "/api/v1/pkce/authorize",
            json={
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "redirect_uri": "https://example.com/callback",
                "provider": "facebook",  # Not supported
            },
        )
        
        assert response.status_code == 400
        assert "Unsupported provider" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_pkce_token_exchange_success(self, async_client: AsyncClient, db_session):
        """Test successful PKCE token exchange."""
        verifier = PKCEService.generate_code_verifier()
        challenge = PKCEService.generate_code_challenge(verifier, method="S256")
        state = secrets.token_urlsafe(32)
        redirect_uri = "https://example.com/callback"
        
        # Store challenge
        await PKCEService.store_challenge(
            db=db_session,
            state=state,
            code_challenge=challenge,
            code_challenge_method="S256",
            redirect_uri=redirect_uri,
        )
        
        # Mock Google OAuth responses
        mock_token_response = {
            "access_token": "mock_access_token",
            "refresh_token": "mock_refresh_token",
            "expires_in": 3600,
        }
        
        mock_user_info = {
            "id": "123456789",
            "email": "test@example.com",
            "name": "Test User",
        }
        
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
             patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            
            # Mock token exchange response
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = mock_token_response
            
            # Mock user info response
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = mock_user_info
            
            # Exchange code for tokens
            response = await async_client.post(
                "/api/v1/pkce/token",
                json={
                    "code": "mock_authorization_code",
                    "code_verifier": verifier,
                    "state": state,
                    "redirect_uri": redirect_uri,
                },
            )
            
            assert response.status_code == 200
            data = response.json()
            
            assert "access_token" in data
            assert "refresh_token" in data
            assert data["token_type"] == "bearer"
            assert data["email"] == "test@example.com"
    
    @pytest.mark.asyncio
    async def test_pkce_token_exchange_redirect_uri_mismatch(self, async_client: AsyncClient, db_session):
        """Test PKCE token exchange with mismatched redirect_uri."""
        verifier = PKCEService.generate_code_verifier()
        challenge = PKCEService.generate_code_challenge(verifier, method="S256")
        state = secrets.token_urlsafe(32)
        original_redirect_uri = "https://example.com/callback"
        wrong_redirect_uri = "https://evil.com/callback"
        
        # Store challenge with original redirect_uri
        await PKCEService.store_challenge(
            db=db_session,
            state=state,
            code_challenge=challenge,
            code_challenge_method="S256",
            redirect_uri=original_redirect_uri,
        )
        
        # Try to exchange with different redirect_uri
        response = await async_client.post(
            "/api/v1/pkce/token",
            json={
                "code": "mock_authorization_code",
                "code_verifier": verifier,
                "state": state,
                "redirect_uri": wrong_redirect_uri,  # Mismatch!
            },
        )
        
        assert response.status_code == 400
        assert "redirect_uri mismatch" in response.json()["detail"]


@pytest.fixture
async def db_session():
    """Database session fixture for testing."""
    # This would be provided by your test setup
    # For now, this is a placeholder
    pass


@pytest.fixture
async def async_client():
    """Async HTTP client fixture for testing."""
    # This would be provided by your test setup
    pass
