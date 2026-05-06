# Product Type Expansion + Catalog Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add five product types (physical, digital, service, donation, gift_card), a product images gallery table, and catalog enrichment fields (subtitle, ribbon, discount price, SEO, tags, type-specific fields) so merchants can create digital downloads, gift cards, and services — not just physical inventory.

**Architecture:** All new product fields are added as nullable/default columns on the existing `products` table so the schema stays unified — no type-table splitting. A separate `product_images` table holds an ordered gallery per product. Existing product endpoints in `admin_web.py` are extended in-place (new optional fields are backwards-compatible). A new `product_type_service.py` module provides pure-function helpers (`is_shippable`, `is_inventory_tracked`, etc.) so routing/fulfillment logic elsewhere doesn't need to inspect product_type directly. Image gallery management lives in `admin_catalog.py` (currently a placeholder).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, PostgreSQL (with RLS), pytest

**Out of scope (deferred):**
- Formal options/variants model (`product_options`, `option_values`, `product_variants` tables). The `variant_label` text field stays for now; formal variants ship when the admin web UI needs them.
- File upload to S3/R2 for digital products. `digital_files` is a JSONB field of `{name, url, size_bytes, type}` objects; merchant provides hosted URLs. CDN upload ships in Phase 2.
- Gift card redemption codes / balance tracking. That's a separate Domain 8 sub-project.
- License key pool for digital products. Deferred.

---

### Task 1: Migration + model columns + ProductImage model + contract test

**Files:**
- Create: `services/api/alembic/versions/20260510000001_product_types.py`
- Modify: `services/api/app/models/tables.py`
- Modify: `services/api/app/models/__init__.py`
- Modify: `services/api/tests/test_admin_console_contracts.py`

- [ ] **Step 1: Write the failing contract test**

Add to `services/api/tests/test_admin_console_contracts.py`:

```python
def test_product_detail_out_schema() -> None:
    from app.routers.admin_catalog import ProductDetailOut

    p = ProductDetailOut(
        id=uuid4(),
        tenant_id=uuid4(),
        sku="WIDGET-01",
        name="Widget",
        product_type="physical",
        status="active",
        unit_price_cents=1999,
        discount_price_cents=None,
        subtitle=None,
        ribbon=None,
        short_description=None,
        description=None,
        tags=[],
        track_quantity=True,
        weight_grams=None,
        shipping_class=None,
        digital_files=None,
        gift_card_amounts_cents=None,
        gift_card_expiry_months=None,
        additional_info_sections=[],
        slug=None,
        meta_title=None,
        meta_description=None,
        og_image_url=None,
        image_url=None,
        images=[],
        category=None,
        product_group_id=None,
        cost_price_cents=None,
        mrp_cents=None,
        barcode=None,
        hsn_code=None,
        negative_inventory_allowed=False,
        reorder_point=0,
        created_at=datetime.now(UTC),
    )
    d = p.model_dump(mode="json")
    assert d["product_type"] == "physical"
    assert d["track_quantity"] is True
    assert d["tags"] == []
```

The imports `from datetime import UTC, datetime` and `from uuid import uuid4` are already at the top.

- [ ] **Step 2: Confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/test_admin_console_contracts.py $CONTAINER:/app/tests/test_admin_console_contracts.py
docker compose exec api python -m pytest tests/test_admin_console_contracts.py::test_product_detail_out_schema -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.routers.admin_catalog'` (currently `admin_catalog.py` is just a stub). Stays red until Task 4.

- [ ] **Step 3: Add columns to the Product model**

In `services/api/app/models/tables.py`, find the `Product` class and add new columns after the existing `active` column:

```python
    # --- product type and enrichment fields (Phase 0 expansion) ---
    product_type: Mapped[str] = mapped_column(
        String(32), default="physical", server_default="physical", nullable=False
    )
    # product_type: 'physical' | 'digital' | 'service' | 'donation' | 'gift_card'
    subtitle: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    ribbon: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    discount_price_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    short_description: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    track_quantity: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    tags: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    additional_info_sections: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # Physical-specific
    weight_grams: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    shipping_class: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # shipping_class: 'standard' | 'fragile' | 'oversized' | 'digital_no_shipping'
    # Digital-specific
    digital_files: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # list of {name: str, url: str, size_bytes: int | None, file_type: str | None}
    # Gift card-specific
    gift_card_amounts_cents: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # list of int (predefined amounts in cents, e.g. [2500, 5000, 10000])
    gift_card_expiry_months: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # null = never expires
    # SEO fields
    slug: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    meta_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    meta_description: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    og_image_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
```

Also add a relationship to the new `ProductImage` model (defined in the next step):

```python
    images: Mapped[list["ProductImage"]] = relationship(
        back_populates="product",
        order_by="ProductImage.sort_order",
        cascade="all, delete-orphan",
    )
```

- [ ] **Step 4: Add the ProductImage model**

In `services/api/app/models/tables.py`, add after the `Product` class (before `Device`):

```python
class ProductImage(Base):
    """Ordered gallery image for a product. Multiple images per product, ordered by sort_order."""
    __tablename__ = "product_images"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    alt_text: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    product: Mapped["Product"] = relationship(back_populates="images")
```

- [ ] **Step 5: Export ProductImage**

