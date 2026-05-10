"""Add plan_features JSONB column to tenant_license_cache

Revision ID: 20260601000001
Revises: 20260531000001
Create Date: 2026-06-01
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260601000001"
down_revision = "20260531000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenant_license_cache",
        sa.Column("plan_features", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenant_license_cache", "plan_features")
