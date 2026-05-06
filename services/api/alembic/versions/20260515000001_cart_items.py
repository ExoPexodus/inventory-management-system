"""Headless storefront: cart_items table

Revision ID: 20260515000001
Revises: 20260514000002
Create Date: 2026-05-15 00:00:01.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "20260515000001"
down_revision = "20260514000002"
branch_labels = None
depends_on = None


_RLS_POLICY = """
COALESCE(current_setting('ims.is_admin', true), '') = 'true'
OR (
  NULLIF(TRIM(COALESCE(current_setting('ims.tenant_id', true), '')), '') IS NOT NULL
  AND tenant_id = (NULLIF(TRIM(COALESCE(current_setting('ims.tenant_id', true), '')), ''))::uuid
)
"""


def upgrade() -> None:
    op.create_table(
        "cart_items",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cart_token", sa.String(128), nullable=False),
        sa.Column("product_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("unit_price_cents", sa.Integer, nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("reservation_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("stock_reservations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("cart_token", "product_id", name="uq_cart_item_token_product"),
    )
    op.create_index("ix_cart_items_cart_token", "cart_items", ["cart_token"])
    op.create_index("ix_cart_items_channel_id", "cart_items", ["channel_id"])
    op.create_index("ix_cart_items_tenant_id", "cart_items", ["tenant_id"])

    op.execute(f"""
        ALTER TABLE cart_items ENABLE ROW LEVEL SECURITY;
        ALTER TABLE cart_items FORCE ROW LEVEL SECURITY;
        CREATE POLICY ims_tenant_isolation ON cart_items
        USING ({_RLS_POLICY})
        WITH CHECK ({_RLS_POLICY});
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS ims_tenant_isolation ON cart_items;")
    op.execute("ALTER TABLE cart_items NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE cart_items DISABLE ROW LEVEL SECURITY;")
    op.drop_index("ix_cart_items_tenant_id", table_name="cart_items")
    op.drop_index("ix_cart_items_channel_id", table_name="cart_items")
    op.drop_index("ix_cart_items_cart_token", table_name="cart_items")
    op.drop_table("cart_items")
