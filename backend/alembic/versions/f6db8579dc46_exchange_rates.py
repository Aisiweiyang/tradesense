"""exchange rates (手工汇率配置)

Revision ID: f6db8579dc46
Revises: c58e20da4f07
Create Date: 2026-09-15
"""
from alembic import op
import sqlalchemy as sa
import app.models.base  # noqa: F401 (custom types)


revision = 'f6db8579dc46'
down_revision = 'c58e20da4f07'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('exchange_rates',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('base_currency', sa.String(length=3), nullable=True),
    sa.Column('quote_currency', sa.String(length=3), nullable=True),
    sa.Column('rate', sa.Float(), nullable=True),
    sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', app.models.base.TZDateTime(timezone=True), nullable=True),
    sa.Column('updated_at', app.models.base.TZDateTime(timezone=True), nullable=True),
    sa.Column('org_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('exchange_rates', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_exchange_rates_org_id'), ['org_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('exchange_rates', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_exchange_rates_org_id'))
    op.drop_table('exchange_rates')