In `services/api/app/models/__init__.py`, add `ProductImage` to BOTH the import block and `__all__` (alphabetical — between `Product` and `ProductGroup`).

- [ ] **Step 6: Write the migration**

Create `services/api/alembic/versions/20260510000001_product_types.py`:

```python
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
    # 1. New columns on products — all nullable or have server defaults so
    #    existing rows are unaffected.
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
```

- [ ] **Step 7: Run migration**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/alembic/versions/20260510000001_product_types.py $CONTAINER:/app/alembic/versions/
docker compose exec api alembic upgrade head
```
Expected: `Running upgrade 20260509000001 -> 20260510000001`

- [ ] **Step 8: Verify schema**

```bash
docker compose exec postgres psql -U ims -d ims -c "\d products" | grep -E "product_type|subtitle|ribbon|track_quantity|tags|slug"
docker compose exec postgres psql -U ims -d ims -c "\d product_images"
docker compose exec postgres psql -U ims -d ims -c "SELECT relrowsecurity FROM pg_class WHERE relname='product_images'"
```
Expected: columns visible, product_images table present, `relrowsecurity = t`.

- [ ] **Step 9: Commit**

```bash
git add services/api/alembic/versions/20260510000001_product_types.py \
        services/api/app/models/tables.py \
        services/api/app/models/__init__.py \
        services/api/tests/test_admin_console_contracts.py
git commit -m "feat(catalog): add product_type + enrichment columns + product_images table"
```

---

### Task 2: Product type service helpers

**Files:**
- Create: `services/api/app/services/product_type_service.py`
- Create: `services/api/tests/services/test_product_type_service.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/services/test_product_type_service.py`:

```python
import pytest

VALID_TYPES = ["physical", "digital", "service", "donation", "gift_card"]


def test_is_shippable_true_for_physical() -> None:
    from app.services.product_type_service import is_shippable
    assert is_shippable("physical") is True


def test_is_shippable_false_for_non_physical_types() -> None:
    from app.services.product_type_service import is_shippable
    for t in ["digital", "service", "donation", "gift_card"]:
        assert is_shippable(t) is False, f"Expected {t} to not be shippable"


def test_is_inventory_tracked_depends_on_track_quantity_flag() -> None:
    from app.services.product_type_service import is_inventory_tracked
    # Physical with track_quantity=True (the default) → tracked
    assert is_inventory_tracked("physical", track_quantity=True) is True
    # Physical with track_quantity=False (made-to-order) → not tracked
    assert is_inventory_tracked("physical", track_quantity=False) is False


def test_is_inventory_tracked_false_for_service_donation_gift_card() -> None:
    from app.services.product_type_service import is_inventory_tracked
    for t in ["service", "donation", "gift_card"]:
        # These types are never inventory-tracked regardless of track_quantity flag
        assert is_inventory_tracked(t, track_quantity=True) is False, f"Expected {t} not tracked"


def test_is_inventory_tracked_digital_respects_flag() -> None:
    """Digital products can optionally track license-key inventory."""
    from app.services.product_type_service import is_inventory_tracked
    assert is_inventory_tracked("digital", track_quantity=True) is True
    assert is_inventory_tracked("digital", track_quantity=False) is False


def test_is_variable_amount_true_only_for_donation() -> None:
    from app.services.product_type_service import is_variable_amount
    assert is_variable_amount("donation") is True
    for t in ["physical", "digital", "service", "gift_card"]:
        assert is_variable_amount(t) is False


def test_is_tax_exempt_by_default_true_only_for_donation() -> None:
    from app.services.product_type_service import is_tax_exempt_by_default
    assert is_tax_exempt_by_default("donation") is True
    for t in ["physical", "digital", "service", "gift_card"]:
        assert is_tax_exempt_by_default(t) is False


def test_all_valid_types_handled_by_all_functions() -> None:
    """Ensures none of the helpers raise on any valid product type."""
    from app.services.product_type_service import (
        is_inventory_tracked, is_shippable, is_tax_exempt_by_default, is_variable_amount,
    )
    for t in VALID_TYPES:
        is_shippable(t)
        is_inventory_tracked(t, track_quantity=True)
        is_variable_amount(t)
        is_tax_exempt_by_default(t)
```

- [ ] **Step 2: Confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/services $CONTAINER:/app/tests/services
docker compose exec api python -m pytest tests/services/test_product_type_service.py -v
docker compose exec api rm -rf /app/tests/services
```
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the service**

Create `services/api/app/services/product_type_service.py`:

