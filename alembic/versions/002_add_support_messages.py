"""Add support messages and enhance support tickets

Revision ID: 002
Revises: 001
Create Date: 2025-01-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Get database connection and inspector
    conn = op.get_bind()
    inspector = inspect(conn)

    # Check if admin_id column exists before adding it
    columns = [col['name'] for col in inspector.get_columns('support_tickets')]
    if 'admin_id' not in columns:
        op.add_column(
            'support_tickets',
            sa.Column('admin_id', sa.BigInteger(), nullable=True)
        )

    # Check if support_messages table exists before creating it
    tables = inspector.get_table_names()
    if 'support_messages' not in tables:
        op.create_table(
            'support_messages',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('ticket_id', sa.Integer(), nullable=False),
            sa.Column('sender_telegram_id', sa.BigInteger(), nullable=False),
            sa.Column('is_admin', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('message', sa.Text(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['ticket_id'], ['support_tickets.id'], ),
            sa.PrimaryKeyConstraint('id')
        )


def downgrade() -> None:
    # Get database connection and inspector
    conn = op.get_bind()
    inspector = inspect(conn)

    # Check if support_messages table exists before dropping it
    tables = inspector.get_table_names()
    if 'support_messages' in tables:
        op.drop_table('support_messages')

    # Check if admin_id column exists before dropping it
    columns = [col['name'] for col in inspector.get_columns('support_tickets')]
    if 'admin_id' in columns:
        op.drop_column('support_tickets', 'admin_id')
