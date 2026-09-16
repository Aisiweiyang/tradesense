"""documents: unique (org, shipment, doc_type, version)

Revision ID: b4e1c7d2a908
Revises: f6db8579dc46
Create Date: 2026-09-16
"""
from alembic import op


revision = 'b4e1c7d2a908'
down_revision = 'f6db8579dc46'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index('uq_documents_shipment_type_version', 'documents',
                    ['org_id', 'shipment_id', 'doc_type', 'version'], unique=True)


def downgrade() -> None:
    op.drop_index('uq_documents_shipment_type_version', table_name='documents')
