"""add webhook_endpoints and webhook_delivery_logs tables

Revision ID: 20260519000001
Revises: 20260518000001
Create Date: 2026-05-19 00:00:01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260519000001"
down_revision = "20260518000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhook_endpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.String(512), nullable=False),
        sa.Column("secret", sa.String(255), nullable=False),
        sa.Column("events", postgresql.ARRAY(sa.String(64)), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_webhook_endpoints_tenant", "webhook_endpoints", ["tenant_id"])

    op.create_table(
        "webhook_delivery_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("endpoint_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("response_status", sa.Integer, nullable=True),
        sa.Column("response_body", sa.Text, nullable=True),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_webhook_delivery_logs_endpoint", "webhook_delivery_logs", ["endpoint_id"])
    op.create_index("ix_webhook_delivery_logs_tenant_status",
                    "webhook_delivery_logs", ["tenant_id", "status"])

    op.execute("""
        INSERT INTO permissions (id, codename, display_name, category, description)
        VALUES (gen_random_uuid(), 'webhooks:manage', 'Manage Webhook Endpoints', 'integrations',
                'Register and manage outbound webhook endpoints')
        ON CONFLICT (codename) DO NOTHING
    """)
    op.execute("""
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), r.id, p.id
        FROM roles r, permissions p
        WHERE r.name = 'owner' AND r.is_system = TRUE AND p.codename = 'webhooks:manage'
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions WHERE permission_id IN "
               "(SELECT id FROM permissions WHERE codename = 'webhooks:manage')")
    op.execute("DELETE FROM permissions WHERE codename = 'webhooks:manage'")
    op.drop_table("webhook_delivery_logs")
    op.drop_table("webhook_endpoints")
