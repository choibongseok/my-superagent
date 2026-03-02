"""Add PKCE challenges table

Revision ID: d416ac523d0a
Revises: 011_workflow_templates
Create Date: 2026-03-02 15:33:30.312754

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'd416ac523d0a'
down_revision = '011_workflow_templates'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create pkce_challenges table
    op.create_table(
        'pkce_challenges',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('state', sa.String(), nullable=False, unique=True, index=True),
        sa.Column('code_challenge', sa.String(), nullable=False),
        sa.Column('code_challenge_method', sa.String(), nullable=False, server_default='S256'),
        sa.Column('redirect_uri', sa.String(), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column('used', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )


def downgrade() -> None:
    # Drop pkce_challenges table
    op.drop_table('pkce_challenges')
