"""add_task_progress_tracking

Revision ID: dff81b988399
Revises: da41651ebfa9
Create Date: 2026-02-24 21:42:34.602001

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'dff81b988399'
down_revision = 'da41651ebfa9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add progress tracking fields
    op.add_column('tasks', sa.Column('progress_percentage', sa.Integer(), nullable=True))
    op.add_column('tasks', sa.Column('progress_message', sa.Text(), nullable=True))
    op.add_column('tasks', sa.Column('progress_steps', sa.JSON(), nullable=True))
    op.add_column('tasks', sa.Column('started_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('tasks', 'started_at')
    op.drop_column('tasks', 'progress_steps')
    op.drop_column('tasks', 'progress_message')
    op.drop_column('tasks', 'progress_percentage')
