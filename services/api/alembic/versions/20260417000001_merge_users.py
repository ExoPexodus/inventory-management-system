"""Merge employees + admin_users into unified users table with RBAC-driven access

Revision ID: 20260417000001
Revises: 20260416000002
Create Date: 2026-04-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
import uuid

revision = "20260417000001"
down_revision = "20260416000002"
branch_labels = None
depends_on = None


NEW_PERMISSIONS = [
    ("cashier_app:access", "Access Cashier App", "access", "Can log into the cashier POS app via PIN on an enrolled device."),
    ("admin_web:access", "Access Admin Web", "access", "Can log into the admin web dashboard with email and password."),
    ("admin_mobile:access", "Access Admin Mobile", "access", "Can log into the admin mobile app (PIN quick-unlock with password fallback)."),
]

SYSTEM_ROLE_PERMS = {
    "owner": ["cashier_app:access", "admin_web:access", "admin_mobile:access"],
    "manager": ["admin_web:access", "admin_mobile:access"],
    "cashier": ["cashier_app:access"],
}


COLUMN_RENAMES = [
    ("transactions", "employee_id", "user_id"),
    ("enrollment_tokens", "employee_id", "user_id"),
    ("admin_audit_logs", "operator_id", "user_id"),
    ("purchase_orders", "created_by", "created_by_user_id"),
    ("stock_adjustments", "approved_by", "approved_by_user_id"),
    ("stock_adjustments", "created_by", "created_by_user_id"),
    ("transfer_orders", "created_by", "created_by_user_id"),
    ("shift_closings", "closed_by", "closed_by_user_id"),
    ("shift_closings", "reviewed_by", "reviewed_by_user_id"),
    ("report_exports", "created_by", "created_by_user_id"),
    ("api_tokens", "created_by", "created_by_user_id"),
]


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Create users table
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shop_id", UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="SET NULL"), nullable=True),
        sa.Column("role_id", UUID(as_uuid=True), sa.ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("device_id", UUID(as_uuid=True), sa.ForeignKey("devices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(64), nullable=True),
        sa.Column("avatar_url", sa.String(1024), nullable=True),
        sa.Column("password_hash", sa.String(128), nullable=True),
        sa.Column("pin_hash", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
    )

    # 2. Add new permissions
    for codename, display_name, category, description in NEW_PERMISSIONS:
        conn.execute(
            sa.text(
                "INSERT INTO permissions (id, codename, display_name, category, description) "
                "VALUES (:id, :codename, :display_name, :category, :description) "
                "ON CONFLICT (codename) DO NOTHING"
            ),
            {
                "id": str(uuid.uuid4()),
                "codename": codename,
                "display_name": display_name,
                "category": category,
                "description": description,
            },
        )

    # 3. Ensure every tenant has an "owner" role (safety net for admin_users backfill)
    conn.execute(sa.text("""
        INSERT INTO roles (id, tenant_id, name, display_name, is_system)
        SELECT gen_random_uuid(), t.id, 'owner', 'Owner', true
        FROM tenants t
        WHERE NOT EXISTS (SELECT 1 FROM roles r WHERE r.tenant_id = t.id AND r.name = 'owner')
    """))

    # 4. Backfill users from admin_users
    conn.execute(sa.text("""
        INSERT INTO users (id, tenant_id, shop_id, role_id, device_id, email, name, phone, avatar_url,
                           password_hash, pin_hash, is_active, created_at, updated_at)
        SELECT
            au.id,
            au.tenant_id,
            NULL::uuid,
            COALESCE(au.role_id, (SELECT r.id FROM roles r WHERE r.tenant_id = au.tenant_id AND r.name = 'owner' LIMIT 1)),
            NULL::uuid,
            au.email,
            COALESCE(au.display_name, au.email),
            NULL,
            au.avatar_url,
            au.password_hash,
            NULL,
            au.is_active,
            au.created_at,
            au.created_at
        FROM admin_users au
        WHERE au.tenant_id IS NOT NULL
    """))

    # 5. Ensure every employee position has a corresponding role
    conn.execute(sa.text("""
        INSERT INTO roles (id, tenant_id, name, display_name, is_system)
        SELECT DISTINCT gen_random_uuid(), e.tenant_id, e.position, INITCAP(REPLACE(e.position, '_', ' ')), false
        FROM employees e
        WHERE NOT EXISTS (
            SELECT 1 FROM roles r WHERE r.tenant_id = e.tenant_id AND r.name = e.position
        )
    """))

    # 6. Backfill users from employees (handle email collisions)
    conn.execute(sa.text("""
        INSERT INTO users (id, tenant_id, shop_id, role_id, device_id, email, name, phone, avatar_url,
                           password_hash, pin_hash, is_active, created_at, updated_at)
        SELECT
            e.id,
            e.tenant_id,
            e.shop_id,
            (SELECT r.id FROM roles r WHERE r.tenant_id = e.tenant_id AND r.name = e.position LIMIT 1),
            e.device_id,
            CASE
                WHEN EXISTS (SELECT 1 FROM users u WHERE u.tenant_id = e.tenant_id AND u.email = e.email)
                THEN e.email || '.cashier'
                ELSE e.email
            END,
            e.name,
            e.phone,
            NULL,
            CASE WHEN e.credential_type = 'password' THEN e.credential_hash ELSE NULL END,
            CASE WHEN e.credential_type = 'pin' THEN e.credential_hash ELSE NULL END,
            e.is_active,
            e.created_at,
            e.updated_at
        FROM employees e
    """))

    # 7. Drop ALL FKs that reference employees or admin_users (dynamic, by name)
    conn.execute(sa.text("""
        DO $$
        DECLARE r record;
        BEGIN
            FOR r IN
                SELECT conname, conrelid::regclass::text AS tbl
                FROM pg_constraint
                WHERE contype = 'f'
                  AND (confrelid = 'employees'::regclass OR confrelid = 'admin_users'::regclass)
            LOOP
                EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', r.tbl, r.conname);
            END LOOP;
        END $$;
    """))

    # 8. Rename columns and attach new FKs pointing to users.id
    for table, old_col, new_col in COLUMN_RENAMES:
        op.alter_column(table, old_col, new_column_name=new_col)
        op.create_foreign_key(
            f"{table}_{new_col}_fkey",
            table, "users",
            [new_col], ["id"],
            ondelete="SET NULL",
        )

    # Add app_target column to enrollment_tokens
    op.add_column(
        "enrollment_tokens",
        sa.Column("app_target", sa.String(32), nullable=False, server_default="cashier"),
    )

    # 9. Drop old tables (CASCADE handles legacy ghost tables like refunds/admin_sessions/etc.)
    op.execute(sa.text("DROP TABLE IF EXISTS employees CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS admin_users CASCADE"))

    # 10. Grant new access permissions to system roles
    for role_name, perm_codenames in SYSTEM_ROLE_PERMS.items():
        for codename in perm_codenames:
            conn.execute(sa.text("""
                INSERT INTO role_permissions (id, role_id, permission_id, created_at)
                SELECT gen_random_uuid(), r.id, p.id, NOW()
                FROM roles r
                CROSS JOIN permissions p
                WHERE r.name = :role_name
                  AND r.is_system = true
                  AND p.codename = :codename
                  AND NOT EXISTS (
                    SELECT 1 FROM role_permissions rp
                    WHERE rp.role_id = r.id AND rp.permission_id = p.id
                  )
            """), {"role_name": role_name, "codename": codename})


def downgrade() -> None:
    """Best-effort reverse. Full restore requires a pre-migration backup."""

    op.create_table(
        "admin_users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(128), nullable=False),
        sa.Column("role_id", UUID(as_uuid=True), nullable=True),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("avatar_url", sa.String(1024), nullable=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("email", name="uq_admin_users_email"),
    )
    op.create_table(
        "employees",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("shop_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(64), nullable=True),
        sa.Column("position", sa.String(64), server_default="cashier"),
        sa.Column("credential_type", sa.String(32), server_default="pin"),
        sa.Column("credential_hash", sa.String(255), nullable=False),
        sa.Column("device_id", UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "email", name="uq_employee_tenant_email"),
    )

    for table, old_col, new_col in COLUMN_RENAMES:
        op.drop_constraint(f"{table}_{new_col}_fkey", table, type_="foreignkey")
        op.alter_column(table, new_col, new_column_name=old_col)

    op.drop_column("enrollment_tokens", "app_target")

    conn = op.get_bind()
    for codename, _, _, _ in NEW_PERMISSIONS:
        conn.execute(sa.text("DELETE FROM permissions WHERE codename = :cn"), {"cn": codename})

    op.drop_table("users")
