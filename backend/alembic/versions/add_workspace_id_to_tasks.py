"""Add workspace_id to tasks and chats for multi-tenancy.

Revision ID: add_workspace_id_to_tasks
Revises: 
Create Date: 2026-02-24 18:52:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = 'add_workspace_id_to_tasks'
down_revision = None  # Will be set by alembic
depends_on = None


def upgrade() -> None:
    """Add workspace_id to tasks and chats for resource isolation."""
    
    # Add workspace_id to tasks (nullable for backward compatibility)
    op.add_column('tasks', sa.Column('workspace_id', UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_tasks_workspace_id',
        'tasks',
        'workspaces',
        ['workspace_id'],
        ['id'],
        ondelete='SET NULL'
    )
    op.create_index('ix_tasks_workspace_id', 'tasks', ['workspace_id'])
    
    # Add workspace_id to chats (nullable for personal chats)
    op.add_column('chats', sa.Column('workspace_id', UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_chats_workspace_id',
        'chats',
        'workspaces',
        ['workspace_id'],
        ['id'],
        ondelete='SET NULL'
    )
    op.create_index('ix_chats_workspace_id', 'chats', ['workspace_id'])
    
    # Add composite indexes for common queries
    op.create_index(
        'ix_tasks_workspace_user',
        'tasks',
        ['workspace_id', 'user_id']
    )
    op.create_index(
        'ix_tasks_workspace_status',
        'tasks',
        ['workspace_id', 'status']
    )


def downgrade() -> None:
    """Remove workspace_id columns."""
    
    # Drop indexes
    op.drop_index('ix_tasks_workspace_status', 'tasks')
    op.drop_index('ix_tasks_workspace_user', 'tasks')
    op.drop_index('ix_chats_workspace_id', 'chats')
    op.drop_index('ix_tasks_workspace_id', 'tasks')
    
    # Drop foreign keys
    op.drop_constraint('fk_chats_workspace_id', 'chats', type_='foreignkey')
    op.drop_constraint('fk_tasks_workspace_id', 'tasks', type_='foreignkey')
    
    # Drop columns
    op.drop_column('chats', 'workspace_id')
    op.drop_column('tasks', 'workspace_id')
