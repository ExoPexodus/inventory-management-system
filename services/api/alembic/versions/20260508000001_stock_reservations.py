"""Stock reservations: soft-TTL holds on stock for channel carts / pending payments

Revision ID: 20260508000001
Revises: 20260507000001
Create Date: 2026-05-08 00:00:01.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "20260508000001"
down_revision = "20260507000001"
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
        "stock_reservations",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shop_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("cart_token", sa.String(128), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False, server_default="cart"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "channel_id", "cart_token", "product_id", "shop_id",
            name="uq_reservation_channel_cart_product_shop",
        ),
    )
    op.create_index("ix_stock_reservations_tenant_id", "stock_reservations", ["tenant_id"])
    op.create_index(
        "ix_stock_reservations_active_lookup",
        "stock_reservations",
        ["product_id", "shop_id", "status"],
    )
    op.create_index(
        "ix_stock_reservations_expiry_sweep",
        "stock_reservations",
        ["status", "expires_at"],
    )

    # Permission seed (5-column form — display_name and category are NOT NULL)
    op.execute("""
        INSERT INTO permissions (id, codename, display_name, category, description)
        VALUES (gen_random_uuid(), 'reservations:manage', 'Manage Stock Reservations', 'inventory',
                'View and manually release stock reservations (debug/support tool)')
        ON CONFLICT (codename) DO UPDATE SET description = EXCLUDED.description
    """)
    # Grant to the system 'owner' role (matches the channels:manage / inventory_pools:manage pattern)
    op.execute("""
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), r.id, p.id
        FROM roles r, permissions p
        WHERE r.name = 'owner' AND r.is_system = true
          AND p.codename = 'reservations:manage'
        ON CONFLICT DO NOTHING
    """)

    # Enable RLS
    op.execute(f"""
        ALTER TABLE stock_reservations ENABLE ROW LEVEL SECURITY;
        ALTER TABLE stock_reservations FORCE ROW LEVEL SECURITY;
        CREATE POLICY ims_tenant_isolation ON stock_reservations
        USING ({_RLS_POLICY})
        WITH CHECK ({_RLS_POLICY});
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS ims_tenant_isolation ON stock_reservations;")
    op.execute("ALTER TABLE stock_reservations NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE stock_reservations DISABLE ROW LEVEL SECURITY;")

    op.execute("""
        DELETE FROM role_permissions WHERE permission_id IN (
            SELECT id FROM permissions WHERE codename = 'reservations:manage'
        )
    """)
    op.execute("DELETE FROM permissions WHERE codename = 'reservations:manage'")

    op.drop_index("ix_stock_reservations_expiry_sweep", table_name="stock_reservations")
    op.drop_index("ix_stock_reservations_active_lookup", table_name="stock_reservations")
    op.drop_index("ix_stock_reservations_tenant_id", table_name="stock_reservations")
    op.drop_table("stock_reservations")
