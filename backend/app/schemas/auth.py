"""Authentication schemas."""

from typing import Optional

from pydantic import BaseModel


class Token(BaseModel):
    """Token response schema."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """Token payload schema."""

    sub: Optional[str] = None
    exp: Optional[int] = None
    type: Optional[str] = None


class GoogleAuthURL(BaseModel):
    """Google OAuth URL response."""

    auth_url: str


class GoogleCallback(BaseModel):
    """Google OAuth callback schema."""

    code: str
    state: Optional[str] = None


class GoogleMobileAuth(BaseModel):
    """Google mobile authentication schema."""

    id_token: str
    access_token: Optional[str] = None


class GuestAuth(BaseModel):
    """Guest authentication schema."""

    device_id: str
    name: str = "Guest"


class UserResponse(BaseModel):
    """User response schema."""

    id: str
    email: str
    name: str
    avatarUrl: Optional[str] = None
    created_at: str
    isGuest: bool = False

    class Config:
        from_attributes = True


class TokenWithUser(BaseModel):
    """Token with user response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse
