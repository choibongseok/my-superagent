"""Enhanced authentication endpoints with multi-provider OAuth and token rotation."""

import json
import secrets
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.api.dependencies import get_current_user
from app.models.user import User
from app.models.oauth_connection import OAuthConnection, OAuthProvider
from app.schemas.auth import (
    GoogleAuthURL,
    GoogleCallback,
    GoogleMobileAuth,
    GitHubCallback,
    MicrosoftCallback,
    GuestAuth,
    RefreshTokenRequest,
    Token,
    UserInfo,
    OAuthProviderInfo,
)
from app.services.oauth_service import OAuthService

router = APIRouter()


def _get_client_info(request: Request) -> tuple:
    """Extract client info from request for security auditing."""
    device_id = request.headers.get("X-Device-ID")
    user_agent = request.headers.get("User-Agent")
    ip_address = request.client.host if request.client else None
    return device_id, user_agent, ip_address


@router.get("/google", response_model=GoogleAuthURL)
async def google_auth():
    """
    Initiate Google OAuth flow.
    
    Returns:
        GoogleAuthURL: Authorization URL for user to visit
    """
    flow = OAuthService.get_google_oauth_flow()
    
    # Generate state token for CSRF protection
    state = secrets.token_urlsafe(32)
    
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=state,
        prompt="consent",
    )
    
    return GoogleAuthURL(auth_url=authorization_url)


@router.get("/github", response_model=GoogleAuthURL)
async def github_auth():
    """
    Initiate GitHub OAuth flow.
    
    Returns:
        GoogleAuthURL: Authorization URL for user to visit
    """
    state = secrets.token_urlsafe(32)
    
    # GitHub OAuth URL
    authorization_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={settings.GITHUB_CLIENT_ID}"
        f"&redirect_uri={settings.GITHUB_REDIRECT_URI}"
        f"&scope=user:email"
        f"&state={state}"
    )
    
    return GoogleAuthURL(auth_url=authorization_url)


@router.get("/microsoft", response_model=GoogleAuthURL)
async def microsoft_auth():
    """
    Initiate Microsoft OAuth flow.
    
    Returns:
        GoogleAuthURL: Authorization URL for user to visit
    """
    state = secrets.token_urlsafe(32)
    
    # Microsoft OAuth URL
    authorization_url = (
        f"https://login.microsoftonline.com/{settings.MICROSOFT_TENANT_ID}/oauth2/v2.0/authorize"
        f"?client_id={settings.MICROSOFT_CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={settings.MICROSOFT_REDIRECT_URI}"
        f"&response_mode=query"
        f"&scope=openid%20profile%20email%20User.Read"
        f"&state={state}"
    )
    
    return GoogleAuthURL(auth_url=authorization_url)


@router.get("/callback", response_class=HTMLResponse)
async def google_callback_redirect(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
):
    """
    OAuth redirect landing page for browser-based login flows.
    Works for Google, GitHub, and Microsoft OAuth flows.
    """
    payload = {
        "type": "agenthq:oauth:callback",
        "code": code,
        "state": state,
        "error": error,
        "error_description": error_description,
    }
    payload_json = json.dumps(payload)

    html = f"""
<!doctype html>
<html>
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>AgentHQ OAuth</title>
    <style>
      body {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background: #0f172a;
        color: #e2e8f0;
      }}
      .card {{
        background: #111827;
        padding: 24px;
        border-radius: 12px;
        border: 1px solid #334155;
        max-width: 460px;
        text-align: center;
      }}
      code {{
        background: #1f2937;
        border-radius: 6px;
        padding: 2px 6px;
      }}
    </style>
  </head>
  <body>
    <div class=\"card\">
      <h1>AgentHQ Authentication</h1>
      <p id=\"status\">Sending authentication result to app…</p>
      <p>If this window does not close automatically, you can close it manually.</p>
    </div>

    <script>
      const payload = {payload_json};
      const statusEl = document.getElementById('status');

      if (window.opener && !window.opener.closed) {{
        window.opener.postMessage(payload, '*');
        statusEl.textContent = payload.error
          ? 'Authentication was cancelled or failed. Returning to app…'
          : 'Authentication successful. Returning to app…';
        setTimeout(() => window.close(), 150);
      }} else {{
        statusEl.textContent = payload.error
          ? `Authentication failed: ${{payload.error_description || payload.error}}`
          : 'No opener window detected. Please return to the app manually.';
      }}
    </script>
  </body>
</html>
"""

    return HTMLResponse(content=html)


@router.get("/github/callback", response_class=HTMLResponse)
async def github_callback_redirect(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
):
    """GitHub OAuth callback redirect handler."""
    return await google_callback_redirect(code, state, error, error_description)


@router.get("/microsoft/callback", response_class=HTMLResponse)
async def microsoft_callback_redirect(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
):
    """Microsoft OAuth callback redirect handler."""
    return await google_callback_redirect(code, state, error, error_description)


@router.post("/callback", response_model=Token)
async def google_callback(
    callback_data: GoogleCallback,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Handle Google OAuth callback with token rotation.
    
    Args:
        callback_data: OAuth callback data
        request: Request object for client info
        db: Database session
        
    Returns:
        Token: Access and refresh tokens
    """
    device_id, user_agent, ip_address = _get_client_info(request)
    
    user, access_token, refresh_token = await OAuthService.authenticate_google(
        db=db,
        code=callback_data.code,
        device_id=device_id,
        user_agent=user_agent,
        ip_address=ip_address,
    )

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserInfo.model_validate(user),
    )


@router.post("/github/callback", response_model=Token)
async def github_callback(
    callback_data: GitHubCallback,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Handle GitHub OAuth callback with token rotation.
    
    Args:
        callback_data: OAuth callback data
        request: Request object for client info
        db: Database session
        
    Returns:
        Token: Access and refresh tokens
    """
    device_id, user_agent, ip_address = _get_client_info(request)
    
    user, access_token, refresh_token = await OAuthService.authenticate_github(
        db=db,
        code=callback_data.code,
        device_id=device_id,
        user_agent=user_agent,
        ip_address=ip_address,
    )

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserInfo.model_validate(user),
    )


