"""RMA Flow — refund_requests, refund_request_lines, refund_request_events tables + tenant RMA settings

Revision ID: 20260602000001
Revises: 20260601000001
Create Date: 2026-06-02
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20260602000001"
down_revision = "20260601000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    #  Extend tenants with RMA settings                                   #
    # ------------------------------------------------------------------ #
    op.add_column("tenants", sa.Column(
        "default_restock_on_refund", sa.Boolean(),
        nullable=False, server_default="true",
    ))
    op.add_column("tenants", sa.Column(
        "refund_window_days", sa.Integer(),
        nullable=False, server_default="30",
    ))
    op.add_column("tenants", sa.Column(
        "rma_auto_approve_under_cents", sa.Integer(),
        nullable=True,
    ))

    # ------------------------------------------------------------------ #
    #  refund_requests                                                     #
    # ------------------------------------------------------------------ #
    op.create_table(
        "refund_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_id", UUID(as_uuid=True), sa.ForeignKey("orders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sale_transaction_id", UUID(as_uuid=True), sa.ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("channel_id", UUID(as_uuid=True), sa.ForeignKey("channels.id", ondelete="SET NULL"), nullable=True),
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("customer_email", sa.String(255), nullable=True),
        sa.Column("customer_name", sa.String(255), nullable=True),
        sa.Column("refund_type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="requested"),
        sa.Column("reason_code", sa.String(32), nullable=False),
        sa.Column("reason_note", sa.Text(), nullable=True),
        sa.Column("refund_shipping", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("return_shipping_required", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("return_shipping_awb", sa.String(128), nullable=True),
        sa.Column("approved_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_reason", sa.Text(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_refund_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("provider_refund_ref", sa.String(255), nullable=True),
        sa.Column("cash_returned", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("cash_returned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auto_approved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_refund_requests_tenant_id", "refund_requests", ["tenant_id"])
    op.create_index("ix_refund_requests_order_id", "refund_requests", ["order_id"])
    op.create_index("ix_refund_requests_customer_id", "refund_requests", ["customer_id"])
    op.create_index("ix_refund_requests_status", "refund_requests", ["status"])

    # ------------------------------------------------------------------ #
    #  refund_request_lines                                                #
    # ------------------------------------------------------------------ #
    op.create_table(
        "refund_request_lines",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("refund_request_id", UUID(as_uuid=True), sa.ForeignKey("refund_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_line_id", UUID(as_uuid=True), sa.ForeignKey("order_lines.id", ondelete="SET NULL"), nullable=True),
        sa.Column("transaction_line_id", UUID(as_uuid=True), sa.ForeignKey("transaction_lines.id", ondelete="SET NULL"), nullable=True),
        sa.Column("product_id", UUID(as_uuid=True), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("product_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("product_sku", sa.String(64), nullable=True),
        sa.Column("quantity_requested", sa.Integer(), nullable=False),
        sa.Column("quantity_approved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unit_price_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("restock_on_approval", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("line_refund_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("exchange_for_product_id", UUID(as_uuid=True), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_refund_request_lines_request_id", "refund_request_lines", ["refund_request_id"])

    # ------------------------------------------------------------------ #
    #  refund_request_events                                               #
    # ------------------------------------------------------------------ #
    op.create_table(
        "refund_request_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("refund_request_id", UUID(as_uuid=True), sa.ForeignKey("refund_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("from_status", sa.String(16), nullable=True),
        sa.Column("to_status", sa.String(16), nullable=True),
        sa.Column("actor_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_kind", sa.String(16), nullable=False, server_default="system"),
        sa.Column("event_metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_refund_request_events_request_id", "refund_request_events", ["refund_request_id"])
    op.create_index("ix_refund_request_events_tenant_id", "refund_request_events", ["tenant_id"])

    # ------------------------------------------------------------------ #
    #  Permissions                                                         #
    # ------------------------------------------------------------------ #
    op.execute("""
        INSERT INTO permissions (id, codename, display_name, category, description)
        VALUES (gen_random_uuid(), 'rma:read', 'View Refund Requests', 'sales',
                'View RMA / refund request inbox and details')
        ON CONFLICT (codename) DO NOTHING
    """)
    op.execute("""
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), r.id, p.id
        FROM roles r, permissions p
        WHERE r.name = 'owner' AND r.is_system = TRUE
          AND p.codename = 'rma:read'
        ON CONFLICT DO NOTHING
    """)
    op.execute("""
        INSERT INTO permissions (id, codename, display_name, category, description)
        VALUES (gen_random_uuid(), 'rma:write', 'Manage Refund Requests', 'sales',
                'Approve, reject, and process RMA / refund requests')
        ON CONFLICT (codename) DO NOTHING
    """)
    op.execute("""
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), r.id, p.id
        FROM roles r, permissions p
        WHERE r.name = 'owner' AND r.is_system = TRUE
          AND p.codename = 'rma:write'
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE codename IN ('rma:read', 'rma:write'))")
    op.execute("DELETE FROM permissions WHERE codename IN ('rma:read', 'rma:write')")

    op.drop_table("refund_request_events")
    op.drop_table("refund_request_lines")
    op.drop_table("refund_requests")

    op.drop_column("tenants", "rma_auto_approve_under_cents")
    op.drop_column("tenants", "refund_window_days")
    op.drop_column("tenants", "default_restock_on_refund")
