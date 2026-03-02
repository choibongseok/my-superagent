"""Schemas for OAuth 2.0 Device Authorization Flow."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DeviceAuthorizationRequest(BaseModel):
    """Request for device authorization (RFC 8628 Section 3.1)."""
    client_id: Optional[str] = None
    scope: Optional[str] = None


class DeviceAuthorizationResponse(BaseModel):
    """Response with device code and user code (RFC 8628 Section 3.2)."""
    device_code: str = Field(..., description="Device verification code")
    user_code: str = Field(..., description="User-friendly code (XXXX-XXXX)")
    verification_uri: str = Field(..., description="URL for user to visit")
    verification_uri_complete: Optional[str] = Field(
        None, description="Optional: URL with user_code embedded"
    )
    expires_in: int = Field(..., description="Lifetime in seconds (typically 600)")
    interval: int = Field(5, description="Minimum polling interval in seconds")


class DeviceTokenRequest(BaseModel):
    """Request to poll for device token (RFC 8628 Section 3.4)."""
    grant_type: str = Field("urn:ietf:params:oauth:grant-type:device_code")
    device_code: str = Field(..., description="Device code from authorization response")
    client_id: Optional[str] = None


class DeviceTokenResponse(BaseModel):
    """Successful token response (RFC 8628 Section 3.5)."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 2592000  # 30 days
    refresh_token: Optional[str] = None
    scope: Optional[str] = None


class DeviceTokenError(BaseModel):
    """Error response for device token polling (RFC 8628 Section 3.5)."""
    error: str = Field(
        ...,
        description=(
            "Error code: authorization_pending, slow_down, "
            "expired_token, access_denied"
        ),
    )
    error_description: Optional[str] = None


class DeviceActivationRequest(BaseModel):
    """Request to activate device with user code."""
    user_code: str = Field(..., description="8-character user code (with or without dash)")


class DeviceActivationInfo(BaseModel):
    """Information about device activation request."""
    user_code: str
    client_id: Optional[str]
    scope: Optional[str]
    created_at: datetime


class DeviceApprovalRequest(BaseModel):
    """Request to approve/deny device."""
    user_code: str
    approved: bool = Field(..., description="True to approve, False to deny")
