"""User schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr


class UserBase(BaseModel):
    """Base user schema."""

    email: EmailStr
    full_name: Optional[str] = None


class UserCreate(UserBase):
    """User creation schema."""

    pass


class UserUpdate(BaseModel):
    """User update schema."""

    full_name: Optional[str] = None


class UserInDB(UserBase):
    """User schema with database fields."""

    id: UUID
    google_id: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class User(UserInDB):
    """Public user schema."""

    pass
