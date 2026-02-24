"""Add marketplace models - MarketplaceTemplate, TemplateInstall, TemplateRating

Revision ID: 282_add_marketplace
Revises: 212_add_nudge_week_tracking
Create Date: 2026-02-24 12:50:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '282_add_marketplace'
down_revision = '212_add_nudge_week_tracking'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum type for template categories
    op.execute("""
        CREATE TYPE templatecategory AS ENUM (
            'business', 'education', 'research', 'marketing',
            'productivity', 'data_analysis', 'reporting', 'other'
        )
    """)
    
    # Create marketplace_templates table
    op.create_table(
        'marketplace_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.Enum('business', 'education', 'research', 'marketing', 'productivity', 'data_analysis', 'reporting', 'other', name='templatecategory'), nullable=False),
        sa.Column('tags', postgresql.JSONB(), nullable=True),
        sa.Column('template_data', postgresql.JSONB(), nullable=False),
        sa.Column('prompt_template', sa.Text(), nullable=True),
        sa.Column('config', postgresql.JSONB(), nullable=True),
        sa.Column('creator_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('creator_name', sa.String(200), nullable=True),
        sa.Column('is_public', sa.Boolean(), nullable=False, default=True),
        sa.Column('is_featured', sa.Boolean(), nullable=False, default=False),
        sa.Column('is_verified', sa.Boolean(), nullable=False, default=False),
        sa.Column('is_archived', sa.Boolean(), nullable=False, default=False),
        sa.Column('install_count', sa.Integer(), nullable=False, default=0),
        sa.Column('view_count', sa.Integer(), nullable=False, default=0),
        sa.Column('rating_avg', sa.Float(), nullable=False, default=0.0),
        sa.Column('rating_count', sa.Integer(), nullable=False, default=0),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    )
    
    # Create indexes for marketplace_templates
    op.create_index('idx_marketplace_category', 'marketplace_templates', ['category'])
    op.create_index('idx_marketplace_is_public', 'marketplace_templates', ['is_public'])
    op.create_index('idx_marketplace_featured', 'marketplace_templates', ['is_featured'])
    op.create_index('idx_marketplace_rating', 'marketplace_templates', ['rating_avg'])
    op.create_index('idx_marketplace_installs', 'marketplace_templates', ['install_count'])
    
    # Create template_installs table
    op.create_table(
        'template_installs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('template_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('marketplace_templates.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('installed_name', sa.String(200), nullable=True),
        sa.Column('customizations', postgresql.JSONB(), nullable=True),
        sa.Column('usage_count', sa.Integer(), nullable=False, default=0),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('is_favorited', sa.Boolean(), nullable=False, default=False),
        sa.Column('installed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('template_id', 'user_id', name='uq_template_user_install'),
    )
    
    # Create indexes for template_installs
    op.create_index('idx_install_user', 'template_installs', ['user_id'])
    op.create_index('idx_install_template', 'template_installs', ['template_id'])
    
    # Recreate template_ratings table with new schema (drop old if exists)
    op.execute("DROP TABLE IF EXISTS template_ratings CASCADE")
    
    op.create_table(
        'template_ratings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('template_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('marketplace_templates.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('review', sa.Text(), nullable=True),
        sa.Column('helpful_count', sa.Integer(), nullable=False, default=0),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, default=False),
        sa.Column('is_flagged', sa.Boolean(), nullable=False, default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('template_id', 'user_id', name='uq_template_user_rating'),
    )
    
    # Create indexes for template_ratings
    op.create_index('idx_rating_template', 'template_ratings', ['template_id'])
    op.create_index('idx_rating_user', 'template_ratings', ['user_id'])


def downgrade() -> None:
    # Drop template_ratings
    op.drop_index('idx_rating_user', table_name='template_ratings')
    op.drop_index('idx_rating_template', table_name='template_ratings')
    op.drop_table('template_ratings')
    
    # Drop template_installs
    op.drop_index('idx_install_template', table_name='template_installs')
    op.drop_index('idx_install_user', table_name='template_installs')
    op.drop_table('template_installs')
    
    # Drop marketplace_templates
    op.drop_index('idx_marketplace_installs', table_name='marketplace_templates')
    op.drop_index('idx_marketplace_rating', table_name='marketplace_templates')
    op.drop_index('idx_marketplace_featured', table_name='marketplace_templates')
    op.drop_index('idx_marketplace_is_public', table_name='marketplace_templates')
    op.drop_index('idx_marketplace_category', table_name='marketplace_templates')
    op.drop_table('marketplace_templates')
    
    # Drop enum type
    op.execute("DROP TYPE templatecategory")
