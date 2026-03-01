"""Add LLM provider and model to tasks

Revision ID: 006_claude_integration
Revises: 005_budget_tracking
Create Date: 2026-03-01 03:32:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '006_claude_integration'
down_revision = '005_budget_tracking'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add LLM provider and model columns to tasks table."""
    # Add llm_provider column
    op.add_column(
        'tasks',
        sa.Column(
            'llm_provider',
            sa.String(length=50),
            nullable=False,
            server_default='openai'
        )
    )
    
    # Add llm_model column
    op.add_column(
        'tasks',
        sa.Column(
            'llm_model',
            sa.String(length=100),
            nullable=False,
            server_default='gpt-4-turbo-preview'
        )
    )
    
    # Add index for querying by provider
    op.create_index(
        'ix_tasks_llm_provider',
        'tasks',
        ['llm_provider']
    )


def downgrade() -> None:
    """Remove LLM provider and model columns from tasks table."""
    op.drop_index('ix_tasks_llm_provider', table_name='tasks')
    op.drop_column('tasks', 'llm_model')
    op.drop_column('tasks', 'llm_provider')
