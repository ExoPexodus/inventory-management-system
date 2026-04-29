"""product catalog fields — barcode, cost_price_cents, mrp_cents, hsn_code, negative_inventory_allowed

Revision ID: 20260429000001
Revises: 33707ff7b81f
Create Date: 2026-04-29 00:00:01.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260429000001"
down_revision = "33707ff7b81f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("cost_price_cents", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("mrp_cents", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("barcode", sa.String(128), nullable=True))
    op.add_column("products", sa.Column("hsn_code", sa.String(32), nullable=True))
    op.add_column(
        "products",
        sa.Column("negative_inventory_allowed", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("products", "negative_inventory_allowed")
    op.drop_column("products", "hsn_code")
    op.drop_column("products", "barcode")
    op.drop_column("products", "mrp_cents")
    op.drop_column("products", "cost_price_cents")