```python
"""Pure-function helpers that answer product-type-specific behavior questions.

These helpers centralise "what does it mean to be a digital product?" so that
routing and fulfillment logic elsewhere can call one function instead of
comparing type strings directly.
"""
from __future__ import annotations

_SHIPPABLE_TYPES: frozenset[str] = frozenset({"physical"})

_NEVER_TRACKED_TYPES: frozenset[str] = frozenset({"service", "donation", "gift_card"})

_VARIABLE_AMOUNT_TYPES: frozenset[str] = frozenset({"donation"})

_TAX_EXEMPT_BY_DEFAULT_TYPES: frozenset[str] = frozenset({"donation"})


def is_shippable(product_type: str) -> bool:
    """Return True if the type normally requires a shipping address / carrier."""
    return product_type in _SHIPPABLE_TYPES


def is_inventory_tracked(product_type: str, *, track_quantity: bool) -> bool:
    """Return True if the product actively deducts from stock on sale.

    Types in ``_NEVER_TRACKED_TYPES`` are always untracked (unlimited).
    For physical and digital, the ``track_quantity`` flag on the product
    controls whether stock is decremented.
    """
    if product_type in _NEVER_TRACKED_TYPES:
        return False
    return track_quantity


def is_variable_amount(product_type: str) -> bool:
    """Return True if the shopper sets the price (e.g. open-amount donation)."""
    return product_type in _VARIABLE_AMOUNT_TYPES


def is_tax_exempt_by_default(product_type: str) -> bool:
    """Return True if the type is typically tax-exempt without explicit configuration."""
    return product_type in _TAX_EXEMPT_BY_DEFAULT_TYPES
```

- [ ] **Step 4: Run tests**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/services/product_type_service.py $CONTAINER:/app/app/services/product_type_service.py
docker cp services/api/tests/services $CONTAINER:/app/tests/services
docker compose exec api python -m pytest tests/services/test_product_type_service.py -v
docker compose exec api rm -rf /app/tests/services
```
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/services/product_type_service.py \
        services/api/tests/services/test_product_type_service.py
git commit -m "feat(catalog): add product_type_service with is_shippable/is_inventory_tracked helpers"
```

---

### Task 3: Extend product API in admin_web.py

**Files:**
- Modify: `services/api/app/routers/admin_web.py`
- Create: `services/api/tests/routers/test_admin_product_types.py`

This task extends the existing product create/list/patch endpoints to accept and return all new enrichment fields. The changes are additive — all new fields are optional, so existing callers continue working unchanged.

- [ ] **Step 1: Read the existing schemas and patch endpoint before modifying**

```bash
grep -n "class.*Product\|class.*Patch\|class.*Create\|def admin" services/api/app/routers/admin_web.py | grep -i product
```

Read the existing `CreateProductBody`, `CreateProductResponse`, `ProductListItem`, and `PatchProductBody` classes in `admin_web.py` so you know exactly where to insert new fields. The classes start around line 1168.

Also read the `admin_create_product` function (~line 1271) and the patch endpoint to understand the Product constructor calls.

- [ ] **Step 2: Write the failing test**

Create `services/api/tests/routers/test_admin_product_types.py`:

```python
# NOTE: `from __future__ import annotations` deliberately absent.

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Product, Tenant


@pytest.fixture()
def auth_headers(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        role="owner",
        role_id=None,
        is_legacy_token=False,
        permissions=frozenset({"catalog:read", "catalog:write"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield {}
    app.dependency_overrides.clear()


def test_create_physical_product_with_enrichment(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/products", json={
        "sku": "WIDGET-001",
        "name": "Widget",
        "unit_price_cents": 1999,
        "product_type": "physical",
        "subtitle": "The best widget",
        "ribbon": "NEW",
        "discount_price_cents": 1499,
        "track_quantity": True,
        "tags": ["bestseller", "widget"],
        "weight_grams": 250,
        "shipping_class": "standard",
    }, headers=auth_headers)
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    assert body["product_type"] == "physical"
    assert body["subtitle"] == "The best widget"
    assert body["ribbon"] == "NEW"
    assert body["discount_price_cents"] == 1499
    assert body["tags"] == ["bestseller", "widget"]
    assert body["weight_grams"] == 250


def test_create_digital_product(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/products", json={
        "sku": "EBOOK-001",
        "name": "My eBook",
        "unit_price_cents": 999,
        "product_type": "digital",
        "track_quantity": False,
        "digital_files": [
            {"name": "ebook.pdf", "url": "https://cdn.example.com/ebook.pdf", "file_type": "pdf"},
        ],
    }, headers=auth_headers)
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    assert body["product_type"] == "digital"
    assert body["track_quantity"] is False
    assert len(body["digital_files"]) == 1


def test_create_donation_product(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/products", json={
        "sku": "DONATE-001",
        "name": "Plant a Tree",
        "unit_price_cents": 0,  # variable amount
        "product_type": "donation",
        "track_quantity": False,
    }, headers=auth_headers)
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    assert body["product_type"] == "donation"


def test_create_gift_card(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/products", json={
        "sku": "GC-001",
        "name": "Gift Card",
        "unit_price_cents": 0,
        "product_type": "gift_card",
        "gift_card_amounts_cents": [2500, 5000, 10000],
        "gift_card_expiry_months": 12,
        "track_quantity": False,
    }, headers=auth_headers)
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    assert body["product_type"] == "gift_card"
    assert body["gift_card_amounts_cents"] == [2500, 5000, 10000]
    assert body["gift_card_expiry_months"] == 12


def test_list_products_includes_product_type(db, tenant: Tenant, auth_headers) -> None:
    """List response includes product_type for each product."""
    client = TestClient(app)
    # Create two products with different types
    client.post("/v1/admin/products", json={
        "sku": "PHYS-01", "name": "Physical", "unit_price_cents": 100, "product_type": "physical",
    }, headers=auth_headers)
    client.post("/v1/admin/products", json={
        "sku": "DIG-01", "name": "Digital", "unit_price_cents": 50, "product_type": "digital",
        "track_quantity": False,
    }, headers=auth_headers)

    resp = client.get("/v1/admin/products", headers=auth_headers)
    assert resp.status_code == 200
    types = {p["product_type"] for p in resp.json()}
    assert "physical" in types
    assert "digital" in types


def test_default_product_type_is_physical(db, tenant: Tenant, auth_headers) -> None:
    """Omitting product_type in the request defaults to 'physical' (backwards compat)."""
    client = TestClient(app)
    resp = client.post("/v1/admin/products", json={
        "sku": "LEGACY-01", "name": "Legacy Product", "unit_price_cents": 100,
    }, headers=auth_headers)
    assert resp.status_code in (200, 201)
    assert resp.json()["product_type"] == "physical"


def test_patch_adds_seo_fields(db, tenant: Tenant, auth_headers) -> None:
    """PATCH can update SEO fields on an existing product."""
    client = TestClient(app)
    create = client.post("/v1/admin/products", json={
        "sku": "SEO-01", "name": "SEO Product", "unit_price_cents": 100,
    }, headers=auth_headers)
    product_id = create.json()["id"]

    resp = client.patch(f"/v1/admin/products/{product_id}", json={
        "slug": "seo-product",
        "meta_title": "Best SEO Product",
        "meta_description": "This is the best SEO product in the world.",
    }, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == "seo-product"
    assert body["meta_title"] == "Best SEO Product"
```

