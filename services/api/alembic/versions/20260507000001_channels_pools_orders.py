"""Channels + inventory pools + orders + customer-channel attribution

Revision ID: 20260507000001
Revises: 20260506000001
Create Date: 2026-05-07 00:00:01.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

revision = "20260507000001"
down_revision = "20260506000001"
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
    # 1. inventory_pools (must come first — channels FK to it)
    op.create_table(
        "inventory_pools",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("fulfillment_policy", sa.String(32), nullable=False, server_default="fulfill_from_primary"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "name", name="uq_pool_tenant_name"),
    )
    op.create_index("ix_inventory_pools_tenant_id", "inventory_pools", ["tenant_id"])

    # 2. inventory_pool_shops (join)
    op.create_table(
        "inventory_pool_shops",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pool_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("inventory_pools.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shop_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("pool_id", "shop_id", name="uq_pool_shop"),
    )
    op.create_index("ix_inventory_pool_shops_pool_id", "inventory_pool_shops", ["pool_id"])
    op.create_index("ix_inventory_pool_shops_shop_id", "inventory_pool_shops", ["shop_id"])

    # 3. channels
    op.create_table(
        "channels",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("config", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("inventory_pool_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("inventory_pools.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("shop_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "name", name="uq_channel_tenant_name"),
    )
    op.create_index("ix_channels_tenant_id", "channels", ["tenant_id"])
    op.create_index("ix_channels_shop_id", "channels", ["shop_id"])
    op.create_index("ix_channels_type", "channels", ["type"])

    # 4. customer_channels
    op.create_table(
        "customer_channels",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("customer_id", "channel_id", name="uq_customer_channel"),
    )
    op.create_index("ix_customer_channels_customer_id", "customer_channels", ["customer_id"])

    # 5. orders
    op.create_table(
        "orders",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("channels.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("customer_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("customer_email", sa.String(255), nullable=True),
        sa.Column("customer_phone", sa.String(64), nullable=True),
        sa.Column("subtotal_cents", sa.Integer, nullable=False),
        sa.Column("tax_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("shipping_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("discount_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_cents", sa.Integer, nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("shipping_address", JSONB, nullable=True),
        sa.Column("billing_address", JSONB, nullable=True),
        sa.Column("placed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("raw_payload", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "channel_id", "external_id", name="uq_order_channel_external"),
    )
    op.create_index("ix_orders_tenant_id", "orders", ["tenant_id"])
    op.create_index("ix_orders_channel_id", "orders", ["channel_id"])
    op.create_index("ix_orders_customer_id", "orders", ["customer_id"])
    op.create_index("ix_orders_placed_at", "orders", ["placed_at"])

    # 6. order_lines
    op.create_table(
        "order_lines",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("sku", sa.String(128), nullable=True),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("unit_price_cents", sa.Integer, nullable=False),
        sa.Column("line_total_cents", sa.Integer, nullable=False),
        sa.Column("tax_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("discount_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("raw_payload", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_order_lines_order_id", "order_lines", ["order_id"])

    # 7. order_payments
    op.create_table(
        "order_payments",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("provider_ref", sa.String(255), nullable=True),
        sa.Column("method", sa.String(32), nullable=False),
        sa.Column("amount_cents", sa.Integer, nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="paid"),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_payload", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_order_payments_order_id", "order_payments", ["order_id"])

    # 8. New columns on existing tables
    op.add_column("transactions", sa.Column(
        "source_channel_id", PG_UUID(as_uuid=True),
        sa.ForeignKey("channels.id", ondelete="SET NULL"), nullable=True,
    ))
    op.create_index("ix_transactions_source_channel_id", "transactions", ["source_channel_id"])

    op.add_column("stock_movements", sa.Column(
        "source_channel_id", PG_UUID(as_uuid=True),
        sa.ForeignKey("channels.id", ondelete="SET NULL"), nullable=True,
    ))
    op.create_index("ix_stock_movements_source_channel_id", "stock_movements", ["source_channel_id"])

    op.add_column("customers", sa.Column(
        "created_via_channel_id", PG_UUID(as_uuid=True),
        sa.ForeignKey("channels.id", ondelete="SET NULL"), nullable=True,
    ))

    # 9. Auto-create per-tenant default pool + per-shop pool + per-shop POS channel.
    # For each existing tenant:
    #   - one InventoryPool(name="All Shops", fulfillment_policy="fulfill_from_primary")
    #     containing all the tenant's shops (reserved for future online channels)
    # For each existing shop:
    #   - one InventoryPool(name="POS at {shop.name}", fulfillment_policy="fulfill_from_primary")
    #     containing only that shop
    #   - one Channel(type="pos", name="POS at {shop.name}", shop_id=shop.id,
    #     inventory_pool_id=<the single-shop pool>, currency_code=<tenant currency>)
    conn = op.get_bind()
    # Tenants and their currency (column is `default_currency_code` on tenants)
    tenant_rows = conn.execute(sa.text("""
        SELECT t.id AS tenant_id, COALESCE(t.default_currency_code, 'USD') AS currency_code
        FROM tenants t
    """)).all()

    for tenant_id, currency_code in tenant_rows:
        # Default "All Shops" pool
        default_pool_id = conn.execute(sa.text("""
            INSERT INTO inventory_pools (id, tenant_id, name, fulfillment_policy)
            VALUES (gen_random_uuid(), :tid, 'All Shops', 'fulfill_from_primary')
            RETURNING id
        """), {"tid": tenant_id}).scalar_one()

        # Add all tenant shops to the default pool
        conn.execute(sa.text("""
            INSERT INTO inventory_pool_shops (id, tenant_id, pool_id, shop_id)
            SELECT gen_random_uuid(), :tid, :pool_id, s.id
            FROM shops s
            WHERE s.tenant_id = :tid
        """), {"tid": tenant_id, "pool_id": default_pool_id})

        # Per-shop POS pool + channel
        shop_rows = conn.execute(sa.text("""
            SELECT id, name FROM shops WHERE tenant_id = :tid
        """), {"tid": tenant_id}).all()

        for shop_id, shop_name in shop_rows:
            pos_pool_id = conn.execute(sa.text("""
                INSERT INTO inventory_pools (id, tenant_id, name, fulfillment_policy)
                VALUES (gen_random_uuid(), :tid, :pname, 'fulfill_from_primary')
                RETURNING id
            """), {"tid": tenant_id, "pname": f"POS at {shop_name}"}).scalar_one()

            conn.execute(sa.text("""
                INSERT INTO inventory_pool_shops (id, tenant_id, pool_id, shop_id)
                VALUES (gen_random_uuid(), :tid, :pool_id, :shop_id)
            """), {"tid": tenant_id, "pool_id": pos_pool_id, "shop_id": shop_id})

            channel_id = conn.execute(sa.text("""
                INSERT INTO channels (id, tenant_id, type, name, status, config,
                                      inventory_pool_id, currency_code, shop_id)
                VALUES (gen_random_uuid(), :tid, 'pos', :cname, 'active', '{}'::jsonb,
                        :pool_id, :currency, :shop_id)
                RETURNING id
            """), {
                "tid": tenant_id,
                "cname": f"POS at {shop_name}",
                "pool_id": pos_pool_id,
                "currency": currency_code,
                "shop_id": shop_id,
            }).scalar_one()

            # Backfill existing transactions and stock_movements for this shop with the POS channel
            conn.execute(sa.text("""
                UPDATE transactions
                SET source_channel_id = :channel_id
                WHERE shop_id = :shop_id AND source_channel_id IS NULL
            """), {"channel_id": channel_id, "shop_id": shop_id})

            conn.execute(sa.text("""
                UPDATE stock_movements
                SET source_channel_id = :channel_id
                WHERE shop_id = :shop_id AND source_channel_id IS NULL
            """), {"channel_id": channel_id, "shop_id": shop_id})

    # 10. Seed permissions: channels:manage and inventory_pools:manage.
    # These are tenant-admin level (different from entitlements:manage which is staff-only).
    conn.execute(sa.text(
        "INSERT INTO permissions (id, codename, display_name, category, description) "
        "VALUES (gen_random_uuid(), 'channels:manage', 'Manage Sales Channels', 'channels', "
        "'Manage tenant sales channels') "
        "ON CONFLICT (codename) DO UPDATE SET description = EXCLUDED.description"
    ))
    conn.execute(sa.text(
        "INSERT INTO permissions (id, codename, display_name, category, description) "
        "VALUES (gen_random_uuid(), 'inventory_pools:manage', 'Manage Inventory Pools', 'channels', "
        "'Manage tenant inventory pools') "
        "ON CONFLICT (codename) DO UPDATE SET description = EXCLUDED.description"
    ))

    # Grant both to owner (system admin) role
    conn.execute(sa.text("""
        INSERT INTO role_permissions (id, role_id, permission_id, created_at)
        SELECT gen_random_uuid(), r.id, p.id, NOW()
        FROM roles r
        CROSS JOIN permissions p
        WHERE r.name = 'owner'
          AND r.is_system = true
          AND p.codename IN ('channels:manage', 'inventory_pools:manage')
        ON CONFLICT (role_id, permission_id) DO NOTHING
    """))

    # 11. Enable RLS on the new tenant-scoped tables
    for table in [
        "inventory_pools", "inventory_pool_shops", "channels",
        "customer_channels", "orders", "order_lines", "order_payments",
    ]:
        op.execute(f"""
            ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
            ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
            CREATE POLICY ims_tenant_isolation ON {table}
            USING ({_RLS_POLICY})
            WITH CHECK ({_RLS_POLICY});
        """)


def downgrade() -> None:
    # Reverse RLS
    for table in [
        "order_payments", "order_lines", "orders",
        "customer_channels", "channels",
        "inventory_pool_shops", "inventory_pools",
    ]:
        op.execute(f"DROP POLICY IF EXISTS ims_tenant_isolation ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    # Reverse permission grants
    conn = op.get_bind()
    conn.execute(sa.text("""
        DELETE FROM role_permissions
        WHERE permission_id IN (
            SELECT id FROM permissions WHERE codename IN ('channels:manage', 'inventory_pools:manage')
        )
    """))
    conn.execute(sa.text(
        "DELETE FROM permissions WHERE codename IN ('channels:manage', 'inventory_pools:manage')"
    ))

    # Reverse column additions
    op.drop_column("customers", "created_via_channel_id")
    op.drop_index("ix_stock_movements_source_channel_id", table_name="stock_movements")
    op.drop_column("stock_movements", "source_channel_id")
    op.drop_index("ix_transactions_source_channel_id", table_name="transactions")
    op.drop_column("transactions", "source_channel_id")

    # Drop tables in reverse dependency order
    op.drop_index("ix_order_payments_order_id", table_name="order_payments")
    op.drop_table("order_payments")
    op.drop_index("ix_order_lines_order_id", table_name="order_lines")
    op.drop_table("order_lines")
    op.drop_index("ix_orders_placed_at", table_name="orders")
    op.drop_index("ix_orders_customer_id", table_name="orders")
    op.drop_index("ix_orders_channel_id", table_name="orders")
    op.drop_index("ix_orders_tenant_id", table_name="orders")
    op.drop_table("orders")
    op.drop_index("ix_customer_channels_customer_id", table_name="customer_channels")
    op.drop_table("customer_channels")
    op.drop_index("ix_channels_type", table_name="channels")
    op.drop_index("ix_channels_shop_id", table_name="channels")
    op.drop_index("ix_channels_tenant_id", table_name="channels")
    op.drop_table("channels")
    op.drop_index("ix_inventory_pool_shops_shop_id", table_name="inventory_pool_shops")
    op.drop_index("ix_inventory_pool_shops_pool_id", table_name="inventory_pool_shops")
    op.drop_table("inventory_pool_shops")
    op.drop_index("ix_inventory_pools_tenant_id", table_name="inventory_pools")
    op.drop_table("inventory_pools")
