"""Make enrollment_tokens.shop_id and devices.default_shop_id nullable for admin mobile.

Revision ID: 20260503000001
Revises: 20260501000002
Create Date: 2026-05-03
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260503000001"
down_revision = "20260501000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("enrollment_tokens", "shop_id", nullable=True)
    op.alter_column("devices", "default_shop_id", nullable=True)


def downgrade() -> None:
    # Rows with NULL shop_id would violate NOT NULL — fill with first shop before downgrading.
    op.alter_column("enrollment_tokens", "shop_id", nullable=False)
    op.alter_column("devices", "default_shop_id", nullable=False)
