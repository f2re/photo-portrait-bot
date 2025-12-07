"""Initial migration

Revision ID: 001
Revises:
Create Date: 2025-01-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()

    # Create users table
    if 'users' not in tables:
        op.create_table(
            'users',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('telegram_id', sa.BigInteger(), nullable=False),
            sa.Column('username', sa.String(length=255), nullable=True),
            sa.Column('first_name', sa.String(length=255), nullable=True),
            sa.Column('free_images_left', sa.Integer(), nullable=False, server_default='3'),
            sa.Column('total_images_processed', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('telegram_id')
        )

    # Create packages table
    if 'packages' not in tables:
        op.create_table(
            'packages',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=50), nullable=False),
            sa.Column('images_count', sa.Integer(), nullable=False),
            sa.Column('price_rub', sa.Numeric(precision=10, scale=2), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.PrimaryKeyConstraint('id')
        )

        # Insert default packages only if we created the table
        op.execute("""
            INSERT INTO packages (name, images_count, price_rub, is_active) VALUES
            ('1 изображение', 1, 50.00, true),
            ('5 изображений', 5, 200.00, true),
            ('10 изображений', 10, 350.00, true),
            ('50 изображений', 50, 1500.00, true)
        """)

    # Create orders table
    if 'orders' not in tables:
        op.create_table(
            'orders',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('package_id', sa.Integer(), nullable=False),
            sa.Column('robokassa_invoice_id', sa.String(length=255), nullable=True),
            sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
            sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('paid_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.ForeignKeyConstraint(['package_id'], ['packages.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('robokassa_invoice_id')
        )

    # Create processed_images table
    if 'processed_images' not in tables:
        op.create_table(
            'processed_images',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('order_id', sa.Integer(), nullable=True),
            sa.Column('original_file_id', sa.String(length=255), nullable=True),
            sa.Column('processed_file_id', sa.String(length=255), nullable=True),
            sa.Column('prompt_used', sa.Text(), nullable=True),
            sa.Column('is_free', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
            sa.PrimaryKeyConstraint('id')
        )

    # Create support_tickets table
    if 'support_tickets' not in tables:
        op.create_table(
            'support_tickets',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('order_id', sa.Integer(), nullable=True),
            sa.Column('message', sa.Text(), nullable=False),
            sa.Column('status', sa.String(length=50), nullable=False, server_default='open'),
            sa.Column('admin_response', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('resolved_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
            sa.PrimaryKeyConstraint('id')
        )

    # Create admins table
    if 'admins' not in tables:
        op.create_table(
            'admins',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('telegram_id', sa.BigInteger(), nullable=False),
            sa.Column('username', sa.String(length=255), nullable=True),
            sa.Column('role', sa.String(length=50), nullable=False, server_default='admin'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('telegram_id')
        )


def downgrade() -> None:
    op.drop_table('admins')
    op.drop_table('support_tickets')
    op.drop_table('processed_images')
    op.drop_table('orders')
    op.drop_table('packages')
    op.drop_table('users')