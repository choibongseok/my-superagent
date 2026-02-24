"""add_scheduled_tasks_table

Revision ID: c5e3a9b2f1d4
Revises: b7f2875b65c2
Create Date: 2026-02-24 23:12:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'c5e3a9b2f1d4'
down_revision = 'b7f2875b65c2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create scheduled_tasks table for recurring task scheduling."""
    op.create_table(
        'scheduled_tasks',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('prompt', sa.Text(), nullable=False),
        sa.Column('task_type', sa.String(length=50), nullable=False),
        sa.Column('task_metadata', sa.JSON(), nullable=True),
        sa.Column('schedule_type', sa.String(length=50), nullable=False),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('cron_expression', sa.String(length=100), nullable=True),
        sa.Column('timezone', sa.String(length=50), nullable=False, server_default='UTC'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_task_id', sa.String(), nullable=True),
        sa.Column('run_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('success_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failure_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('max_runs', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['last_task_id'], ['tasks.id'], ondelete='SET NULL'),
    )
    
    # Create indexes for common queries
    op.create_index('ix_scheduled_tasks_user_id', 'scheduled_tasks', ['user_id'])
    op.create_index('ix_scheduled_tasks_is_active', 'scheduled_tasks', ['is_active'])
    op.create_index('ix_scheduled_tasks_next_run_at', 'scheduled_tasks', ['next_run_at'])
    op.create_index('ix_sched_user_active', 'scheduled_tasks', ['user_id', 'is_active'])
    op.create_index('ix_sched_next_run', 'scheduled_tasks', ['is_active', 'next_run_at'])


def downgrade() -> None:
    """Drop scheduled_tasks table."""
    op.drop_index('ix_sched_next_run', table_name='scheduled_tasks')
    op.drop_index('ix_sched_user_active', table_name='scheduled_tasks')
    op.drop_index('ix_scheduled_tasks_next_run_at', table_name='scheduled_tasks')
    op.drop_index('ix_scheduled_tasks_is_active', table_name='scheduled_tasks')
    op.drop_index('ix_scheduled_tasks_user_id', table_name='scheduled_tasks')
    op.drop_table('scheduled_tasks')
