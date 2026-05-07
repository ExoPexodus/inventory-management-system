"""add storefront_otps table

Revision ID: 20260521000001
Revises: 20260520000001
Create Date: 2026-05-21 00:00:01
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260521000001"
down_revision = "20260520000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "storefront_otps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_storefront_otps_email_channel", "storefront_otps",
                    ["email", "channel_id"])


def downgrade() -> None:
    op.drop_table("storefront_otps")
