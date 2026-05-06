"""Shipping engine: shipping_zones + shipping_rates tables

Revision ID: 20260511000001
Revises: 20260510000001
Create Date: 2026-05-11 00:00:01.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

revision = "20260511000001"
down_revision = "20260510000001"
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
        "shipping_zones",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("countries", JSONB, nullable=True),
        sa.Column("is_catch_all", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "channel_id", "name",
                            name="uq_shipping_zone_channel_name"),
    )
    op.create_index("ix_shipping_zones_tenant_id", "shipping_zones", ["tenant_id"])
    op.create_index("ix_shipping_zones_channel_id", "shipping_zones", ["channel_id"])

    op.create_table(
        "shipping_rates",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("zone_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("shipping_zones.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("base_price_cents", sa.Integer, nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("free_above_cents", sa.Integer, nullable=True),
        sa.Column("condition_type", sa.String(32), nullable=False, server_default="none"),
        sa.Column("condition_min", sa.Integer, nullable=True),
        sa.Column("condition_max", sa.Integer, nullable=True),
        sa.Column("applies_to_classes", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_shipping_rates_zone_id", "shipping_rates", ["zone_id"])
    op.create_index("ix_shipping_rates_tenant_id", "shipping_rates", ["tenant_id"])

    op.execute("""
        INSERT INTO permissions (id, codename, display_name, category, description)
        VALUES (gen_random_uuid(), 'shipping:manage', 'Manage Shipping', 'shipping',
                'Manage shipping zones and rates')
        ON CONFLICT (codename) DO UPDATE SET description = EXCLUDED.description
    """)
    op.execute("""
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), r.id, p.id
        FROM roles r, permissions p
        WHERE r.name = 'owner' AND r.is_system = true
          AND p.codename = 'shipping:manage'
        ON CONFLICT DO NOTHING
    """)

    for table in ["shipping_zones", "shipping_rates"]:
        op.execute(f"""
            ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
            ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
            CREATE POLICY ims_tenant_isolation ON {table}
            USING ({_RLS_POLICY})
            WITH CHECK ({_RLS_POLICY});
        """)


def downgrade() -> None:
    for table in ["shipping_rates", "shipping_zones"]:
        op.execute(f"DROP POLICY IF EXISTS ims_tenant_isolation ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.execute("""
        DELETE FROM role_permissions WHERE permission_id IN (
            SELECT id FROM permissions WHERE codename = 'shipping:manage'
        )
    """)
    op.execute("DELETE FROM permissions WHERE codename = 'shipping:manage'")

    op.drop_index("ix_shipping_rates_tenant_id", table_name="shipping_rates")
    op.drop_index("ix_shipping_rates_zone_id", table_name="shipping_rates")
    op.drop_table("shipping_rates")
    op.drop_index("ix_shipping_zones_channel_id", table_name="shipping_zones")
    op.drop_index("ix_shipping_zones_tenant_id", table_name="shipping_zones")
    op.drop_table("shipping_zones")
