"""add storage configuration fields to tenants

Revision ID: 20260524000001
Revises: 20260523000001
Create Date: 2026-05-24 00:00:01
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "20260524000001"
down_revision = "20260523000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants",
        sa.Column("storage_mode", sa.String(16), nullable=False, server_default="platform"))
    op.add_column("tenants",
        sa.Column("byo_storage_endpoint", sa.Text, nullable=True))
    op.add_column("tenants",
        sa.Column("byo_storage_bucket", sa.String(255), nullable=True))
    op.add_column("tenants",
        sa.Column("byo_storage_access_key", sa.Text, nullable=True))
    op.add_column("tenants",
        sa.Column("byo_storage_secret_key", sa.Text, nullable=True))
    op.add_column("tenants",
        sa.Column("byo_storage_public_url", sa.String(512), nullable=True))
    op.add_column("tenants",
        sa.Column("byo_storage_region", sa.String(32), nullable=True))


def downgrade() -> None:
    for col in ["storage_mode", "byo_storage_endpoint", "byo_storage_bucket",
                "byo_storage_access_key", "byo_storage_secret_key",
                "byo_storage_public_url", "byo_storage_region"]:
        op.drop_column("tenants", col)