- [ ] **Step 3: Confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/routers/test_admin_product_types.py $CONTAINER:/app/tests/routers/test_admin_product_types.py
docker compose exec api python -m pytest tests/routers/test_admin_product_types.py -v
docker compose exec api rm -f /app/tests/routers/test_admin_product_types.py
```
Expected: Most or all tests fail — the API doesn't yet return/accept `product_type` and other new fields.

- [ ] **Step 4: Extend the product schemas in admin_web.py**

In `services/api/app/routers/admin_web.py`, make the following changes:

**Add to `CreateProductBody`** (all optional with defaults for backwards compat):

```python
class CreateProductBody(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    unit_price_cents: int = Field(ge=0)
    category: str | None = Field(default=None, max_length=128)
    product_group_id: UUID | None = None
    variant_label: str | None = Field(default=None, max_length=128)
    barcode: str | None = Field(default=None, max_length=128)
    cost_price_cents: int | None = Field(default=None, ge=0)
    mrp_cents: int | None = Field(default=None, ge=0)
    hsn_code: str | None = Field(default=None, max_length=32)
    negative_inventory_allowed: bool = False
    # --- new enrichment fields (all optional, backwards compatible) ---
    product_type: str = "physical"
    subtitle: str | None = None
    ribbon: str | None = None
    discount_price_cents: int | None = Field(default=None, ge=0)
    short_description: str | None = None
    track_quantity: bool = True
    tags: list[str] | None = None
    additional_info_sections: list[dict] | None = None
    weight_grams: int | None = Field(default=None, ge=0)
    shipping_class: str | None = None
    digital_files: list[dict] | None = None
    gift_card_amounts_cents: list[int] | None = None
    gift_card_expiry_months: int | None = Field(default=None, ge=1)
    slug: str | None = None
    meta_title: str | None = None
    meta_description: str | None = None
    og_image_url: str | None = None
```

**Add to `CreateProductResponse`** (all optional with defaults):

```python
class CreateProductResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    sku: str
    name: str
    unit_price_cents: int
    category: str | None
    product_group_id: UUID | None = None
    group_title: str | None = None
    variant_label: str | None = None
    reorder_point: int = 0
    barcode: str | None = None
    cost_price_cents: int | None = None
    mrp_cents: int | None = None
    hsn_code: str | None = None
    negative_inventory_allowed: bool = False
    # --- new fields ---
    product_type: str = "physical"
    subtitle: str | None = None
    ribbon: str | None = None
    discount_price_cents: int | None = None
    short_description: str | None = None
    track_quantity: bool = True
    tags: list[str] | None = None
    additional_info_sections: list[dict] | None = None
    weight_grams: int | None = None
    shipping_class: str | None = None
    digital_files: list[dict] | None = None
    gift_card_amounts_cents: list[int] | None = None
    gift_card_expiry_months: int | None = None
    slug: str | None = None
    meta_title: str | None = None
    meta_description: str | None = None
    og_image_url: str | None = None
```

**Add to `ProductListItem`**:

```python
class ProductListItem(BaseModel):
    id: UUID
    sku: str
    name: str
    status: str
    category: str | None
    unit_price_cents: int
    reorder_point: int
    variant_label: str | None = None
    group_title: str | None = None
    barcode: str | None = None
    cost_price_cents: int | None = None
    mrp_cents: int | None = None
    hsn_code: str | None = None
    negative_inventory_allowed: bool = False
    # --- new fields ---
    product_type: str = "physical"
    subtitle: str | None = None
    ribbon: str | None = None
    discount_price_cents: int | None = None
    track_quantity: bool = True
    tags: list[str] | None = None
    slug: str | None = None
```

**Add to `PatchProductBody`**: read it first (~line 1393), then add the same optional fields from `CreateProductBody`.

**Update `admin_create_product`**: Add all new fields to the `Product(...)` constructor call, e.g.:

```python
    prod = Product(
        tenant_id=tenant_id,
        product_group_id=group.id if group else None,
        sku=body.sku.strip(),
        name=body.name.strip(),
        unit_price_cents=body.unit_price_cents,
        category=body.category.strip() if body.category else None,
        variant_label=body.variant_label.strip() if body.variant_label else None,
        barcode=body.barcode.strip() if body.barcode else None,
        cost_price_cents=body.cost_price_cents,
        mrp_cents=body.mrp_cents,
        hsn_code=body.hsn_code.strip() if body.hsn_code else None,
        negative_inventory_allowed=body.negative_inventory_allowed,
        # new fields
        product_type=body.product_type,
        subtitle=body.subtitle,
        ribbon=body.ribbon,
        discount_price_cents=body.discount_price_cents,
        short_description=body.short_description,
        track_quantity=body.track_quantity,
        tags=body.tags,
        additional_info_sections=body.additional_info_sections,
        weight_grams=body.weight_grams,
        shipping_class=body.shipping_class,
        digital_files=body.digital_files,
        gift_card_amounts_cents=body.gift_card_amounts_cents,
        gift_card_expiry_months=body.gift_card_expiry_months,
        slug=body.slug,
        meta_title=body.meta_title,
        meta_description=body.meta_description,
        og_image_url=body.og_image_url,
    )
```

**Update `CreateProductResponse` constructor calls** (in `admin_create_product` and patch endpoint) to include the new fields from the product row. Since all fields have defaults in the schema, simply add `product_type=prod.product_type, subtitle=prod.subtitle, ...` etc. to the constructor call. If the existing code uses `from_orm`/`model_validate`, it will pick up the new fields automatically; if it builds the response manually, add each field.

**Update `admin_list_products`** to include the new fields in the `ProductListItem(...)` constructor call.

**Update the patch endpoint** to accept and apply the new fields.

- [ ] **Step 5: Run tests**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/routers/admin_web.py $CONTAINER:/app/app/routers/admin_web.py
docker cp services/api/tests $CONTAINER:/app/tests
docker compose restart api
sleep 5
docker compose exec api python -m pytest tests/routers/test_admin_product_types.py -v
docker compose exec api rm -rf /app/tests
```
Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/routers/admin_web.py \
        services/api/tests/routers/test_admin_product_types.py
git commit -m "feat(catalog): extend product API with type, enrichment, SEO, and type-specific fields"
```

---

### Task 4: Product detail + image management endpoints (admin_catalog.py)

**Files:**
- Modify: `services/api/app/routers/admin_catalog.py`
- Modify: `services/api/app/main.py`
- Create: `services/api/tests/routers/test_admin_catalog_products.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/routers/test_admin_catalog_products.py`:

```python
# NOTE: `from __future__ import annotations` deliberately absent.

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Product, ProductImage, Tenant


@pytest.fixture()
def product(db, tenant: Tenant) -> Product:
    p = Product(
        tenant_id=tenant.id, sku=f"sku-{uuid.uuid4().hex[:6]}",
        name="Widget", unit_price_cents=1999, product_type="physical",
    )
    db.add(p)
    db.flush()
    return p


@pytest.fixture()
def auth_headers(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        role="owner",
        role_id=None,
        is_legacy_token=False,
        permissions=frozenset({"catalog:read", "catalog:write"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield {}
    app.dependency_overrides.clear()


def test_get_product_detail(db, tenant: Tenant, product: Product, auth_headers) -> None:
    """GET /v1/admin/catalog/products/{id} returns full product detail including new fields."""
    client = TestClient(app)
    resp = client.get(f"/v1/admin/catalog/products/{product.id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == str(product.id)
    assert body["product_type"] == "physical"
    assert body["track_quantity"] is True
    assert body["images"] == []
    assert body["tags"] is None or body["tags"] == []


def test_get_product_detail_404_for_unknown(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.get(f"/v1/admin/catalog/products/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404


def test_add_image_to_product(db, tenant: Tenant, product: Product, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post(f"/v1/admin/catalog/products/{product.id}/images", json={
        "url": "https://cdn.example.com/widget.jpg",
        "alt_text": "A beautiful widget",
        "sort_order": 0,
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["url"] == "https://cdn.example.com/widget.jpg"
    assert body["alt_text"] == "A beautiful widget"
    assert body["product_id"] == str(product.id)


def test_list_product_images(db, tenant: Tenant, product: Product, auth_headers) -> None:
    # Add two images
    db.add(ProductImage(
        tenant_id=tenant.id, product_id=product.id,
        url="https://cdn.example.com/a.jpg", sort_order=1,
    ))
    db.add(ProductImage(
        tenant_id=tenant.id, product_id=product.id,
        url="https://cdn.example.com/b.jpg", sort_order=0,
    ))
    db.commit()

    client = TestClient(app)
    resp = client.get(f"/v1/admin/catalog/products/{product.id}/images", headers=auth_headers)
    assert resp.status_code == 200
    urls = [img["url"] for img in resp.json()]
    # sort_order 0 should come first
    assert urls[0] == "https://cdn.example.com/b.jpg"


def test_delete_image(db, tenant: Tenant, product: Product, auth_headers) -> None:
    img = ProductImage(
        tenant_id=tenant.id, product_id=product.id,
        url="https://cdn.example.com/doomed.jpg", sort_order=0,
    )
    db.add(img)
    db.commit()

    client = TestClient(app)
    resp = client.delete(f"/v1/admin/catalog/products/{product.id}/images/{img.id}", headers=auth_headers)
    assert resp.status_code == 204


def test_cross_tenant_product_image_blocked(db, tenant: Tenant, auth_headers) -> None:
    """Adding an image to a product from another tenant returns 404."""
    other = Tenant(name=f"other-{uuid.uuid4().hex[:6]}", slug=f"other-{uuid.uuid4().hex[:8]}")
    db.add(other)
    db.flush()
    other_p = Product(
        tenant_id=other.id, sku=f"sku-{uuid.uuid4().hex[:6]}",
        name="Other", unit_price_cents=100,
    )
    db.add(other_p)
    db.commit()

    client = TestClient(app)
    resp = client.post(f"/v1/admin/catalog/products/{other_p.id}/images", json={
        "url": "https://cdn.example.com/stolen.jpg",
    }, headers=auth_headers)
    assert resp.status_code == 404
```

- [ ] **Step 2: Confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/routers/test_admin_catalog_products.py $CONTAINER:/app/tests/routers/test_admin_catalog_products.py
docker compose exec api python -m pytest tests/routers/test_admin_catalog_products.py -v
docker compose exec api rm -f /app/tests/routers/test_admin_catalog_products.py
```
Expected: FAIL — endpoints don't exist yet in admin_catalog.py.

- [ ] **Step 3: Implement admin_catalog.py**

Replace the stub content of `services/api/app/routers/admin_catalog.py` with:

```python
"""Admin catalog endpoints: product detail view and image gallery management.

The existing CRUD endpoints (create/list/patch products) live in admin_web.py
for backwards compat. This router adds:
  - GET  /v1/admin/catalog/products/{id}         — full product detail (all fields incl. images)
  - GET  /v1/admin/catalog/products/{id}/images  — list images ordered by sort_order
  - POST /v1/admin/catalog/products/{id}/images  — add an image to the gallery
  - DELETE /v1/admin/catalog/products/{id}/images/{image_id} — remove an image

Auth: requires catalog:read or catalog:write (matching admin_web.py convention).
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import Product, ProductImage

router = APIRouter(prefix="/v1/admin/catalog", tags=["Admin Catalog"])


# --- Schemas ---

class ProductImageOut(BaseModel):
    id: UUID
    tenant_id: UUID
    product_id: UUID
    url: str
    alt_text: str | None
    sort_order: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ProductImageIn(BaseModel):
    url: str = Field(min_length=1, max_length=1024)
    alt_text: str | None = Field(default=None, max_length=255)
    sort_order: int = 0


class ProductDetailOut(BaseModel):
    id: UUID
    tenant_id: UUID
    sku: str
    name: str
    product_type: str
    status: str
    unit_price_cents: int
    discount_price_cents: int | None
    subtitle: str | None
    ribbon: str | None
    short_description: str | None
    description: str | None
    tags: list[str] | None
    track_quantity: bool
    weight_grams: int | None
    shipping_class: str | None
    digital_files: list[dict] | None
    gift_card_amounts_cents: list[int] | None
    gift_card_expiry_months: int | None
    additional_info_sections: list[dict] | None
    slug: str | None
    meta_title: str | None
    meta_description: str | None
    og_image_url: str | None
    image_url: str | None
    images: list[ProductImageOut]
    category: str | None
    product_group_id: UUID | None
    cost_price_cents: int | None
    mrp_cents: int | None
    barcode: str | None
    hsn_code: str | None
    negative_inventory_allowed: bool
    reorder_point: int
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Helpers ---

def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator not assigned to a tenant",
        )
    return ctx.tenant_id


def _get_product_or_404(db: Session, product_id: UUID, tenant_id: UUID) -> Product:
    product = db.execute(
        select(Product)
        .options(selectinload(Product.images))
        .where(Product.id == product_id, Product.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


# --- Routes ---

@router.get(
    "/products/{product_id}",
    response_model=ProductDetailOut,
    dependencies=[require_permission("catalog:read")],
)
def get_product_detail(
    product_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> Product:
    tenant_id = _require_tenant(ctx)
    return _get_product_or_404(db, product_id, tenant_id)


@router.get(
    "/products/{product_id}/images",
    response_model=list[ProductImageOut],
    dependencies=[require_permission("catalog:read")],
)
def list_product_images(
    product_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[ProductImage]:
    tenant_id = _require_tenant(ctx)
    _get_product_or_404(db, product_id, tenant_id)  # 404 if not owned
    rows = db.execute(
        select(ProductImage)
        .where(ProductImage.product_id == product_id)
        .order_by(ProductImage.sort_order, ProductImage.created_at)
    ).scalars().all()
    return list(rows)


@router.post(
    "/products/{product_id}/images",
    response_model=ProductImageOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("catalog:write")],
)
def add_product_image(
    product_id: UUID,
    body: ProductImageIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ProductImage:
    tenant_id = _require_tenant(ctx)
    _get_product_or_404(db, product_id, tenant_id)

    img = ProductImage(
        tenant_id=tenant_id,
        product_id=product_id,
        url=body.url,
        alt_text=body.alt_text,
        sort_order=body.sort_order,
    )
    db.add(img)
    db.commit()
    db.refresh(img)
    return img


@router.delete(
    "/products/{product_id}/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("catalog:write")],
)
def delete_product_image(
    product_id: UUID,
    image_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_tenant(ctx)
    _get_product_or_404(db, product_id, tenant_id)

    img = db.get(ProductImage, image_id)
    if img is None or img.product_id != product_id or img.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    db.delete(img)
    db.commit()
```

- [ ] **Step 4: Mount the router**

`admin_catalog.py`'s router is already imported in `main.py` (the stub was there all along). Verify it's included:

```bash
grep "admin_catalog" services/api/app/main.py
```

If the import/include is already there, nothing to do. If not, add `admin_catalog` to the imports and include block.

- [ ] **Step 5: Run tests**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/routers/admin_catalog.py $CONTAINER:/app/app/routers/admin_catalog.py
docker cp services/api/app/main.py $CONTAINER:/app/app/main.py
docker cp services/api/tests $CONTAINER:/app/tests
docker compose restart api
sleep 5
docker compose exec api python -m pytest tests/routers/test_admin_catalog_products.py tests/test_admin_console_contracts.py::test_product_detail_out_schema -v
docker compose exec api rm -rf /app/tests
```
Expected: 6 router tests + 1 contract test = 7 passed.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/routers/admin_catalog.py \
        services/api/app/main.py \
        services/api/tests/routers/test_admin_catalog_products.py
git commit -m "feat(catalog): add product detail endpoint + image gallery management"
```

---

### Task 5: Integration smoke test

**Files:**
- Create: `services/api/tests/integration/test_product_types_e2e.py`

- [ ] **Step 1: Write the integration test**

Create `services/api/tests/integration/test_product_types_e2e.py`:

```python
"""End-to-end smoke test for product type expansion + catalog enrichment.

Covers:
- Creating each of the five product types via API
- product_type_service helpers align with the created products
- Image gallery lifecycle: add, list (ordered by sort_order), delete
- Product detail endpoint returns all enrichment fields
"""
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Product, Tenant


@pytest.fixture()
def auth(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=uuid.uuid4(), tenant_id=tenant.id,
        role="owner", role_id=None, is_legacy_token=False,
        permissions=frozenset({"catalog:read", "catalog:write"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield
    app.dependency_overrides.clear()


PRODUCT_TYPES = [
    ("PHYS-E2E",   "Physical Widget",    1999, "physical",  {"track_quantity": True,  "weight_grams": 200}),
    ("DIG-E2E",    "Digital eBook",       999, "digital",   {"track_quantity": False, "digital_files": [{"name": "ebook.pdf", "url": "https://cdn.test/book.pdf"}]}),
    ("SVC-E2E",    "Consultation",       5000, "service",   {"track_quantity": False}),
    ("DONATE-E2E", "Plant a Tree",          0, "donation",  {"track_quantity": False}),
    ("GC-E2E",     "Gift Card",             0, "gift_card", {"track_quantity": False, "gift_card_amounts_cents": [2500, 5000]}),
]


def test_all_five_product_types_create_successfully(db, tenant: Tenant, auth) -> None:
    client = TestClient(app)
    for sku, name, price, ptype, extra in PRODUCT_TYPES:
        body = {"sku": sku, "name": name, "unit_price_cents": price, "product_type": ptype, **extra}
        resp = client.post("/v1/admin/products", json=body)
        assert resp.status_code in (200, 201), f"{ptype}: {resp.text}"
        result = resp.json()
        assert result["product_type"] == ptype, f"Expected {ptype}, got {result['product_type']}"


def test_product_type_service_aligns_with_created_products(db, tenant: Tenant, auth) -> None:
    from app.services.product_type_service import is_inventory_tracked, is_shippable

    client = TestClient(app)
    for sku, name, price, ptype, extra in PRODUCT_TYPES:
        body = {"sku": f"{sku}-SVC", "name": f"{name} SVC", "unit_price_cents": price,
                "product_type": ptype, **extra}
        resp = client.post("/v1/admin/products", json=body)
        track_qty = resp.json().get("track_quantity", True)

        shippable = is_shippable(ptype)
        tracked = is_inventory_tracked(ptype, track_quantity=track_qty)

        if ptype == "physical":
            assert shippable is True
            assert tracked is True  # default track_quantity=True
        elif ptype == "donation":
            assert shippable is False
            assert tracked is False
        elif ptype == "digital":
            assert shippable is False
            assert tracked is False  # track_quantity=False in fixture


def test_image_gallery_lifecycle(db, tenant: Tenant, auth) -> None:
    """Create product → add two images with sort_order → list ordered → delete one."""
    client = TestClient(app)

    # Create product
    resp = client.post("/v1/admin/products", json={
        "sku": "IMG-E2E", "name": "Image Gallery Widget", "unit_price_cents": 100,
    })
    assert resp.status_code in (200, 201)
    product_id = resp.json()["id"]

    # Add images (reversed sort order to test ordering)
    i2 = client.post(f"/v1/admin/catalog/products/{product_id}/images", json={
        "url": "https://cdn.test/img2.jpg", "sort_order": 1,
    })
    i1 = client.post(f"/v1/admin/catalog/products/{product_id}/images", json={
        "url": "https://cdn.test/img1.jpg", "sort_order": 0,
    })
    assert i1.status_code == 201
    assert i2.status_code == 201
    image_id = i2.json()["id"]

    # List — sorted by sort_order
    list_resp = client.get(f"/v1/admin/catalog/products/{product_id}/images")
    assert list_resp.status_code == 200
    urls = [img["url"] for img in list_resp.json()]
    assert urls[0] == "https://cdn.test/img1.jpg"  # sort_order=0 first
    assert urls[1] == "https://cdn.test/img2.jpg"  # sort_order=1 second

    # Detail endpoint shows images
    detail_resp = client.get(f"/v1/admin/catalog/products/{product_id}")
    assert detail_resp.status_code == 200
    assert len(detail_resp.json()["images"]) == 2

    # Delete one
    del_resp = client.delete(f"/v1/admin/catalog/products/{product_id}/images/{image_id}")
    assert del_resp.status_code == 204

    # Confirm removed
    list_resp2 = client.get(f"/v1/admin/catalog/products/{product_id}/images")
    assert len(list_resp2.json()) == 1


def test_enrichment_fields_roundtrip(db, tenant: Tenant, auth) -> None:
    """Create product with all enrichment fields, fetch via detail, confirm values."""
    client = TestClient(app)
    resp = client.post("/v1/admin/products", json={
        "sku": "ENRICH-E2E",
        "name": "Enriched Product",
        "unit_price_cents": 2999,
        "product_type": "physical",
        "subtitle": "The most enriched",
        "ribbon": "SALE",
        "discount_price_cents": 2499,
        "tags": ["sale", "featured"],
        "slug": "enriched-product",
        "meta_title": "Enriched Product | Shop",
        "weight_grams": 300,
        "shipping_class": "standard",
    })
    assert resp.status_code in (200, 201)
    product_id = resp.json()["id"]

    detail = client.get(f"/v1/admin/catalog/products/{product_id}")
    assert detail.status_code == 200
    d = detail.json()
    assert d["subtitle"] == "The most enriched"
    assert d["ribbon"] == "SALE"
    assert d["discount_price_cents"] == 2499
    assert d["tags"] == ["sale", "featured"]
    assert d["slug"] == "enriched-product"
    assert d["weight_grams"] == 300
```

- [ ] **Step 2: Run integration test**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest tests/integration/test_product_types_e2e.py -v
docker compose exec api rm -rf /app/tests
```
Expected: 4 passed.

- [ ] **Step 3: Run the full product-types suite**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest \
  tests/services/test_product_type_service.py \
  tests/routers/test_admin_product_types.py \
  tests/routers/test_admin_catalog_products.py \
  tests/integration/test_product_types_e2e.py \
  tests/test_admin_console_contracts.py::test_product_detail_out_schema \
  -v 2>&1 | tail -10
docker compose exec api rm -rf /app/tests
```
Expected ballpark: ~28 tests passing.

- [ ] **Step 4: Commit**

```bash
git add services/api/tests/integration/test_product_types_e2e.py
git commit -m "test(catalog): end-to-end smoke test for product type expansion"
```

---

## Done. Summary of what shipped

- 17 new columns on `products` (`product_type`, `subtitle`, `ribbon`, `discount_price_cents`, `short_description`, `track_quantity`, `tags`, `additional_info_sections`, `weight_grams`, `shipping_class`, `digital_files`, `gift_card_amounts_cents`, `gift_card_expiry_months`, `slug`, `meta_title`, `meta_description`, `og_image_url`)
- New `product_images` table with gallery ordering
- `app/services/product_type_service.py` — `is_shippable`, `is_inventory_tracked`, `is_variable_amount`, `is_tax_exempt_by_default`
- Extended `admin_web.py` product schemas to accept and return all new fields (backwards compatible)
- New `admin_catalog.py` endpoints: product detail, image list/add/delete
- ~28 tests

## What this unlocks

- **Shipping engine** (§5.4): `is_shippable(product.product_type)` is the gate. Only physical products generate shipping rates.
- **Tax engine** (§5.5): `is_tax_exempt_by_default` seeds tax behavior. Tax classes per product type can layer on top.
- **Digital product delivery**: when hosted checkout ships (Phase 2), it reads `digital_files` from the product to send download links.
- **Gift card sub-project** (Domain 8): the schema (`gift_card_amounts_cents`, `gift_card_expiry_months`) is in place; the code-generation / redemption logic ships as a separate sub-project.
- **Shopify/Woo connectors** (Phase 1): product type maps to Shopify's `product_type` field; digital products map to Shopify's digital/service product types.

## Follow-up work (not in this plan)

- Formal options/variants model (`product_options`, `option_values`, `product_variants`) — `variant_label` text field stays for now
- File upload to S3/R2 for `digital_files` — currently merchant provides hosted URLs
- Gift card redemption codes + balance tracking (Domain 8 sub-project)

---

*End of plan.*
