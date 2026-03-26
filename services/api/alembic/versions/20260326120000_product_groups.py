"""product_groups + product variant fields

Revision ID: 20260326120000
Revises: 20250328120000
Create Date: 2026-03-26

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260326120000"
down_revision: Union[str, None] = "20250328120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "product_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.execute(
        """
        ALTER TABLE product_groups ENABLE ROW LEVEL SECURITY;
        ALTER TABLE product_groups FORCE ROW LEVEL SECURITY;
        CREATE POLICY ims_tenant_isolation ON product_groups
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

    op.add_column(
        "products",
        sa.Column("product_group_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "products",
        sa.Column("variant_label", sa.String(length=128), nullable=True),
    )
    op.create_foreign_key(
        "fk_products_product_group_id",
        "products",
        "product_groups",
        ["product_group_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_products_product_group_id", "products", type_="foreignkey")
    op.drop_column("products", "variant_label")
    op.drop_column("products", "product_group_id")

    op.execute("DROP POLICY IF EXISTS ims_tenant_isolation ON product_groups;")
    op.execute("ALTER TABLE product_groups NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE product_groups DISABLE ROW LEVEL SECURITY;")
    op.drop_table("product_groups")
