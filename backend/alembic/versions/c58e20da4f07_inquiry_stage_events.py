"""inquiry stage events (销售漏斗)

Revision ID: c58e20da4f07
Revises: a3d91c7f5b21
Create Date: 2026-09-15
"""
from alembic import op
import sqlalchemy as sa
import app.models.base  # noqa: F401 (custom types)


revision = 'c58e20da4f07'
down_revision = 'a3d91c7f5b21'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('inquiry_stage_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('inquiry_id', sa.Integer(), nullable=False),
    sa.Column('from_stage', sa.String(length=30), nullable=True),
    sa.Column('to_stage', sa.String(length=30), nullable=False),
    sa.Column('note', sa.String(length=300), nullable=True),
    sa.Column('actor_user_id', sa.Integer(), nullable=True),
    sa.Column('occurred_at', app.models.base.TZDateTime(timezone=True), nullable=True),
    sa.Column('created_at', app.models.base.TZDateTime(timezone=True), nullable=True),
    sa.Column('updated_at', app.models.base.TZDateTime(timezone=True), nullable=True),
    sa.Column('org_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['inquiry_id'], ['inquiries.id'], ),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('inquiry_stage_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_inquiry_stage_events_org_id'), ['org_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_inquiry_stage_events_inquiry_id'), ['inquiry_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_inquiry_stage_events_to_stage'), ['to_stage'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('inquiry_stage_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_inquiry_stage_events_to_stage'))
        batch_op.drop_index(batch_op.f('ix_inquiry_stage_events_inquiry_id'))
        batch_op.drop_index(batch_op.f('ix_inquiry_stage_events_org_id'))
    op.drop_table('inquiry_stage_events')
