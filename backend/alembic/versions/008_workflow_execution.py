"""Add workflow execution tracking

Revision ID: 008_workflow_execution
Revises: 007_enhanced_oauth
Create Date: 2026-03-02 07:05:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '008_workflow_execution'
down_revision = '007_enhanced_oauth'
branch_labels = None
depends_on = None


def upgrade():
    """Add workflow_executions table."""
    op.create_table(
        'workflow_executions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('execution_id', sa.String(length=36), nullable=False),
        sa.Column('workflow_id', sa.String(length=100), nullable=False),
        sa.Column('workflow_name', sa.String(length=255), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('current_step', sa.String(length=36), nullable=True),
        sa.Column('initial_inputs', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('step_results', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('final_output', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('metadata', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    
    # Indexes
    op.create_index(op.f('ix_workflow_executions_id'), 'workflow_executions', ['id'], unique=False)
    op.create_index(op.f('ix_workflow_executions_execution_id'), 'workflow_executions', ['execution_id'], unique=True)
    op.create_index(op.f('ix_workflow_executions_workflow_id'), 'workflow_executions', ['workflow_id'], unique=False)
    op.create_index(op.f('ix_workflow_executions_user_id'), 'workflow_executions', ['user_id'], unique=False)
    op.create_index(op.f('ix_workflow_executions_status'), 'workflow_executions', ['status'], unique=False)


def downgrade():
    """Remove workflow_executions table."""
    op.drop_index(op.f('ix_workflow_executions_status'), table_name='workflow_executions')
    op.drop_index(op.f('ix_workflow_executions_user_id'), table_name='workflow_executions')
    op.drop_index(op.f('ix_workflow_executions_workflow_id'), table_name='workflow_executions')
    op.drop_index(op.f('ix_workflow_executions_execution_id'), table_name='workflow_executions')
    op.drop_index(op.f('ix_workflow_executions_id'), table_name='workflow_executions')
    op.drop_table('workflow_executions')
