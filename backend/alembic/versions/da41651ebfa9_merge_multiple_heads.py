"""merge_multiple_heads

Revision ID: da41651ebfa9
Revises: 002, 282_add_marketplace, add_workspace_id_to_tasks
Create Date: 2026-02-24 21:42:30.539758

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'da41651ebfa9'
down_revision = ('002', '282_add_marketplace', 'add_workspace_id_to_tasks')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
