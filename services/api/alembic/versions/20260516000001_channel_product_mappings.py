"""Channel product mappings: bridge IMS products to external channel IDs

Revision ID: 20260516000001
Revises: 20260515000001
Create Date: 2026-05-16 00:00:01.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "20260516000001"
down_revision = "20260515000001"
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
    op.create_table(
        "channel_product_mappings",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_product_id", sa.String(255), nullable=False),
        sa.Column("external_variant_id", sa.String(255), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("channel_id", "product_id", name="uq_channel_product_mapping"),
    )
    op.create_index("ix_channel_product_mappings_channel_id",
                    "channel_product_mappings", ["channel_id"])
    op.create_index("ix_channel_product_mappings_product_id",
                    "channel_product_mappings", ["product_id"])
    op.create_index("ix_channel_product_mappings_tenant_id",
                    "channel_product_mappings", ["tenant_id"])

    op.execute(f"""
        ALTER TABLE channel_product_mappings ENABLE ROW LEVEL SECURITY;
        ALTER TABLE channel_product_mappings FORCE ROW LEVEL SECURITY;
        CREATE POLICY ims_tenant_isolation ON channel_product_mappings
        USING ({_RLS_POLICY})
        WITH CHECK ({_RLS_POLICY});
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS ims_tenant_isolation ON channel_product_mappings;")
    op.execute("ALTER TABLE channel_product_mappings NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE channel_product_mappings DISABLE ROW LEVEL SECURITY;")
    op.drop_index("ix_channel_product_mappings_tenant_id",
                  table_name="channel_product_mappings")
    op.drop_index("ix_channel_product_mappings_product_id",
                  table_name="channel_product_mappings")
    op.drop_index("ix_channel_product_mappings_channel_id",
                  table_name="channel_product_mappings")
    op.drop_table("channel_product_mappings")
