"""add_scheduled_tasks_and_executions

Revision ID: 004_scheduled_tasks
Revises: 003_nudge_email_logs
Create Date: 2026-03-01 01:20:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

# revision identifiers, used by Alembic.
revision = '004_scheduled_tasks'
down_revision = '003_nudge_email_logs'
branch_labels = None
depends_on = None


def upgrade():
    # Create scheduled_tasks table
    op.create_table(
        'scheduled_tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('task_type', sa.String(50), nullable=False),
        sa.Column('prompt_template', sa.Text(), nullable=False),
        
        sa.Column('schedule_type', sa.String(50), nullable=False),
        sa.Column('schedule_config', postgresql.JSON(), nullable=False),
        sa.Column('cron_expression', sa.String(100), nullable=True),
        
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('last_run_at', sa.DateTime(), nullable=True),
        sa.Column('next_run_at', sa.DateTime(), nullable=True),
        sa.Column('run_count', sa.Integer(), default=0, nullable=False),
        
        sa.Column('notify_on_completion', sa.Boolean(), default=True, nullable=False),
        sa.Column('notification_email', sa.String(255), nullable=True),
        sa.Column('notification_channels', postgresql.JSON(), nullable=True),
        
        sa.Column('output_config', postgresql.JSON(), nullable=True),
        
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    )
    
    # Create indexes for scheduled_tasks
    op.create_index('ix_scheduled_tasks_name', 'scheduled_tasks', ['name'])
    op.create_index('ix_scheduled_tasks_user_id', 'scheduled_tasks', ['user_id'])
    op.create_index('ix_scheduled_tasks_is_active', 'scheduled_tasks', ['is_active'])
    op.create_index('ix_scheduled_tasks_next_run_at', 'scheduled_tasks', ['next_run_at'])
    
    # Create scheduled_task_executions table
    op.create_table(
        'scheduled_task_executions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('scheduled_task_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('scheduled_tasks.id'), nullable=False),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tasks.id'), nullable=True),
        
        sa.Column('started_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(50), default='running', nullable=False),
        
        sa.Column('success', sa.Boolean(), default=False, nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('output_data', postgresql.JSON(), nullable=True),
    )
    
    # Create indexes for scheduled_task_executions
    op.create_index('ix_scheduled_task_executions_scheduled_task_id', 'scheduled_task_executions', ['scheduled_task_id'])
    op.create_index('ix_scheduled_task_executions_task_id', 'scheduled_task_executions', ['task_id'])
    op.create_index('ix_scheduled_task_executions_started_at', 'scheduled_task_executions', ['started_at'])


def downgrade():
    # Drop tables
    op.drop_table('scheduled_task_executions')
    op.drop_table('scheduled_tasks')
