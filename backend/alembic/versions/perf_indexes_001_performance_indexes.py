"""Add performance indexes

Revision ID: perf_indexes_001
Revises: previous_migration
Create Date: 2026-03-01 07:22:00.000000

This migration adds database indexes to improve query performance for
frequently accessed tables and columns.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "perf_indexes_001"
down_revision = None  # Will be set automatically by alembic
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add performance indexes."""
    # Users table indexes
    op.create_index(
        "idx_users_email",
        "users",
        ["email"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "idx_users_is_active",
        "users",
        ["is_active"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "idx_users_created_at",
        "users",
        ["created_at"],
        unique=False,
        if_not_exists=True,
    )

    # Tasks table indexes
    op.create_index(
        "idx_tasks_user_id",
        "tasks",
        ["user_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "idx_tasks_status",
        "tasks",
        ["status"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "idx_tasks_created_at",
        "tasks",
        ["created_at"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "idx_tasks_user_created",
        "tasks",
        ["user_id", "created_at"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "idx_tasks_user_status",
        "tasks",
        ["user_id", "status"],
        unique=False,
        if_not_exists=True,
    )

    # Workspace members indexes
    op.create_index(
        "idx_workspace_members_workspace_id",
        "workspace_members",
        ["workspace_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "idx_workspace_members_user_id",
        "workspace_members",
        ["user_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "idx_workspace_members_workspace_user",
        "workspace_members",
        ["workspace_id", "user_id"],
        unique=True,
        if_not_exists=True,
    )

    # Messages table indexes
    op.create_index(
        "idx_messages_chat_id",
        "messages",
        ["chat_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "idx_messages_created_at",
        "messages",
        ["created_at"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "idx_messages_chat_created",
        "messages",
        ["chat_id", "created_at"],
        unique=False,
        if_not_exists=True,
    )

    # Scheduled tasks indexes
    op.create_index(
        "idx_scheduled_tasks_user_id",
        "scheduled_tasks",
        ["user_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "idx_scheduled_tasks_next_run",
        "scheduled_tasks",
        ["next_run_at"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "idx_scheduled_tasks_is_active",
        "scheduled_tasks",
        ["is_active"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "idx_scheduled_tasks_active_next_run",
        "scheduled_tasks",
        ["is_active", "next_run_at"],
        unique=False,
        if_not_exists=True,
    )

    # Budget tracking indexes
    op.create_index(
        "idx_budget_user_id",
        "budgets",
        ["user_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "idx_budget_timestamp",
        "budgets",
        ["timestamp"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "idx_budget_user_timestamp",
        "budgets",
        ["user_id", "timestamp"],
        unique=False,
        if_not_exists=True,
    )

    # OAuth connections indexes
    op.create_index(
        "idx_oauth_user_id",
        "oauth_connections",
        ["user_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "idx_oauth_provider",
        "oauth_connections",
        ["provider"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "idx_oauth_user_provider",
        "oauth_connections",
        ["user_id", "provider"],
        unique=True,
        if_not_exists=True,
    )

    # Fact checks indexes
    op.create_index(
        "idx_fact_checks_user_id",
        "fact_checks",
        ["user_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "idx_fact_checks_created_at",
        "fact_checks",
        ["created_at"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    """Remove performance indexes."""
    # Fact checks
    op.drop_index("idx_fact_checks_created_at", table_name="fact_checks")
    op.drop_index("idx_fact_checks_user_id", table_name="fact_checks")

    # OAuth connections
    op.drop_index("idx_oauth_user_provider", table_name="oauth_connections")
    op.drop_index("idx_oauth_provider", table_name="oauth_connections")
    op.drop_index("idx_oauth_user_id", table_name="oauth_connections")

    # Budget tracking
    op.drop_index("idx_budget_user_timestamp", table_name="budgets")
    op.drop_index("idx_budget_timestamp", table_name="budgets")
    op.drop_index("idx_budget_user_id", table_name="budgets")

    # Scheduled tasks
    op.drop_index("idx_scheduled_tasks_active_next_run", table_name="scheduled_tasks")
    op.drop_index("idx_scheduled_tasks_is_active", table_name="scheduled_tasks")
    op.drop_index("idx_scheduled_tasks_next_run", table_name="scheduled_tasks")
    op.drop_index("idx_scheduled_tasks_user_id", table_name="scheduled_tasks")

    # Messages
    op.drop_index("idx_messages_chat_created", table_name="messages")
    op.drop_index("idx_messages_created_at", table_name="messages")
    op.drop_index("idx_messages_chat_id", table_name="messages")

    # Workspace members
    op.drop_index("idx_workspace_members_workspace_user", table_name="workspace_members")
    op.drop_index("idx_workspace_members_user_id", table_name="workspace_members")
    op.drop_index("idx_workspace_members_workspace_id", table_name="workspace_members")

    # Tasks
    op.drop_index("idx_tasks_user_status", table_name="tasks")
    op.drop_index("idx_tasks_user_created", table_name="tasks")
    op.drop_index("idx_tasks_created_at", table_name="tasks")
    op.drop_index("idx_tasks_status", table_name="tasks")
    op.drop_index("idx_tasks_user_id", table_name="tasks")

    # Users
    op.drop_index("idx_users_created_at", table_name="users")
    op.drop_index("idx_users_is_active", table_name="users")
    op.drop_index("idx_users_email", table_name="users")
