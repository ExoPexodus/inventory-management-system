"""platform managed currency

Revision ID: 33707ff7b81f
Revises: 20260419120000
Create Date: 2026-04-19 13:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "33707ff7b81f"
down_revision = "20260419120000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("currency_synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_column("tenants", "currency_conversion_rate")
    op.drop_column("tenants", "currency_display_mode")


def downgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("currency_display_mode", sa.String(16), nullable=False, server_default="symbol"),
    )
    op.add_column(
        "tenants",
        sa.Column("currency_conversion_rate", sa.Float(), nullable=True),
    )
    op.drop_column("tenants", "currency_synced_at")
