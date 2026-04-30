"""tenant and shop timezone fields + tenant financial year start month

Revision ID: 20260429000002
Revises: 20260429000001
Create Date: 2026-04-29 00:00:02.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260429000002"
down_revision = "20260429000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("timezone", sa.String(64), nullable=True))
    op.add_column("tenants", sa.Column("financial_year_start_month", sa.SmallInteger(), nullable=True))
    op.add_column("shops", sa.Column("timezone", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("shops", "timezone")
    op.drop_column("tenants", "financial_year_start_month")
    op.drop_column("tenants", "timezone")
