"""Add tenant_feature_overrides + feature_flags tables; seed entitlements:manage permission

Revision ID: 20260506000001
Revises: 20260503000001
Create Date: 2026-05-06 00:00:01.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

revision = "20260506000001"
down_revision = "20260503000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. tenant_feature_overrides
    op.create_table(
        "tenant_feature_overrides",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("feature_key", sa.String(128), nullable=False),
        sa.Column("value", JSONB, nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "feature_key", name="uq_tenant_feature_override_key"),
    )

    # 2a. Drop the legacy unused feature_flags table from
    # 20260326200000_phase4_analytics_platform.py — that table was created but
    # never wired up (no model, no service references it). We replace it with
    # the engineering-flag schema below.
    op.drop_table("feature_flags")

    # 2. feature_flags
    op.create_table(
        "feature_flags",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(128), unique=True, nullable=False),
        sa.Column("default_state", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("rollout_rules", JSONB, nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 3. Seed permission. Deliberately NOT auto-granted to any role: this is an
    #    IMS-staff-only permission (overrides bypass commercial gates) and must
    #    be granted to specific operators by a staff workflow, not by default.
    conn = op.get_bind()
    conn.execute(sa.text(
        "INSERT INTO permissions (id, codename, display_name, category, description) "
        "VALUES (gen_random_uuid(), 'entitlements:manage', 'Manage Entitlements', 'billing', "
        "'Manage tenant feature overrides and engineering flags (IMS staff only)') "
        "ON CONFLICT (codename) DO UPDATE SET description = EXCLUDED.description"
    ))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        "DELETE FROM role_permissions WHERE permission_id IN "
        "(SELECT id FROM permissions WHERE codename = 'entitlements:manage')"
    ))
    conn.execute(sa.text("DELETE FROM permissions WHERE codename = 'entitlements:manage'"))
    op.drop_table("feature_flags")
    op.drop_table("tenant_feature_overrides")
    # Re-create the legacy unused feature_flags table so the schema after
    # downgrade matches what 20260326200000_phase4_analytics_platform.py
    # leaves behind.
    op.create_table(
        "feature_flags",
        sa.Column("id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("tenant_scope", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
