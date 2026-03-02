"""
Workspace models for multi-project organization and team collaboration.

Workspaces allow users to organize their agents, chats, and tasks
into separate contexts (e.g., Marketing, Finance, Development).
Supports both personal and team workspaces.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

from sqlalchemy import String, Text, Boolean, ForeignKey, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.chat import Chat
    from app.models.task import Task
    from app.models.workspace_member import WorkspaceMember
    from app.models.workspace_invitation import WorkspaceInvitation


class Workspace(Base, TimestampMixin):
    """
    Workspace for organizing work into projects/contexts.
    
    Each workspace has:
    - Independent chat history and memory
    - Separate task organization
    - Optional templates and settings
    - Team collaboration support (owner + members)
    - Visual customization (color, icon)
    """
    __tablename__ = "workspaces"
    
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Visual customization
    color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)  # Hex color
    icon: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Emoji or icon name
    
    # Ownership & team settings
    owner_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    owner: Mapped["User"] = relationship("User", back_populates="owned_workspaces", foreign_keys=[owner_id])
    
    # Settings
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_members: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    
    # Template info (optional)
    template_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # marketing, finance, etc
    
    # Relationships
    members: Mapped[list["WorkspaceMember"]] = relationship(
        "WorkspaceMember", back_populates="workspace", cascade="all, delete-orphan"
    )
    invitations: Mapped[list["WorkspaceInvitation"]] = relationship(
        "WorkspaceInvitation", back_populates="workspace", cascade="all, delete-orphan"
    )
    chats: Mapped[list["Chat"]] = relationship("Chat", back_populates="workspace", cascade="all, delete-orphan")
    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="workspace", cascade="all, delete-orphan")
    
    # Statistics (computed)
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<Workspace(id={self.id}, name={self.name}, owner_id={self.owner_id})>"
    
    def to_dict(self, include_members=False):
        """Convert to dictionary for API responses."""
        result = {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "color": self.color,
            "icon": self.icon,
            "owner_id": str(self.owner_id),
            "is_default": self.is_default,
            "is_archived": self.is_archived,
            "is_active": self.is_active,
            "max_members": self.max_members,
            "template_type": self.template_type,
            "last_activity_at": self.last_activity_at.isoformat() if self.last_activity_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        
        if include_members:
            result["members"] = [
                {
                    "user_id": str(m.user_id),
                    "role": m.role,
                    "joined_at": m.joined_at.isoformat() if m.joined_at else None,
                }
                for m in self.members
            ]
            result["member_count"] = len(self.members)
        
        return result


class WorkspaceTemplate(Base):
    """
    Pre-defined workspace templates for common use cases.
    
    Templates provide:
    - Default name and description
    - Suggested color/icon
    - Category (business, personal, development, etc)
    - Sample configuration
    """
    __tablename__ = "workspace_templates"
    
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(50))  # business, personal, development, etc
    color: Mapped[str] = mapped_column(String(7))  # Default hex color
    icon: Mapped[str] = mapped_column(String(50))  # Default emoji/icon
    
    # Configuration (JSON strings)
    default_settings: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    sample_prompts: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON list
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    
    def __repr__(self):
        return f"<WorkspaceTemplate(id={self.id}, name={self.name}, category={self.category})>"
    
    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "color": self.color,
            "icon": self.icon,
            "default_settings": self.default_settings,
            "sample_prompts": self.sample_prompts,
            "is_active": self.is_active,
            "sort_order": self.sort_order,
        }
