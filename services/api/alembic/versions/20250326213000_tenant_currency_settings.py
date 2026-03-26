"""tenant currency settings

Revision ID: 20250326213000
Revises: 20250326200000
Create Date: 2025-03-26

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20250326213000"
down_revision: Union[str, None] = "20250326200000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("default_currency_code", sa.String(length=3), server_default="USD", nullable=False),
    )
    op.add_column(
        "tenants",
        sa.Column("currency_exponent", sa.Integer(), server_default="2", nullable=False),
    )
    op.add_column(
        "tenants",
        sa.Column("currency_symbol_override", sa.String(length=8), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenants", "currency_symbol_override")
    op.drop_column("tenants", "currency_exponent")
    op.drop_column("tenants", "default_currency_code")

