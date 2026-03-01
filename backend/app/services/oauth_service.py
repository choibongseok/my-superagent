"""Enhanced OAuth service with multi-provider support and token rotation."""

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from google_auth_oauthlib.flow import Flow
import httpx
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.encryption import encrypt_token, decrypt_token
from app.core.security import create_access_token
from app.models.user import User
from app.models.oauth_connection import OAuthConnection, OAuthProvider
from app.models.refresh_token import RefreshToken


class OAuthService:
    """Service for handling OAuth operations with multiple providers."""
    
    @staticmethod
    def _hash_token(token: str) -> str:
        """Create a secure hash of a token for storage."""
        return hashlib.sha256(token.encode()).hexdigest()
    
    @staticmethod
    async def create_refresh_token(
        db: AsyncSession,
        user_id: UUID,
        device_id: Optional[str] = None,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
        token_family: Optional[UUID] = None,
        previous_token_id: Optional[UUID] = None,
    ) -> Tuple[str, RefreshToken]:
        """
        Create a new refresh token with rotation support.
        
        Args:
            db: Database session
            user_id: User ID
            device_id: Device identifier
            user_agent: User agent string
            ip_address: IP address
            token_family: Token family UUID for rotation chain
            previous_token_id: ID of the previous token in the rotation chain
            
        Returns:
            Tuple[str, RefreshToken]: Raw token and RefreshToken model
        """
        # Generate cryptographically secure random token
        raw_token = secrets.token_urlsafe(32)
        token_hash = OAuthService._hash_token(raw_token)
        
        # Create refresh token record
        refresh_token = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=datetime.utcnow() + timedelta(
                days=settings.REFRESH_TOKEN_EXPIRE_DAYS
            ),
            device_id=device_id,
            user_agent=user_agent,
            ip_address=ip_address,
            token_family=token_family or None,
            previous_token_id=previous_token_id,
        )
        
        db.add(refresh_token)
        await db.commit()
        await db.refresh(refresh_token)
        
        return raw_token, refresh_token
    
    @staticmethod
    async def verify_and_rotate_refresh_token(
        db: AsyncSession,
        raw_token: str,
        device_id: Optional[str] = None,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Tuple[User, str, str]:
        """
        Verify a refresh token and rotate it (issue new one, revoke old one).
        
        Implements automatic reuse detection: if a revoked token is used,
        revoke the entire token family for security.
        
        Args:
            db: Database session
            raw_token: Raw refresh token to verify
            device_id: Device identifier
            user_agent: User agent string
            ip_address: IP address
            
        Returns:
            Tuple[User, str, str]: User, new access token, new refresh token
            
        Raises:
            HTTPException: If token is invalid or revoked
        """
        token_hash = OAuthService._hash_token(raw_token)
        
        # Find the token
        result = await db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash
            )
        )
        token = result.scalar_one_or_none()
        
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )
        
        # Check if token was already used (reuse detection)
        if token.is_revoked:
            # Security breach! Revoke entire token family
            await db.execute(
                RefreshToken.__table__.update()
                .where(RefreshToken.token_family == token.token_family)
                .values(is_revoked=True, revoked_at=datetime.utcnow())
            )
            await db.commit()
            
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token reuse detected. All tokens in family revoked.",
            )
        
        # Check if token is expired
        if token.is_expired:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token expired",
            )
        
        # Get the user
        result = await db.execute(
            select(User).where(User.id == token.user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
            )
        
        # Revoke the current token
        token.is_revoked = True
        token.revoked_at = datetime.utcnow()
        
        # Create new refresh token (rotate)
        new_raw_token, new_refresh_token = await OAuthService.create_refresh_token(
            db=db,
            user_id=user.id,
            device_id=device_id,
            user_agent=user_agent,
            ip_address=ip_address,
            token_family=token.token_family,
            previous_token_id=token.id,
        )
        
        # Create new access token
        access_token = create_access_token(data={"sub": str(user.id)})
        
        await db.commit()
        
        return user, access_token, new_raw_token
    
    @staticmethod
    async def revoke_refresh_token(
        db: AsyncSession,
        raw_token: str,
    ) -> None:
        """
        Revoke a refresh token (logout).
        
        Args:
            db: Database session
            raw_token: Raw refresh token to revoke
        """
        token_hash = OAuthService._hash_token(raw_token)
        
        result = await db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash
            )
        )
        token = result.scalar_one_or_none()
        
        if token:
            token.is_revoked = True
            token.revoked_at = datetime.utcnow()
            await db.commit()
    
    @staticmethod
    async def revoke_all_user_tokens(
        db: AsyncSession,
        user_id: UUID,
    ) -> None:
        """
        Revoke all refresh tokens for a user.
        
        Args:
            db: Database session
            user_id: User ID
        """
        await db.execute(
            RefreshToken.__table__.update()
            .where(RefreshToken.user_id == user_id)
            .values(is_revoked=True, revoked_at=datetime.utcnow())
        )
        await db.commit()
    
    @staticmethod
    async def cleanup_expired_tokens(db: AsyncSession) -> int:
        """
        Clean up expired and old revoked tokens.
        
        Args:
            db: Database session
            
        Returns:
            int: Number of tokens deleted
        """
        # Delete tokens that are expired or revoked more than 30 days ago
        cutoff_date = datetime.utcnow() - timedelta(days=30)
        
        result = await db.execute(
            select(RefreshToken).where(
                or_(
                    RefreshToken.expires_at < datetime.utcnow(),
                    (RefreshToken.is_revoked == True) & (RefreshToken.revoked_at < cutoff_date),
                )
            )
        )
        tokens = result.scalars().all()
        
        for token in tokens:
            await db.delete(token)
        
        await db.commit()
        return len(tokens)
    
    @staticmethod
    def get_google_oauth_flow():
        """Create Google OAuth flow."""
        return Flow.from_client_config(
            {
                "web": {
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
                }
            },
            scopes=settings.google_scopes_list,
            redirect_uri=settings.GOOGLE_REDIRECT_URI,
        )
    
    @staticmethod
    async def authenticate_google(
        db: AsyncSession,
        code: str,
        device_id: Optional[str] = None,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Tuple[User, str, str]:
        """
        Authenticate user with Google OAuth.
        
        Args:
            db: Database session
            code: OAuth authorization code
            device_id: Device identifier
            user_agent: User agent string
            ip_address: IP address
            
        Returns:
            Tuple[User, str, str]: User, access token, refresh token
        """
        try:
            # Exchange authorization code for tokens
            flow = OAuthService.get_google_oauth_flow()
            flow.fetch_token(code=code)
            
            credentials = flow.credentials
            
            # Verify ID token
            idinfo = google_id_token.verify_oauth2_token(
                credentials.id_token,
                google_requests.Request(),
                settings.GOOGLE_CLIENT_ID,
            )
            
            # Extract user info
            google_id = idinfo["sub"]
            email = idinfo.get("email")
            full_name = idinfo.get("name")
            
            if not email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email not provided by Google",
                )
            
            # Find or create user
            result = await db.execute(
                select(User).where(User.google_id == google_id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                # Create new user
                user = User(
                    email=email,
                    full_name=full_name,
                    google_id=google_id,
                )
                db.add(user)
                await db.flush()
            
            # Store or update OAuth connection with encrypted tokens
            result = await db.execute(
                select(OAuthConnection).where(
                    OAuthConnection.user_id == user.id,
                    OAuthConnection.provider == OAuthProvider.GOOGLE,
                )
            )
            connection = result.scalar_one_or_none()
            
            if not connection:
                connection = OAuthConnection(
                    user_id=user.id,
                    provider=OAuthProvider.GOOGLE,
                    provider_user_id=google_id,
                    email=email,
                )
                db.add(connection)
            
            # Encrypt and store tokens
            connection.access_token_encrypted = encrypt_token(credentials.token)
            if credentials.refresh_token:
                connection.refresh_token_encrypted = encrypt_token(
                    credentials.refresh_token
                )
            connection.last_used_at = datetime.utcnow()
            
            # Store token expiry if available
            if credentials.expiry:
                connection.token_expires_at = credentials.expiry
            
            await db.commit()
            await db.refresh(user)
            
            # Create JWT tokens with rotation support
            access_token = create_access_token(data={"sub": str(user.id)})
            raw_refresh_token, _ = await OAuthService.create_refresh_token(
                db=db,
                user_id=user.id,
                device_id=device_id,
                user_agent=user_agent,
                ip_address=ip_address,
            )
            
            return user, access_token, raw_refresh_token
            
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Authentication failed: {str(e)}",
            )
    
    @staticmethod
    async def authenticate_github(
        db: AsyncSession,
        code: str,
        device_id: Optional[str] = None,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Tuple[User, str, str]:
        """
        Authenticate user with GitHub OAuth.
        
        Args:
            db: Database session
            code: OAuth authorization code
            device_id: Device identifier
            user_agent: User agent string
            ip_address: IP address
            
        Returns:
            Tuple[User, str, str]: User, access token, refresh token
        """
        try:
            # Exchange code for access token
            async with httpx.AsyncClient() as client:
                token_response = await client.post(
                    "https://github.com/login/oauth/access_token",
                    data={
                        "client_id": settings.GITHUB_CLIENT_ID,
                        "client_secret": settings.GITHUB_CLIENT_SECRET,
                        "code": code,
                    },
                    headers={"Accept": "application/json"},
                )
                token_response.raise_for_status()
                token_data = token_response.json()
                
                access_token_raw = token_data.get("access_token")
                if not access_token_raw:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Failed to get access token from GitHub",
                    )
                
                # Get user info
                user_response = await client.get(
                    "https://api.github.com/user",
                    headers={
                        "Authorization": f"Bearer {access_token_raw}",
                        "Accept": "application/json",
                    },
                )
                user_response.raise_for_status()
                github_user = user_response.json()
                
                # Get user email if not public
                email = github_user.get("email")
                if not email:
                    email_response = await client.get(
                        "https://api.github.com/user/emails",
                        headers={
                            "Authorization": f"Bearer {access_token_raw}",
                            "Accept": "application/json",
                        },
                    )
                    email_response.raise_for_status()
                    emails = email_response.json()
                    
                    # Find primary verified email
                    for e in emails:
                        if e.get("primary") and e.get("verified"):
                            email = e.get("email")
                            break
                
                if not email:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="No verified email found in GitHub account",
                    )
                
                github_id = str(github_user["id"])
                full_name = github_user.get("name") or github_user.get("login")
                
                # Find or create user by email
                result = await db.execute(
                    select(User).where(User.email == email)
                )
                user = result.scalar_one_or_none()
                
                if not user:
                    # Create new user
                    user = User(
                        email=email,
                        full_name=full_name,
                    )
                    db.add(user)
                    await db.flush()
                
                # Store or update OAuth connection
                result = await db.execute(
                    select(OAuthConnection).where(
                        OAuthConnection.user_id == user.id,
                        OAuthConnection.provider == OAuthProvider.GITHUB,
                    )
                )
                connection = result.scalar_one_or_none()
                
                if not connection:
                    connection = OAuthConnection(
                        user_id=user.id,
                        provider=OAuthProvider.GITHUB,
                        provider_user_id=github_id,
                        email=email,
                    )
                    db.add(connection)
                
                # Encrypt and store token
                connection.access_token_encrypted = encrypt_token(access_token_raw)
                connection.last_used_at = datetime.utcnow()
                
                await db.commit()
                await db.refresh(user)
                
                # Create JWT tokens
                access_token = create_access_token(data={"sub": str(user.id)})
                raw_refresh_token, _ = await OAuthService.create_refresh_token(
                    db=db,
                    user_id=user.id,
                    device_id=device_id,
                    user_agent=user_agent,
                    ip_address=ip_address,
                )
                
                return user, access_token, raw_refresh_token
                
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"GitHub authentication failed: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Authentication failed: {str(e)}",
            )
    
    @staticmethod
    async def authenticate_microsoft(
        db: AsyncSession,
        code: str,
        device_id: Optional[str] = None,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Tuple[User, str, str]:
        """
        Authenticate user with Microsoft OAuth.
        
        Args:
            db: Database session
            code: OAuth authorization code
            device_id: Device identifier
            user_agent: User agent string
            ip_address: IP address
            
        Returns:
            Tuple[User, str, str]: User, access token, refresh token
        """
        try:
            # Exchange code for access token
            async with httpx.AsyncClient() as client:
                token_response = await client.post(
                    f"https://login.microsoftonline.com/{settings.MICROSOFT_TENANT_ID}/oauth2/v2.0/token",
                    data={
                        "client_id": settings.MICROSOFT_CLIENT_ID,
                        "client_secret": settings.MICROSOFT_CLIENT_SECRET,
                        "code": code,
                        "redirect_uri": settings.MICROSOFT_REDIRECT_URI,
                        "grant_type": "authorization_code",
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                token_response.raise_for_status()
                token_data = token_response.json()
                
                access_token_raw = token_data.get("access_token")
                refresh_token_raw = token_data.get("refresh_token")
                
                if not access_token_raw:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Failed to get access token from Microsoft",
                    )
                
                # Get user info from Microsoft Graph
                user_response = await client.get(
                    "https://graph.microsoft.com/v1.0/me",
                    headers={
                        "Authorization": f"Bearer {access_token_raw}",
                        "Accept": "application/json",
                    },
                )
                user_response.raise_for_status()
                ms_user = user_response.json()
                
                ms_id = ms_user["id"]
                email = ms_user.get("mail") or ms_user.get("userPrincipalName")
                full_name = ms_user.get("displayName")
                
                if not email:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Email not provided by Microsoft",
                    )
                
                # Find or create user by email
                result = await db.execute(
                    select(User).where(User.email == email)
                )
                user = result.scalar_one_or_none()
                
                if not user:
                    # Create new user
                    user = User(
                        email=email,
                        full_name=full_name,
                    )
                    db.add(user)
                    await db.flush()
                
                # Store or update OAuth connection
                result = await db.execute(
                    select(OAuthConnection).where(
                        OAuthConnection.user_id == user.id,
                        OAuthConnection.provider == OAuthProvider.MICROSOFT,
                    )
                )
                connection = result.scalar_one_or_none()
                
                if not connection:
                    connection = OAuthConnection(
                        user_id=user.id,
                        provider=OAuthProvider.MICROSOFT,
                        provider_user_id=ms_id,
                        email=email,
                    )
                    db.add(connection)
                
                # Encrypt and store tokens
                connection.access_token_encrypted = encrypt_token(access_token_raw)
                if refresh_token_raw:
                    connection.refresh_token_encrypted = encrypt_token(refresh_token_raw)
                connection.last_used_at = datetime.utcnow()
                
                # Store expiry if available
                if token_data.get("expires_in"):
                    connection.token_expires_at = datetime.utcnow() + timedelta(
                        seconds=token_data["expires_in"]
                    )
                
                await db.commit()
                await db.refresh(user)
                
                # Create JWT tokens
                access_token = create_access_token(data={"sub": str(user.id)})
                raw_refresh_token, _ = await OAuthService.create_refresh_token(
                    db=db,
                    user_id=user.id,
                    device_id=device_id,
                    user_agent=user_agent,
                    ip_address=ip_address,
                )
                
                return user, access_token, raw_refresh_token
                
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Microsoft authentication failed: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Authentication failed: {str(e)}",
            )
