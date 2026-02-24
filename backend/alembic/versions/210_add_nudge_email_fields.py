"""Add nudge email fields to users table (#210 Usage Nudge Emails).

Revision ID: 210_add_nudge_email_fields
Revises: 001
Create Date: 2026-02-24 20:47:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "210_add_nudge_email_fields"
down_revision = "206_share_expiry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add last_task_created_at field
    op.add_column(
        "users",
        sa.Column(
            "last_task_created_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.create_index(
        op.f("ix_users_last_task_created_at"),
        "users",
        ["last_task_created_at"],
        unique=False,
    )

    # Add nudge_email_count field
    op.add_column(
        "users",
        sa.Column(
            "nudge_email_count",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
    )

    # Add nudge_email_week_start field
    op.add_column(
        "users",
        sa.Column(
            "nudge_email_week_start",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.create_index(
        op.f("ix_users_nudge_email_week_start"),
        "users",
        ["nudge_email_week_start"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_users_nudge_email_week_start"), table_name="users")
    op.drop_column("users", "nudge_email_week_start")
    op.drop_column("users", "nudge_email_count")
    op.drop_index(op.f("ix_users_last_task_created_at"), table_name="users")
    op.drop_column("users", "last_task_created_at")
