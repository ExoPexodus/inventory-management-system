"""storefront magic links table

Revision ID: 20260526000001
Revises: 20260525000001
Create Date: 2026-05-26 00:00:01
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "20260526000001"
down_revision = "20260525000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "storefront_magic_links",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", UUID(as_uuid=True), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("redirect_url", sa.String(1024), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_storefront_magic_links_token_hash", "storefront_magic_links", ["token_hash"])


def downgrade() -> None:
    op.drop_index("ix_storefront_magic_links_token_hash", "storefront_magic_links")
    op.drop_table("storefront_magic_links")
