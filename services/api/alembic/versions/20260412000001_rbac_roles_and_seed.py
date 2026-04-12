"""RBAC: roles table, reseed permissions, link admin_users.role_id

Revision ID: 20260412000001
Revises: 20260404000001
Create Date: 2026-04-12
"""

from typing import Sequence, Union
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260412000001"
down_revision: Union[str, None] = "20260404000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ---------------------------------------------------------------------------
# Permission catalogue (28 permissions)
# ---------------------------------------------------------------------------
PERMISSIONS = [
    ("staff:read",          "View Employees",               "staff",        "View employee records"),
    ("staff:write",         "Manage Employees",             "staff",        "Create, edit, deactivate, and invite employees"),
    ("catalog:read",        "View Catalog",                 "catalog",      "View products and product groups"),
    ("catalog:write",       "Manage Catalog",               "catalog",      "Create and edit products, CSV import"),
    ("inventory:read",      "View Inventory",               "inventory",    "View stock levels and movements"),
    ("inventory:write",     "Manage Inventory",             "inventory",    "Create adjustments and bulk reorder points"),
    ("procurement:read",    "View Procurement",             "procurement",  "View suppliers and purchase orders"),
    ("procurement:write",   "Manage Procurement",           "procurement",  "Create and edit suppliers and purchase orders"),
    ("sales:read",          "View Sales",                   "sales",        "View transactions"),
    ("sales:write",         "Manage Sales",                 "sales",        "Update transaction status"),
    ("analytics:read",      "View Analytics",               "analytics",    "View dashboards and summaries"),
    ("operations:read",     "View Operations",              "operations",   "View shifts and reconciliation"),
    ("operations:write",    "Manage Operations",            "operations",   "Open/close shifts, resolve and approve"),
    ("settings:read",       "View Settings",                "settings",     "View tenant settings"),
    ("settings:write",      "Manage Settings",              "settings",     "Update settings, currency, and email config"),
    ("integrations:read",   "View Integrations",            "integrations", "View webhooks and API tokens"),
    ("integrations:write",  "Manage Integrations",          "integrations", "Create and delete webhooks and tokens"),
    ("operators:read",      "View Operators",               "operators",    "View admin operator accounts"),
    ("operators:write",     "Manage Operators",             "operators",    "Create, edit, and deactivate operators"),
    ("roles:read",          "View Roles",                   "roles",        "View roles and their permissions"),
    ("roles:write",         "Manage Roles",                 "roles",        "Create, edit, and delete custom roles"),
    ("audit:read",          "View Audit Log",               "audit",        "View audit log entries"),
    ("reports:read",        "Export Reports",               "reports",      "Export CSV reports"),
    ("notifications:read",  "View Notifications",           "notifications","View notifications"),
    ("notifications:write", "Manage Notifications",         "notifications","Mark notifications as read"),
    ("enrollment:write",    "Create Enrollment Tokens",     "enrollment",   "Generate enrollment tokens for devices"),
    ("shops:read",          "View Shops",                   "shops",        "View shop records"),
    ("shops:write",         "Manage Shops",                 "shops",        "Create shops and edit tax configuration"),
]

# All permission codenames
ALL_PERMS = [p[0] for p in PERMISSIONS]

# Manager gets everything except settings/integrations/operators/roles/enrollment/shops:write
MANAGER_PERMS = [
    "staff:read", "staff:write",
    "catalog:read", "catalog:write",
    "inventory:read", "inventory:write",
    "procurement:read", "procurement:write",
    "sales:read", "sales:write",
    "analytics:read",
    "operations:read", "operations:write",
    "notifications:read", "notifications:write",
    "audit:read",
    "reports:read",
    "shops:read",
]

# Cashier has no admin permissions (POS device only)
CASHIER_PERMS: list[str] = []

SYSTEM_ROLES = [
    ("owner",   "Owner",   ALL_PERMS),
    ("manager", "Manager", MANAGER_PERMS),
    ("cashier", "Cashier", CASHIER_PERMS),
]


def _new_uuid() -> str:
    return str(uuid.uuid4())


