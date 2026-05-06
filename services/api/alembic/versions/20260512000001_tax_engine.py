"""Tax engine: tax_regions + tax_rules tables, tax_class on products, tax_included_in_price on channels

Revision ID: 20260512000001
Revises: 20260511000001
Create Date: 2026-05-12 00:00:01.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

revision = "20260512000001"
down_revision = "20260511000001"
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
    op.add_column("products", sa.Column("tax_class", sa.String(32), nullable=True))
    op.add_column("channels", sa.Column("tax_included_in_price", sa.Boolean, nullable=True))

    op.create_table(
        "tax_regions",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("state_code", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "country_code", "state_code",
                            name="uq_tax_region_tenant_country_state"),
    )
    op.create_index("ix_tax_regions_tenant_id", "tax_regions", ["tenant_id"])
    op.create_index("ix_tax_regions_country", "tax_regions", ["country_code"])

    op.create_table(
        "tax_rules",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("region_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tax_regions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tax_class", sa.String(32), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("components", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("region_id", "tax_class", name="uq_tax_rule_region_class"),
    )
    op.create_index("ix_tax_rules_region_id", "tax_rules", ["region_id"])
    op.create_index("ix_tax_rules_tenant_id", "tax_rules", ["tenant_id"])

    op.execute("""
        INSERT INTO permissions (id, codename, display_name, category, description)
        VALUES (gen_random_uuid(), 'tax:manage', 'Manage Tax', 'billing',
                'Manage tax regions and rules')
        ON CONFLICT (codename) DO UPDATE SET description = EXCLUDED.description
    """)
    op.execute("""
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), r.id, p.id
        FROM roles r, permissions p
        WHERE r.name = 'owner' AND r.is_system = true
          AND p.codename = 'tax:manage'
        ON CONFLICT DO NOTHING
    """)

    for table in ["tax_regions", "tax_rules"]:
        op.execute(f"""
            ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
            ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
            CREATE POLICY ims_tenant_isolation ON {table}
            USING ({_RLS_POLICY})
            WITH CHECK ({_RLS_POLICY});
        """)


def downgrade() -> None:
    for table in ["tax_rules", "tax_regions"]:
        op.execute(f"DROP POLICY IF EXISTS ims_tenant_isolation ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.execute("""
        DELETE FROM role_permissions WHERE permission_id IN (
            SELECT id FROM permissions WHERE codename = 'tax:manage'
        )
    """)
    op.execute("DELETE FROM permissions WHERE codename = 'tax:manage'")

    op.drop_index("ix_tax_rules_tenant_id", table_name="tax_rules")
    op.drop_index("ix_tax_rules_region_id", table_name="tax_rules")
    op.drop_table("tax_rules")
    op.drop_index("ix_tax_regions_country", table_name="tax_regions")
    op.drop_index("ix_tax_regions_tenant_id", table_name="tax_regions")
    op.drop_table("tax_regions")

    op.drop_column("channels", "tax_included_in_price")
    op.drop_column("products", "tax_class")
