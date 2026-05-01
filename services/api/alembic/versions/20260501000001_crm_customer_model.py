"""CRM: customer_groups and customers tables, customer fields on transactions, permission seeds

Revision ID: 20260501000001
Revises: 20260429000002
Create Date: 2026-05-01 00:00:01.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "20260501000001"
down_revision = "20260429000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. customer_groups
    op.create_table(
        "customer_groups",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("colour", sa.String(7), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "name", name="uq_customer_group_tenant_name"),
    )

    # 2. customers
    op.create_table(
        "customers",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("group_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("customer_groups.id", ondelete="SET NULL"), nullable=True),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("address_line1", sa.String(255), nullable=True),
        sa.Column("city", sa.String(128), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "phone", name="uq_customer_tenant_phone"),
    )
    op.create_index("ix_customers_tenant_phone", "customers", ["tenant_id", "phone"])

    # 3. Transaction additions
    op.add_column("transactions", sa.Column(
        "customer_id", PG_UUID(as_uuid=True),
        sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    ))
    op.add_column("transactions", sa.Column("customer_phone", sa.String(20), nullable=True))

    # 4. Seed permissions and grant to roles
    conn = op.get_bind()

    conn.execute(sa.text("""
        INSERT INTO permissions (id, codename, display_name, category)
        VALUES
            (gen_random_uuid(), 'customers:read',  'View customers',   'customers'),
            (gen_random_uuid(), 'customers:write', 'Manage customers', 'customers')
        ON CONFLICT (codename) DO NOTHING
    """))

    conn.execute(sa.text("""
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), rp.role_id, p.id
        FROM role_permissions rp
        JOIN permissions ep ON ep.id = rp.permission_id AND ep.codename = 'catalog:read'
        JOIN permissions p  ON p.codename = 'customers:read'
        WHERE NOT EXISTS (
            SELECT 1 FROM role_permissions x
            WHERE x.role_id = rp.role_id AND x.permission_id = p.id
        )
    """))

    conn.execute(sa.text("""
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), rp.role_id, p.id
        FROM role_permissions rp
        JOIN permissions ep ON ep.id = rp.permission_id AND ep.codename = 'catalog:write'
        JOIN permissions p  ON p.codename = 'customers:write'
        WHERE NOT EXISTS (
            SELECT 1 FROM role_permissions x
            WHERE x.role_id = rp.role_id AND x.permission_id = p.id
        )
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        "DELETE FROM permissions WHERE codename IN ('customers:read', 'customers:write')"
    ))
    op.drop_column("transactions", "customer_phone")
    op.drop_column("transactions", "customer_id")
    op.drop_index("ix_customers_tenant_phone", table_name="customers")
    op.drop_table("customers")
    op.drop_table("customer_groups")
