"""Rename robokassa_invoice_id to invoice_id

Revision ID: e894ec52b163
Revises: 002
Create Date: 2025-11-16 13:59:57.811816

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'e894ec52b163'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('orders')]

    # Rename robokassa_invoice_id to invoice_id in orders table
    if 'robokassa_invoice_id' in columns and 'invoice_id' not in columns:
        op.alter_column('orders', 'robokassa_invoice_id', new_column_name='invoice_id')


def downgrade() -> None:
    # Rename invoice_id back to robokassa_invoice_id
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('orders')]

    if 'invoice_id' in columns and 'robokassa_invoice_id' not in columns:
        op.alter_column('orders', 'invoice_id', new_column_name='robokassa_invoice_id')