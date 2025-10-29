"""Pydantic schemas."""

from app.schemas.auth import GoogleAuthURL, GoogleCallback, Token, TokenPayload
from app.schemas.task import Task, TaskCreate, TaskInDB, TaskList, TaskUpdate
from app.schemas.user import User, UserCreate, UserInDB, UserUpdate

__all__ = [
    # Auth
    "Token",
    "TokenPayload",
    "GoogleAuthURL",
    "GoogleCallback",
    # User
    "User",
    "UserCreate",
    "UserUpdate",
    "UserInDB",
    # Task
    "Task",
    "TaskCreate",
    "TaskUpdate",
    "TaskInDB",
    "TaskList",
]
