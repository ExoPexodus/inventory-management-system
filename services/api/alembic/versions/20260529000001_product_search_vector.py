"""product full-text search vector column, triggers, and GIN index

Revision ID: 20260529000001
Revises: 20260528000001
Create Date: 2026-05-29 00:00:01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260529000001"
down_revision = "20260528000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add search_vector column
    op.add_column(
        "products",
        sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True),
    )

    # 2. Create the core helper function that builds and updates the vector
    op.execute("""
        CREATE OR REPLACE FUNCTION products_refresh_search_vector(prod_id UUID)
        RETURNS void AS $$
        BEGIN
          UPDATE products SET search_vector =
            setweight(to_tsvector('simple', coalesce(name, '')), 'A') ||
            setweight(to_tsvector('simple', coalesce(sku, '')), 'B') ||
            setweight(to_tsvector('simple', coalesce(
              (SELECT string_agg(c.name, ' ')
               FROM product_categories pc JOIN categories c ON c.id = pc.category_id
               WHERE pc.product_id = prod_id),
              ''
            )), 'C') ||
            setweight(to_tsvector('simple', coalesce(
              (SELECT string_agg(val, ' ')
               FROM jsonb_array_elements_text(CASE jsonb_typeof(tags) WHEN 'array' THEN tags ELSE '[]'::jsonb END) AS val),
              ''
            )), 'C') ||
            setweight(to_tsvector('simple', coalesce(short_description, '') || ' ' || coalesce(description, '')), 'D')
          WHERE id = prod_id;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # 3a. Trigger wrapper function for products INSERT/UPDATE
    op.execute("""
        CREATE OR REPLACE FUNCTION trigger_products_refresh_search_vector()
        RETURNS TRIGGER AS $$
        BEGIN
          PERFORM products_refresh_search_vector(NEW.id);
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # 3b. Products trigger — fires AFTER INSERT OR UPDATE of relevant columns only
    #     (UPDATE OF search_vector is excluded so the helper's own UPDATE won't recurse)
    op.execute("""
        CREATE TRIGGER tg_products_search_vector
        AFTER INSERT OR UPDATE OF name, sku, description, short_description, tags ON products
        FOR EACH ROW EXECUTE FUNCTION trigger_products_refresh_search_vector();
    """)

    # 3c. Trigger wrapper function for product_categories INSERT/UPDATE/DELETE
    op.execute("""
        CREATE OR REPLACE FUNCTION trigger_product_categories_refresh_search_vector()
        RETURNS TRIGGER AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            PERFORM products_refresh_search_vector(OLD.product_id);
            RETURN OLD;
          ELSE
            PERFORM products_refresh_search_vector(NEW.product_id);
            RETURN NEW;
          END IF;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # 3d. product_categories trigger
    op.execute("""
        CREATE TRIGGER tg_product_categories_search_vector
        AFTER INSERT OR UPDATE OR DELETE ON product_categories
        FOR EACH ROW EXECUTE FUNCTION trigger_product_categories_refresh_search_vector();
    """)

    # 4. Backfill all existing rows
    op.execute("SELECT products_refresh_search_vector(id) FROM products;")

    # 5. Create GIN index for fast FTS queries
    op.create_index(
        "ix_products_search_vector",
        "products",
        ["search_vector"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    # Drop triggers first, then functions, then index, then column

    op.execute("DROP TRIGGER IF EXISTS tg_product_categories_search_vector ON product_categories;")
    op.execute("DROP TRIGGER IF EXISTS tg_products_search_vector ON products;")

    op.execute("DROP FUNCTION IF EXISTS trigger_product_categories_refresh_search_vector();")
    op.execute("DROP FUNCTION IF EXISTS trigger_products_refresh_search_vector();")
    op.execute("DROP FUNCTION IF EXISTS products_refresh_search_vector(UUID);")

    op.drop_index("ix_products_search_vector", table_name="products")
    op.drop_column("products", "search_vector")
