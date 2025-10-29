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
