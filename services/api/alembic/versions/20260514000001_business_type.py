"""Add business_type to tenants and kind to shops

Revision ID: 20260514000001
Revises: 20260513000001
Create Date: 2026-05-14 00:00:01.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260514000001"
down_revision = "20260513000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column(
        "business_type", sa.String(32), nullable=False, server_default="retail"
    ))
    op.add_column("shops", sa.Column(
        "kind", sa.String(32), nullable=False, server_default="physical"
    ))
    op.create_index("ix_shops_kind", "shops", ["tenant_id", "kind"])


def downgrade() -> None:
    op.drop_index("ix_shops_kind", table_name="shops")
    op.drop_column("shops", "kind")
    op.drop_column("tenants", "business_type")
