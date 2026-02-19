"""Add share_token and expires_at to tasks (#206 Share Link Expiry)

Revision ID: 206_share_expiry
Revises: phase_8_templates
Create Date: 2026-02-19 17:16:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '206_share_expiry'
down_revision = 'phase_8_templates'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # share_token: nullable UUID, unique — generated on demand via POST /tasks/{id}/share
    op.add_column(
        'tasks',
        sa.Column(
            'share_token',
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_index(
        'ix_tasks_share_token',
        'tasks',
        ['share_token'],
        unique=True,
    )

    # expires_at: nullable TIMESTAMPTZ — null means link was never created / never expires
    op.add_column(
        'tasks',
        sa.Column(
            'expires_at',
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('tasks', 'expires_at')
    op.drop_index('ix_tasks_share_token', table_name='tasks')
    op.drop_column('tasks', 'share_token')
