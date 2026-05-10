"""hierarchical categories table

Revision ID: 20260527000001
Revises: 20260526000001
Create Date: 2026-05-27 00:00:01
"""
from __future__ import annotations

import re
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import UUID

revision = "20260527000001"
down_revision = "20260526000001"
branch_labels = None
depends_on = None


def _slugify(value: str) -> str:
    """Convert an arbitrary string to a URL-safe slug."""
    s = value.lower()
    # Replace non-alphanumeric chars (except hyphens) with hyphens
    s = re.sub(r"[^a-z0-9]+", "-", s)
    # Collapse multiple consecutive hyphens
    s = re.sub(r"-{2,}", "-", s)
    # Strip leading/trailing hyphens
    s = s.strip("-")
    return s


def upgrade() -> None:
    # ----------------------------------------------------------------
    # 1. Create categories table
    # ----------------------------------------------------------------
    op.create_table(
        "categories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_categories_tenant_slug"),
    )
    op.create_index("ix_categories_tenant_id", "categories", ["tenant_id"])
    op.create_index("ix_categories_parent_id", "categories", ["parent_id"])

    # ----------------------------------------------------------------
    # 2. Create product_categories join table
    # ----------------------------------------------------------------
    op.create_table(
        "product_categories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "category_id",
            UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "product_id", "category_id", name="uq_product_categories_product_category"
        ),
    )
    op.create_index(
        "ix_product_categories_product_id", "product_categories", ["product_id"]
    )
    op.create_index(
        "ix_product_categories_category_id", "product_categories", ["category_id"]
    )

    # ----------------------------------------------------------------
    # 3. Migrate legacy Product.category strings → Category rows
    # ----------------------------------------------------------------
    conn = op.get_bind()

    tenant_ids = conn.execute(text("SELECT id FROM tenants")).fetchall()

    for (tenant_id,) in tenant_ids:
        # Fetch distinct non-null, non-empty legacy category values for this tenant
        rows = conn.execute(
            text(
                "SELECT DISTINCT category FROM products "
                "WHERE tenant_id = :tid AND category IS NOT NULL AND category <> ''"
            ),
            {"tid": tenant_id},
        ).fetchall()

        # Track slugs used within this tenant to handle collisions
        used_slugs: set[str] = set()
        # Map original category string → new category UUID
        cat_map: dict[str, uuid.UUID] = {}

        for (raw_name,) in rows:
            slug = _slugify(raw_name)
            if not slug:
                # Fallback: use first 6 chars of a UUID
                slug = "category-" + str(uuid.uuid4()).replace("-", "")[:6]

            # Collision handling: append hex suffix until unique within tenant
            candidate = slug
            if candidate in used_slugs:
                suffix = str(uuid.uuid4()).replace("-", "")[:6]
                candidate = f"{slug}-{suffix}"
            used_slugs.add(candidate)

            cat_id = uuid.uuid4()
            cat_map[raw_name] = cat_id

            conn.execute(
                text(
                    "INSERT INTO categories (id, tenant_id, parent_id, slug, name, "
                    "description, sort_order, created_at, updated_at) "
                    "VALUES (:id, :tenant_id, NULL, :slug, :name, NULL, 0, now(), now())"
                ),
                {
                    "id": str(cat_id),
                    "tenant_id": str(tenant_id),
                    "slug": candidate,
                    "name": raw_name,
                },
            )

        # Insert product_categories rows
        for raw_name, cat_id in cat_map.items():
            product_rows = conn.execute(
                text(
                    "SELECT id, tenant_id FROM products "
                    "WHERE tenant_id = :tid AND category = :cat"
                ),
                {"tid": tenant_id, "cat": raw_name},
            ).fetchall()

            for (prod_id, prod_tenant_id) in product_rows:
                conn.execute(
                    text(
                        "INSERT INTO product_categories "
                        "(id, tenant_id, product_id, category_id, created_at) "
                        "VALUES (:id, :tenant_id, :product_id, :category_id, now())"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "tenant_id": str(prod_tenant_id),
                        "product_id": str(prod_id),
                        "category_id": str(cat_id),
                    },
                )

    # ----------------------------------------------------------------
    # 4. Drop legacy category column from products
    # ----------------------------------------------------------------
    op.drop_column("products", "category")


def downgrade() -> None:
    # Restore the legacy column (data is NOT recovered)
    op.add_column(
        "products",
        sa.Column("category", sa.String(128), nullable=True),
    )
    op.drop_index("ix_product_categories_category_id", "product_categories")
    op.drop_index("ix_product_categories_product_id", "product_categories")
    op.drop_table("product_categories")
    op.drop_index("ix_categories_parent_id", "categories")
    op.drop_index("ix_categories_tenant_id", "categories")
    op.drop_table("categories")
