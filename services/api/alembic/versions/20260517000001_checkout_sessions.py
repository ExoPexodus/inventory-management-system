"""Hosted checkout: checkout_sessions table

Revision ID: 20260517000001
Revises: 20260516000001
Create Date: 2026-05-17 00:00:01.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

revision = "20260517000001"
down_revision = "20260516000001"
branch_labels = None
depends_on = None


_RLS_POLICY = """
COALESCE(current_setting('ims.is_admin', true), '') = 'true'
OR (
  NULLIF(TRIM(COALESCE(current_setting('ims.tenant_id', true), '')), '') IS NOT NULL
  AND tenant_id = (NULLIF(TRIM(COALESCE(current_setting('ims.tenant_id', true), '')), ''))::uuid
)
"""


def upgrade() -> None:
    op.create_table(
        "checkout_sessions",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cart_token", sa.String(128), nullable=False),
        sa.Column("session_token", sa.String(128), unique=True, nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("payment_provider", sa.String(32), nullable=True),
        sa.Column("external_payment_id", sa.String(255), nullable=True),
        sa.Column("subtotal_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("discount_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("shipping_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tax_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("customer_email", sa.String(255), nullable=True),
        sa.Column("shipping_address", JSONB, nullable=True),
        sa.Column("discount_code", sa.String(128), nullable=True),
        sa.Column("order_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("orders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_checkout_sessions_tenant_id", "checkout_sessions", ["tenant_id"])
    op.create_index("ix_checkout_sessions_channel_id", "checkout_sessions", ["channel_id"])
    op.create_index("ix_checkout_sessions_session_token", "checkout_sessions", ["session_token"])
    op.create_index("ix_checkout_sessions_status", "checkout_sessions", ["status", "expires_at"])

    op.execute(f"""
        ALTER TABLE checkout_sessions ENABLE ROW LEVEL SECURITY;
        ALTER TABLE checkout_sessions FORCE ROW LEVEL SECURITY;
        CREATE POLICY ims_tenant_isolation ON checkout_sessions
        USING ({_RLS_POLICY})
        WITH CHECK ({_RLS_POLICY});
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS ims_tenant_isolation ON checkout_sessions;")
    op.execute("ALTER TABLE checkout_sessions NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE checkout_sessions DISABLE ROW LEVEL SECURITY;")
    op.drop_index("ix_checkout_sessions_status", table_name="checkout_sessions")
    op.drop_index("ix_checkout_sessions_session_token", table_name="checkout_sessions")
    op.drop_index("ix_checkout_sessions_channel_id", table_name="checkout_sessions")
    op.drop_index("ix_checkout_sessions_tenant_id", table_name="checkout_sessions")
    op.drop_table("checkout_sessions")
