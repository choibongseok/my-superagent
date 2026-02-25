"""add recovery suggestions table

Revision ID: recovery_suggestions_001
Revises: # Will be filled in later
Create Date: 2026-02-25 05:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'recovery_suggestions_001'
down_revision: Union[str, None] = None  # Set this to the latest migration
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create recovery_suggestions table"""
    op.create_table(
        'recovery_suggestions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('suggestion_type', sa.String(50), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('confidence_score', sa.Integer(), nullable=False, server_default='50'),
        sa.Column('action_payload', sa.JSON(), nullable=False),
        sa.Column('error_category', sa.String(100), nullable=True),
        sa.Column('estimated_success_rate', sa.Integer(), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('was_selected', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('selection_timestamp', sa.Integer(), nullable=True),
        sa.Column('outcome_success', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.Integer(), nullable=False),
        sa.Column('expires_at', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )
    
    # Indexes for efficient querying
    op.create_index('ix_recovery_suggestions_task_id', 'recovery_suggestions', ['task_id'])
    op.create_index('ix_recovery_suggestions_user_id', 'recovery_suggestions', ['user_id'])
    op.create_index('ix_recovery_suggestions_suggestion_type', 'recovery_suggestions', ['suggestion_type'])
    op.create_index('ix_recovery_suggestions_error_category', 'recovery_suggestions', ['error_category'])


def downgrade() -> None:
    """Drop recovery_suggestions table"""
    op.drop_index('ix_recovery_suggestions_error_category', table_name='recovery_suggestions')
    op.drop_index('ix_recovery_suggestions_suggestion_type', table_name='recovery_suggestions')
    op.drop_index('ix_recovery_suggestions_user_id', table_name='recovery_suggestions')
    op.drop_index('ix_recovery_suggestions_task_id', table_name='recovery_suggestions')
    op.drop_table('recovery_suggestions')
