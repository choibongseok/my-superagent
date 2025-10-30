"""Authentication schemas."""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr


class UserInfo(BaseModel):
    """User information schema for token response."""

    id: UUID
    email: EmailStr
    full_name: Optional[str] = None

    model_config = {"from_attributes": True}


class Token(BaseModel):
    """Token response schema."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserInfo


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
