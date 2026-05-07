"""add shipment fields to orders + shipment_events table

Revision ID: 20260523000001
Revises: 20260522000001
Create Date: 2026-05-23 00:00:01
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260523000001"
down_revision = "20260522000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for col_name, col_type, kwargs in [
        ("fulfillment_status", sa.String(32), {"nullable": False, "server_default": "pending"}),
        ("shipping_provider",  sa.String(32),  {"nullable": True}),
        ("provider_order_id",  sa.String(255), {"nullable": True}),
        ("awb_code",           sa.String(64),  {"nullable": True}),
        ("tracking_url",       sa.String(512), {"nullable": True}),
        ("carrier_name",       sa.String(128), {"nullable": True}),
        ("label_url",          sa.String(512), {"nullable": True}),
        ("shipped_at",         sa.DateTime(timezone=True), {"nullable": True}),
        ("delivered_at",       sa.DateTime(timezone=True), {"nullable": True}),
    ]:
        op.add_column("orders", sa.Column(col_name, col_type, **kwargs))

    op.create_index("ix_orders_fulfillment_status", "orders",
                    ["tenant_id", "fulfillment_status"])

    op.create_table(
        "shipment_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("description", sa.String(512), nullable=True),
        sa.Column("provider_event_id", sa.String(255), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("order_id", "provider_event_id",
                            name="uq_shipment_event_order_provider"),
    )
    op.create_index("ix_shipment_events_order", "shipment_events", ["order_id"])

    op.execute("""
        INSERT INTO permissions (id, codename, display_name, category, description)
        VALUES (gen_random_uuid(), 'shipping:manage', 'Manage Shipping Providers', 'commerce',
                'Configure carrier shipping providers and manage shipment dispatch')
        ON CONFLICT (codename) DO NOTHING
    """)
    op.execute("""
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), r.id, p.id
        FROM roles r, permissions p
        WHERE r.name = 'owner' AND r.is_system = TRUE AND p.codename = 'shipping:manage'
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions WHERE permission_id IN "
               "(SELECT id FROM permissions WHERE codename = 'shipping:manage')")
    op.execute("DELETE FROM permissions WHERE codename = 'shipping:manage'")
    op.drop_table("shipment_events")
    for col in ["fulfillment_status", "shipping_provider", "provider_order_id", "awb_code",
                "tracking_url", "carrier_name", "label_url", "shipped_at", "delivered_at"]:
        op.drop_column("orders", col)
