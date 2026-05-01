"""CRM: RLS policies on customer_groups + customers, index on transactions.customer_id

Revision ID: 20260501000002
Revises: 20260501000001
Create Date: 2026-05-01 00:00:02.000000
"""
from __future__ import annotations

from alembic import op

revision = "20260501000002"
down_revision = "20260501000001"
branch_labels = None
depends_on = None

_RLS_POLICY = """
COALESCE(current_setting('ims.is_admin', true), '') = 'true'
OR (
  NULLIF(TRIM(COALESCE(current_setting('ims.tenant_id', true), '')), '') IS NOT NULL
  AND tenant_id = (NULLIF(TRIM(COALESCE(current_setting('ims.tenant_id', true), '')), ''))::uuid
)
"""


def upgrade() -> None:
    # RLS for customer_groups
    op.execute(f"""
        ALTER TABLE customer_groups ENABLE ROW LEVEL SECURITY;
        ALTER TABLE customer_groups FORCE ROW LEVEL SECURITY;
        CREATE POLICY ims_tenant_isolation ON customer_groups
        USING ({_RLS_POLICY})
        WITH CHECK ({_RLS_POLICY});
    """)

    # RLS for customers
    op.execute(f"""
        ALTER TABLE customers ENABLE ROW LEVEL SECURITY;
        ALTER TABLE customers FORCE ROW LEVEL SECURITY;
        CREATE POLICY ims_tenant_isolation ON customers
        USING ({_RLS_POLICY})
        WITH CHECK ({_RLS_POLICY});
    """)

    # Performance index for customer profile transaction lookups
    op.create_index("ix_transactions_customer_id", "transactions", ["customer_id"])


def downgrade() -> None:
    op.drop_index("ix_transactions_customer_id", table_name="transactions")

    op.execute("DROP POLICY IF EXISTS ims_tenant_isolation ON customers;")
    op.execute("ALTER TABLE customers NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE customers DISABLE ROW LEVEL SECURITY;")

    op.execute("DROP POLICY IF EXISTS ims_tenant_isolation ON customer_groups;")
    op.execute("ALTER TABLE customer_groups NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE customer_groups DISABLE ROW LEVEL SECURITY;")
