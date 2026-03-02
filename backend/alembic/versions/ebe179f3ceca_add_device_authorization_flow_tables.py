"""Add device authorization flow tables

Revision ID: ebe179f3ceca
Revises: d416ac523d0a
Create Date: 2026-03-02 16:02:46.736022

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ebe179f3ceca'
down_revision = 'd416ac523d0a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create device_codes table for OAuth Device Authorization Flow."""
    op.create_table(
        'device_codes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('device_code', sa.String(length=128), nullable=False),
        sa.Column('user_code', sa.String(length=8), nullable=False),
        sa.Column('verification_uri', sa.String(length=255), nullable=False),
        sa.Column('verification_uri_complete', sa.String(length=512), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('interval', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('approved', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('denied', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('access_token', sa.Text(), nullable=True),
        sa.Column('client_id', sa.String(length=255), nullable=True),
        sa.Column('scope', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('last_polled_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    
    # Indexes for fast lookups
    op.create_index(op.f('ix_device_codes_device_code'), 'device_codes', ['device_code'], unique=True)
    op.create_index(op.f('ix_device_codes_user_code'), 'device_codes', ['user_code'], unique=True)
    op.create_index(op.f('ix_device_codes_user_id'), 'device_codes', ['user_id'], unique=False)
    op.create_index(op.f('ix_device_codes_expires_at'), 'device_codes', ['expires_at'], unique=False)


def downgrade() -> None:
    """Drop device_codes table."""
    op.drop_index(op.f('ix_device_codes_expires_at'), table_name='device_codes')
    op.drop_index(op.f('ix_device_codes_user_id'), table_name='device_codes')
    op.drop_index(op.f('ix_device_codes_user_code'), table_name='device_codes')
    op.drop_index(op.f('ix_device_codes_device_code'), table_name='device_codes')
    op.drop_table('device_codes')
