"""add tenant_id to admin_users for strict operator scoping

Revision ID: 20260326143000
Revises: 20260326120000
Create Date: 2026-03-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260326143000"
down_revision: Union[str, None] = "20260326120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "admin_users",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_admin_users_tenant_id",
        "admin_users",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_admin_users_tenant_id", "admin_users", type_="foreignkey")
    op.drop_column("admin_users", "tenant_id")
