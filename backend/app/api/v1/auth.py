"""Authentication endpoints."""

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from google.auth.transport import requests
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, create_refresh_token
from app.models.user import User
from app.api.dependencies import get_current_user
from app.schemas.auth import (
    GoogleAuthURL,
    GoogleCallback,
    GoogleMobileAuth,
    GuestAuth,
    RefreshTokenRequest,
    Token,
    UserInfo,
)

router = APIRouter()


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


@router.get("/google", response_model=GoogleAuthURL)
async def google_auth():
    """
    Initiate Google OAuth flow.
    
    Returns:
        GoogleAuthURL: Authorization URL for user to visit
    """
    flow = get_google_oauth_flow()
    
    # Generate state token for CSRF protection
    state = secrets.token_urlsafe(32)
    
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=state,
        prompt="consent",
    )
    
    return GoogleAuthURL(auth_url=authorization_url)


@router.post("/callback", response_model=Token)
async def google_callback(
    callback_data: GoogleCallback,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Handle Google OAuth callback.
    
    Args:
        callback_data: OAuth callback data
        db: Database session
        
    Returns:
        Token: Access and refresh tokens
    """
    try:
        # Exchange authorization code for tokens
        flow = get_google_oauth_flow()
        flow.fetch_token(code=callback_data.code)
        
        credentials = flow.credentials
        
        # Verify ID token
        idinfo = id_token.verify_oauth2_token(
            credentials.id_token,
            requests.Request(),
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
                google_access_token=credentials.token,
                google_refresh_token=credentials.refresh_token,
            )
            db.add(user)
        else:
            # Update existing user
            user.google_access_token = credentials.token
            if credentials.refresh_token:
                user.google_refresh_token = credentials.refresh_token
        
        await db.commit()
        await db.refresh(user)
        
        # Create JWT tokens
        access_token = create_access_token(data={"sub": str(user.id)})
        refresh_token = create_refresh_token(data={"sub": str(user.id)})

        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            user=UserInfo.model_validate(user),
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Authentication failed: {str(e)}",
        )


@router.post("/google/mobile", response_model=Token)
async def google_mobile_auth(
    mobile_auth: GoogleMobileAuth,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Handle Google OAuth for mobile apps.
    Mobile apps send id_token and access_token directly from Google Sign-In SDK.
    
    Args:
        mobile_auth: Google tokens from mobile SDK
        db: Database session
        
    Returns:
        Token: Access and refresh tokens
    """
    try:
        # Verify ID token from mobile client
        idinfo = id_token.verify_oauth2_token(
            mobile_auth.id_token,
            requests.Request(),
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
                google_access_token=mobile_auth.access_token,
                # Mobile flow doesn't provide refresh token, 
                # but we can use the access token
            )
            db.add(user)
        else:
            # Update existing user tokens
            user.google_access_token = mobile_auth.access_token
        
        await db.commit()
        await db.refresh(user)
        
        # Create JWT tokens for our backend
        access_token = create_access_token(data={"sub": str(user.id)})
        refresh_token = create_refresh_token(data={"sub": str(user.id)})

        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            user=UserInfo.model_validate(user),
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Mobile authentication failed: {str(e)}",
        )


@router.post("/guest", response_model=Token)
async def guest_auth(
    guest_data: GuestAuth,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Create a guest session for mobile users without Google account.
    
    Args:
        guest_data: Guest device info (device_id, name)
        db: Database session
        
    Returns:
        Token: Access and refresh tokens for guest session
    """
    try:
        device_id = guest_data.device_id
        guest_name = guest_data.name or "Guest User"
        
        if not device_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Device ID required for guest mode",
            )
        
        # Check if guest user already exists for this device
        result = await db.execute(
            select(User).where(
                User.email == f"guest_{device_id}@agenthq.local"
            )
        )
        user = result.scalar_one_or_none()
        
        if not user:
            # Create new guest user
            user = User(
                email=f"guest_{device_id}@agenthq.local",
                full_name=guest_name,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
        
        # Create JWT tokens
        access_token = create_access_token(data={"sub": str(user.id)})
        refresh_token = create_refresh_token(data={"sub": str(user.id)})

        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            user=UserInfo.model_validate(user),
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Guest authentication failed: {str(e)}",
        )


@router.get("/me", response_model=UserInfo)
async def get_current_user_info(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    Get current authenticated user information.
    
    Args:
        current_user: Current user from JWT token
        
    Returns:
        UserInfo: Current user information
    """
    return UserInfo.model_validate(current_user)


@router.post("/logout")
async def logout(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    Logout endpoint (client should clear tokens).
    Backend doesn't maintain session state, so this is mainly for logging/cleanup.
    
    Args:
        current_user: Current user from JWT token
        
    Returns:
        Success message
    """
    return {"message": "Logged out successfully"}


@router.post("/refresh", response_model=Token)
async def refresh_token(
    token_data: RefreshTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Refresh access token.

    Args:
        token_data: Refresh token payload
        db: Database session

    Returns:
        Token: New access and refresh tokens
    """
    from app.core.security import decode_token
    
    payload = decode_token(token_data.refresh_token)
    
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    
    user_id = payload.get("sub")
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
    
    # Verify user exists
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    
    # Create new tokens
    access_token = create_access_token(data={"sub": user_id})
    new_refresh_token = create_refresh_token(data={"sub": user_id})

    return Token(
        access_token=access_token,
        refresh_token=new_refresh_token,
        user=UserInfo.model_validate(user),
    )
