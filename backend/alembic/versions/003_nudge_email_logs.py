"""Add nudge_email_logs table for persistent email tracking

Revision ID: 003_nudge_email_logs
Revises: 002
Create Date: 2026-03-01 00:11:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003_nudge_email_logs'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create nudge_email_logs table."""
    op.create_table(
        'nudge_email_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email_type', sa.String(length=50), nullable=False, server_default='usage_nudge'),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('success', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('error_message', sa.String(length=512), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for efficient queries
    op.create_index('ix_nudge_email_logs_user_id', 'nudge_email_logs', ['user_id'])
    op.create_index('ix_nudge_email_logs_email_type', 'nudge_email_logs', ['email_type'])
    op.create_index('ix_nudge_email_logs_sent_at', 'nudge_email_logs', ['sent_at'])
    
    # Composite index for weekly limit queries (user + sent_at)
    op.create_index(
        'ix_nudge_email_logs_user_sent_at', 
        'nudge_email_logs', 
        ['user_id', 'sent_at']
    )


def downgrade() -> None:
    """Drop nudge_email_logs table."""
    op.drop_index('ix_nudge_email_logs_user_sent_at', table_name='nudge_email_logs')
    op.drop_index('ix_nudge_email_logs_sent_at', table_name='nudge_email_logs')
    op.drop_index('ix_nudge_email_logs_email_type', table_name='nudge_email_logs')
    op.drop_index('ix_nudge_email_logs_user_id', table_name='nudge_email_logs')
    op.drop_table('nudge_email_logs')
