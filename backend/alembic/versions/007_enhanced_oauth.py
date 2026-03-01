"""Enhanced OAuth features - refresh token rotation and multi-provider support.

Revision ID: 007_enhanced_oauth
Revises: 006_claude_integration
Create Date: 2026-03-01

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '007_enhanced_oauth'
down_revision = '006_claude_integration'
branch_labels = None
depends_on = None


def upgrade():
    """Add refresh_tokens and oauth_connections tables for enhanced OAuth."""
    
    # Create refresh_tokens table for token rotation
    op.create_table(
        'refresh_tokens',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('token_hash', sa.String(length=255), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('is_revoked', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('device_id', sa.String(length=255), nullable=True),
        sa.Column('user_agent', sa.String(length=512), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('token_family', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('previous_token_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['previous_token_id'], ['refresh_tokens.id'], ondelete='SET NULL'),
    )
    op.create_index('ix_refresh_tokens_user_id', 'refresh_tokens', ['user_id'])
    op.create_index('ix_refresh_tokens_token_hash', 'refresh_tokens', ['token_hash'], unique=True)
    op.create_index('ix_refresh_tokens_is_revoked', 'refresh_tokens', ['is_revoked'])
    op.create_index('ix_refresh_tokens_token_family', 'refresh_tokens', ['token_family'])
    
    # Create oauth_connections table for multi-provider support
    op.create_table(
        'oauth_connections',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider', sa.Enum('GOOGLE', 'GITHUB', 'MICROSOFT', name='oauthprovider'), nullable=False),
        sa.Column('provider_user_id', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('access_token_encrypted', sa.String(length=1024), nullable=False),
        sa.Column('refresh_token_encrypted', sa.String(length=1024), nullable=True),
        sa.Column('token_expires_at', sa.DateTime(), nullable=True),
        sa.Column('scopes', sa.String(length=1024), nullable=True),
        sa.Column('provider_data', sa.String(length=2048), nullable=True),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_oauth_connections_user_id', 'oauth_connections', ['user_id'])
    op.create_index('ix_oauth_connections_provider', 'oauth_connections', ['provider'])
    op.create_index('ix_oauth_connections_provider_user_id', 'oauth_connections', ['provider_user_id'])
    
    # Migrate existing Google OAuth tokens to oauth_connections
    # This is a data migration - existing users with google_access_token get a connection entry
    op.execute("""
        INSERT INTO oauth_connections (
            id, user_id, provider, provider_user_id, email,
            access_token_encrypted, refresh_token_encrypted,
            created_at, updated_at
        )
        SELECT
            gen_random_uuid(),
            id,
            'GOOGLE',
            google_id,
            email,
            COALESCE(google_access_token, ''),
            COALESCE(google_refresh_token, ''),
            created_at,
            updated_at
        FROM users
        WHERE google_id IS NOT NULL AND google_access_token IS NOT NULL
    """)


def downgrade():
    """Remove enhanced OAuth tables."""
    op.drop_index('ix_oauth_connections_provider_user_id', table_name='oauth_connections')
    op.drop_index('ix_oauth_connections_provider', table_name='oauth_connections')
    op.drop_index('ix_oauth_connections_user_id', table_name='oauth_connections')
    op.drop_table('oauth_connections')
    op.execute('DROP TYPE oauthprovider')
    
    op.drop_index('ix_refresh_tokens_token_family', table_name='refresh_tokens')
    op.drop_index('ix_refresh_tokens_is_revoked', table_name='refresh_tokens')
    op.drop_index('ix_refresh_tokens_token_hash', table_name='refresh_tokens')
    op.drop_index('ix_refresh_tokens_user_id', table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
