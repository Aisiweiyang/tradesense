"""document field changes (单证版本差异)

Revision ID: a3d91c7f5b21
Revises: faa503be34fc
Create Date: 2026-09-14
"""
from alembic import op
import sqlalchemy as sa
import app.models.base  # noqa: F401 (custom types)


revision = 'a3d91c7f5b21'
down_revision = 'faa503be34fc'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('document_field_changes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('prev_document_id', sa.Integer(), nullable=True),
    sa.Column('shipment_id', sa.Integer(), nullable=False),
    sa.Column('field_name', sa.String(length=60), nullable=False),
    sa.Column('old_value', sa.Text(), nullable=True),
    sa.Column('new_value', sa.Text(), nullable=True),
    sa.Column('change_type', sa.String(length=10), nullable=True),
    sa.Column('prev_version', sa.Integer(), nullable=True),
    sa.Column('changed_at', app.models.base.TZDateTime(timezone=True), nullable=True),
    sa.Column('created_at', app.models.base.TZDateTime(timezone=True), nullable=True),
    sa.Column('updated_at', app.models.base.TZDateTime(timezone=True), nullable=True),
    sa.Column('org_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ),
    sa.ForeignKeyConstraint(['prev_document_id'], ['documents.id'], ),
    sa.ForeignKeyConstraint(['shipment_id'], ['shipments.id'], ),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('document_field_changes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_document_field_changes_org_id'), ['org_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_document_field_changes_document_id'), ['document_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_document_field_changes_shipment_id'), ['shipment_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_document_field_changes_field_name'), ['field_name'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('document_field_changes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_document_field_changes_field_name'))
        batch_op.drop_index(batch_op.f('ix_document_field_changes_shipment_id'))
        batch_op.drop_index(batch_op.f('ix_document_field_changes_document_id'))
        batch_op.drop_index(batch_op.f('ix_document_field_changes_org_id'))
    op.drop_table('document_field_changes')
