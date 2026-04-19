"""tenant currency and deployment mode

Revision ID: cda681b0bf46
Revises: 20260416000001
Create Date: 2026-04-19 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "cda681b0bf46"
down_revision = "20260416000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "platform_tenants",
        sa.Column("default_currency_code", sa.String(3), nullable=False, server_default="USD"),
    )
    op.add_column(
        "platform_tenants",
        sa.Column("currency_exponent", sa.Integer(), nullable=False, server_default="2"),
    )
    op.add_column(
        "platform_tenants",
        sa.Column("currency_symbol_override", sa.String(8), nullable=True),
    )
    op.add_column(
        "platform_tenants",
        sa.Column("deployment_mode", sa.String(16), nullable=False, server_default="cloud"),
    )


def downgrade() -> None:
    op.drop_column("platform_tenants", "deployment_mode")
    op.drop_column("platform_tenants", "currency_symbol_override")
    op.drop_column("platform_tenants", "currency_exponent")
    op.drop_column("platform_tenants", "default_currency_code")
