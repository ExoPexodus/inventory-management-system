"""add storage quota tracking fields

Revision ID: 20260525000001
Revises: 20260524000001
Create Date: 2026-05-25 00:00:01
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "20260525000001"
down_revision = "20260524000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants",
        sa.Column("storage_bytes_used", sa.BigInteger, nullable=False, server_default="0"))
    op.add_column("product_images",
        sa.Column("file_size_bytes", sa.BigInteger, nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "storage_bytes_used")
    op.drop_column("product_images", "file_size_bytes")
