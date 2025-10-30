"""Add chat and message models

Revision ID: c4d39e6ece1f
Revises: 001
Create Date: 2025-10-29 08:40:53.620666

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4d39e6ece1f'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create message_role enum
    op.execute("CREATE TYPE message_role AS ENUM ('user', 'assistant', 'system')")

    # Create chats table
    op.create_table(
        'chats',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chats_user_id'), 'chats', ['user_id'], unique=False)

    # Create messages table
    op.create_table(
        'messages',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('chat_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('role', sa.Enum('user', 'assistant', 'system', name='message_role'), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['chat_id'], ['chats.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_messages_chat_id'), 'messages', ['chat_id'], unique=False)
    op.create_index(op.f('ix_messages_user_id'), 'messages', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_messages_user_id'), table_name='messages')
    op.drop_index(op.f('ix_messages_chat_id'), table_name='messages')
    op.drop_table('messages')
    op.drop_index(op.f('ix_chats_user_id'), table_name='chats')
    op.drop_table('chats')
    op.execute('DROP TYPE message_role')
