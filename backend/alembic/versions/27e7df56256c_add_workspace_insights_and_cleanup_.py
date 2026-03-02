"""Add workspace insights and cleanup tracking

Revision ID: 27e7df56256c
Revises: ebe179f3ceca
Create Date: 2026-03-02 16:32:56.520459

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '27e7df56256c'
down_revision = 'ebe179f3ceca'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create workspace_insights table
    op.create_table(
        'workspace_insights',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('analyzed_at', sa.DateTime(), nullable=False),
        sa.Column('total_files', sa.Integer(), nullable=True, default=0),
        sa.Column('total_size_bytes', sa.Integer(), nullable=True, default=0),
        sa.Column('duplicate_files', sa.JSON(), nullable=True),
        sa.Column('stale_files', sa.JSON(), nullable=True),
        sa.Column('storage_breakdown', sa.JSON(), nullable=True),
        sa.Column('organization_suggestions', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_workspace_insights_id'), 'workspace_insights', ['id'], unique=False)
    op.create_index(op.f('ix_workspace_insights_user_id'), 'workspace_insights', ['user_id'], unique=False)
    
    # Create workspace_cleanup_logs table
    op.create_table(
        'workspace_cleanup_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('insight_id', sa.Integer(), nullable=True),
        sa.Column('operation_type', sa.String(length=50), nullable=False),
        sa.Column('performed_at', sa.DateTime(), nullable=False),
        sa.Column('files_affected', sa.Integer(), nullable=True, default=0),
        sa.Column('bytes_freed', sa.Integer(), nullable=True, default=0),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['insight_id'], ['workspace_insights.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_workspace_cleanup_logs_id'), 'workspace_cleanup_logs', ['id'], unique=False)
    op.create_index(op.f('ix_workspace_cleanup_logs_user_id'), 'workspace_cleanup_logs', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_workspace_cleanup_logs_user_id'), table_name='workspace_cleanup_logs')
    op.drop_index(op.f('ix_workspace_cleanup_logs_id'), table_name='workspace_cleanup_logs')
    op.drop_table('workspace_cleanup_logs')
    
    op.drop_index(op.f('ix_workspace_insights_user_id'), table_name='workspace_insights')
    op.drop_index(op.f('ix_workspace_insights_id'), table_name='workspace_insights')
    op.drop_table('workspace_insights')
