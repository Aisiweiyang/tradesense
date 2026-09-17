"""org settings and inquiry attachments

Revision ID: bbfad02a6489
Revises: b4e1c7d2a908
Create Date: 2026-09-18 00:07:26.247850
"""
from alembic import op
import sqlalchemy as sa
import app.models.base  # noqa: F401 (custom types)


revision = 'bbfad02a6489'
down_revision = 'b4e1c7d2a908'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('organizations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('settings_json', sa.Text(), nullable=True))
    op.execute("UPDATE organizations SET settings_json = '{}' WHERE settings_json IS NULL")
    op.create_table('inquiry_attachments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('inquiry_id', sa.Integer(), nullable=False),
    sa.Column('file_path', sa.String(length=500), nullable=True),
    sa.Column('original_filename', sa.String(length=300), nullable=True),
    sa.Column('media_type', sa.String(length=50), nullable=True),
    sa.Column('size', sa.Integer(), nullable=True),
    sa.Column('extracted_text', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('uploaded_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', app.models.base.TZDateTime(timezone=True), nullable=True),
    sa.Column('updated_at', app.models.base.TZDateTime(timezone=True), nullable=True),
    sa.Column('org_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['inquiry_id'], ['inquiries.id'], ),
    sa.ForeignKeyConstraint(['uploaded_by_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('inquiry_attachments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_inquiry_attachments_org_id'), ['org_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_inquiry_attachments_inquiry_id'), ['inquiry_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('inquiry_attachments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_inquiry_attachments_inquiry_id'))
        batch_op.drop_index(batch_op.f('ix_inquiry_attachments_org_id'))
    op.drop_table('inquiry_attachments')
    with op.batch_alter_table('organizations', schema=None) as batch_op:
        batch_op.drop_column('settings_json')
