"""product category, shop default tax, shop_product_tax, transaction.tax_cents

Revision ID: 20250327100000
Revises: 20250326213000
Create Date: 2025-03-27

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20250327100000"
down_revision: Union[str, None] = "20250326213000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("category", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "shops",
        sa.Column("default_tax_rate_bps", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "transactions",
        sa.Column("tax_cents", sa.Integer(), server_default="0", nullable=False),
    )

    op.create_table(
        "shop_product_tax",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tax_exempt", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("effective_tax_rate_bps", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("shop_id", "product_id", name="uq_shop_product_tax_shop_product"),
    )

    op.execute(
        """
        ALTER TABLE shop_product_tax ENABLE ROW LEVEL SECURITY;
        ALTER TABLE shop_product_tax FORCE ROW LEVEL SECURITY;
        CREATE POLICY ims_tenant_isolation ON shop_product_tax
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
    op.execute("DROP POLICY IF EXISTS ims_tenant_isolation ON shop_product_tax;")
    op.execute("ALTER TABLE shop_product_tax NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE shop_product_tax DISABLE ROW LEVEL SECURITY;")
    op.drop_table("shop_product_tax")
    op.drop_column("transactions", "tax_cents")
    op.drop_column("shops", "default_tax_rate_bps")
    op.drop_column("products", "category")
