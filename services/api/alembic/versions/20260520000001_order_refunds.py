"""add order_refunds table

Revision ID: 20260520000001
Revises: 20260519000001
Create Date: 2026-05-20 00:00:01
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260520000001"
down_revision = "20260519000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "order_refunds",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount_cents", sa.Integer, nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("reason", sa.String(512), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="issued"),
        sa.Column("issued_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_order_refunds_order", "order_refunds", ["order_id"])
    op.create_index("ix_order_refunds_tenant", "order_refunds", ["tenant_id"])
    op.execute("""
        INSERT INTO permissions (id, codename, display_name, category, description)
        VALUES (gen_random_uuid(), 'orders:manage', 'Manage E-commerce Orders', 'commerce',
                'View and refund e-commerce orders')
        ON CONFLICT (codename) DO NOTHING
    """)
    op.execute("""
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), r.id, p.id
        FROM roles r, permissions p
        WHERE r.name = 'owner' AND r.is_system = TRUE AND p.codename = 'orders:manage'
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions WHERE permission_id IN "
               "(SELECT id FROM permissions WHERE codename = 'orders:manage')")
    op.execute("DELETE FROM permissions WHERE codename = 'orders:manage'")
    op.drop_table("order_refunds")
