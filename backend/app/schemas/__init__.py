"""Pydantic schemas."""

from app.schemas.auth import GoogleAuthURL, GoogleCallback, Token, TokenPayload
from app.schemas.task import Task, TaskCreate, TaskInDB, TaskList, TaskUpdate
from app.schemas.user import User, UserCreate, UserInDB, UserUpdate
from app.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceUpdate,
    WorkspaceResponse,
    WorkspaceListResponse,
    WorkspaceMemberCreate,
    WorkspaceMemberUpdate,
    WorkspaceMemberResponse,
    WorkspaceMemberListResponse,
    InvitationCreate,
    InvitationResponse,
    InvitationListResponse,
    InvitationAcceptRequest,
    InvitationAcceptResponse,
)

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
    # Workspace
    "WorkspaceCreate",
    "WorkspaceUpdate",
    "WorkspaceResponse",
    "WorkspaceListResponse",
    "WorkspaceMemberCreate",
    "WorkspaceMemberUpdate",
    "WorkspaceMemberResponse",
    "WorkspaceMemberListResponse",
    "InvitationCreate",
    "InvitationResponse",
    "InvitationListResponse",
    "InvitationAcceptRequest",
    "InvitationAcceptResponse",
]
