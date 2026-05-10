"""discount quantity/category conditions and tiers

Revision ID: 20260528000001
Revises: 20260527000001
Create Date: 2026-05-28 00:00:01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "20260528000001"
down_revision = "20260527000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ----------------------------------------------------------------
    # 1. Add 4 new condition columns to discounts
    # ----------------------------------------------------------------
    op.add_column(
        "discounts",
        sa.Column(
            "condition_quantity_scope",
            sa.String(16),
            nullable=False,
            server_default="none",
        ),
    )
    op.add_column(
        "discounts",
        sa.Column("condition_min_quantity", sa.Integer(), nullable=True),
    )
    op.add_column(
        "discounts",
        sa.Column(
            "condition_category_id",
            UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "discounts",
        sa.Column("condition_tag", sa.String(64), nullable=True),
    )

    # ----------------------------------------------------------------
    # 2. Create discount_tiers table
    # ----------------------------------------------------------------
    op.create_table(
        "discount_tiers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "discount_id",
            UUID(as_uuid=True),
            sa.ForeignKey("discounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("threshold_quantity", sa.Integer(), nullable=False),
        sa.Column("value_bps", sa.Integer(), nullable=True),
        sa.Column("value_cents", sa.Integer(), nullable=True),
        sa.Column(
            "sort_order", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "discount_id",
            "threshold_quantity",
            name="uq_discount_tiers_discount_threshold",
        ),
    )
    op.create_index(
        "ix_discount_tiers_discount_id", "discount_tiers", ["discount_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_discount_tiers_discount_id", "discount_tiers")
    op.drop_table("discount_tiers")
    op.drop_column("discounts", "condition_tag")
    op.drop_column("discounts", "condition_category_id")
    op.drop_column("discounts", "condition_min_quantity")
    op.drop_column("discounts", "condition_quantity_scope")
