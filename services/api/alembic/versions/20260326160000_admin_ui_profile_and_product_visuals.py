"""add admin profile and product visual planning columns

Revision ID: 20260326160000
Revises: 20260326143000
Create Date: 2026-03-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260326160000"
down_revision: Union[str, None] = "20260326143000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("products", sa.Column("image_url", sa.String(length=1024), nullable=True))
    op.add_column(
        "products",
        sa.Column("reorder_point", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("admin_users", sa.Column("display_name", sa.String(length=255), nullable=True))
    op.add_column("admin_users", sa.Column("avatar_url", sa.String(length=1024), nullable=True))


def downgrade() -> None:
    op.drop_column("admin_users", "avatar_url")
    op.drop_column("admin_users", "display_name")
    op.drop_column("products", "reorder_point")
    op.drop_column("products", "image_url")
