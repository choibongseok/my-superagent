"""Add API key management tables

Revision ID: 010_api_key_management
Revises: 009_rate_limit_overrides
Create Date: 2026-03-02 12:05:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '010_api_key_management'
down_revision = '009_rate_limit_overrides'
branch_labels = None
depends_on = None


def upgrade():
    """Add api_keys and api_key_usage tables."""
    
    # Create api_keys table
    op.create_table(
        'api_keys',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('key_hash', sa.String(length=64), nullable=False),
        sa.Column('key_prefix', sa.String(length=10), nullable=False),
        sa.Column('scopes', sa.Text(), nullable=False, server_default='read'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('usage_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('key_hash'),
        comment='API keys for programmatic access'
    )
    
    # Indexes for api_keys
    op.create_index('ix_api_keys_user_id', 'api_keys', ['user_id'])
    op.create_index('ix_api_keys_key_hash', 'api_keys', ['key_hash'], unique=True)
    op.create_index('ix_api_keys_key_prefix', 'api_keys', ['key_prefix'])
    op.create_index('ix_api_keys_is_active', 'api_keys', ['is_active'])
    op.create_index('ix_api_keys_expires_at', 'api_keys', ['expires_at'])
    op.create_index('idx_api_keys_user_active', 'api_keys', ['user_id', 'is_active'])
    op.create_index('idx_api_keys_expires', 'api_keys', ['expires_at', 'is_active'])
    
    # Create api_key_usage table
    op.create_table(
        'api_key_usage',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('api_key_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('endpoint', sa.String(length=255), nullable=False),
        sa.Column('method', sa.String(length=10), nullable=False),
        sa.Column('status_code', sa.Integer(), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=512), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['api_key_id'], ['api_keys.id'], ondelete='CASCADE'),
        comment='API key usage tracking for analytics'
    )
    
    # Indexes for api_key_usage
    op.create_index('ix_api_key_usage_api_key_id', 'api_key_usage', ['api_key_id'])
    op.create_index('ix_api_key_usage_endpoint', 'api_key_usage', ['endpoint'])
    op.create_index('ix_api_key_usage_status_code', 'api_key_usage', ['status_code'])
    op.create_index('ix_api_key_usage_created_at', 'api_key_usage', ['created_at'])
    op.create_index('idx_usage_key_time', 'api_key_usage', ['api_key_id', 'created_at'])
    op.create_index('idx_usage_endpoint_time', 'api_key_usage', ['endpoint', 'created_at'])
    op.create_index('idx_usage_status_time', 'api_key_usage', ['status_code', 'created_at'])


def downgrade():
    """Drop api_keys and api_key_usage tables."""
    
    # Drop api_key_usage table
    op.drop_index('idx_usage_status_time', table_name='api_key_usage')
    op.drop_index('idx_usage_endpoint_time', table_name='api_key_usage')
    op.drop_index('idx_usage_key_time', table_name='api_key_usage')
    op.drop_index('ix_api_key_usage_created_at', table_name='api_key_usage')
    op.drop_index('ix_api_key_usage_status_code', table_name='api_key_usage')
    op.drop_index('ix_api_key_usage_endpoint', table_name='api_key_usage')
    op.drop_index('ix_api_key_usage_api_key_id', table_name='api_key_usage')
    op.drop_table('api_key_usage')
    
    # Drop api_keys table
    op.drop_index('idx_api_keys_expires', table_name='api_keys')
    op.drop_index('idx_api_keys_user_active', table_name='api_keys')
    op.drop_index('ix_api_keys_expires_at', table_name='api_keys')
    op.drop_index('ix_api_keys_is_active', table_name='api_keys')
    op.drop_index('ix_api_keys_key_prefix', table_name='api_keys')
    op.drop_index('ix_api_keys_key_hash', table_name='api_keys')
    op.drop_index('ix_api_keys_user_id', table_name='api_keys')
    op.drop_table('api_keys')
