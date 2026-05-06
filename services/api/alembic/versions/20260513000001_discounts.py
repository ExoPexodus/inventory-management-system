"""Discounts module: discounts + discount_uses tables

Revision ID: 20260513000001
Revises: 20260512000001
Create Date: 2026-05-13 00:00:01.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "20260513000001"
down_revision = "20260512000001"
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
        "discounts",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(128), nullable=True),
        sa.Column("discount_type", sa.String(32), nullable=False),
        sa.Column("value_bps", sa.Integer, nullable=True),
        sa.Column("value_cents", sa.Integer, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("stackable", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("min_subtotal_cents", sa.Integer, nullable=True),
        sa.Column("max_uses_total", sa.Integer, nullable=True),
        sa.Column("max_uses_per_customer", sa.Integer, nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_discounts_tenant_id", "discounts", ["tenant_id"])
    op.create_index("ix_discounts_code", "discounts", ["tenant_id", "code"],
                    unique=True, postgresql_where=sa.text("code IS NOT NULL"))
    op.create_index("ix_discounts_status", "discounts", ["tenant_id", "status"])

    op.create_table(
        "discount_uses",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("discount_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("discounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cart_token", sa.String(128), nullable=True),
        sa.Column("customer_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("order_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("orders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("discount_amount_cents", sa.Integer, nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_discount_uses_discount_id", "discount_uses", ["discount_id"])
    op.create_index("ix_discount_uses_customer_id", "discount_uses", ["customer_id"])
    op.create_index("ix_discount_uses_tenant_id", "discount_uses", ["tenant_id"])

    op.execute("""
        INSERT INTO permissions (id, codename, display_name, category, description)
        VALUES (gen_random_uuid(), 'discounts:manage', 'Manage Discounts', 'billing',
                'Create, edit, and delete discount codes and promotions')
        ON CONFLICT (codename) DO UPDATE SET description = EXCLUDED.description
    """)
    op.execute("""
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), r.id, p.id
        FROM roles r, permissions p
        WHERE r.name = 'owner' AND r.is_system = true
          AND p.codename = 'discounts:manage'
        ON CONFLICT DO NOTHING
    """)

    for table in ["discounts", "discount_uses"]:
        op.execute(f"""
            ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
            ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
            CREATE POLICY ims_tenant_isolation ON {table}
            USING ({_RLS_POLICY})
            WITH CHECK ({_RLS_POLICY});
        """)


def downgrade() -> None:
    for table in ["discount_uses", "discounts"]:
        op.execute(f"DROP POLICY IF EXISTS ims_tenant_isolation ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.execute("""
        DELETE FROM role_permissions WHERE permission_id IN (
            SELECT id FROM permissions WHERE codename = 'discounts:manage'
        )
    """)
    op.execute("DELETE FROM permissions WHERE codename = 'discounts:manage'")

    op.drop_index("ix_discount_uses_tenant_id", table_name="discount_uses")
    op.drop_index("ix_discount_uses_customer_id", table_name="discount_uses")
    op.drop_index("ix_discount_uses_discount_id", table_name="discount_uses")
    op.drop_table("discount_uses")
    op.drop_index("ix_discounts_status", table_name="discounts")
    op.drop_index("ix_discounts_code", table_name="discounts")
    op.drop_index("ix_discounts_tenant_id", table_name="discounts")
    op.drop_table("discounts")
