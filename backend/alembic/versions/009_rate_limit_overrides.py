"""Add rate limit overrides and is_admin field

Revision ID: 009_rate_limit_overrides
Revises: 7eb9bc6c90a4
Create Date: 2026-03-02 09:40:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '009_rate_limit_overrides'
down_revision = '7eb9bc6c90a4'
branch_labels = None
depends_on = None


def upgrade():
    """Add rate_limit_overrides table and is_admin field to users."""
    
    # Add is_admin field to users table
    op.add_column(
        'users',
        sa.Column('is_admin', sa.Boolean(), nullable=False, server_default='false')
    )
    op.create_index(op.f('ix_users_is_admin'), 'users', ['is_admin'], unique=False)
    
    # Create rate_limit_overrides table
    op.create_table(
        'rate_limit_overrides',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('endpoint_pattern', sa.String(length=255), nullable=False),
        sa.Column('custom_limit', sa.Integer(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('reason', sa.String(length=500), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='CASCADE'),
    )
    
    # Indexes for rate_limit_overrides
    op.create_index(op.f('ix_rate_limit_overrides_id'), 'rate_limit_overrides', ['id'], unique=False)
    op.create_index(
        'ix_rate_limit_override_user_endpoint', 
        'rate_limit_overrides', 
        ['user_id', 'endpoint_pattern'], 
        unique=False
    )
    op.create_index(
        'ix_rate_limit_override_expires_at', 
        'rate_limit_overrides', 
        ['expires_at'], 
        unique=False
    )


def downgrade():
    """Remove rate_limit_overrides table and is_admin field."""
    
    # Drop rate_limit_overrides table
    op.drop_index('ix_rate_limit_override_expires_at', table_name='rate_limit_overrides')
    op.drop_index('ix_rate_limit_override_user_endpoint', table_name='rate_limit_overrides')
    op.drop_index(op.f('ix_rate_limit_overrides_id'), table_name='rate_limit_overrides')
    op.drop_table('rate_limit_overrides')
    
    # Drop is_admin field from users
    op.drop_index(op.f('ix_users_is_admin'), table_name='users')
    op.drop_column('users', 'is_admin')
