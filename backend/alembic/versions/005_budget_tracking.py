"""Add budget tracking tables

Revision ID: 005_budget_tracking
Revises: 004_scheduled_tasks
Create Date: 2026-03-01 01:52:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

# revision identifiers, used by Alembic.
revision = '005_budget_tracking'
down_revision = '004_scheduled_tasks'
branch_labels = None
depends_on = None


def upgrade():
    """Create budget tracking tables."""
    
    # Create enums
    budget_period_enum = sa.Enum('daily', 'weekly', 'monthly', 'yearly', name='budgetperiod')
    budget_alert_level_enum = sa.Enum('warning', 'critical', 'exceeded', name='budgetalertlevel')
    
    budget_period_enum.create(op.get_bind(), checkfirst=True)
    budget_alert_level_enum.create(op.get_bind(), checkfirst=True)
    
    # Create user_budgets table
    op.create_table(
        'user_budgets',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        
        # Budget configuration
        sa.Column('period', budget_period_enum, nullable=False, server_default='monthly'),
        sa.Column('limit_usd', sa.Float(), nullable=False),
        
        # Current period tracking
        sa.Column('current_spend_usd', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
        
        # Alert settings
        sa.Column('enable_alerts', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('alert_email', sa.String(), nullable=True),
        sa.Column('warning_threshold_pct', sa.Integer(), nullable=False, server_default='75'),
        sa.Column('critical_threshold_pct', sa.Integer(), nullable=False, server_default='90'),
        
        # Alert state
        sa.Column('last_warning_sent', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_critical_sent', sa.DateTime(timezone=True), nullable=True),
        sa.Column('budget_exceeded', sa.Boolean(), nullable=False, server_default='false'),
        
        # Metadata
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    
    # Create indexes for user_budgets
    op.create_index('ix_user_budgets_user_id', 'user_budgets', ['user_id'])
    op.create_index('ix_user_budgets_period', 'user_budgets', ['period_start', 'period_end'])
    
    # Create budget_alerts table
    op.create_table(
        'budget_alerts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('budget_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('user_budgets.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        
        # Alert details
        sa.Column('level', budget_alert_level_enum, nullable=False),
        sa.Column('spend_usd', sa.Float(), nullable=False),
        sa.Column('limit_usd', sa.Float(), nullable=False),
        sa.Column('usage_percentage', sa.Float(), nullable=False),
        
        # Notification status
        sa.Column('email_sent', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('email_sent_at', sa.DateTime(timezone=True), nullable=True),
        
        # Metadata
        sa.Column('message', sa.String(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    
    # Create indexes for budget_alerts
    op.create_index('ix_budget_alerts_budget_id', 'budget_alerts', ['budget_id'])
    op.create_index('ix_budget_alerts_user_id', 'budget_alerts', ['user_id'])
    op.create_index('ix_budget_alerts_level', 'budget_alerts', ['level'])
    op.create_index('ix_budget_alerts_created_at', 'budget_alerts', ['created_at'])
    
    # Create cost_records table
    op.create_table(
        'cost_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=True),
        
        # LangFuse integration
        sa.Column('langfuse_trace_id', sa.String(), nullable=True),
        sa.Column('langfuse_span_id', sa.String(), nullable=True),
        
        # Cost details
        sa.Column('model', sa.String(), nullable=False),
        sa.Column('agent_type', sa.String(), nullable=False),
        
        sa.Column('input_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('output_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_tokens', sa.Integer(), nullable=False, server_default='0'),
        
        sa.Column('cost_usd', sa.Float(), nullable=False),
        
        # Metadata
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    
    # Create indexes for cost_records
    op.create_index('ix_cost_records_user_id', 'cost_records', ['user_id'])
    op.create_index('ix_cost_records_task_id', 'cost_records', ['task_id'])
    op.create_index('ix_cost_records_model', 'cost_records', ['model'])
    op.create_index('ix_cost_records_agent_type', 'cost_records', ['agent_type'])
    op.create_index('ix_cost_records_created_at', 'cost_records', ['created_at'])
    op.create_index('ix_cost_records_langfuse_trace', 'cost_records', ['langfuse_trace_id'])


def downgrade():
    """Drop budget tracking tables."""
    op.drop_table('cost_records')
    op.drop_table('budget_alerts')
    op.drop_table('user_budgets')
    
    # Drop enums
    sa.Enum(name='budgetalertlevel').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='budgetperiod').drop(op.get_bind(), checkfirst=True)
