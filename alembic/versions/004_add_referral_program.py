"""Add referral program

Revision ID: 004
Revises: 003
Create Date: 2025-12-02

This migration adds:
- Referral program fields to users table (referred_by_id, referral_code, total_referrals)
- referral_rewards table for tracking referral rewards history
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add referral program fields and rewards table"""
    conn = op.get_bind()
    inspector = inspect(conn)

    # Add referral fields to users table
    users_columns = [col['name'] for col in inspector.get_columns('users')]

    if 'referred_by_id' not in users_columns:
        op.add_column('users', sa.Column('referred_by_id', sa.Integer(), nullable=True))
        op.create_foreign_key('fk_users_referred_by', 'users', 'users', ['referred_by_id'], ['id'])
        op.create_index(op.f('ix_users_referred_by_id'), 'users', ['referred_by_id'], unique=False)

    if 'referral_code' not in users_columns:
        op.add_column('users', sa.Column('referral_code', sa.String(length=20), nullable=True))
        op.create_index(op.f('ix_users_referral_code'), 'users', ['referral_code'], unique=True)

    if 'total_referrals' not in users_columns:
        op.add_column('users', sa.Column('total_referrals', sa.Integer(), nullable=False, server_default='0'))

    # Create referral_rewards table
    tables = inspector.get_table_names()
    if 'referral_rewards' not in tables:
        op.create_table(
            'referral_rewards',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('referred_user_id', sa.Integer(), nullable=False),
            sa.Column('order_id', sa.Integer(), nullable=True),
            sa.Column('reward_type', sa.String(length=50), nullable=False),
            sa.Column('images_rewarded', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.ForeignKeyConstraint(['referred_user_id'], ['users.id'], ),
            sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
            sa.PrimaryKeyConstraint('id')
        )

        # Create indexes for referral_rewards
        op.create_index('idx_referral_rewards_user_type', 'referral_rewards', ['user_id', 'reward_type'], unique=False)
        op.create_index('idx_referral_rewards_created', 'referral_rewards', ['created_at'], unique=False)
        op.create_index(op.f('ix_referral_rewards_reward_type'), 'referral_rewards', ['reward_type'], unique=False)


def downgrade() -> None:
    """Remove referral program fields and rewards table"""
    conn = op.get_bind()
    inspector = inspect(conn)

    # Drop referral_rewards table
    tables = inspector.get_table_names()
    if 'referral_rewards' in tables:
        op.drop_index('idx_referral_rewards_created', table_name='referral_rewards')
        op.drop_index('idx_referral_rewards_user_type', table_name='referral_rewards')
        op.drop_index(op.f('ix_referral_rewards_reward_type'), table_name='referral_rewards')
        op.drop_table('referral_rewards')

    # Drop referral fields from users table
    users_columns = [col['name'] for col in inspector.get_columns('users')]

    if 'total_referrals' in users_columns:
        op.drop_column('users', 'total_referrals')

    if 'referral_code' in users_columns:
        op.drop_index(op.f('ix_users_referral_code'), table_name='users')
        op.drop_column('users', 'referral_code')

    if 'referred_by_id' in users_columns:
        op.drop_index(op.f('ix_users_referred_by_id'), table_name='users')
        op.drop_constraint('fk_users_referred_by', 'users', type_='foreignkey')
        op.drop_column('users', 'referred_by_id')
