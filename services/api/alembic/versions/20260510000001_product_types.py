"""Product type expansion + catalog enrichment + product_images table

Revision ID: 20260510000001
Revises: 20260509000001
Create Date: 2026-05-10 00:00:01.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

revision = "20260510000001"
down_revision = "20260509000001"
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
    # 1. New columns on products
    op.add_column("products", sa.Column(
        "product_type", sa.String(32), nullable=False, server_default="physical"
    ))
    op.add_column("products", sa.Column("subtitle", sa.String(512), nullable=True))
    op.add_column("products", sa.Column("ribbon", sa.String(64), nullable=True))
    op.add_column("products", sa.Column("discount_price_cents", sa.Integer, nullable=True))
    op.add_column("products", sa.Column("short_description", sa.Text(), nullable=True))
    op.add_column("products", sa.Column(
        "track_quantity", sa.Boolean, nullable=False, server_default=sa.text("true")
    ))
    op.add_column("products", sa.Column("tags", JSONB, nullable=True))
    op.add_column("products", sa.Column("additional_info_sections", JSONB, nullable=True))
    op.add_column("products", sa.Column("weight_grams", sa.Integer, nullable=True))
    op.add_column("products", sa.Column("shipping_class", sa.String(64), nullable=True))
    op.add_column("products", sa.Column("digital_files", JSONB, nullable=True))
    op.add_column("products", sa.Column("gift_card_amounts_cents", JSONB, nullable=True))
    op.add_column("products", sa.Column("gift_card_expiry_months", sa.Integer, nullable=True))
    op.add_column("products", sa.Column("slug", sa.String(512), nullable=True))
    op.add_column("products", sa.Column("meta_title", sa.String(255), nullable=True))
    op.add_column("products", sa.Column("meta_description", sa.Text(), nullable=True))
    op.add_column("products", sa.Column("og_image_url", sa.String(1024), nullable=True))

    op.create_index("ix_products_product_type", "products", ["tenant_id", "product_type"])
    op.create_index(
        "ix_products_slug", "products", ["tenant_id", "slug"],
        unique=True,
        postgresql_where=sa.text("slug IS NOT NULL"),
    )
    op.create_index(
        "ix_products_tags",
        "products",
        ["tags"],
        postgresql_using="gin",
        postgresql_where=sa.text("tags IS NOT NULL"),
    )

    # 2. product_images table
    op.create_table(
        "product_images",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.String(1024), nullable=False),
        sa.Column("alt_text", sa.String(255), nullable=True),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_product_images_product_id", "product_images", ["product_id"])

    # 3. RLS on product_images
    op.execute(f"""
        ALTER TABLE product_images ENABLE ROW LEVEL SECURITY;
        ALTER TABLE product_images FORCE ROW LEVEL SECURITY;
        CREATE POLICY ims_tenant_isolation ON product_images
        USING ({_RLS_POLICY})
        WITH CHECK ({_RLS_POLICY});
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS ims_tenant_isolation ON product_images;")
    op.execute("ALTER TABLE product_images NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE product_images DISABLE ROW LEVEL SECURITY;")

    op.drop_index("ix_product_images_product_id", table_name="product_images")
    op.drop_table("product_images")

    op.drop_index("ix_products_tags", table_name="products")
    op.drop_index("ix_products_slug", table_name="products")
    op.drop_index("ix_products_product_type", table_name="products")

    for col in [
        "og_image_url", "meta_description", "meta_title", "slug",
        "gift_card_expiry_months", "gift_card_amounts_cents", "digital_files",
        "shipping_class", "weight_grams", "additional_info_sections", "tags",
        "track_quantity", "short_description", "discount_price_cents",
        "ribbon", "subtitle", "product_type",
    ]:
        op.drop_column("products", col)
