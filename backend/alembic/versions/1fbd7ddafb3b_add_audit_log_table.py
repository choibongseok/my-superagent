"""add_audit_log_table

Revision ID: 1fbd7ddafb3b
Revises: c5e3a9b2f1d4
Create Date: 2026-02-24 23:35:11.308396

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '1fbd7ddafb3b'
down_revision = 'c5e3a9b2f1d4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create audit_logs table for compliance tracking"""
    op.create_table(
        'audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('event_type', sa.String(100), nullable=False, index=True),
        sa.Column('action', sa.String(100), nullable=False, index=True),
        sa.Column('resource_type', sa.String(100), nullable=True, index=True),
        sa.Column('resource_id', sa.String(255), nullable=True, index=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.Text, nullable=True),
        sa.Column('method', sa.String(10), nullable=True),
        sa.Column('endpoint', sa.String(500), nullable=True, index=True),
        sa.Column('status_code', sa.Integer, nullable=True),
        sa.Column('before_data', postgresql.JSON, nullable=True),
        sa.Column('after_data', postgresql.JSON, nullable=True),
        sa.Column('changes', postgresql.JSON, nullable=True),
        sa.Column('extra_metadata', postgresql.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, index=True),
    )
    
    # Create composite indexes for fast queries
    op.create_index(
        'ix_audit_logs_user_created',
        'audit_logs',
        ['user_id', 'created_at']
    )
    op.create_index(
        'ix_audit_logs_resource',
        'audit_logs',
        ['resource_type', 'resource_id']
    )
    op.create_index(
        'ix_audit_logs_event_created',
        'audit_logs',
        ['event_type', 'created_at']
    )
    op.create_index(
        'ix_audit_logs_workspace_created',
        'audit_logs',
        ['workspace_id', 'created_at']
    )


def downgrade() -> None:
    """Drop audit_logs table"""
    op.drop_index('ix_audit_logs_workspace_created', 'audit_logs')
    op.drop_index('ix_audit_logs_event_created', 'audit_logs')
    op.drop_index('ix_audit_logs_resource', 'audit_logs')
    op.drop_index('ix_audit_logs_user_created', 'audit_logs')
    op.drop_table('audit_logs')

