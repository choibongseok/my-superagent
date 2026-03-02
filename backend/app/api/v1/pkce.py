"""PKCE OAuth endpoints for mobile apps."""

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token
from app.models.user import User
from app.models.oauth_connection import OAuthConnection, OAuthProvider
from app.schemas.pkce import (
    PKCEAuthRequest,
    PKCEAuthResponse,
    PKCETokenRequest,
    PKCETokenResponse,
    PKCEStatusResponse,
)
from app.services.pkce_service import PKCEService
from app.services.oauth_service import OAuthService

router = APIRouter()


@router.get("/status", response_model=PKCEStatusResponse)
async def get_pkce_status():
    """
    Get PKCE feature status and supported providers.
    
    Returns:
        PKCEStatusResponse: PKCE configuration info
    """
    supported_providers = []
    
    if settings.GOOGLE_CLIENT_ID:
        supported_providers.append("google")
    if settings.GITHUB_CLIENT_ID:
        supported_providers.append("github")
    if settings.MICROSOFT_CLIENT_ID:
        supported_providers.append("microsoft")
    
    return PKCEStatusResponse(
        enabled=True,
        supported_providers=supported_providers,
        supported_methods=["S256", "plain"],
    )


@router.post("/authorize", response_model=PKCEAuthResponse)
async def pkce_authorize(
    request: PKCEAuthRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Initiate PKCE OAuth flow for mobile apps.
    
    Mobile app flow:
    1. Generate code_verifier (random 128-char string)
    2. Compute code_challenge = SHA256(code_verifier)
    3. Call this endpoint with code_challenge
    4. Redirect user to returned auth_url
    5. After authorization, call /pkce/token with code + code_verifier
    
    Args:
        request: PKCE authorization request with code_challenge
        db: Database session
        
    Returns:
        PKCEAuthResponse: Authorization URL and state
    """
    # Validate challenge method
    if request.code_challenge_method not in ["S256", "plain"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="code_challenge_method must be 'S256' or 'plain'",
        )
    
    # Generate state for CSRF protection
    state = secrets.token_urlsafe(32)
    
    # Store challenge for later verification
    await PKCEService.store_challenge(
        db=db,
        state=state,
        code_challenge=request.code_challenge,
        code_challenge_method=request.code_challenge_method,
        redirect_uri=request.redirect_uri,
    )
    
    # Generate authorization URL based on provider
    if request.provider == "google":
        auth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth"
            f"?client_id={settings.GOOGLE_CLIENT_ID}"
            f"&redirect_uri={request.redirect_uri}"
            f"&response_type=code"
            f"&scope=openid email profile"
            f"&state={state}"
            f"&code_challenge={request.code_challenge}"
            f"&code_challenge_method={request.code_challenge_method}"
        )
    elif request.provider == "github":
        # GitHub doesn't officially support PKCE in public docs,
        # but we can still use it client-side for security
        auth_url = (
            f"https://github.com/login/oauth/authorize"
            f"?client_id={settings.GITHUB_CLIENT_ID}"
            f"&redirect_uri={request.redirect_uri}"
            f"&scope=user:email"
            f"&state={state}"
        )
    elif request.provider == "microsoft":
        auth_url = (
            f"https://login.microsoftonline.com/{settings.MICROSOFT_TENANT_ID}/oauth2/v2.0/authorize"
            f"?client_id={settings.MICROSOFT_CLIENT_ID}"
            f"&redirect_uri={request.redirect_uri}"
            f"&response_type=code"
            f"&scope=openid email profile"
            f"&state={state}"
            f"&code_challenge={request.code_challenge}"
            f"&code_challenge_method={request.code_challenge_method}"
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider: {request.provider}",
        )
    
    return PKCEAuthResponse(
        auth_url=auth_url,
        state=state,
    )


@router.post("/token", response_model=PKCETokenResponse)
async def pkce_token(
    request: PKCETokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    http_request: Request,
):
    """
    Exchange authorization code for tokens using PKCE.
    
    This endpoint verifies the code_verifier against the stored code_challenge,
    then exchanges the authorization code for access tokens.
    
    Args:
        request: Token request with code and code_verifier
        db: Database session
        http_request: FastAPI request for client info
        
    Returns:
        PKCETokenResponse: Access and refresh tokens
    """
    # Verify code_verifier against stored challenge
    challenge = await PKCEService.verify_challenge(
        db=db,
        state=request.state,
        code_verifier=request.code_verifier,
    )
    
    # Verify redirect_uri matches
    if challenge.redirect_uri != request.redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="redirect_uri mismatch",
        )
    
    # Exchange authorization code for tokens
    # (Provider-specific token exchange logic)
    
    # For now, we'll handle Google OAuth
    async with httpx.AsyncClient() as client:
        # Exchange code for Google tokens
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": request.code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "redirect_uri": request.redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": request.code_verifier,  # PKCE parameter
            },
        )
        
        if token_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Token exchange failed: {token_response.text}",
            )
        
        token_data = token_response.json()
        google_access_token = token_data.get("access_token")
        google_refresh_token = token_data.get("refresh_token")
        
        # Get user info from Google
        user_info_response = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {google_access_token}"},
        )
        
        if user_info_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to fetch user info",
            )
        
        user_info = user_info_response.json()
    
    # Find or create user
    google_id = user_info.get("id")
    email = user_info.get("email")
    full_name = user_info.get("name")
    
    result = await db.execute(
        select(User).where(User.google_id == google_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        # Create new user
        user = User(
            google_id=google_id,
            email=email,
            full_name=full_name,
            google_access_token=google_access_token,
            google_refresh_token=google_refresh_token,
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    else:
        # Update existing user tokens
        user.google_access_token = google_access_token
        if google_refresh_token:
            user.google_refresh_token = google_refresh_token
        await db.commit()
        await db.refresh(user)
    
    # Create OAuth connection record
    result = await db.execute(
        select(OAuthConnection).where(
            OAuthConnection.user_id == user.id,
            OAuthConnection.provider == OAuthProvider.GOOGLE,
        )
    )
    oauth_connection = result.scalar_one_or_none()
    
    if not oauth_connection:
        oauth_connection = OAuthConnection(
            user_id=user.id,
            provider=OAuthProvider.GOOGLE,
            provider_user_id=google_id,
            access_token=google_access_token,
            refresh_token=google_refresh_token,
        )
        db.add(oauth_connection)
    else:
        oauth_connection.access_token = google_access_token
        if google_refresh_token:
            oauth_connection.refresh_token = google_refresh_token
    
    await db.commit()
    
    # Create JWT access token
    access_token = create_access_token(data={"sub": str(user.id)})
    
    # Create refresh token
    device_id = http_request.headers.get("X-Device-ID")
    user_agent = http_request.headers.get("User-Agent")
    ip_address = http_request.client.host if http_request.client else None
    
    refresh_token_raw, _ = await OAuthService.create_refresh_token(
        db=db,
        user_id=user.id,
        device_id=device_id,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    
    return PKCETokenResponse(
        access_token=access_token,
        refresh_token=refresh_token_raw,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user_id=str(user.id),
        email=user.email,
    )
