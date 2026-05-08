# Storefront Image Gallery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the storefront catalog so the product list returns an efficient single thumbnail URL via a correlated subquery, and the product detail returns the full ordered image gallery array.

**Architecture:** One file changes — `services/api/app/routers/storefront/catalog.py`. The list endpoint replaces `selectinload` with a correlated scalar subquery that fetches only the first image URL per product in the same SQL round-trip. The detail endpoint keeps `selectinload` and populates the new `images` field. `StorefrontProductOut` gains `images: list[StorefrontImageOut] | None` (null on list, populated on detail). The SDK `StorefrontProduct` type gains the same optional field. `products.image_url` stays as a silent legacy override.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x, TypeScript (SDK types only)

---

## Codebase context

### Current state of catalog.py
- `_to_out(product, currency)` — reads `product.image_url or product.images[0].url`
- List query uses `selectinload(Product.images)` — loads ALL images for every product in the page (over-fetching)
- Detail query uses `selectinload(Product.images)` — correct for single product
- Both endpoints call the same `_to_out` — no way to distinguish list vs detail output

### ProductImage model fields
```python
# product_images table
url: str
alt_text: str | None
sort_order: int        # default 0 — lower = earlier
created_at: datetime
```
`Product.images` relationship is ordered by `sort_order` at the ORM level.

### Correlated subquery pattern (SQLAlchemy 2.x)
```python
from sqlalchemy import select as sa_select

first_image_subq = (
    sa_select(ProductImage.url)
    .where(ProductImage.product_id == Product.id)
    .order_by(ProductImage.sort_order.asc(), ProductImage.created_at.asc())
    .limit(1)
    .correlate(Product)
    .scalar_subquery()
)

# Use in a select alongside Product:
rows = db.execute(
    sa_select(Product, first_image_subq.label("first_image_url"))
    .where(...)
).all()

# Each row is a Row object; access as:
for row in rows:
    product: Product = row[0]
    first_image_url: str | None = row[1]
```

### image_url priority
```python
# product.image_url is the legacy direct-URL column (only set by demo seed scripts)
# first_image_url is the first gallery image from product_images (sort_order ASC)
resolved_image_url = product.image_url or first_image_url or None
```

### Deploy pattern
```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/routers/storefront/catalog.py \
    $CONTAINER:/app/app/routers/storefront/catalog.py
docker compose restart api && sleep 6
```

---

## File map

| File | Change |
|------|--------|
| `services/api/app/routers/storefront/catalog.py` | All backend changes (models, queries, functions) |
| `services/api/tests/storefront/test_catalog.py` | New image-related tests appended |
| `packages/storefront-sdk/src/types.ts` | Add `StorefrontProductImage`, extend `StorefrontProduct` |

---

## Task 1: Rewrite catalog.py — correlated subquery + gallery response

**Files:**
- Modify: `services/api/app/routers/storefront/catalog.py`
- Modify: `services/api/tests/storefront/test_catalog.py`

- [ ] **Step 1: Write the failing tests**

Append to `services/api/tests/storefront/test_catalog.py`:

