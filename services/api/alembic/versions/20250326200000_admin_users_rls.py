"""admin_users + row-level security

Revision ID: 20250326200000
Revises: 20250324120000
Create Date: 2025-03-26

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20250326200000"
down_revision: Union[str, None] = "20250324120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "admin_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=128), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_admin_users_email"),
    )

    op.execute(
        """
        ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
        ALTER TABLE tenants FORCE ROW LEVEL SECURITY;
        CREATE POLICY ims_tenant_isolation ON tenants
        USING (
          COALESCE(current_setting('ims.is_admin', true), '') = 'true'
          OR (
            NULLIF(TRIM(COALESCE(current_setting('ims.tenant_id', true), '')), '') IS NOT NULL
            AND id = (NULLIF(TRIM(COALESCE(current_setting('ims.tenant_id', true), '')), ''))::uuid
          )
        )
        WITH CHECK (
          COALESCE(current_setting('ims.is_admin', true), '') = 'true'
          OR (
            NULLIF(TRIM(COALESCE(current_setting('ims.tenant_id', true), '')), '') IS NOT NULL
            AND id = (NULLIF(TRIM(COALESCE(current_setting('ims.tenant_id', true), '')), ''))::uuid
          )
        );
        """
    )

    for table in ("shops", "products", "transactions", "stock_movements"):
        op.execute(
            f"""
            ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
            ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
            CREATE POLICY ims_tenant_isolation ON {table}
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

    op.execute(
        """
        ALTER TABLE transaction_lines ENABLE ROW LEVEL SECURITY;
        ALTER TABLE transaction_lines FORCE ROW LEVEL SECURITY;
        CREATE POLICY ims_tenant_isolation ON transaction_lines
        USING (
          COALESCE(current_setting('ims.is_admin', true), '') = 'true'
          OR EXISTS (
            SELECT 1 FROM transactions t
            WHERE t.id = transaction_lines.transaction_id
            AND NULLIF(TRIM(COALESCE(current_setting('ims.tenant_id', true), '')), '') IS NOT NULL
            AND t.tenant_id = (NULLIF(TRIM(COALESCE(current_setting('ims.tenant_id', true), '')), ''))::uuid
          )
        )
        WITH CHECK (
          COALESCE(current_setting('ims.is_admin', true), '') = 'true'
          OR EXISTS (
            SELECT 1 FROM transactions t
            WHERE t.id = transaction_lines.transaction_id
            AND NULLIF(TRIM(COALESCE(current_setting('ims.tenant_id', true), '')), '') IS NOT NULL
            AND t.tenant_id = (NULLIF(TRIM(COALESCE(current_setting('ims.tenant_id', true), '')), ''))::uuid
          )
        );
        """
    )

    op.execute(
        """
        ALTER TABLE payment_allocations ENABLE ROW LEVEL SECURITY;
        ALTER TABLE payment_allocations FORCE ROW LEVEL SECURITY;
        CREATE POLICY ims_tenant_isolation ON payment_allocations
        USING (
          COALESCE(current_setting('ims.is_admin', true), '') = 'true'
          OR EXISTS (
            SELECT 1 FROM transactions t
            WHERE t.id = payment_allocations.transaction_id
            AND NULLIF(TRIM(COALESCE(current_setting('ims.tenant_id', true), '')), '') IS NOT NULL
            AND t.tenant_id = (NULLIF(TRIM(COALESCE(current_setting('ims.tenant_id', true), '')), ''))::uuid
          )
        )
        WITH CHECK (
          COALESCE(current_setting('ims.is_admin', true), '') = 'true'
          OR EXISTS (
            SELECT 1 FROM transactions t
            WHERE t.id = payment_allocations.transaction_id
            AND NULLIF(TRIM(COALESCE(current_setting('ims.tenant_id', true), '')), '') IS NOT NULL
            AND t.tenant_id = (NULLIF(TRIM(COALESCE(current_setting('ims.tenant_id', true), '')), ''))::uuid
          )
        );
        """
    )


def downgrade() -> None:
    for table in (
        "payment_allocations",
        "transaction_lines",
        "stock_movements",
        "transactions",
        "products",
        "shops",
        "tenants",
    ):
        op.execute(f"DROP POLICY IF EXISTS ims_tenant_isolation ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.drop_table("admin_users")
