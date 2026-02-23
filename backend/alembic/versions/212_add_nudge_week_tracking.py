"""Track weekly nudge-email quota reset for usage nudges (Sprint #210).

Revision ID: 212_nudge_week_tracking
Revises: 206_share_expiry
Create Date: 2026-02-23 11:06:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "212_nudge_week_tracking"
down_revision = "206_share_expiry"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
