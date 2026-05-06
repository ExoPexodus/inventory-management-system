# Headless Storefront API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a public storefront REST API so custom frontends (Next.js storefronts, mobile apps, headless platforms) can list products, manage a cart with live inventory holds, apply discounts, get shipping and tax estimates, and submit an order — all powered entirely by the IMS without requiring Shopify or WooCommerce.

**Architecture:** A new `storefront/` router module under `/v1/storefront/…`. All endpoints require an `X-Channel-Id` header that identifies which headless channel is being served; the IMS resolves tenant, inventory pool, and pricing context from that channel. Cart state is stored server-side in a new `cart_items` table (keyed by `cart_token`), with soft-TTL stock reservations maintained automatically via the existing reservation engine. Order submission (Path 2 — merchant's own checkout) creates an `Order` row and commits stock movements by converting reservations. Shipping + tax + discount calculations delegate to the existing calculate services.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, PostgreSQL, pytest

**Auth model:** Requests include `X-Channel-Id: <uuid>` header. The channel must be active and of type `headless`. No separate API key is needed for Phase 1 — channel_id is the routing token. Rate-limiting and scoped API keys ship in a follow-up security hardening plan.

**Out of scope (deferred):**
- Hosted checkout (Path 1 — IMS-hosted checkout page). That's Phase 2.
- Shopper account auth (signup, login, order history). Deferred — anonymous carts work for Phase 1.
- GraphQL endpoint. REST only for Phase 1.
- Collections / policy pages / store info endpoints.
- Per-origin rate limiting.

---

### Task 1: cart_items table + CartItem model

**Files:**
- Create: `services/api/alembic/versions/20260515000001_cart_items.py`
- Modify: `services/api/app/models/tables.py`
- Modify: `services/api/app/models/__init__.py`

- [ ] **Step 1: Add the SQLAlchemy model**

In `services/api/app/models/tables.py`, append after `DiscountUse`:

```python
class CartItem(Base):
    """A line in a headless storefront cart.

    Cart state is server-side and keyed by cart_token (a client-generated or
    server-generated UUID string). Each item holds a soft stock reservation via
    the existing reservation engine. When the cart is submitted as an order, all
    reservations are committed to StockMovements.
    """
    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint("cart_token", "product_id", name="uq_cart_item_token_product"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), nullable=False
    )
    cart_token: Mapped[str] = mapped_column(String(128), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    reservation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_reservations.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 2: Export the model**

In `services/api/app/models/__init__.py`, add `CartItem` alphabetically (between `Channel` and `CustomerChannel`/`InventoryPool`).

- [ ] **Step 3: Write the migration**

Create `services/api/alembic/versions/20260515000001_cart_items.py`:

```python
"""Headless storefront: cart_items table

Revision ID: 20260515000001
Revises: 20260514000002
Create Date: 2026-05-15 00:00:01.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "20260515000001"
down_revision = "20260514000002"
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
        "cart_items",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cart_token", sa.String(128), nullable=False),
        sa.Column("product_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("unit_price_cents", sa.Integer, nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("reservation_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("stock_reservations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("cart_token", "product_id", name="uq_cart_item_token_product"),
    )
    op.create_index("ix_cart_items_cart_token", "cart_items", ["cart_token"])
    op.create_index("ix_cart_items_channel_id", "cart_items", ["channel_id"])
    op.create_index("ix_cart_items_tenant_id", "cart_items", ["tenant_id"])

    op.execute(f"""
        ALTER TABLE cart_items ENABLE ROW LEVEL SECURITY;
        ALTER TABLE cart_items FORCE ROW LEVEL SECURITY;
        CREATE POLICY ims_tenant_isolation ON cart_items
        USING ({_RLS_POLICY})
        WITH CHECK ({_RLS_POLICY});
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS ims_tenant_isolation ON cart_items;")
    op.execute("ALTER TABLE cart_items NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE cart_items DISABLE ROW LEVEL SECURITY;")
    op.drop_index("ix_cart_items_tenant_id", table_name="cart_items")
    op.drop_index("ix_cart_items_channel_id", table_name="cart_items")
    op.drop_index("ix_cart_items_cart_token", table_name="cart_items")
    op.drop_table("cart_items")
```

- [ ] **Step 4: Run migration**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/alembic/versions/20260515000001_cart_items.py $CONTAINER:/app/alembic/versions/
docker compose exec api alembic upgrade head
```
Expected: `Running upgrade 20260514000002 -> 20260515000001`

- [ ] **Step 5: Verify**

```bash
docker compose exec postgres psql -U ims -d ims -c "\d cart_items"
docker compose exec postgres psql -U ims -d ims -c "SELECT relrowsecurity FROM pg_class WHERE relname='cart_items'"
```
Expected: table described, `relrowsecurity = t`.

- [ ] **Step 6: Commit**

```bash
git add services/api/alembic/versions/20260515000001_cart_items.py \
        services/api/app/models/tables.py \
        services/api/app/models/__init__.py
git commit -m "feat(storefront): add cart_items table with RLS"
```

---

### Task 2: Storefront auth dependency + catalog endpoints

**Files:**
- Create: `services/api/app/routers/storefront/` (package)
- Create: `services/api/app/routers/storefront/__init__.py`
- Create: `services/api/app/routers/storefront/auth.py`
- Create: `services/api/app/routers/storefront/catalog.py`
- Modify: `services/api/app/main.py`
- Create: `services/api/tests/storefront/` (package)
- Create: `services/api/tests/storefront/__init__.py`
- Create: `services/api/tests/storefront/test_catalog.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/storefront/__init__.py` (empty).

Create `services/api/tests/storefront/test_catalog.py`:

```python
# NOTE: `from __future__ import annotations` deliberately absent.

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Channel, InventoryPool, InventoryPoolShop, Product, Shop, Tenant


@pytest.fixture()
def storefront(db, tenant: Tenant, shop: Shop):
    """Create a headless channel + two active products + one draft product."""
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    channel = Channel(
        tenant_id=tenant.id, type="headless", name=f"headless-{uuid.uuid4().hex[:6]}",
        config={}, inventory_pool_id=pool.id, currency_code="INR",
    )
    db.add(channel)
    db.flush()

    p1 = Product(
        tenant_id=tenant.id, name="Widget Alpha", sku="SKU-A",
        unit_price_cents=1999, product_type="physical", status="active",
        slug="widget-alpha", tags=["bestseller"],
    )
    p2 = Product(
        tenant_id=tenant.id, name="Widget Beta", sku="SKU-B",
        unit_price_cents=2999, product_type="physical", status="active",
        slug="widget-beta",
    )
    p3 = Product(
        tenant_id=tenant.id, name="Draft Item", sku="SKU-D",
        unit_price_cents=999, product_type="physical", status="draft",
    )
    db.add(p1)
    db.add(p2)
    db.add(p3)
    db.commit()

    return {"channel": channel, "products": [p1, p2], "draft": p3}


def test_list_products_only_active(db, tenant: Tenant, storefront) -> None:
    """Draft and archived products must not appear in the catalog."""
    client = TestClient(app)
    resp = client.get("/v1/storefront/products",
                      headers={"X-Channel-Id": str(storefront["channel"].id)})
    assert resp.status_code == 200, resp.text
    names = {p["name"] for p in resp.json()["items"]}
    assert "Widget Alpha" in names
    assert "Widget Beta" in names
    assert "Draft Item" not in names


def test_list_products_search(db, tenant: Tenant, storefront) -> None:
    client = TestClient(app)
    resp = client.get("/v1/storefront/products?q=Alpha",
                      headers={"X-Channel-Id": str(storefront["channel"].id)})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["name"] == "Widget Alpha"


def test_get_product_by_slug(db, tenant: Tenant, storefront) -> None:
    client = TestClient(app)
    resp = client.get("/v1/storefront/products/widget-alpha",
                      headers={"X-Channel-Id": str(storefront["channel"].id)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == "widget-alpha"
    assert body["unit_price_cents"] == 1999


def test_get_product_by_id(db, tenant: Tenant, storefront) -> None:
    p = storefront["products"][0]
    client = TestClient(app)
    resp = client.get(f"/v1/storefront/products/{p.id}",
                      headers={"X-Channel-Id": str(storefront["channel"].id)})
    assert resp.status_code == 200
    assert resp.json()["id"] == str(p.id)


def test_unknown_channel_rejected(db, tenant: Tenant) -> None:
    client = TestClient(app)
    resp = client.get("/v1/storefront/products",
                      headers={"X-Channel-Id": str(uuid.uuid4())})
    assert resp.status_code == 404


def test_missing_channel_header_rejected(db, tenant: Tenant) -> None:
    client = TestClient(app)
    resp = client.get("/v1/storefront/products")
    assert resp.status_code == 422


def test_non_headless_channel_rejected(db, tenant: Tenant, shop: Shop) -> None:
    """Only headless-type channels can be used as storefront channels."""
    pool = InventoryPool(tenant_id=tenant.id, name=f"p-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    pos_ch = Channel(
        tenant_id=tenant.id, type="pos", name="POS",
        config={}, inventory_pool_id=pool.id, currency_code="INR", shop_id=shop.id,
    )
    db.add(pos_ch)
    db.commit()

    client = TestClient(app)
    resp = client.get("/v1/storefront/products",
                      headers={"X-Channel-Id": str(pos_ch.id)})
    assert resp.status_code == 403
```

- [ ] **Step 2: Confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
mkdir -p services/api/tests/storefront && touch services/api/tests/storefront/__init__.py
docker cp services/api/tests/storefront $CONTAINER:/app/tests/storefront
docker compose exec api python -m pytest tests/storefront/test_catalog.py -v
docker compose exec api rm -rf /app/tests/storefront
```
Expected: FAIL — storefront module doesn't exist.

- [ ] **Step 3: Create the auth dependency**

Create `services/api/app/routers/storefront/__init__.py` (empty).

Create `services/api/app/routers/storefront/auth.py`:

```python
"""Storefront auth: resolve channel from X-Channel-Id header.

All storefront endpoints call ``get_storefront_channel`` to validate the request.
The channel must be active and of type 'headless' or 'manual'. POS and
Shopify/WooCommerce channels are not valid storefront channels.
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db.admin_deps_db import get_db_admin
from app.models import Channel


_ALLOWED_CHANNEL_TYPES = {"headless", "manual"}


def get_storefront_channel(
    x_channel_id: Annotated[UUID, Header(alias="X-Channel-Id")],
    db: Annotated[Session, Depends(get_db_admin)],
) -> Channel:
    """Resolve and validate the storefront channel from the X-Channel-Id header."""
    channel = db.get(Channel, x_channel_id)
    if channel is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel {x_channel_id} not found",
        )
    if channel.type not in _ALLOWED_CHANNEL_TYPES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Channel type '{channel.type}' cannot be used as a storefront channel. "
                   f"Only {sorted(_ALLOWED_CHANNEL_TYPES)} are allowed.",
        )
    if channel.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Channel is not active (status={channel.status})",
        )
    return channel


StorefrontChannelDep = Annotated[Channel, Depends(get_storefront_channel)]
```

- [ ] **Step 4: Create the catalog router**

Create `services/api/app/routers/storefront/catalog.py`:

```python
"""Storefront catalog: product listing and detail endpoints."""
from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.billing.pricing import price_for_product_in_currency
from app.db.admin_deps_db import get_db_admin
from app.models import Product
from app.routers.storefront.auth import StorefrontChannelDep

router = APIRouter(prefix="/v1/storefront", tags=["Storefront Catalog"])


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


def _to_product_out(product: Product, channel_currency: str) -> StorefrontProductOut:
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
        currency_code=channel_currency,
        image_url=product.image_url,
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
    db: Annotated[Session, Depends(get_db_admin)],
    q: str | None = None,
    product_type: str | None = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
) -> ProductListOut:
    """List active products in the channel's tenant catalog."""
    stmt = (
        select(Product)
        .where(
            Product.tenant_id == channel.tenant_id,
            Product.status == "active",
        )
        .order_by(Product.name)
    )
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(Product.name.ilike(like), Product.sku.ilike(like))
        )
    if product_type:
        stmt = stmt.where(Product.product_type == product_type)

    total = db.execute(
        select(Product).where(Product.tenant_id == channel.tenant_id,
                              Product.status == "active").with_only_columns(
            __import__("sqlalchemy", fromlist=["func"]).func.count()
        )
    ).scalar_one()

    offset = (page - 1) * per_page
    rows = db.execute(stmt.offset(offset).limit(per_page)).scalars().all()

    return ProductListOut(
        items=[_to_product_out(r, channel.currency_code) for r in rows],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/products/{product_slug_or_id}", response_model=StorefrontProductOut)
def get_product(
    product_slug_or_id: str,
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> StorefrontProductOut:
    """Get a single product by slug or UUID."""
    product = None
    try:
        uid = UUID(product_slug_or_id)
        product = db.execute(
            select(Product).where(
                Product.id == uid,
                Product.tenant_id == channel.tenant_id,
                Product.status == "active",
            )
        ).scalar_one_or_none()
    except ValueError:
        # Not a UUID — treat as slug
        pass

    if product is None:
        product = db.execute(
            select(Product).where(
                Product.slug == product_slug_or_id,
                Product.tenant_id == channel.tenant_id,
                Product.status == "active",
            )
        ).scalar_one_or_none()

    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    return _to_product_out(product, channel.currency_code)
```

Note: the `total` query in `list_products` uses a simplified approach. If it causes import issues, replace with:
```python
from sqlalchemy import func as sqlfunc
total = db.execute(
    select(sqlfunc.count(Product.id)).where(
        Product.tenant_id == channel.tenant_id,
        Product.status == "active",
    )
).scalar_one()
```

- [ ] **Step 5: Mount the catalog router**

In `services/api/app/main.py`, add the storefront catalog router. Since `storefront` is a sub-package, import it as:
```python
from app.routers.storefront import catalog as storefront_catalog
```
and include: `app.include_router(storefront_catalog.router)`

- [ ] **Step 6: Run tests**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/main.py $CONTAINER:/app/app/main.py
docker cp services/api/app/routers/storefront $CONTAINER:/app/app/routers/storefront
docker cp services/api/tests/storefront $CONTAINER:/app/tests/storefront
docker compose restart api
sleep 5
docker compose exec api python -m pytest tests/storefront/test_catalog.py -v
docker compose exec api rm -rf /app/tests/storefront
```
Expected: 7 passed.

- [ ] **Step 7: Commit**

```bash
git add services/api/app/routers/storefront/__init__.py \
        services/api/app/routers/storefront/auth.py \
        services/api/app/routers/storefront/catalog.py \
        services/api/app/main.py \
        services/api/tests/storefront/__init__.py \
        services/api/tests/storefront/test_catalog.py
git commit -m "feat(storefront): catalog endpoints GET /v1/storefront/products[/{id}]"
```

---

### Task 3: Cart endpoints (create + add items + read)

**Files:**
- Create: `services/api/app/routers/storefront/cart.py`
- Modify: `services/api/app/main.py`
- Create: `services/api/tests/storefront/test_cart.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/storefront/test_cart.py`:

```python
# NOTE: `from __future__ import annotations` deliberately absent.

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Channel, InventoryPool, InventoryPoolShop, Product, Shop, StockMovement, Tenant


@pytest.fixture()
def storefront(db, tenant: Tenant, shop: Shop):
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    channel = Channel(
        tenant_id=tenant.id, type="headless", name=f"headless-{uuid.uuid4().hex[:6]}",
        config={}, inventory_pool_id=pool.id, currency_code="INR",
    )
    db.add(channel)
    db.flush()

    product = Product(
        tenant_id=tenant.id, name="Widget", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=1999, product_type="physical", status="active",
    )
    db.add(product)
    db.flush()
    # Seed 10 units of stock
    db.add(StockMovement(
        tenant_id=tenant.id, shop_id=shop.id, product_id=product.id,
        quantity_delta=10, movement_type="purchase_receipt",
        idempotency_key=f"seed-{uuid.uuid4().hex}",
    ))
    db.commit()
    return {"channel": channel, "product": product, "shop": shop}


def _headers(storefront):
    return {"X-Channel-Id": str(storefront["channel"].id)}


def test_create_cart(db, tenant: Tenant, storefront) -> None:
    client = TestClient(app)
    resp = client.post("/v1/storefront/cart", headers=_headers(storefront))
    assert resp.status_code == 201
    body = resp.json()
    assert "cart_token" in body
    assert body["items"] == []
    assert body["total_cents"] == 0


def test_add_item_to_cart(db, tenant: Tenant, storefront) -> None:
    client = TestClient(app)
    cart_resp = client.post("/v1/storefront/cart", headers=_headers(storefront))
    token = cart_resp.json()["cart_token"]

    add_resp = client.post(f"/v1/storefront/cart/{token}/items", json={
        "product_id": str(storefront["product"].id),
        "quantity": 2,
    }, headers=_headers(storefront))
    assert add_resp.status_code == 200
    cart = add_resp.json()
    assert len(cart["items"]) == 1
    assert cart["items"][0]["quantity"] == 2
    assert cart["items"][0]["unit_price_cents"] == 1999
    assert cart["total_cents"] == 3998


def test_get_cart(db, tenant: Tenant, storefront) -> None:
    client = TestClient(app)
    cart_resp = client.post("/v1/storefront/cart", headers=_headers(storefront))
    token = cart_resp.json()["cart_token"]

    client.post(f"/v1/storefront/cart/{token}/items", json={
        "product_id": str(storefront["product"].id),
        "quantity": 1,
    }, headers=_headers(storefront))

    get_resp = client.get(f"/v1/storefront/cart/{token}", headers=_headers(storefront))
    assert get_resp.status_code == 200
    assert len(get_resp.json()["items"]) == 1


def test_update_item_quantity(db, tenant: Tenant, storefront) -> None:
    client = TestClient(app)
    cart_resp = client.post("/v1/storefront/cart", headers=_headers(storefront))
    token = cart_resp.json()["cart_token"]

    client.post(f"/v1/storefront/cart/{token}/items", json={
        "product_id": str(storefront["product"].id), "quantity": 1,
    }, headers=_headers(storefront))

    # Update quantity to 3
    update_resp = client.post(f"/v1/storefront/cart/{token}/items", json={
        "product_id": str(storefront["product"].id), "quantity": 3,
    }, headers=_headers(storefront))
    assert update_resp.status_code == 200
    assert update_resp.json()["total_cents"] == 5997  # 1999 * 3


def test_remove_item_from_cart(db, tenant: Tenant, storefront) -> None:
    client = TestClient(app)
    cart_resp = client.post("/v1/storefront/cart", headers=_headers(storefront))
    token = cart_resp.json()["cart_token"]

    add_resp = client.post(f"/v1/storefront/cart/{token}/items", json={
        "product_id": str(storefront["product"].id), "quantity": 2,
    }, headers=_headers(storefront))
    item_id = add_resp.json()["items"][0]["id"]

    del_resp = client.delete(f"/v1/storefront/cart/{token}/items/{item_id}",
                             headers=_headers(storefront))
    assert del_resp.status_code == 200
    assert del_resp.json()["items"] == []


def test_add_draft_product_rejected(db, tenant: Tenant, storefront) -> None:
    draft = Product(
        tenant_id=tenant.id, name="Draft", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=100, product_type="physical", status="draft",
    )
    db.add(draft)
    db.commit()

    client = TestClient(app)
    cart_resp = client.post("/v1/storefront/cart", headers=_headers(storefront))
    token = cart_resp.json()["cart_token"]

    resp = client.post(f"/v1/storefront/cart/{token}/items", json={
        "product_id": str(draft.id), "quantity": 1,
    }, headers=_headers(storefront))
    assert resp.status_code == 404


def test_stock_reservation_created(db, tenant: Tenant, storefront) -> None:
    """Adding a physical product to cart creates a soft reservation."""
    from sqlalchemy import select
    from app.models import StockReservation

    client = TestClient(app)
    cart_resp = client.post("/v1/storefront/cart", headers=_headers(storefront))
    token = cart_resp.json()["cart_token"]

    client.post(f"/v1/storefront/cart/{token}/items", json={
        "product_id": str(storefront["product"].id), "quantity": 2,
    }, headers=_headers(storefront))

    reservations = db.execute(
        select(StockReservation).where(
            StockReservation.cart_token == token,
            StockReservation.status == "active",
        )
    ).scalars().all()
    assert len(reservations) == 1
    assert reservations[0].quantity == 2
```

- [ ] **Step 2: Confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/storefront $CONTAINER:/app/tests/storefront
docker compose exec api python -m pytest tests/storefront/test_cart.py -v
docker compose exec api rm -rf /app/tests/storefront
```
Expected: FAIL — cart router doesn't exist.

- [ ] **Step 3: Implement the cart router**

Create `services/api/app/routers/storefront/cart.py`:

```python
"""Storefront cart: create, read, add/update/remove items.

Cart state is server-side and keyed by cart_token. Adding a physical product
creates a soft stock reservation. Updating quantity updates the reservation.
Removing an item releases the reservation. The cart_token is generated by the
server on cart creation.
"""
from __future__ import annotations

import uuid
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.admin_deps_db import get_db_admin
from app.models import CartItem, Channel, Product, StockReservation
from app.routers.storefront.auth import StorefrontChannelDep
from app.services.inventory_pool_service import pool_shops
from app.services.product_type_service import is_inventory_tracked
from app.services.reservation_service import release_reservation, reserve

router = APIRouter(prefix="/v1/storefront", tags=["Storefront Cart"])


class AddItemIn(BaseModel):
    product_id: UUID
    quantity: int = Field(ge=1)


class CartItemOut(BaseModel):
    id: UUID
    product_id: UUID
    product_name: str
    quantity: int
    unit_price_cents: int
    line_total_cents: int
    currency_code: str


class CartOut(BaseModel):
    cart_token: str
    channel_id: UUID
    items: list[CartItemOut]
    subtotal_cents: int
    total_cents: int
    currency_code: str


def _load_cart(db: Session, channel: Channel, cart_token: str) -> CartOut:
    rows = db.execute(
        select(CartItem, Product)
        .join(Product, CartItem.product_id == Product.id)
        .where(
            CartItem.cart_token == cart_token,
            CartItem.channel_id == channel.id,
        )
        .order_by(CartItem.created_at)
    ).all()

    items = [
        CartItemOut(
            id=ci.id,
            product_id=ci.product_id,
            product_name=prod.name,
            quantity=ci.quantity,
            unit_price_cents=ci.unit_price_cents,
            line_total_cents=ci.unit_price_cents * ci.quantity,
            currency_code=ci.currency_code,
        )
        for ci, prod in rows
    ]
    subtotal = sum(i.line_total_cents for i in items)
    return CartOut(
        cart_token=cart_token,
        channel_id=channel.id,
        items=items,
        subtotal_cents=subtotal,
        total_cents=subtotal,
        currency_code=channel.currency_code,
    )


def _get_shop_id_for_pool(db: Session, channel: Channel) -> UUID | None:
    """Pick the first shop in the channel's inventory pool (for reservations)."""
    shop_ids = pool_shops(db, channel.inventory_pool_id)
    return shop_ids[0] if shop_ids else None


@router.post("/cart", response_model=CartOut, status_code=status.HTTP_201_CREATED)
def create_cart(
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> CartOut:
    """Create a new empty cart and return its token."""
    token = str(uuid.uuid4())
    return CartOut(
        cart_token=token,
        channel_id=channel.id,
        items=[],
        subtotal_cents=0,
        total_cents=0,
        currency_code=channel.currency_code,
    )


@router.get("/cart/{cart_token}", response_model=CartOut)
def get_cart(
    cart_token: str,
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> CartOut:
    return _load_cart(db, channel, cart_token)


@router.post("/cart/{cart_token}/items", response_model=CartOut)
def add_or_update_item(
    cart_token: str,
    body: AddItemIn,
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> CartOut:
    """Add a product to the cart (or update quantity if already present).

    For shippable inventory-tracked products, creates/updates a stock reservation.
    """
    product = db.execute(
        select(Product).where(
            Product.id == body.product_id,
            Product.tenant_id == channel.tenant_id,
            Product.status == "active",
        )
    ).scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or inactive")

    # Resolve price in channel currency
    try:
        from app.billing.pricing import price_for_product_in_currency
        price = price_for_product_in_currency(db, product.id, channel.currency_code,
                                               channel_id=channel.id)
        unit_price = price.amount_cents
    except Exception:
        unit_price = product.unit_price_cents

    # Upsert cart item
    existing = db.execute(
        select(CartItem).where(
            CartItem.cart_token == cart_token,
            CartItem.product_id == body.product_id,
            CartItem.channel_id == channel.id,
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.quantity = body.quantity
        existing.unit_price_cents = unit_price
        item = existing
    else:
        item = CartItem(
            tenant_id=channel.tenant_id,
            channel_id=channel.id,
            cart_token=cart_token,
            product_id=body.product_id,
            quantity=body.quantity,
            unit_price_cents=unit_price,
            currency_code=channel.currency_code,
        )
        db.add(item)
    db.flush()

    # Manage reservation for inventory-tracked products
    if is_inventory_tracked(product.product_type, track_quantity=product.track_quantity):
        shop_id = _get_shop_id_for_pool(db, channel)
        if shop_id:
            res = reserve(
                db,
                tenant_id=channel.tenant_id,
                channel_id=channel.id,
                product_id=product.id,
                shop_id=shop_id,
                quantity=body.quantity,
                cart_token=cart_token,
                purpose="cart",
            )
            item.reservation_id = res.id
            db.flush()

    db.commit()
    return _load_cart(db, channel, cart_token)


@router.delete("/cart/{cart_token}/items/{item_id}", response_model=CartOut)
def remove_item(
    cart_token: str,
    item_id: UUID,
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> CartOut:
    """Remove an item from the cart and release its reservation."""
    item = db.execute(
        select(CartItem).where(
            CartItem.id == item_id,
            CartItem.cart_token == cart_token,
            CartItem.channel_id == channel.id,
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")

    if item.reservation_id:
        release_reservation(db, item.reservation_id)

    db.delete(item)
    db.commit()
    return _load_cart(db, channel, cart_token)
```

- [ ] **Step 4: Mount the cart router**

In `services/api/app/main.py`, add:
```python
from app.routers.storefront import cart as storefront_cart
```
and `app.include_router(storefront_cart.router)`.

- [ ] **Step 5: Run tests**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/main.py $CONTAINER:/app/app/main.py
docker cp services/api/app/routers/storefront $CONTAINER:/app/app/routers/storefront
docker cp services/api/tests/storefront $CONTAINER:/app/tests/storefront
docker compose restart api
sleep 5
docker compose exec api python -m pytest tests/storefront/test_cart.py -v
docker compose exec api rm -rf /app/tests/storefront
```
Expected: 8 passed.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/routers/storefront/cart.py \
        services/api/app/main.py \
        services/api/tests/storefront/test_cart.py
git commit -m "feat(storefront): cart endpoints create/read/add-items/remove-items with reservations"
```

---

### Task 4: Cart checkout summary + discount + Path 2 order submission

**Files:**
- Create: `services/api/app/routers/storefront/checkout.py`
- Modify: `services/api/app/main.py`
- Create: `services/api/tests/storefront/test_checkout.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/storefront/test_checkout.py`:

```python
# NOTE: `from __future__ import annotations` deliberately absent.

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import (
    Channel, Discount, InventoryPool, InventoryPoolShop, Order,
    Product, Shop, StockMovement, Tenant,
)


@pytest.fixture()
def storefront(db, tenant: Tenant, shop: Shop):
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    channel = Channel(
        tenant_id=tenant.id, type="headless", name=f"headless-{uuid.uuid4().hex[:6]}",
        config={}, inventory_pool_id=pool.id, currency_code="INR",
        tax_included_in_price=False,
    )
    db.add(channel)
    db.flush()

    product = Product(
        tenant_id=tenant.id, name="Widget", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=10000, product_type="physical", status="active",
        weight_grams=500,
    )
    db.add(product)
    db.flush()
    db.add(StockMovement(
        tenant_id=tenant.id, shop_id=shop.id, product_id=product.id,
        quantity_delta=50, movement_type="purchase_receipt",
        idempotency_key=f"seed-{uuid.uuid4().hex}",
    ))
    db.commit()
    return {"channel": channel, "product": product}


def _headers(storefront):
    return {"X-Channel-Id": str(storefront["channel"].id)}


def _make_cart(client, storefront):
    cart = client.post("/v1/storefront/cart", headers=_headers(storefront)).json()
    client.post(f"/v1/storefront/cart/{cart['cart_token']}/items", json={
        "product_id": str(storefront["product"].id), "quantity": 2,
    }, headers=_headers(storefront))
    return cart["cart_token"]


def test_get_cart_summary(db, tenant: Tenant, storefront) -> None:
    """GET /v1/storefront/cart/{token}/summary returns subtotal + placeholder shipping/tax."""
    client = TestClient(app)
    token = _make_cart(client, storefront)

    resp = client.get(f"/v1/storefront/cart/{token}/summary",
                      params={"destination_country": "IN"},
                      headers=_headers(storefront))
    assert resp.status_code == 200
    body = resp.json()
    assert body["subtotal_cents"] == 20000  # 10000 * 2
    assert "discount_cents" in body
    assert "tax_cents" in body
    assert "total_cents" in body


def test_apply_discount_to_cart(db, tenant: Tenant, storefront) -> None:
    disc = Discount(
        tenant_id=tenant.id, name="10% off", code="TEN",
        discount_type="percentage", value_bps=1000, status="active",
    )
    db.add(disc)
    db.commit()

    client = TestClient(app)
    token = _make_cart(client, storefront)

    resp = client.post(f"/v1/storefront/cart/{token}/discount", json={
        "code": "TEN",
    }, headers=_headers(storefront))
    assert resp.status_code == 200
    body = resp.json()
    assert body["discount_cents"] == 2000  # 20000 * 10%
    assert body["final_subtotal_cents"] == 18000


def test_submit_order_path2(db, tenant: Tenant, storefront) -> None:
    """POST /v1/storefront/orders creates an Order row and commits reservations."""
    from sqlalchemy import select

    client = TestClient(app)
    token = _make_cart(client, storefront)

    resp = client.post("/v1/storefront/orders", json={
        "cart_token": token,
        "payment_provider": "stripe",
        "payment_reference": "pi_test_12345",
        "customer_email": "shopper@example.com",
        "shipping_address": {"country": "IN", "city": "Mumbai"},
    }, headers=_headers(storefront))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "confirmed"
    assert body["customer_email"] == "shopper@example.com"
    assert body["total_cents"] == 20000

    # Order exists in DB
    order = db.execute(
        select(Order).where(Order.id == uuid.UUID(body["id"]))
    ).scalar_one()
    assert order.tenant_id == tenant.id
    assert order.channel_id == storefront["channel"].id


def test_submit_order_clears_cart(db, tenant: Tenant, storefront) -> None:
    """After order submission, the cart is empty."""
    client = TestClient(app)
    token = _make_cart(client, storefront)

    client.post("/v1/storefront/orders", json={
        "cart_token": token,
        "payment_provider": "cod",
        "payment_reference": "cod-001",
    }, headers=_headers(storefront))

    cart = client.get(f"/v1/storefront/cart/{token}", headers=_headers(storefront)).json()
    assert cart["items"] == []
```

- [ ] **Step 2: Confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/storefront $CONTAINER:/app/tests/storefront
docker compose exec api python -m pytest tests/storefront/test_checkout.py -v
docker compose exec api rm -rf /app/tests/storefront
```
Expected: FAIL — endpoints don't exist.

- [ ] **Step 3: Implement the checkout router**

Create `services/api/app/routers/storefront/checkout.py`:

```python
"""Storefront checkout: summary, discount, and Path-2 order submission."""
from __future__ import annotations

import uuid
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.admin_deps_db import get_db_admin
from app.models import CartItem, Order, OrderLine, OrderPayment, Product
from app.routers.storefront.auth import StorefrontChannelDep
from app.services.customer_resolver import resolve_or_create_customer
from app.services.discount_service import (
    DiscountNotEligibleError, DiscountNotFoundError, apply_discount,
)
from app.services.reservation_service import commit_reservation

router = APIRouter(prefix="/v1/storefront", tags=["Storefront Checkout"])


class CartSummaryOut(BaseModel):
    cart_token: str
    subtotal_cents: int
    discount_cents: int
    tax_cents: int
    shipping_cents: int
    total_cents: int
    currency_code: str
    discount_code: str | None


class DiscountApplyIn(BaseModel):
    code: str


class DiscountApplyOut(BaseModel):
    cart_token: str
    discount_code: str
    discount_type: str
    discount_cents: int
    final_subtotal_cents: int
    is_free_shipping: bool


class SubmitOrderIn(BaseModel):
    cart_token: str
    payment_provider: str
    payment_reference: str
    customer_email: str | None = None
    customer_phone: str | None = None
    shipping_address: dict | None = None
    billing_address: dict | None = None
    discount_code: str | None = None


class OrderOut(BaseModel):
    id: str
    channel_id: str
    status: str
    customer_email: str | None
    subtotal_cents: int
    discount_cents: int
    tax_cents: int
    shipping_cents: int
    total_cents: int
    currency_code: str


def _load_cart_items(db: Session, channel_id: UUID, cart_token: str) -> list[tuple[CartItem, Product]]:
    rows = db.execute(
        select(CartItem, Product)
        .join(Product, CartItem.product_id == Product.id)
        .where(
            CartItem.cart_token == cart_token,
            CartItem.channel_id == channel_id,
        )
    ).all()
    return list(rows)


@router.get("/cart/{cart_token}/summary", response_model=CartSummaryOut)
def cart_summary(
    cart_token: str,
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db_admin)],
    destination_country: str | None = Query(default=None),
    destination_state: str | None = Query(default=None),
    discount_code: str | None = Query(default=None),
) -> CartSummaryOut:
    """Return a pre-payment summary: subtotal + discount + tax + shipping + total."""
    rows = _load_cart_items(db, channel.id, cart_token)
    if not rows:
        return CartSummaryOut(
            cart_token=cart_token, subtotal_cents=0, discount_cents=0,
            tax_cents=0, shipping_cents=0, total_cents=0,
            currency_code=channel.currency_code, discount_code=None,
        )

    subtotal = sum(ci.unit_price_cents * ci.quantity for ci, _ in rows)

    # Discount
    discount_cents = 0
    applied_code = None
    if discount_code:
        try:
            result = apply_discount(
                db, tenant_id=channel.tenant_id, channel_id=channel.id,
                code=discount_code, cart_subtotal_cents=subtotal,
            )
            discount_cents = result["discount_amount_cents"]
            applied_code = discount_code
        except (DiscountNotFoundError, DiscountNotEligibleError):
            pass

    discounted_subtotal = subtotal - discount_cents

    # Tax (if destination provided)
    tax_cents = 0
    if destination_country:
        try:
            from app.services.tax_service import calculate_tax_for_cart
            cart_lines = [
                {"product_id": ci.product_id, "quantity": ci.quantity,
                 "unit_price_cents": ci.unit_price_cents}
                for ci, _ in rows
            ]
            tax_result = calculate_tax_for_cart(
                db, channel_id=channel.id,
                destination_country=destination_country,
                destination_state=destination_state,
                cart_lines=cart_lines,
                currency=channel.currency_code,
            )
            tax_cents = tax_result["total_tax_cents"]
        except Exception:
            pass

    total = discounted_subtotal + tax_cents
    return CartSummaryOut(
        cart_token=cart_token, subtotal_cents=subtotal, discount_cents=discount_cents,
        tax_cents=tax_cents, shipping_cents=0, total_cents=total,
        currency_code=channel.currency_code, discount_code=applied_code,
    )


@router.post("/cart/{cart_token}/discount", response_model=DiscountApplyOut)
def apply_cart_discount(
    cart_token: str,
    body: DiscountApplyIn,
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> DiscountApplyOut:
    """Validate a discount code against the current cart subtotal."""
    rows = _load_cart_items(db, channel.id, cart_token)
    subtotal = sum(ci.unit_price_cents * ci.quantity for ci, _ in rows)

    try:
        result = apply_discount(
            db, tenant_id=channel.tenant_id, channel_id=channel.id,
            code=body.code, cart_subtotal_cents=subtotal,
        )
    except DiscountNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except DiscountNotEligibleError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return DiscountApplyOut(
        cart_token=cart_token,
        discount_code=body.code,
        discount_type=result["discount_type"],
        discount_cents=result["discount_amount_cents"],
        final_subtotal_cents=result["final_total_cents"],
        is_free_shipping=result["is_free_shipping"],
    )


@router.post("/orders", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def submit_order(
    body: SubmitOrderIn,
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> OrderOut:
    """Path 2: create an order from a paid cart.

    The caller's frontend has already collected payment; this endpoint receives
    the payment reference, creates the Order row, commits stock reservations to
    StockMovements, and clears the cart.
    """
    rows = _load_cart_items(db, channel.id, body.cart_token)
    if not rows:
        raise HTTPException(status_code=400, detail="Cart is empty")

    subtotal = sum(ci.unit_price_cents * ci.quantity for ci, _ in rows)

    # Discount
    discount_cents = 0
    if body.discount_code:
        try:
            dr = apply_discount(
                db, tenant_id=channel.tenant_id, channel_id=channel.id,
                code=body.discount_code, cart_subtotal_cents=subtotal,
            )
            discount_cents = dr["discount_amount_cents"]
        except (DiscountNotFoundError, DiscountNotEligibleError):
            pass

    total = subtotal - discount_cents

    # Customer resolution (optional)
    customer_id = None
    if body.customer_email or body.customer_phone:
        cust = resolve_or_create_customer(
            db, channel.tenant_id, channel.id,
            email=body.customer_email, phone=body.customer_phone,
        )
        if cust:
            customer_id = cust.id

    # Create Order
    order = Order(
        tenant_id=channel.tenant_id,
        channel_id=channel.id,
        status="confirmed",
        customer_id=customer_id,
        customer_email=body.customer_email,
        customer_phone=body.customer_phone,
        subtotal_cents=subtotal,
        discount_cents=discount_cents,
        tax_cents=0,
        shipping_cents=0,
        total_cents=total,
        currency_code=channel.currency_code,
        shipping_address=body.shipping_address,
        billing_address=body.billing_address,
    )
    db.add(order)
    db.flush()

    # Order lines + commit reservations
    for cart_item, product in rows:
        db.add(OrderLine(
            tenant_id=channel.tenant_id,
            order_id=order.id,
            product_id=product.id,
            title=product.name,
            sku=product.sku,
            quantity=cart_item.quantity,
            unit_price_cents=cart_item.unit_price_cents,
            line_total_cents=cart_item.unit_price_cents * cart_item.quantity,
        ))
        if cart_item.reservation_id:
            commit_reservation(db, cart_item.reservation_id)
        db.delete(cart_item)

    # Payment record
    db.add(OrderPayment(
        tenant_id=channel.tenant_id,
        order_id=order.id,
        provider=body.payment_provider,
        provider_ref=body.payment_reference,
        method="card",
        amount_cents=total,
        status="paid",
    ))

    db.commit()
    db.refresh(order)
    return OrderOut(
        id=str(order.id),
        channel_id=str(order.channel_id),
        status=order.status,
        customer_email=order.customer_email,
        subtotal_cents=order.subtotal_cents,
        discount_cents=order.discount_cents,
        tax_cents=order.tax_cents,
        shipping_cents=order.shipping_cents,
        total_cents=order.total_cents,
        currency_code=order.currency_code,
    )
```

- [ ] **Step 4: Mount the checkout router**

In `services/api/app/main.py`, add:
```python
from app.routers.storefront import checkout as storefront_checkout
```
and `app.include_router(storefront_checkout.router)`.

- [ ] **Step 5: Run tests**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/main.py $CONTAINER:/app/app/main.py
docker cp services/api/app/routers/storefront $CONTAINER:/app/app/routers/storefront
docker cp services/api/tests/storefront $CONTAINER:/app/tests/storefront
docker compose restart api
sleep 5
docker compose exec api python -m pytest tests/storefront/test_checkout.py -v
docker compose exec api rm -rf /app/tests/storefront
```
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/routers/storefront/checkout.py \
        services/api/app/main.py \
        services/api/tests/storefront/test_checkout.py
git commit -m "feat(storefront): cart summary, discount apply, Path-2 order submission"
```

---

### Task 5: Integration smoke test

**Files:**
- Create: `services/api/tests/integration/test_storefront_e2e.py`

- [ ] **Step 1: Write the integration test**

Create `services/api/tests/integration/test_storefront_e2e.py`:

```python
"""End-to-end smoke test for the headless storefront API.

Exercises the full shopper flow:
1. Create a cart
2. Browse catalog, add items
3. Apply a discount
4. Get checkout summary (subtotal + discount + tax)
5. Submit order (Path 2)
6. Verify stock was committed and cart cleared
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import (
    Channel, Discount, InventoryPool, InventoryPoolShop, Order,
    Product, Shop, StockMovement, StockReservation, Tenant, TaxRegion, TaxRule,
)


@pytest.fixture()
def setup(db, tenant: Tenant, shop: Shop):
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    channel = Channel(
        tenant_id=tenant.id, type="headless", name=f"headless-{uuid.uuid4().hex[:6]}",
        config={}, inventory_pool_id=pool.id, currency_code="INR",
        tax_included_in_price=False,
    )
    db.add(channel)
    db.flush()

    product = Product(
        tenant_id=tenant.id, name="Handmade Mug", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=10000, product_type="physical", status="active",
        slug="handmade-mug", weight_grams=400,
    )
    db.add(product)
    db.flush()
    db.add(StockMovement(
        tenant_id=tenant.id, shop_id=shop.id, product_id=product.id,
        quantity_delta=100, movement_type="purchase_receipt",
        idempotency_key=f"seed-{uuid.uuid4().hex}",
    ))

    # 10% discount
    discount = Discount(
        tenant_id=tenant.id, name="10% off", code="TEN",
        discount_type="percentage", value_bps=1000, status="active",
    )
    db.add(discount)

    # India GST 18% region
    region = TaxRegion(tenant_id=tenant.id, name="India GST", country_code="IN")
    db.add(region)
    db.flush()
    db.add(TaxRule(
        tenant_id=tenant.id, region_id=region.id,
        tax_class="standard", label="GST 18%",
        components=[{"label": "GST", "rate_bps": 1800}],
    ))
    db.commit()

    return {"channel": channel, "product": product}


def _h(setup):
    return {"X-Channel-Id": str(setup["channel"].id)}


def test_full_shopper_flow(db, tenant: Tenant, setup) -> None:
    client = TestClient(app)

    # 1. Browse catalog
    catalog = client.get("/v1/storefront/products", headers=_h(setup))
    assert catalog.status_code == 200
    assert any(p["name"] == "Handmade Mug" for p in catalog.json()["items"])

    # 2. Get product by slug
    detail = client.get("/v1/storefront/products/handmade-mug", headers=_h(setup))
    assert detail.status_code == 200
    assert detail.json()["slug"] == "handmade-mug"

    # 3. Create cart and add 2 mugs
    cart = client.post("/v1/storefront/cart", headers=_h(setup)).json()
    token = cart["cart_token"]

    add = client.post(f"/v1/storefront/cart/{token}/items", json={
        "product_id": str(setup["product"].id), "quantity": 2,
    }, headers=_h(setup))
    assert add.status_code == 200
    assert add.json()["total_cents"] == 20000

    # Reservation created
    reservations = db.execute(
        select(StockReservation).where(
            StockReservation.cart_token == token, StockReservation.status == "active"
        )
    ).scalars().all()
    assert len(reservations) == 1
    assert reservations[0].quantity == 2

    # 4. Apply discount
    disc = client.post(f"/v1/storefront/cart/{token}/discount",
                       json={"code": "TEN"}, headers=_h(setup))
    assert disc.status_code == 200
    assert disc.json()["discount_cents"] == 2000  # 20000 * 10%
    assert disc.json()["final_subtotal_cents"] == 18000

    # 5. Get summary with tax
    summary = client.get(
        f"/v1/storefront/cart/{token}/summary",
        params={"destination_country": "IN", "discount_code": "TEN"},
        headers=_h(setup),
    )
    assert summary.status_code == 200
    s = summary.json()
    assert s["subtotal_cents"] == 20000
    assert s["discount_cents"] == 2000
    assert s["tax_cents"] == 3240  # (20000 - 2000) * 18% = 18000 * 18% = 3240
    assert s["total_cents"] == 21240  # 18000 + 3240

    # 6. Submit order
    order_resp = client.post("/v1/storefront/orders", json={
        "cart_token": token,
        "payment_provider": "stripe",
        "payment_reference": "pi_test_stripe_123",
        "customer_email": "mug-buyer@example.com",
        "shipping_address": {"country": "IN", "city": "Bangalore"},
        "discount_code": "TEN",
    }, headers=_h(setup))
    assert order_resp.status_code == 201, order_resp.text
    order = order_resp.json()
    assert order["status"] == "confirmed"
    assert order["customer_email"] == "mug-buyer@example.com"
    assert order["discount_cents"] == 2000
    assert order["total_cents"] == 18000  # 20000 - 2000 (tax computed separately by hosted checkout)

    # 7. Cart is cleared
    cart_after = client.get(f"/v1/storefront/cart/{token}", headers=_h(setup)).json()
    assert cart_after["items"] == []

    # 8. Stock reservation committed (status changed)
    res_after = db.execute(
        select(StockReservation).where(StockReservation.cart_token == token)
    ).scalars().all()
    assert all(r.status == "committed" for r in res_after)
```

- [ ] **Step 2: Run integration test**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest tests/integration/test_storefront_e2e.py -v
docker compose exec api rm -rf /app/tests
```
Expected: 1 passed.

- [ ] **Step 3: Run full storefront suite**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest \
  tests/storefront/ \
  tests/integration/test_storefront_e2e.py \
  -v 2>&1 | tail -10
docker compose exec api rm -rf /app/tests
```
Expected ballpark: ~21 tests passing (7 catalog + 8 cart + 4 checkout + 1 e2e).

- [ ] **Step 4: Commit**

```bash
git add services/api/tests/integration/test_storefront_e2e.py
git commit -m "test(storefront): end-to-end shopper flow from catalog to order submission"
```

---

## Done. Summary of what shipped

- `cart_items` table with RLS (links cart_token, channel, product, reservation)
- `app/routers/storefront/auth.py` — `X-Channel-Id` header dependency
- `app/routers/storefront/catalog.py` — `GET /v1/storefront/products`, `GET /v1/storefront/products/{slug_or_id}`
- `app/routers/storefront/cart.py` — `POST /v1/storefront/cart`, `GET /v1/storefront/cart/{token}`, `POST/DELETE /v1/storefront/cart/{token}/items` (with automatic reservation management)
- `app/routers/storefront/checkout.py` — `GET /v1/storefront/cart/{token}/summary`, `POST /v1/storefront/cart/{token}/discount`, `POST /v1/storefront/orders`
- ~21 tests

## What this unlocks

- **Custom storefronts** can wire a complete shopping experience using only IMS endpoints — no Shopify, no WooCommerce needed
- **Hosted checkout (Phase 2)**: `POST /v1/storefront/checkout/session` (Path 1 — IMS-hosted checkout page) builds directly on top of the cart and checkout infrastructure here
- **Shopify/WooCommerce connectors**: these will sync catalog INTO Shopify/Woo and pull orders BACK into IMS — orthogonal to the headless API, can ship concurrently

## Follow-up work (not in this plan)

- Shopper account auth (signup, login, order history) — `POST /v1/storefront/customers`
- Pagination cursor-based for large catalogs
- `GET /v1/storefront/collections`, `GET /v1/storefront/store`, `GET /v1/storefront/policies`
- Currency-switching (`?currency=USD`) — plugs into the FX engine
- Hosted checkout (Path 1 — `POST /v1/storefront/checkout/session`)
- Rate limiting per origin on storefront endpoints

---

*End of plan.*