@router.post("/microsoft/callback", response_model=Token)
async def microsoft_callback(
    callback_data: MicrosoftCallback,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Handle Microsoft OAuth callback with token rotation.
    
    Args:
        callback_data: OAuth callback data
        request: Request object for client info
        db: Database session
        
    Returns:
        Token: Access and refresh tokens
    """
    device_id, user_agent, ip_address = _get_client_info(request)
    
    user, access_token, refresh_token = await OAuthService.authenticate_microsoft(
        db=db,
        code=callback_data.code,
        device_id=device_id,
        user_agent=user_agent,
        ip_address=ip_address,
    )

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserInfo.model_validate(user),
    )


@router.post("/google/mobile", response_model=Token)
async def google_mobile_auth(
    mobile_auth: GoogleMobileAuth,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Handle Google OAuth for mobile apps with improved security.
    Mobile apps send id_token and access_token directly from Google Sign-In SDK.
    
    Args:
        mobile_auth: Google tokens from mobile SDK
        request: Request object for client info
        db: Database session
        
    Returns:
        Token: Access and refresh tokens
    """
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token
    
    device_id, user_agent, ip_address = _get_client_info(request)
    
    try:
        # Verify ID token from mobile client
        idinfo = google_id_token.verify_oauth2_token(
            mobile_auth.id_token,
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
        
        # Store or update OAuth connection
        from app.core.encryption import encrypt_token
        from datetime import datetime
        
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
        
        if mobile_auth.access_token:
            connection.access_token_encrypted = encrypt_token(mobile_auth.access_token)
        connection.last_used_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(user)
        
        # Create JWT tokens with rotation
        from app.core.security import create_access_token
        
        access_token = create_access_token(data={"sub": str(user.id)})
        raw_refresh_token, _ = await OAuthService.create_refresh_token(
            db=db,
            user_id=user.id,
            device_id=device_id,
            user_agent=user_agent,
            ip_address=ip_address,
        )

        return Token(
            access_token=access_token,
            refresh_token=raw_refresh_token,
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
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Create a guest session for mobile users without OAuth account.
    
    Args:
        guest_data: Guest device info (device_id, name)
        request: Request object for client info
        db: Database session
        
    Returns:
        Token: Access and refresh tokens for guest session
    """
    device_id, user_agent, ip_address = _get_client_info(request)
    
    try:
        device_id = guest_data.device_id or device_id
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
        
        # Create JWT tokens with rotation
        from app.core.security import create_access_token
        
        access_token = create_access_token(data={"sub": str(user.id)})
        raw_refresh_token, _ = await OAuthService.create_refresh_token(
            db=db,
            user_id=user.id,
            device_id=device_id,
            user_agent=user_agent,
            ip_address=ip_address,
        )

        return Token(
            access_token=access_token,
            refresh_token=raw_refresh_token,
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


@router.get("/me/providers", response_model=List[OAuthProviderInfo])
async def get_user_oauth_providers(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get all OAuth provider connections for current user.
    
    Args:
        current_user: Current user from JWT token
        db: Database session
        
    Returns:
        List[OAuthProviderInfo]: List of connected OAuth providers
    """
    result = await db.execute(
        select(OAuthConnection).where(
            OAuthConnection.user_id == current_user.id
        )
    )
    connections = result.scalars().all()
    
    provider_info = []
    for conn in connections:
        provider_info.append(
            OAuthProviderInfo(
                provider=conn.provider.value,
                connected=True,
                email=conn.email,
                last_used=conn.last_used_at.isoformat() if conn.last_used_at else None,
            )
        )
    
    return provider_info


@router.post("/logout")
async def logout(
    current_user: Annotated[User, Depends(get_current_user)],
    token_data: RefreshTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Logout endpoint - revokes the refresh token.
    
    Args:
        current_user: Current user from JWT token
        token_data: Refresh token to revoke
        db: Database session
        
    Returns:
        Success message
    """
    await OAuthService.revoke_refresh_token(
        db=db,
        raw_token=token_data.refresh_token,
    )
    
    return {"message": "Logged out successfully"}


@router.post("/logout-all")
async def logout_all(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Logout from all devices - revokes all refresh tokens for user.
    
    Args:
        current_user: Current user from JWT token
        db: Database session
        
    Returns:
        Success message
    """
    await OAuthService.revoke_all_user_tokens(
        db=db,
        user_id=current_user.id,
    )
    
    return {"message": "Logged out from all devices successfully"}


@router.post("/refresh", response_model=Token)
async def refresh_token(
    token_data: RefreshTokenRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Refresh access token with automatic token rotation.
    
    Old refresh token is revoked and a new one is issued.
    If a revoked token is reused, all tokens in the family are revoked (security breach detection).

    Args:
        token_data: Refresh token payload
        request: Request object for client info
        db: Database session

    Returns:
        Token: New access and refresh tokens
    """
    device_id, user_agent, ip_address = _get_client_info(request)
    
    user, access_token, new_refresh_token = await OAuthService.verify_and_rotate_refresh_token(
        db=db,
        raw_token=token_data.refresh_token,
        device_id=device_id,
        user_agent=user_agent,
        ip_address=ip_address,
    )

    return Token(
        access_token=access_token,
        refresh_token=new_refresh_token,
        user=UserInfo.model_validate(user),
    )