```python
def test_list_products_images_field_is_null(db, tenant: Tenant, storefront) -> None:
    """List endpoint never returns the images array — always null."""
    from app.db.session import get_db
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        resp = client.get("/v1/storefront/products",
                          headers={"X-Channel-Id": str(storefront["channel"].id)})
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["images"] is None
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_list_products_image_url_from_gallery(db, tenant: Tenant, storefront) -> None:
    """image_url is populated from gallery when products.image_url is null."""
    from app.models import ProductImage
    from app.db.session import get_db
    product = storefront["products"][0]
    db.add(ProductImage(
        tenant_id=tenant.id, product_id=product.id,
        url="https://cdn.example.com/img1.jpg", sort_order=0,
    ))
    db.add(ProductImage(
        tenant_id=tenant.id, product_id=product.id,
        url="https://cdn.example.com/img2.jpg", sort_order=1,
    ))
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        resp = client.get("/v1/storefront/products",
                          headers={"X-Channel-Id": str(storefront["channel"].id)})
        assert resp.status_code == 200
        item = next(i for i in resp.json()["items"] if i["id"] == str(product.id))
        # Must return the FIRST gallery image (sort_order 0), not the second
        assert item["image_url"] == "https://cdn.example.com/img1.jpg"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_detail_returns_full_gallery(db, tenant: Tenant, storefront) -> None:
    """Detail endpoint populates the images array in sort_order."""
    from app.models import ProductImage
    from app.db.session import get_db
    product = storefront["products"][0]
    db.add(ProductImage(
        tenant_id=tenant.id, product_id=product.id,
        url="https://cdn.example.com/a.jpg", sort_order=1,
    ))
    db.add(ProductImage(
        tenant_id=tenant.id, product_id=product.id,
        url="https://cdn.example.com/b.jpg", sort_order=0,
    ))
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        resp = client.get(f"/v1/storefront/products/{product.id}",
                          headers={"X-Channel-Id": str(storefront["channel"].id)})
        assert resp.status_code == 200
        body = resp.json()
        assert body["images"] is not None
        assert len(body["images"]) == 2
        # Sorted by sort_order: b.jpg (0) before a.jpg (1)
        assert body["images"][0]["url"] == "https://cdn.example.com/b.jpg"
        assert body["images"][1]["url"] == "https://cdn.example.com/a.jpg"
        # image_url is the first (lowest sort_order)
        assert body["image_url"] == "https://cdn.example.com/b.jpg"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_detail_products_image_url_overrides_gallery(db, tenant: Tenant, storefront) -> None:
    """products.image_url takes priority over the gallery (legacy override)."""
    from app.models import ProductImage
    from app.db.session import get_db
    product = storefront["products"][0]
    # Set the legacy direct-URL field
    product.image_url = "https://legacy.example.com/hero.jpg"
    db.add(ProductImage(
        tenant_id=tenant.id, product_id=product.id,
        url="https://cdn.example.com/gallery.jpg", sort_order=0,
    ))
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        resp = client.get(f"/v1/storefront/products/{product.id}",
                          headers={"X-Channel-Id": str(storefront["channel"].id)})
        assert resp.status_code == 200
        body = resp.json()
        # Legacy direct URL wins for image_url
        assert body["image_url"] == "https://legacy.example.com/hero.jpg"
        # But gallery still returned in images array
        assert len(body["images"]) == 1
        assert body["images"][0]["url"] == "https://cdn.example.com/gallery.jpg"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_detail_no_gallery_images_is_empty_list(db, tenant: Tenant, storefront) -> None:
    """Detail images field is an empty list (not null) when product has no gallery."""
    from app.db.session import get_db
    product = storefront["products"][0]
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        resp = client.get(f"/v1/storefront/products/{product.id}",
                          headers={"X-Channel-Id": str(storefront["channel"].id)})
        assert resp.status_code == 200
        body = resp.json()
        assert body["images"] == []
        assert body["image_url"] is None
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 2: Run failing tests**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/storefront/test_catalog.py \
    $CONTAINER:/app/tests/storefront/test_catalog.py
docker compose exec api python -m pytest \
    /app/tests/storefront/test_catalog.py \
    -k "image" -v 2>&1 | tail -20
docker compose exec api rm /app/tests/storefront/test_catalog.py
```

