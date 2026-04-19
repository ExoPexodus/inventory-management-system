"""auto resolve reconciliation

Revision ID: 20260419120000
Revises: 20260417000001
Create Date: 2026-04-19 04:05:50.102549

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260419120000"
down_revision = "20260417000001"
branch_labels = None
depends_on = None


SYSTEM_ROLE_NAME = "system"


def upgrade() -> None:
    # 1. Columns on tenants
    op.add_column(
        "tenants",
        sa.Column("auto_resolve_shortage_cents", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "tenants",
        sa.Column("auto_resolve_overage_cents", sa.Integer(), nullable=False, server_default="0"),
    )

    # 2. Columns on shops (nullable = inherit from tenant)
    op.add_column(
        "shops",
        sa.Column("auto_resolve_shortage_cents_override", sa.Integer(), nullable=True),
    )
    op.add_column(
        "shops",
        sa.Column("auto_resolve_overage_cents_override", sa.Integer(), nullable=True),
    )

    # 3. Data migration: one system Role + User per existing tenant (idempotent)
    conn = op.get_bind()

    # Seed one `system` Role per tenant, idempotent
    conn.execute(sa.text("""
        INSERT INTO roles (id, tenant_id, name, display_name, is_system, created_at)
        SELECT gen_random_uuid(), t.id, :role_name, :display_name, true, NOW()
        FROM tenants t
        WHERE NOT EXISTS (
            SELECT 1 FROM roles r
            WHERE r.tenant_id = t.id AND r.name = :role_name
        )
    """), {"role_name": SYSTEM_ROLE_NAME, "display_name": "System (automated actions)"})

    # Seed one system User per tenant, tied to its system role, idempotent by email
    conn.execute(sa.text("""
        INSERT INTO users (id, tenant_id, role_id, email, name, password_hash, is_active, created_at, updated_at)
        SELECT
            gen_random_uuid(),
            t.id,
            r.id,
            'system+' || t.id::text || '@internal.ims',
            'System',
            NULL,
            false,
            NOW(),
            NOW()
        FROM tenants t
        JOIN roles r ON r.tenant_id = t.id AND r.name = :role_name
        WHERE NOT EXISTS (
            SELECT 1 FROM users u
            WHERE u.tenant_id = t.id
              AND u.email = 'system+' || t.id::text || '@internal.ims'
        )
    """), {"role_name": SYSTEM_ROLE_NAME})


def downgrade() -> None:
    conn = op.get_bind()

    # Delete only the sentinel users this migration seeded (identified by the email template)
    conn.execute(sa.text("""
        DELETE FROM users
        WHERE email LIKE 'system+%@internal.ims'
          AND role_id IN (SELECT id FROM roles WHERE name = 'system' AND is_system = true)
    """))

    # Delete system roles only if they have no remaining users attached
    conn.execute(sa.text("""
        DELETE FROM roles
        WHERE name = 'system'
          AND is_system = true
          AND NOT EXISTS (SELECT 1 FROM users u WHERE u.role_id = roles.id)
    """))

    op.drop_column("shops", "auto_resolve_overage_cents_override")
    op.drop_column("shops", "auto_resolve_shortage_cents_override")
    op.drop_column("tenants", "auto_resolve_overage_cents")
    op.drop_column("tenants", "auto_resolve_shortage_cents")
