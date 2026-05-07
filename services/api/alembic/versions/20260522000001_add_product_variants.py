"""add product_variants table

Revision ID: 20260522000001
Revises: 20260521000001
Create Date: 2026-05-22 00:00:01
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260522000001"
down_revision = "20260521000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_variants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("options", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("unit_price_cents", sa.Integer, nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("barcode", sa.String(128), nullable=True),
        sa.Column("image_url", sa.String(1024), nullable=True),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "sku", name="uq_variant_tenant_sku"),
    )
    op.create_index("ix_product_variants_product", "product_variants", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_product_variants_product", table_name="product_variants")
    op.drop_table("product_variants")
