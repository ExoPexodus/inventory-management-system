"""Add tenant_license_cache table and download_token to tenants

Revision ID: 20260416000001
Revises: 20260415000002
Create Date: 2026-04-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "20260416000001"
down_revision = "20260415000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("download_token", sa.String(64), nullable=True))

    op.create_table(
        "tenant_license_cache",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("subscription_status", sa.String(32), nullable=False),
        sa.Column("plan_codename", sa.String(64), nullable=False),
        sa.Column("billing_cycle", sa.String(16), nullable=True),
        sa.Column("active_addons", JSONB, nullable=True),
        sa.Column("max_shops", sa.Integer, server_default="1", nullable=False),
        sa.Column("max_employees", sa.Integer, server_default="5", nullable=False),
        sa.Column("storage_limit_mb", sa.Integer, server_default="500", nullable=False),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("grace_period_days", sa.Integer, server_default="7"),
        sa.Column("is_in_grace_period", sa.Boolean, server_default="false"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("tenant_license_cache")
    op.drop_column("tenants", "download_token")
