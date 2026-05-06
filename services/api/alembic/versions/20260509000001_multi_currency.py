"""Multi-currency: product_prices + fx_rates tables, currency:manage permission

Revision ID: 20260509000001
Revises: 20260508000001
Create Date: 2026-05-09 00:00:01.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "20260509000001"
down_revision = "20260508000001"
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
        "product_prices",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=True),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("amount_cents", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "product_id", "channel_id", "currency_code",
            name="uq_product_price_product_channel_currency",
        ),
    )
    op.create_index("ix_product_prices_tenant_id", "product_prices", ["tenant_id"])
    op.create_index("ix_product_prices_lookup", "product_prices", ["product_id", "currency_code"])

    op.create_table(
        "fx_rates",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_currency", sa.String(3), nullable=False),
        sa.Column("to_currency", sa.String(3), nullable=False),
        sa.Column("rate", sa.Numeric(20, 10), nullable=False),
        sa.Column("source", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("effective_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "tenant_id", "from_currency", "to_currency",
            name="uq_fx_tenant_pair",
        ),
    )
    op.create_index("ix_fx_rates_tenant_id", "fx_rates", ["tenant_id"])
    op.create_index("ix_fx_rates_pair_lookup", "fx_rates", ["tenant_id", "from_currency", "to_currency"])

    op.execute("""
        INSERT INTO permissions (id, codename, display_name, category, description)
        VALUES (gen_random_uuid(), 'currency:manage', 'Manage Currency Configuration', 'billing',
                'Manage tenant FX rates and per-channel/per-product price overrides')
        ON CONFLICT (codename) DO UPDATE SET description = EXCLUDED.description
    """)
    op.execute("""
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), r.id, p.id
        FROM roles r, permissions p
        WHERE r.name = 'owner' AND r.is_system = true
          AND p.codename = 'currency:manage'
        ON CONFLICT DO NOTHING
    """)

    for table in ["product_prices", "fx_rates"]:
        op.execute(f"""
            ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
            ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
            CREATE POLICY ims_tenant_isolation ON {table}
            USING ({_RLS_POLICY})
            WITH CHECK ({_RLS_POLICY});
        """)


def downgrade() -> None:
    for table in ["fx_rates", "product_prices"]:
        op.execute(f"DROP POLICY IF EXISTS ims_tenant_isolation ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.execute("""
        DELETE FROM role_permissions WHERE permission_id IN (
            SELECT id FROM permissions WHERE codename = 'currency:manage'
        )
    """)
    op.execute("DELETE FROM permissions WHERE codename = 'currency:manage'")

    op.drop_index("ix_fx_rates_pair_lookup", table_name="fx_rates")
    op.drop_index("ix_fx_rates_tenant_id", table_name="fx_rates")
    op.drop_table("fx_rates")
    op.drop_index("ix_product_prices_lookup", table_name="product_prices")
    op.drop_index("ix_product_prices_tenant_id", table_name="product_prices")
    op.drop_table("product_prices")
