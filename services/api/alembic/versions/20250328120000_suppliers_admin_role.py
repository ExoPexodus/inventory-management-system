"""suppliers table + admin_users.role

Revision ID: 20250328120000
Revises: 20250327100000
Create Date: 2025-03-28

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20250328120000"
down_revision: Union[str, None] = "20250327100000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "admin_users",
        sa.Column("role", sa.String(length=64), server_default="admin", nullable=False),
    )

    op.create_table(
        "suppliers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("contact_phone", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.execute(
        """
        ALTER TABLE suppliers ENABLE ROW LEVEL SECURITY;
        ALTER TABLE suppliers FORCE ROW LEVEL SECURITY;
        CREATE POLICY ims_tenant_isolation ON suppliers
        USING (
          COALESCE(current_setting('ims.is_admin', true), '') = 'true'
          OR (
            NULLIF(TRIM(COALESCE(current_setting('ims.tenant_id', true), '')), '') IS NOT NULL
            AND tenant_id = (NULLIF(TRIM(COALESCE(current_setting('ims.tenant_id', true), '')), ''))::uuid
          )
        )
        WITH CHECK (
          COALESCE(current_setting('ims.is_admin', true), '') = 'true'
          OR (
            NULLIF(TRIM(COALESCE(current_setting('ims.tenant_id', true), '')), '') IS NOT NULL
            AND tenant_id = (NULLIF(TRIM(COALESCE(current_setting('ims.tenant_id', true), '')), ''))::uuid
          )
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS ims_tenant_isolation ON suppliers;")
    op.execute("ALTER TABLE suppliers NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE suppliers DISABLE ROW LEVEL SECURITY;")
    op.drop_table("suppliers")
    op.drop_column("admin_users", "role")
