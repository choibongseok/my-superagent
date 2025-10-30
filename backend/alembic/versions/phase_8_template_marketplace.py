"""Add template marketplace and plugin system models (Phase 8)

Revision ID: phase_8_templates
Revises: c4d39e6ece1f
Create Date: 2025-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'phase_8_templates'
down_revision = 'c4d39e6ece1f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create teams table
    op.create_table(
        'teams',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_teams_owner_id'), 'teams', ['owner_id'], unique=False)

    # Create templates table
    op.create_table(
        'templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(length=100), nullable=False),
        sa.Column('tags', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('author_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('prompt_template', sa.Text(), nullable=False),
        sa.Column('parameters', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('example_inputs', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('example_outputs', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_official', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_featured', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('usage_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('rating', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('rating_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('version', sa.String(length=20), nullable=False, server_default='1.0.0'),
        sa.Column('changelog', sa.Text(), nullable=True),
        sa.Column('parent_template_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['author_id'], ['users.id']),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['parent_template_id'], ['templates.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for templates
    op.create_index(op.f('ix_templates_category'), 'templates', ['category'], unique=False)
    op.create_index(op.f('ix_templates_author_id'), 'templates', ['author_id'], unique=False)
    op.create_index(op.f('ix_templates_team_id'), 'templates', ['team_id'], unique=False)
    op.create_index(op.f('ix_templates_is_public'), 'templates', ['is_public'], unique=False)
    op.create_index(op.f('ix_templates_is_official'), 'templates', ['is_official'], unique=False)
    op.create_index(op.f('ix_templates_is_featured'), 'templates', ['is_featured'], unique=False)
    op.create_index(op.f('ix_templates_usage_count'), 'templates', ['usage_count'], unique=False)

    # Composite indexes
    op.create_index('ix_templates_category_public', 'templates', ['category', 'is_public'], unique=False)
    op.create_index('ix_templates_author_public', 'templates', ['author_id', 'is_public'], unique=False)
    op.create_index('ix_templates_usage_rating', 'templates', ['usage_count', 'rating'], unique=False)
    op.create_index('ix_templates_featured_public', 'templates', ['is_featured', 'is_public'], unique=False)

    # Create template_ratings table
    op.create_table(
        'template_ratings',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('template_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('review', sa.Text(), nullable=True),
        sa.Column('helpful_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('unhelpful_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['template_id'], ['templates.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for template_ratings
    op.create_index(op.f('ix_template_ratings_template_id'), 'template_ratings', ['template_id'], unique=False)
    op.create_index(op.f('ix_template_ratings_user_id'), 'template_ratings', ['user_id'], unique=False)
    op.create_index('ix_template_ratings_unique', 'template_ratings', ['template_id', 'user_id'], unique=True)
    op.create_index('ix_template_ratings_template', 'template_ratings', ['template_id', 'rating'], unique=False)


def downgrade() -> None:
    # Drop template_ratings
    op.drop_index('ix_template_ratings_template', table_name='template_ratings')
    op.drop_index('ix_template_ratings_unique', table_name='template_ratings')
    op.drop_index(op.f('ix_template_ratings_user_id'), table_name='template_ratings')
    op.drop_index(op.f('ix_template_ratings_template_id'), table_name='template_ratings')
    op.drop_table('template_ratings')

    # Drop templates
    op.drop_index('ix_templates_featured_public', table_name='templates')
    op.drop_index('ix_templates_usage_rating', table_name='templates')
    op.drop_index('ix_templates_author_public', table_name='templates')
    op.drop_index('ix_templates_category_public', table_name='templates')
    op.drop_index(op.f('ix_templates_usage_count'), table_name='templates')
    op.drop_index(op.f('ix_templates_is_featured'), table_name='templates')
    op.drop_index(op.f('ix_templates_is_official'), table_name='templates')
    op.drop_index(op.f('ix_templates_is_public'), table_name='templates')
    op.drop_index(op.f('ix_templates_team_id'), table_name='templates')
    op.drop_index(op.f('ix_templates_author_id'), table_name='templates')
    op.drop_index(op.f('ix_templates_category'), table_name='templates')
    op.drop_table('templates')

    # Drop teams
    op.drop_index(op.f('ix_teams_owner_id'), table_name='teams')
    op.drop_table('teams')