Expected: 5 failures (models and functions don't have images yet).

- [ ] **Step 3: Rewrite catalog.py**

Replace the entire file with:

```python
"""Storefront catalog: product listing and detail endpoints."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models import Product, ProductImage
from app.routers.storefront.auth import StorefrontChannelDep

router = APIRouter(prefix="/v1/storefront", tags=["Storefront Catalog"])


class StorefrontImageOut(BaseModel):
    url: str
    alt_text: str | None
    sort_order: int

    model_config = {"from_attributes": True}


class StorefrontProductOut(BaseModel):
    id: UUID
    name: str
    slug: str | None
    subtitle: str | None
    ribbon: str | None
    description: str | None
    short_description: str | None
    product_type: str
    status: str
    sku: str
    unit_price_cents: int
    discount_price_cents: int | None
    currency_code: str
    image_url: str | None
    images: list[StorefrontImageOut] | None = None
    tags: list[str] | None
    track_quantity: bool
    weight_grams: int | None
    shipping_class: str | None
    digital_files: list[dict] | None
    gift_card_amounts_cents: list[int] | None
    gift_card_expiry_months: int | None
    meta_title: str | None
    meta_description: str | None

    model_config = {"from_attributes": True}


class ProductListOut(BaseModel):
    items: list[StorefrontProductOut]
    total: int
    page: int
    per_page: int


# Correlated scalar subquery: first gallery image URL per product (by sort_order ASC)
_first_image_subq = (
    select(ProductImage.url)
    .where(ProductImage.product_id == Product.id)
    .order_by(ProductImage.sort_order.asc(), ProductImage.created_at.asc())
    .limit(1)
    .correlate(Product)
    .scalar_subquery()
)


def _to_out_list(product: Product, currency: str, first_image_url: str | None) -> StorefrontProductOut:
    """Build a list-context product response. `images` is always null (bandwidth)."""
    return StorefrontProductOut(
        id=product.id,
        name=product.name,
        slug=product.slug,
        subtitle=product.subtitle,
        ribbon=product.ribbon,
        description=product.description,
        short_description=product.short_description,
        product_type=product.product_type,
        status=product.status,
        sku=product.sku,
        unit_price_cents=product.unit_price_cents,
        discount_price_cents=product.discount_price_cents,
        currency_code=currency,
        image_url=product.image_url or first_image_url,
        images=None,
        tags=product.tags,
        track_quantity=product.track_quantity,
        weight_grams=product.weight_grams,
        shipping_class=product.shipping_class,
        digital_files=product.digital_files,
        gift_card_amounts_cents=product.gift_card_amounts_cents,
        gift_card_expiry_months=product.gift_card_expiry_months,
        meta_title=product.meta_title,
        meta_description=product.meta_description,
    )


def _to_out_detail(product: Product, currency: str) -> StorefrontProductOut:
    """Build a detail-context product response. `images` is the full gallery array."""
    gallery = [
        StorefrontImageOut(url=img.url, alt_text=img.alt_text, sort_order=img.sort_order)
        for img in product.images  # already ordered by sort_order from the relationship
    ]
    first_gallery_url = gallery[0].url if gallery else None
    return StorefrontProductOut(
        id=product.id,
        name=product.name,
        slug=product.slug,
        subtitle=product.subtitle,
        ribbon=product.ribbon,
        description=product.description,
        short_description=product.short_description,
        product_type=product.product_type,
        status=product.status,
        sku=product.sku,
        unit_price_cents=product.unit_price_cents,
        discount_price_cents=product.discount_price_cents,
        currency_code=currency,
        image_url=product.image_url or first_gallery_url,
        images=gallery,
        tags=product.tags,
        track_quantity=product.track_quantity,
        weight_grams=product.weight_grams,
        shipping_class=product.shipping_class,
        digital_files=product.digital_files,
        gift_card_amounts_cents=product.gift_card_amounts_cents,
        gift_card_expiry_months=product.gift_card_expiry_months,
        meta_title=product.meta_title,
        meta_description=product.meta_description,
    )


@router.get("/products", response_model=ProductListOut)
def list_products(
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db)],
    q: str | None = None,
    product_type: str | None = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
) -> ProductListOut:
    base_where = [
        Product.tenant_id == channel.tenant_id,
        Product.status == "active",
    ]
    if q and q.strip():
        like = f"%{q.strip()}%"
        base_where.append(or_(Product.name.ilike(like), Product.sku.ilike(like)))
    if product_type:
        base_where.append(Product.product_type == product_type)

    total = db.execute(
        select(func.count(Product.id)).where(*base_where)
    ).scalar_one()

    # Correlated subquery: fetches only the first image URL for each product,
    # no extra queries, no over-fetching of full gallery.
    rows = db.execute(
        select(Product, _first_image_subq.label("first_image_url"))
        .where(*base_where)
        .order_by(Product.name)
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).all()

    items = [
        _to_out_list(row[0], channel.currency_code, row[1])
        for row in rows
    ]
    return ProductListOut(items=items, total=total, page=page, per_page=per_page)


@router.get("/products/{product_slug_or_id}", response_model=StorefrontProductOut)
def get_product(
    product_slug_or_id: str,
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db)],
) -> StorefrontProductOut:
    product = None
    try:
        uid = UUID(product_slug_or_id)
        product = db.execute(
            select(Product)
            .options(selectinload(Product.images))
            .where(
                Product.id == uid,
                Product.tenant_id == channel.tenant_id,
                Product.status == "active",
            )
        ).scalar_one_or_none()
    except ValueError:
        pass

    if product is None:
        product = db.execute(
            select(Product)
            .options(selectinload(Product.images))
            .where(
                Product.slug == product_slug_or_id,
                Product.tenant_id == channel.tenant_id,
                Product.status == "active",
            )
        ).scalar_one_or_none()

    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    return _to_out_detail(product, channel.currency_code)
```

- [ ] **Step 4: Deploy and run all catalog tests**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/routers/storefront/catalog.py \
    $CONTAINER:/app/app/routers/storefront/catalog.py
docker compose restart api && sleep 6
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest \
    /app/tests/storefront/test_catalog.py -v 2>&1 | tail -20
docker compose exec api rm -rf /app/tests
```

Expected: all 12+ tests pass (5 existing + 5 new image tests).

- [ ] **Step 5: Commit**

```bash
git add services/api/app/routers/storefront/catalog.py \
        services/api/tests/storefront/test_catalog.py
git commit -m "feat(storefront): return full gallery on detail, correlated subquery on list"
```

---

## Task 2: Update Storefront SDK types

**Files:**
- Modify: `packages/storefront-sdk/src/types.ts`

- [ ] **Step 1: Add StorefrontProductImage and update StorefrontProduct**

Read `packages/storefront-sdk/src/types.ts`. Find the `StorefrontProduct` interface. Make two changes:

**a) Add `StorefrontProductImage` interface before `StorefrontProduct`:**

```typescript
export interface StorefrontProductImage {
  url: string;
  alt_text: string | null;
  sort_order: number;
}
```

**b) Add `images` field to `StorefrontProduct`:**

```typescript
export interface StorefrontProduct {
  id: string;
  name: string;
  slug: string | null;
  subtitle: string | null;
  ribbon: string | null;
  description: string | null;
  short_description: string | null;
  product_type: string;
  status: string;
  sku: string;
  unit_price_cents: number;
  discount_price_cents: number | null;
  currency_code: string;
  image_url: string | null;
  images: StorefrontProductImage[] | null;  // null in list, populated in detail
  tags: string[] | null;
  track_quantity: boolean;
  weight_grams: number | null;
  meta_title: string | null;
  meta_description: string | null;
}
```

- [ ] **Step 2: Export StorefrontProductImage from index.ts**

Read `packages/storefront-sdk/src/index.ts`. Add `StorefrontProductImage` to the `export type *` re-export. Since the file uses `export type * from "./types.js"` it already re-exports everything — no change needed. Just verify this is the case.

- [ ] **Step 3: Commit**

```bash
git add packages/storefront-sdk/src/types.ts
git commit -m "feat(sdk): add StorefrontProductImage type, images field on StorefrontProduct"
```

---

## Task 3: Full test suite + push

- [ ] **Step 1: Run full API test suite**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest /app/tests/ -q 2>&1 | tail -6
docker compose exec api rm -rf /app/tests
```

Expected: all previously-passing tests still pass, new image tests pass.

- [ ] **Step 2: Push**

```bash
git push origin main
```

---

## Self-review

**Spec coverage:**

| Requirement | Task |
|---|---|
| Product list returns single thumbnail URL | Task 1 — `_to_out_list` with `first_image_url` |
| List uses correlated subquery (no N+1, no over-fetching) | Task 1 — `_first_image_subq` |
| List `images` field is `null` | Task 1 — `images=None` in `_to_out_list` |
| Product detail returns full gallery array | Task 1 — `_to_out_detail` with `gallery` |
| Detail gallery sorted by `sort_order ASC` | Task 1 — ORM relationship already ordered, verified in tests |
| `products.image_url` is legacy override (not removed) | Task 1 — `product.image_url or first_gallery_url` |
| `StorefrontProductOut` gains `images` field | Task 1 — new `images: list[StorefrontImageOut] | None = None` |
| SDK `StorefrontProduct` gains `images` field | Task 2 |
| Tests: list images=null | Task 1 — `test_list_products_images_field_is_null` |
| Tests: list image_url from gallery | Task 1 — `test_list_products_image_url_from_gallery` |
| Tests: detail full gallery | Task 1 — `test_detail_returns_full_gallery` |
| Tests: legacy override priority | Task 1 — `test_detail_products_image_url_overrides_gallery` |
| Tests: empty gallery = empty list | Task 1 — `test_detail_no_gallery_images_is_empty_list` |

**No placeholders found.**

**Type consistency:**
- `StorefrontImageOut.url/alt_text/sort_order` matches `ProductImage.url/alt_text/sort_order` ✅
- `_to_out_list(product, currency, first_image_url)` — three args, used correctly in list query ✅
- `_to_out_detail(product, currency)` — two args, used in both detail branches ✅
- `_first_image_subq` is module-level constant — used only in `list_products` ✅
- SDK `StorefrontProductImage` field names match API `StorefrontImageOut` exactly ✅
