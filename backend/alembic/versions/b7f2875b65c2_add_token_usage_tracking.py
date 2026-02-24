"""add_token_usage_tracking

Revision ID: b7f2875b65c2
Revises: dff81b988399
Create Date: 2026-02-24 21:56:04.752280

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7f2875b65c2'
down_revision = 'dff81b988399'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create token_usage table for LLM cost tracking."""
    op.create_table(
        'token_usage',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('task_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('model', sa.String(), nullable=False),
        sa.Column('provider', sa.String(), nullable=False),
        sa.Column('prompt_tokens', sa.Integer(), nullable=False, default=0),
        sa.Column('completion_tokens', sa.Integer(), nullable=False, default=0),
        sa.Column('total_tokens', sa.Integer(), nullable=False, default=0),
        sa.Column('cost_usd', sa.Float(), nullable=False, default=0.0),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    
    # Create indexes for common queries
    op.create_index('ix_token_usage_task_id', 'token_usage', ['task_id'])
    op.create_index('ix_token_usage_user_id', 'token_usage', ['user_id'])
    op.create_index('ix_token_usage_model', 'token_usage', ['model'])
    op.create_index('ix_token_usage_created_at', 'token_usage', ['created_at'])
    op.create_index('ix_token_usage_user_created', 'token_usage', ['user_id', 'created_at'])
    op.create_index('ix_token_usage_model_created', 'token_usage', ['model', 'created_at'])
    op.create_index('ix_token_usage_task_created', 'token_usage', ['task_id', 'created_at'])


def downgrade() -> None:
    """Drop token_usage table."""
    op.drop_index('ix_token_usage_task_created', table_name='token_usage')
    op.drop_index('ix_token_usage_model_created', table_name='token_usage')
    op.drop_index('ix_token_usage_user_created', table_name='token_usage')
    op.drop_index('ix_token_usage_created_at', table_name='token_usage')
    op.drop_index('ix_token_usage_model', table_name='token_usage')
    op.drop_index('ix_token_usage_user_id', table_name='token_usage')
    op.drop_index('ix_token_usage_task_id', table_name='token_usage')
    op.drop_table('token_usage')

