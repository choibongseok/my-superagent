"""PKCE OAuth schemas."""

from typing import Optional
from pydantic import BaseModel, Field


class PKCEAuthRequest(BaseModel):
    """Request to initiate PKCE OAuth flow."""
    
    code_challenge: str = Field(..., description="SHA-256 hash of code_verifier (base64 URL-safe)")
    code_challenge_method: str = Field(default="S256", description="Challenge method (S256 or plain)")
    redirect_uri: str = Field(..., description="Redirect URI for callback")
    provider: str = Field(default="google", description="OAuth provider (google, github, microsoft)")


class PKCEAuthResponse(BaseModel):
    """Response with authorization URL for PKCE flow."""
    
    auth_url: str = Field(..., description="Authorization URL to redirect user")
    state: str = Field(..., description="State parameter for CSRF protection")


class PKCETokenRequest(BaseModel):
    """Request to exchange authorization code for tokens (PKCE)."""
    
    code: str = Field(..., description="Authorization code from OAuth provider")
    code_verifier: str = Field(..., description="Original code verifier (plain text)")
    state: str = Field(..., description="State parameter from authorization request")
    redirect_uri: str = Field(..., description="Same redirect_uri used in authorization request")


class PKCETokenResponse(BaseModel):
    """Response with access and refresh tokens."""
    
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="Refresh token for renewing access")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration time in seconds")
    user_id: str = Field(..., description="User UUID")
    email: str = Field(..., description="User email")


class PKCEStatusResponse(BaseModel):
    """PKCE feature status."""
    
    enabled: bool = Field(..., description="Whether PKCE is enabled")
    supported_providers: list[str] = Field(..., description="List of providers that support PKCE")
    supported_methods: list[str] = Field(..., description="Supported challenge methods")