def upgrade() -> None:
    conn = op.get_bind()

    # ------------------------------------------------------------------
    # 1. Create roles table
    # ------------------------------------------------------------------
    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("is_system", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_roles_tenant_name"),
    )

    # ------------------------------------------------------------------
    # 2. Drop old role_permissions (string role column, no FK to roles)
    #    and recreate with UUID role_id FK
    # ------------------------------------------------------------------
    op.drop_table("role_permissions")
    op.create_table(
        "role_permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("permission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("role_id", "permission_id", name="uq_role_permissions"),
    )

    # ------------------------------------------------------------------
    # 3. Seed permissions table (upsert by codename so re-runs are safe)
    # ------------------------------------------------------------------
    perm_table = sa.table(
        "permissions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("codename", sa.String),
        sa.column("display_name", sa.String),
        sa.column("category", sa.String),
        sa.column("description", sa.Text),
    )

    existing_rows = conn.execute(sa.select(perm_table.c.codename, perm_table.c.id)).fetchall()
    existing_by_codename: dict[str, str] = {r[0]: str(r[1]) for r in existing_rows}

    perm_id_by_codename: dict[str, str] = {}
    for codename, display_name, category, description in PERMISSIONS:
        if codename in existing_by_codename:
            perm_id_by_codename[codename] = existing_by_codename[codename]
        else:
            new_id = _new_uuid()
            conn.execute(
                perm_table.insert().values(
                    id=new_id,
                    codename=codename,
                    display_name=display_name,
                    category=category,
                    description=description,
                )
            )
            perm_id_by_codename[codename] = new_id

    # ------------------------------------------------------------------
    # 4. For each tenant, create 3 system roles and assign permissions
    # ------------------------------------------------------------------
    tenant_table = sa.table("tenants", sa.column("id", postgresql.UUID(as_uuid=True)))
    tenant_rows = conn.execute(sa.select(tenant_table.c.id)).fetchall()
    tenant_ids = [str(r[0]) for r in tenant_rows]

    role_table = sa.table(
        "roles",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("tenant_id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("display_name", sa.String),
        sa.column("is_system", sa.Boolean),
    )

    rp_table = sa.table(
        "role_permissions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("role_id", postgresql.UUID(as_uuid=True)),
        sa.column("permission_id", postgresql.UUID(as_uuid=True)),
    )

    # Map: (tenant_id, role_name) -> role_id  — needed later to migrate admin_users
    tenant_role_ids: dict[tuple[str, str], str] = {}

    for tenant_id in tenant_ids:
        for role_name, display_name, perms in SYSTEM_ROLES:
            role_id = _new_uuid()
            conn.execute(
                role_table.insert().values(
                    id=role_id,
                    tenant_id=tenant_id,
                    name=role_name,
                    display_name=display_name,
                    is_system=True,
                )
            )
            tenant_role_ids[(tenant_id, role_name)] = role_id

            for perm_codename in perms:
                conn.execute(
                    rp_table.insert().values(
                        id=_new_uuid(),
                        role_id=role_id,
                        permission_id=perm_id_by_codename[perm_codename],
                    )
                )

    # ------------------------------------------------------------------
    # 5. Add role_id column to admin_users (nullable first)
    # ------------------------------------------------------------------
    op.add_column(
        "admin_users",
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # ------------------------------------------------------------------
    # 6. Map existing admin_users.role string → role_id
    #    "admin" / "superadmin" / "owner" / unknown → owner role
    #    "manager" → manager role
    #    "cashier" → cashier role
    # ------------------------------------------------------------------
    au_table = sa.table(
        "admin_users",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("role", sa.String),
        sa.column("role_id", postgresql.UUID(as_uuid=True)),
        sa.column("tenant_id", postgresql.UUID(as_uuid=True)),
    )

    admin_rows = conn.execute(
        sa.select(au_table.c.id, au_table.c.role, au_table.c.tenant_id)
    ).fetchall()

    for row in admin_rows:
        user_id = str(row[0])
        old_role = (row[1] or "admin").lower()
        tenant_id = str(row[2]) if row[2] else None

        # Determine which system role name to map to
        if old_role in ("manager",):
            target_role_name = "manager"
        elif old_role in ("cashier",):
            target_role_name = "cashier"
        else:
            target_role_name = "owner"

        new_role_id: str | None = None
        if tenant_id and (tenant_id, target_role_name) in tenant_role_ids:
            new_role_id = tenant_role_ids[(tenant_id, target_role_name)]
        elif tenant_id:
            # Fallback to owner if the mapped role doesn't exist for some reason
            new_role_id = tenant_role_ids.get((tenant_id, "owner"))

        if new_role_id:
            conn.execute(
                sa.update(au_table)
                .where(au_table.c.id == user_id)
                .values(role_id=new_role_id)
            )

    # ------------------------------------------------------------------
    # 7. Make role_id NOT NULL and add FK constraint
    #    (admins without a tenant are left nullable — superadmin / CI accounts)
    # ------------------------------------------------------------------
    # Set any still-null role_id rows to NULL is acceptable for tenant-less admins.
    # Only enforce NOT NULL for tenant-scoped admins via a partial index / app logic.
    # For now we leave the column nullable to avoid breaking super-admin accounts.
    op.create_foreign_key(
        "fk_admin_users_role_id",
        "admin_users",
        "roles",
        ["role_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # ------------------------------------------------------------------
    # 8. Drop the old freeform role string column
    # ------------------------------------------------------------------
    op.drop_column("admin_users", "role")


def downgrade() -> None:
    # Restore role string column
    op.add_column(
        "admin_users",
        sa.Column("role", sa.String(length=64), server_default="admin", nullable=False),
    )

    # Populate role string from role name via JOIN
    conn = op.get_bind()
    conn.execute(sa.text("""
        UPDATE admin_users au
        SET role = r.name
        FROM roles r
        WHERE au.role_id = r.id
    """))

    op.drop_constraint("fk_admin_users_role_id", "admin_users", type_="foreignkey")
    op.drop_column("admin_users", "role_id")

    # Recreate old role_permissions with string role column
    op.drop_table("role_permissions")
    op.create_table(
        "role_permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("permission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("role", "permission_id", name="uq_role_permission"),
    )

    op.drop_table("roles")
