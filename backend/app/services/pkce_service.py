"""PKCE (Proof Key for Code Exchange) service for OAuth 2.0."""

import base64
import hashlib
import secrets
from typing import Optional, Tuple
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.core.config import settings
from app.models.pkce_challenge import PKCEChallenge


class PKCEService:
    """Service for handling PKCE operations."""
    
    @staticmethod
    def generate_code_verifier(length: int = 128) -> str:
        """
        Generate a cryptographically secure code verifier.
        
        Args:
            length: Length of the verifier (43-128 characters, default 128)
            
        Returns:
            URL-safe base64-encoded random string
        """
        if length < 43 or length > 128:
            raise ValueError("Code verifier length must be between 43 and 128")
        
        # Generate random bytes and encode as URL-safe base64
        random_bytes = secrets.token_bytes(length)
        code_verifier = base64.urlsafe_b64encode(random_bytes).decode('utf-8')
        
        # Remove padding characters
        code_verifier = code_verifier.rstrip('=')
        
        # Ensure length is within spec (43-128)
        return code_verifier[:length]
    
    @staticmethod
    def generate_code_challenge(code_verifier: str, method: str = "S256") -> str:
        """
        Generate code challenge from code verifier.
        
        Args:
            code_verifier: The code verifier
            method: Challenge method ("S256" for SHA-256, "plain" for no hashing)
            
        Returns:
            Code challenge string
        """
        if method == "S256":
            # SHA-256 hash the verifier
            sha256_hash = hashlib.sha256(code_verifier.encode('utf-8')).digest()
            # Base64 URL-safe encode
            code_challenge = base64.urlsafe_b64encode(sha256_hash).decode('utf-8')
            # Remove padding
            return code_challenge.rstrip('=')
        elif method == "plain":
            # Plain method: challenge = verifier
            return code_verifier
        else:
            raise ValueError(f"Unsupported challenge method: {method}")
    
    @staticmethod
    async def store_challenge(
        db: AsyncSession,
        state: str,
        code_challenge: str,
        code_challenge_method: str,
        redirect_uri: str,
        user_id: Optional[UUID] = None,
    ) -> PKCEChallenge:
        """
        Store PKCE challenge for later verification.
        
        Args:
            db: Database session
            state: OAuth state parameter
            code_challenge: The code challenge
            code_challenge_method: Challenge method (S256 or plain)
            redirect_uri: Redirect URI
            user_id: Optional user ID if already authenticated
            
        Returns:
            PKCEChallenge model instance
        """
        # Create challenge record with 10-minute expiration
        challenge = PKCEChallenge(
            state=state,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            redirect_uri=redirect_uri,
            user_id=user_id,
            expires_at=datetime.utcnow() + timedelta(minutes=10),
        )
        
        db.add(challenge)
        await db.commit()
        await db.refresh(challenge)
        
        return challenge
    
    @staticmethod
    async def verify_challenge(
        db: AsyncSession,
        state: str,
        code_verifier: str,
    ) -> PKCEChallenge:
        """
        Verify code verifier against stored challenge.
        
        Args:
            db: Database session
            state: OAuth state parameter
            code_verifier: Code verifier to verify
            
        Returns:
            PKCEChallenge if verification succeeds
            
        Raises:
            HTTPException: If challenge not found, expired, or verification fails
        """
        # Find challenge by state
        result = await db.execute(
            select(PKCEChallenge).where(PKCEChallenge.state == state)
        )
        challenge = result.scalar_one_or_none()
        
        if not challenge:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired PKCE challenge",
            )
        
        # Check if expired
        if challenge.expires_at < datetime.utcnow():
            await db.delete(challenge)
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="PKCE challenge expired",
            )
        
        # Check if already used
        if challenge.used:
            await db.delete(challenge)
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="PKCE challenge already used",
            )
        
        # Generate challenge from provided verifier
        computed_challenge = PKCEService.generate_code_challenge(
            code_verifier,
            challenge.code_challenge_method,
        )
        
        # Verify challenge matches
        if computed_challenge != challenge.code_challenge:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid code verifier",
            )
        
        # Mark as used
        challenge.used = True
        challenge.used_at = datetime.utcnow()
        await db.commit()
        await db.refresh(challenge)
        
        return challenge
    
    @staticmethod
    async def cleanup_expired_challenges(db: AsyncSession) -> int:
        """
        Clean up expired PKCE challenges.
        
        Args:
            db: Database session
            
        Returns:
            Number of challenges deleted
        """
        result = await db.execute(
            select(PKCEChallenge).where(
                PKCEChallenge.expires_at < datetime.utcnow()
            )
        )
        challenges = result.scalars().all()
        
        for challenge in challenges:
            await db.delete(challenge)
        
        await db.commit()
        return len(challenges)
