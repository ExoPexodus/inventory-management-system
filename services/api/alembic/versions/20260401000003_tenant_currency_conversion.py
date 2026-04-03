"""add currency conversion columns to tenants

Revision ID: 20260401000003
Revises: 20260401000002
Create Date: 2026-04-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260401000003"
down_revision: Union[str, None] = "20260401000002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("currency_display_mode", sa.String(length=16), server_default="symbol", nullable=False),
    )
    op.add_column(
        "tenants",
        sa.Column("currency_conversion_rate", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenants", "currency_conversion_rate")
    op.drop_column("tenants", "currency_display_mode")
