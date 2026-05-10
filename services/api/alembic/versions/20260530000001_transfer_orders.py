"""transfer orders: add approval/lifecycle columns and transfers:approve permission

Revision ID: 20260530000001
Revises: 20260529000001
Create Date: 2026-05-30 00:00:01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "20260530000001"
down_revision = "20260529000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── tenants: transfer settings ─────────────────────────────────────────
    op.add_column(
        "tenants",
        sa.Column("transfer_auto_approve_under_cents", sa.Integer(), nullable=True),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "transfer_allow_self_approval",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # ── transfer_orders: approval / lifecycle columns ──────────────────────
    op.add_column(
        "transfer_orders",
        sa.Column(
            "approved_by_user_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "transfer_orders",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "transfer_orders",
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "transfer_orders",
        sa.Column("rejection_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "transfer_orders",
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "transfer_orders",
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "transfer_orders",
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "transfer_orders",
        sa.Column("notes", sa.Text(), nullable=True),
    )

    # ── transfer_order_lines: cost snapshot + per-line notes ───────────────
    op.add_column(
        "transfer_order_lines",
        sa.Column("unit_cost_at_transfer_cents", sa.Integer(), nullable=True),
    )
    op.add_column(
        "transfer_order_lines",
        sa.Column("line_notes", sa.Text(), nullable=True),
    )

    # ── permission seed ────────────────────────────────────────────────────
    op.execute("""
        INSERT INTO permissions (id, codename, display_name, category, description)
        VALUES (gen_random_uuid(), 'transfers:approve', 'Approve Transfer Orders', 'operations',
                'Approve or reject inter-shop inventory transfer orders')
        ON CONFLICT (codename) DO NOTHING
    """)
    op.execute("""
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), r.id, p.id
        FROM roles r, permissions p
        WHERE r.name = 'owner' AND r.is_system = TRUE
          AND p.codename = 'transfers:approve'
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    # Remove permission grants and permission
    op.execute("""
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE codename = 'transfers:approve')
    """)
    op.execute("DELETE FROM permissions WHERE codename = 'transfers:approve'")

    # transfer_order_lines columns
    op.drop_column("transfer_order_lines", "line_notes")
    op.drop_column("transfer_order_lines", "unit_cost_at_transfer_cents")

    # transfer_orders columns
    op.drop_column("transfer_orders", "notes")
    op.drop_column("transfer_orders", "cancelled_at")
    op.drop_column("transfer_orders", "received_at")
    op.drop_column("transfer_orders", "shipped_at")
    op.drop_column("transfer_orders", "rejection_reason")
    op.drop_column("transfer_orders", "rejected_at")
    op.drop_column("transfer_orders", "approved_at")
    op.drop_column("transfer_orders", "approved_by_user_id")

    # tenants columns
    op.drop_column("tenants", "transfer_allow_self_approval")
    op.drop_column("tenants", "transfer_auto_approve_under_cents")
