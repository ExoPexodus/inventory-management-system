"""Initial platform schema

Revision ID: 20260416000001
Revises: -
Create Date: 2026-04-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "20260416000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Platform operators
    op.create_table(
        "platform_operators",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Platform tenants
    op.create_table(
        "platform_tenants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(64), unique=True, nullable=False),
        sa.Column("region", sa.String(32), server_default="in"),
        sa.Column("api_base_url", sa.String(512), nullable=False),
        sa.Column("api_shared_secret", sa.String(255), nullable=False),
        sa.Column("download_token", sa.String(64), unique=True, nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Plans
    op.create_table(
        "plans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("codename", sa.String(64), unique=True, nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("base_price_cents", sa.Integer, nullable=False),
        sa.Column("currency_code", sa.String(3), server_default="INR"),
        sa.Column("yearly_discount_pct", sa.Integer, server_default="0"),
        sa.Column("max_shops", sa.Integer, server_default="1", nullable=False),
        sa.Column("max_employees", sa.Integer, server_default="5", nullable=False),
        sa.Column("storage_limit_mb", sa.Integer, server_default="500", nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Addons
    op.create_table(
        "addons",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("codename", sa.String(64), unique=True, nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("price_cents", sa.Integer, nullable=False),
        sa.Column("currency_code", sa.String(3), server_default="INR"),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Subscriptions
    op.create_table(
        "subscriptions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("platform_tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan_id", UUID(as_uuid=True), sa.ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(32), server_default="trial", nullable=False),
        sa.Column("billing_cycle", sa.String(16), server_default="monthly", nullable=False),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("grace_period_days", sa.Integer, server_default="7"),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Subscription addons
    op.create_table(
        "subscription_addons",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("subscription_id", UUID(as_uuid=True), sa.ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("addon_id", UUID(as_uuid=True), sa.ForeignKey("addons.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("subscription_id", "addon_id", name="uq_sub_addon_active"),
    )

    # Tenant limit overrides
    op.create_table(
        "tenant_limit_overrides",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("platform_tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("limit_key", sa.String(64), nullable=False),
        sa.Column("limit_value", sa.Integer, nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "limit_key", name="uq_tenant_limit_key"),
    )

    # Payment gateway configs
    op.create_table(
        "payment_gateway_configs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("gateway", sa.String(32), nullable=False),
        sa.Column("region", sa.String(32), nullable=False),
        sa.Column("config_encrypted", JSONB, nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("gateway", "region", name="uq_gateway_region"),
    )

    # Payments
    op.create_table(
        "payments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("platform_tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subscription_id", UUID(as_uuid=True), sa.ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount_cents", sa.Integer, nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("gateway", sa.String(32), nullable=False),
        sa.Column("gateway_payment_id", sa.String(255), nullable=True),
        sa.Column("gateway_order_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("method", sa.String(64), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Invoices
    op.create_table(
        "invoices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("platform_tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subscription_id", UUID(as_uuid=True), sa.ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("payment_id", UUID(as_uuid=True), sa.ForeignKey("payments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("invoice_number", sa.String(64), unique=True, nullable=False),
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),
        sa.Column("seller_gstin", sa.String(20), nullable=True),
        sa.Column("buyer_gstin", sa.String(20), nullable=True),
        sa.Column("seller_legal_name", sa.String(255), nullable=True),
        sa.Column("buyer_legal_name", sa.String(255), nullable=True),
        sa.Column("place_of_supply", sa.String(64), nullable=True),
        sa.Column("line_items", JSONB, nullable=False),
        sa.Column("subtotal_cents", sa.Integer, nullable=False),
        sa.Column("tax_cents", sa.Integer, server_default="0"),
        sa.Column("total_cents", sa.Integer, nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("file_url", sa.String(1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # App releases
    op.create_table(
        "app_releases",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("app_name", sa.String(64), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("version_code", sa.Integer, nullable=False),
        sa.Column("changelog", sa.Text, nullable=True),
        sa.Column("file_path", sa.String(1024), nullable=False),
        sa.Column("file_size_bytes", sa.Integer, nullable=True),
        sa.Column("checksum_sha256", sa.String(64), nullable=True),
        sa.Column("uploaded_by", UUID(as_uuid=True), sa.ForeignKey("platform_operators.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("app_name", "version", name="uq_app_version"),
    )

    # Audit logs
    op.create_table(
        "platform_audit_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("operator_id", UUID(as_uuid=True), sa.ForeignKey("platform_operators.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(128), nullable=False),
        sa.Column("resource_id", sa.String(128), nullable=True),
        sa.Column("details", JSONB, nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("platform_audit_logs")
    op.drop_table("app_releases")
    op.drop_table("invoices")
    op.drop_table("payments")
    op.drop_table("payment_gateway_configs")
    op.drop_table("tenant_limit_overrides")
    op.drop_table("subscription_addons")
    op.drop_table("subscriptions")
    op.drop_table("addons")
    op.drop_table("plans")
    op.drop_table("platform_tenants")
    op.drop_table("platform_operators")
