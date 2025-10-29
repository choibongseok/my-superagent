"""Authentication endpoints."""

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from google.auth.transport import requests
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, create_refresh_token
from app.models.user import User
from app.schemas import auth as schemas
from app.schemas.auth import GoogleAuthURL, GoogleCallback, Token

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
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Authentication failed: {str(e)}",
        )


@router.post("/google/mobile", response_model=schemas.TokenWithUser)
async def google_mobile_auth(
    auth_data: schemas.GoogleMobileAuth,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Mobile Google Sign-In authentication.
    
    Args:
        auth_data: Google ID token from mobile SDK
        db: Database session
        
    Returns:
        TokenWithUser: Access token, refresh token, and user info
    """
    try:
        # Verify ID token from Google
        idinfo = id_token.verify_oauth2_token(
            auth_data.id_token,
            requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
        
        # Extract user info
        google_id = idinfo["sub"]
        email = idinfo.get("email")
        full_name = idinfo.get("name")
        picture = idinfo.get("picture")
        
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
                google_access_token=auth_data.access_token,
            )
            db.add(user)
        else:
            # Update existing user
            if auth_data.access_token:
                user.google_access_token = auth_data.access_token
        
        await db.commit()
        await db.refresh(user)
        
        # Create JWT tokens
        access_token = create_access_token(data={"sub": str(user.id)})
        refresh_token = create_refresh_token(data={"sub": str(user.id)})
        
        # Create user response
        user_response = schemas.UserResponse(
            id=str(user.id),
            email=user.email,
            name=user.full_name or "User",
            avatarUrl=picture,
            created_at=user.created_at.isoformat(),
            isGuest=False,
        )
        
        return schemas.TokenWithUser(
            access_token=access_token,
            refresh_token=refresh_token,
            user=user_response,
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Mobile authentication failed: {str(e)}",
        )


@router.post("/guest", response_model=schemas.TokenWithUser)
async def guest_auth(
    guest_data: schemas.GuestAuth,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Guest authentication (no Google account required).
    
    Args:
        guest_data: Guest device info
        db: Database session
        
    Returns:
        TokenWithUser: Access token and guest user info
    """
    try:
        # Check if guest user already exists
        email = f"guest_{guest_data.device_id}@agenthq.local"
        
        result = await db.execute(
            select(User).where(User.email == email)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            # Create new guest user
            user = User(
                email=email,
                full_name=guest_data.name,
                is_active=True,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
        
        # Create JWT tokens
        access_token = create_access_token(data={"sub": str(user.id)})
        refresh_token = create_refresh_token(data={"sub": str(user.id)})
        
        # Create user response
        user_response = schemas.UserResponse(
            id=str(user.id),
            email=user.email,
            name=user.full_name or "Guest",
            avatarUrl=None,
            created_at=user.created_at.isoformat(),
            isGuest=True,
        )
        
        return schemas.TokenWithUser(
            access_token=access_token,
            refresh_token=refresh_token,
            user=user_response,
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Guest authentication failed: {str(e)}",
        )


@router.get("/me", response_model=schemas.UserResponse)
async def get_current_user_info(
    user: Annotated[User, Depends(get_current_user)],
):
    """
    Get current user information.
    
    Args:
        user: Current authenticated user
        
    Returns:
        UserResponse: Current user information
    """
    return schemas.UserResponse(
        id=str(user.id),
        email=user.email,
        name=user.full_name or "User",
        avatarUrl=None,  # TODO: Add avatar URL support
        created_at=user.created_at.isoformat(),
        isGuest=user.email.startswith("guest_"),
    )


@router.post("/logout")
async def logout():
    """
    Logout endpoint (client should clear tokens).
    
    Returns:
        dict: Success message
    """
    return {"message": "Logged out successfully"}


@router.post("/refresh", response_model=Token)
async def refresh_token(
    token_data: Token,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Refresh access token.
    
    Args:
        token_data: Token with refresh token
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
    )
