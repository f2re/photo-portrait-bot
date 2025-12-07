"""Add UTM tracking and Yandex Metrika integration

Revision ID: 003
Revises: e894ec52b163
Create Date: 2025-01-22

This migration adds:
- UTM tracking fields to users table (source, medium, campaign, content, term)
- metrika_client_id field to users table for Yandex Metrika integration
- utm_events table for tracking user events and conversions
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = 'e894ec52b163'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add UTM tracking fields and events table"""
    conn = op.get_bind()
    inspector = inspect(conn)

    # Add UTM fields to users table
    users_columns = [col['name'] for col in inspector.get_columns('users')]

    if 'utm_source' not in users_columns:
        op.add_column('users', sa.Column('utm_source', sa.String(length=255), nullable=True))
        op.create_index(op.f('ix_users_utm_source'), 'users', ['utm_source'], unique=False)

    if 'utm_medium' not in users_columns:
        op.add_column('users', sa.Column('utm_medium', sa.String(length=255), nullable=True))
        op.create_index(op.f('ix_users_utm_medium'), 'users', ['utm_medium'], unique=False)

    if 'utm_campaign' not in users_columns:
        op.add_column('users', sa.Column('utm_campaign', sa.String(length=255), nullable=True))
        op.create_index(op.f('ix_users_utm_campaign'), 'users', ['utm_campaign'], unique=False)

    if 'utm_content' not in users_columns:
        op.add_column('users', sa.Column('utm_content', sa.String(length=255), nullable=True))

    if 'utm_term' not in users_columns:
        op.add_column('users', sa.Column('utm_term', sa.String(length=255), nullable=True))

    if 'metrika_client_id' not in users_columns:
        op.add_column('users', sa.Column('metrika_client_id', sa.String(length=36), nullable=True))
        op.create_index(op.f('ix_users_metrika_client_id'), 'users', ['metrika_client_id'], unique=True)

    # Create utm_events table
    tables = inspector.get_table_names()
    if 'utm_events' not in tables:
        op.create_table(
            'utm_events',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('event_type', sa.String(length=50), nullable=False),
            sa.Column('metrika_client_id', sa.String(length=36), nullable=True),
            sa.Column('event_value', sa.Numeric(precision=10, scale=2), nullable=True),
            sa.Column('currency', sa.String(length=3), nullable=True, server_default='RUB'),
            sa.Column('event_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column('sent_to_metrika', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('sent_at', sa.DateTime(), nullable=True),
            sa.Column('metrika_upload_id', sa.String(length=255), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id')
        )

        # Create indexes for utm_events
        op.create_index('idx_utm_events_user_type', 'utm_events', ['user_id', 'event_type'], unique=False)
        op.create_index('idx_utm_events_created', 'utm_events', ['created_at'], unique=False)
        op.create_index('idx_utm_events_sent', 'utm_events', ['sent_to_metrika'], unique=False)
        op.create_index(op.f('ix_utm_events_event_type'), 'utm_events', ['event_type'], unique=False)
        op.create_index(op.f('ix_utm_events_metrika_client_id'), 'utm_events', ['metrika_client_id'], unique=False)


def downgrade() -> None:
    """Remove UTM tracking fields and events table"""
    conn = op.get_bind()
    inspector = inspect(conn)

    # Drop utm_events table
    tables = inspector.get_table_names()
    if 'utm_events' in tables:
        op.drop_index('idx_utm_events_sent', table_name='utm_events')
        op.drop_index('idx_utm_events_created', table_name='utm_events')
        op.drop_index('idx_utm_events_user_type', table_name='utm_events')
        op.drop_index(op.f('ix_utm_events_metrika_client_id'), table_name='utm_events')
        op.drop_index(op.f('ix_utm_events_event_type'), table_name='utm_events')
        op.drop_table('utm_events')

    # Drop UTM fields from users table
    users_columns = [col['name'] for col in inspector.get_columns('users')]

    if 'metrika_client_id' in users_columns:
        op.drop_index(op.f('ix_users_metrika_client_id'), table_name='users')
        op.drop_column('users', 'metrika_client_id')

    if 'utm_term' in users_columns:
        op.drop_column('users', 'utm_term')

    if 'utm_content' in users_columns:
        op.drop_column('users', 'utm_content')

    if 'utm_campaign' in users_columns:
        op.drop_index(op.f('ix_users_utm_campaign'), table_name='users')
        op.drop_column('users', 'utm_campaign')

    if 'utm_medium' in users_columns:
        op.drop_index(op.f('ix_users_utm_medium'), table_name='users')
        op.drop_column('users', 'utm_medium')

    if 'utm_source' in users_columns:
        op.drop_index(op.f('ix_users_utm_source'), table_name='users')
        op.drop_column('users', 'utm_source')
