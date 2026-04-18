"""auto resolve reconciliation

Revision ID: 46e831b94fc1
Revises: 20260417000001
Create Date: 2026-04-19 04:05:50.102549

"""
from __future__ import annotations

import uuid
from alembic import op
import sqlalchemy as sa

revision = "46e831b94fc1"
down_revision = "20260417000001"
branch_labels = None
depends_on = None


SYSTEM_ROLE_NAME = "system"
SYSTEM_USER_EMAIL_TEMPLATE = "system+{tenant_id}@internal.ims"
UNUSABLE_PASSWORD_HASH = "!auto-resolve-sentinel"


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
    tenants = conn.execute(sa.text("SELECT id FROM tenants")).fetchall()
    for (tenant_id,) in tenants:
        existing_role = conn.execute(
            sa.text("SELECT id FROM roles WHERE tenant_id = :t AND name = :n"),
            {"t": tenant_id, "n": SYSTEM_ROLE_NAME},
        ).fetchone()

        if existing_role is None:
            role_id = uuid.uuid4()
            conn.execute(
                sa.text(
                    "INSERT INTO roles (id, tenant_id, name, display_name, is_system, created_at) "
                    "VALUES (:id, :t, :n, :d, :s, NOW())"
                ),
                {
                    "id": role_id,
                    "t": tenant_id,
                    "n": SYSTEM_ROLE_NAME,
                    "d": "System (automated actions)",
                    "s": True,
                },
            )
        else:
            role_id = existing_role[0]

        existing_user = conn.execute(
            sa.text("SELECT id FROM users WHERE tenant_id = :t AND role_id = :r"),
            {"t": tenant_id, "r": role_id},
        ).fetchone()
        if existing_user is None:
            conn.execute(
                sa.text(
                    "INSERT INTO users (id, tenant_id, role_id, email, name, password_hash, is_active, created_at, updated_at) "
                    "VALUES (:id, :t, :r, :e, :n, :p, :a, NOW(), NOW())"
                ),
                {
                    "id": uuid.uuid4(),
                    "t": tenant_id,
                    "r": role_id,
                    "e": SYSTEM_USER_EMAIL_TEMPLATE.format(tenant_id=tenant_id),
                    "n": "System",
                    "p": UNUSABLE_PASSWORD_HASH,
                    "a": False,
                },
            )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        "DELETE FROM users WHERE role_id IN (SELECT id FROM roles WHERE name = 'system')"
    ))
    conn.execute(sa.text("DELETE FROM roles WHERE name = 'system'"))

    op.drop_column("shops", "auto_resolve_overage_cents_override")
    op.drop_column("shops", "auto_resolve_shortage_cents_override")
    op.drop_column("tenants", "auto_resolve_overage_cents")
    op.drop_column("tenants", "auto_resolve_shortage_cents")
