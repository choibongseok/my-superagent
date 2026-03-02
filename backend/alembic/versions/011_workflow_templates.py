"""add workflow templates

Revision ID: 011_workflow_templates
Revises: 010_api_key_management
Create Date: 2026-03-02 15:22:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '011_workflow_templates'
down_revision = '010_api_key_management'
branch_labels = None
depends_on = None


def upgrade():
    # Create workflow_templates table
    op.create_table(
        'workflow_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('version', sa.String(length=20), nullable=False, server_default='v1'),
        sa.Column('steps', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('variables', postgresql.JSON(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('triggers', postgresql.JSON(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('tags', postgresql.JSON(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for workflow_templates
    op.create_index('ix_workflow_templates_name', 'workflow_templates', ['name'])
    op.create_index('ix_workflow_templates_category', 'workflow_templates', ['category'])
    op.create_index('ix_workflow_templates_created_by_public', 'workflow_templates', ['created_by_id', 'is_public'])
    op.create_index('ix_workflow_templates_category_public', 'workflow_templates', ['category', 'is_public'])
    
    # Create workflow_executions table
    op.create_table(
        'workflow_executions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workflow_template_id', sa.Integer(), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('current_step', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_steps', sa.Integer(), nullable=False),
        sa.Column('input_variables', postgresql.JSON(astext_type=sa.Text()), nullable=True, server_default='{}'),
        sa.Column('results', postgresql.JSON(astext_type=sa.Text()), nullable=True, server_default='{}'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['workflow_template_id'], ['workflow_templates.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for workflow_executions
    op.create_index('ix_workflow_executions_status', 'workflow_executions', ['status'])
    op.create_index('ix_workflow_executions_user_status', 'workflow_executions', ['user_id', 'status'])
    op.create_index('ix_workflow_executions_started_at', 'workflow_executions', ['started_at'])


def downgrade():
    # Drop workflow_executions table
    op.drop_index('ix_workflow_executions_started_at', table_name='workflow_executions')
    op.drop_index('ix_workflow_executions_user_status', table_name='workflow_executions')
    op.drop_index('ix_workflow_executions_status', table_name='workflow_executions')
    op.drop_table('workflow_executions')
    
    # Drop workflow_templates table
    op.drop_index('ix_workflow_templates_category_public', table_name='workflow_templates')
    op.drop_index('ix_workflow_templates_created_by_public', table_name='workflow_templates')
    op.drop_index('ix_workflow_templates_category', table_name='workflow_templates')
    op.drop_index('ix_workflow_templates_name', table_name='workflow_templates')
    op.drop_table('workflow_templates')
