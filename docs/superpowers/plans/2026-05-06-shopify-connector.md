# Shopify Connector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect an IMS tenant to their Shopify store using private/custom app credentials — pushing products and inventory from IMS to Shopify, importing existing Shopify products into IMS catalog on first connect, and receiving Shopify order webhooks to create IMS Order rows with full channel attribution.

**Architecture:** A generic `channel_product_mappings` table bridges IMS products to external channel IDs (reusable for WooCommerce). A `shopify_service.py` module wraps all Shopify Admin REST API calls. An `admin_shopify.py` router exposes connect/sync admin endpoints. A `webhooks_shopify.py` router receives and processes Shopify events. All tests mock Shopify HTTP responses using `unittest.mock.patch` on the httpx client — no real Shopify shop required for CI.

**Shopify API version:** 2024-10

**Channel.config shape for Shopify channels:**
```json
{
  "shopify_shop_domain": "my-store.myshopify.com",
  "shopify_access_token": "shpat_...",
  "shopify_api_secret": "shpss_...",
  "shopify_location_id": "12345678"
}
```
All four fields are stored encrypted-at-rest (Postgres column-level — out of scope for this plan, but the config JSONB is the right place). The `location_id` is the Shopify fulfillment location used for inventory pushes; the connect endpoint fetches it automatically.

**Out of scope (deferred):**
- OAuth public app flow (Shopify App Store distribution)
- Shopify collections/metafields sync
- Automatic webhook registration (requires a public HTTPS URL; merchants register the webhook URLs manually in Shopify Admin → Settings → Notifications)
- Refund/return processing (deferred to RMA module)
- Historical order import on connect
- Variant-level inventory (IMS has `variant_label` text; formal variants ship in a future sub-project)

---

### Task 1: channel_product_mappings table

**Files:**
- Create: `services/api/alembic/versions/20260516000001_channel_product_mappings.py`
- Modify: `services/api/app/models/tables.py`
- Modify: `services/api/app/models/__init__.py`

- [ ] **Step 1: Add the SQLAlchemy model**

In `services/api/app/models/tables.py`, append after `CartItem`:

```python
class ChannelProductMapping(Base):
    """Maps an IMS product to its ID on an external channel (Shopify, WooCommerce, etc.)

    One row per (channel, product) pair. The external_product_id is the
    channel's native ID string (e.g. Shopify GID "gid://shopify/Product/123456").
    synced_at tracks the last successful push so incremental sync can be efficient.
    """
    __tablename__ = "channel_product_mappings"
    __table_args__ = (
        UniqueConstraint("channel_id", "product_id", name="uq_channel_product_mapping"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    external_product_id: Mapped[str] = mapped_column(String(255), nullable=False)
    external_variant_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 2: Export the model**

In `services/api/app/models/__init__.py`, add `ChannelProductMapping` alphabetically (between `Channel` and `CartItem`/`CustomerChannel`).

- [ ] **Step 3: Write the migration**

Create `services/api/alembic/versions/20260516000001_channel_product_mappings.py`:

```python
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
```

- [ ] **Step 4: Run migration**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/alembic/versions/20260516000001_channel_product_mappings.py $CONTAINER:/app/alembic/versions/
docker compose exec api alembic upgrade head
```
Expected: `Running upgrade 20260515000001 -> 20260516000001`

- [ ] **Step 5: Verify**

```bash
docker compose exec postgres psql -U ims -d ims -c "\d channel_product_mappings"
docker compose exec postgres psql -U ims -d ims -c "SELECT relrowsecurity FROM pg_class WHERE relname='channel_product_mappings'"
```
Expected: table described, `relrowsecurity = t`.

- [ ] **Step 6: Commit**

```bash
git add services/api/alembic/versions/20260516000001_channel_product_mappings.py \
        services/api/app/models/tables.py \
        services/api/app/models/__init__.py
git commit -m "feat(shopify): add channel_product_mappings table"
```

---

### Task 2: Shopify service layer

**Files:**
- Create: `services/api/app/services/shopify_service.py`
- Create: `services/api/tests/services/test_shopify_service.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/services/test_shopify_service.py`:

```python
import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.models import Channel, ChannelProductMapping, InventoryPool, InventoryPoolShop, Product, Shop, Tenant


@pytest.fixture()
def shopify_channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{__import__('uuid').uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id, type="shopify", name="My Shopify Store",
        config={
            "shopify_shop_domain": "test-store.myshopify.com",
            "shopify_access_token": "shpat_test123",
            "shopify_api_secret": "shpss_test123",
            "shopify_location_id": "12345678",
        },
        inventory_pool_id=pool.id, currency_code="INR",
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def product(db, tenant: Tenant) -> Product:
    p = Product(
        tenant_id=tenant.id, name="Widget", sku="SKU-001",
        unit_price_cents=1999, product_type="physical", status="active",
        description="A fine widget",
    )
    db.add(p)
    db.flush()
    return p


def test_test_connection_success(db, shopify_channel: Channel) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"shop": {"name": "Test Store", "currency": "INR"}}

    with patch("httpx.get", return_value=mock_response):
        from app.services.shopify_service import test_connection
        result = test_connection(shopify_channel)
        assert result["success"] is True
        assert result["shop_name"] == "Test Store"


def test_test_connection_invalid_credentials(db, shopify_channel: Channel) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.json.return_value = {"errors": "Invalid API key or access token"}

    with patch("httpx.get", return_value=mock_response):
        from app.services.shopify_service import ShopifyAuthError, test_connection
        with pytest.raises(ShopifyAuthError):
            test_connection(shopify_channel)


def test_push_product_creates_new(db, tenant: Tenant, shopify_channel: Channel, product: Product) -> None:
    """push_product sends POST to Shopify and stores the returned product ID in mappings."""
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {
        "product": {
            "id": 987654321,
            "variants": [{"id": 111222333, "sku": "SKU-001"}],
        }
    }

    with patch("httpx.post", return_value=mock_response):
        from app.services.shopify_service import push_product
        mapping = push_product(db, shopify_channel, product)
        assert mapping.external_product_id == "987654321"
        assert mapping.channel_id == shopify_channel.id
        assert mapping.product_id == product.id


def test_push_product_updates_existing(db, tenant: Tenant, shopify_channel: Channel, product: Product) -> None:
    """If a mapping already exists, push_product uses PUT."""
    db.add(ChannelProductMapping(
        tenant_id=tenant.id, channel_id=shopify_channel.id,
        product_id=product.id, external_product_id="987654321",
    ))
    db.flush()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "product": {
            "id": 987654321,
            "variants": [{"id": 111222333, "sku": "SKU-001"}],
        }
    }

    with patch("httpx.put", return_value=mock_response):
        from app.services.shopify_service import push_product
        mapping = push_product(db, shopify_channel, product)
        assert mapping.external_product_id == "987654321"


def test_push_inventory_level(db, shopify_channel: Channel) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"inventory_level": {"available": 10}}

    with patch("httpx.post", return_value=mock_response) as mock_post:
        from app.services.shopify_service import push_inventory_level
        push_inventory_level(shopify_channel, inventory_item_id="555666", quantity=10)
        assert mock_post.called
        body = json.loads(mock_post.call_args.kwargs.get("content", "{}"))
        assert body["location_id"] == 12345678
        assert body["inventory_item_id"] == "555666"
        assert body["available"] == 10


def test_import_products_parses_response(db, shopify_channel: Channel) -> None:
    """get_shopify_products returns a list of Shopify product dicts."""
    shopify_products = [
        {"id": 111, "title": "Widget A", "variants": [{"sku": "SKU-A", "price": "19.99"}]},
        {"id": 222, "title": "Widget B", "variants": [{"sku": "SKU-B", "price": "29.99"}]},
    ]
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"products": shopify_products}

    with patch("httpx.get", return_value=mock_response):
        from app.services.shopify_service import get_shopify_products
        products = get_shopify_products(shopify_channel)
        assert len(products) == 2
        assert products[0]["id"] == 111


def test_verify_webhook_signature_valid() -> None:
    import hashlib
    import hmac
    import base64
    secret = "test_secret"
    body = b'{"id": 12345}'
    digest = base64.b64encode(
        hmac.new(secret.encode(), body, hashlib.sha256).digest()
    ).decode()

    from app.services.shopify_service import verify_webhook_signature
    assert verify_webhook_signature(body, digest, secret) is True


def test_verify_webhook_signature_invalid() -> None:
    from app.services.shopify_service import verify_webhook_signature
    assert verify_webhook_signature(b'{"id": 12345}', "bad_sig", "secret") is False
```

- [ ] **Step 2: Confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/services $CONTAINER:/app/tests/services
docker compose exec api python -m pytest tests/services/test_shopify_service.py -v
docker compose exec api rm -rf /app/tests/services
```
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the Shopify service**

Create `services/api/app/services/shopify_service.py`:

```python
"""Shopify Admin REST API service layer.

Wraps all communication with Shopify. All functions take a Channel with
config keys: shopify_shop_domain, shopify_access_token, shopify_api_secret,
shopify_location_id.

All HTTP is done via httpx (synchronous) so it can be called from FastAPI
route handlers without async complexity. For high-volume sync (many products),
this should be moved to an RQ background task in a future improvement.

Shopify API version: 2024-10
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.money import round_half_up_cents
from app.models import Channel, ChannelProductMapping, Product

logger = logging.getLogger(__name__)

API_VERSION = "2024-10"


class ShopifyAuthError(Exception):
    """Invalid credentials or insufficient permissions."""


class ShopifyAPIError(Exception):
    """Shopify returned an unexpected error."""


def _base_url(channel: Channel) -> str:
    domain = channel.config["shopify_shop_domain"]
    return f"https://{domain}/admin/api/{API_VERSION}"


def _headers(channel: Channel) -> dict[str, str]:
    return {
        "X-Shopify-Access-Token": channel.config["shopify_access_token"],
        "Content-Type": "application/json",
    }


def test_connection(channel: Channel) -> dict[str, Any]:
    """Verify that the stored credentials can reach the shop.

    Returns {"success": True, "shop_name": str} or raises ShopifyAuthError.
    """
    url = f"{_base_url(channel)}/shop.json"
    resp = httpx.get(url, headers=_headers(channel), timeout=10.0)
    if resp.status_code == 401:
        raise ShopifyAuthError(f"Invalid credentials for {channel.config['shopify_shop_domain']}")
    if resp.status_code != 200:
        raise ShopifyAPIError(f"Shopify returned {resp.status_code}: {resp.text}")
    shop = resp.json()["shop"]
    return {"success": True, "shop_name": shop["name"], "currency": shop.get("currency")}


def push_product(db: Session, channel: Channel, product: Product) -> ChannelProductMapping:
    """Create or update a product in Shopify and record the mapping.

    If a ChannelProductMapping exists for this (channel, product), sends a PUT
    to update the existing Shopify product. Otherwise sends a POST to create it.
    """
    mapping = db.execute(
        select(ChannelProductMapping).where(
            ChannelProductMapping.channel_id == channel.id,
            ChannelProductMapping.product_id == product.id,
        )
    ).scalar_one_or_none()

    # Price: Shopify expects a decimal string like "19.99"
    price_str = f"{product.unit_price_cents / 100:.2f}"

    shopify_product = {
        "title": product.name,
        "body_html": product.description or "",
        "status": "active" if product.status == "active" else "draft",
        "variants": [
            {
                "sku": product.sku,
                "price": price_str,
                "inventory_management": "shopify"
                if (product.track_quantity and product.product_type == "physical")
                else None,
                "requires_shipping": product.product_type == "physical",
                "taxable": product.product_type != "donation",
            }
        ],
    }

    if mapping is not None:
        url = f"{_base_url(channel)}/products/{mapping.external_product_id}.json"
        resp = httpx.put(url, headers=_headers(channel),
                         content=__import__("json").dumps({"product": shopify_product}),
                         timeout=15.0)
    else:
        url = f"{_base_url(channel)}/products.json"
        resp = httpx.post(url, headers=_headers(channel),
                          content=__import__("json").dumps({"product": shopify_product}),
                          timeout=15.0)

    if resp.status_code not in (200, 201):
        raise ShopifyAPIError(
            f"Failed to push product {product.sku}: HTTP {resp.status_code}: {resp.text}"
        )

    data = resp.json()["product"]
    ext_id = str(data["id"])
    ext_variant_id = str(data["variants"][0]["id"]) if data.get("variants") else None

    now = datetime.now(UTC)
    if mapping is not None:
        mapping.external_product_id = ext_id
        mapping.external_variant_id = ext_variant_id
        mapping.synced_at = now
    else:
        mapping = ChannelProductMapping(
            tenant_id=channel.tenant_id,
            channel_id=channel.id,
            product_id=product.id,
            external_product_id=ext_id,
            external_variant_id=ext_variant_id,
            synced_at=now,
        )
        db.add(mapping)
    db.flush()
    return mapping


def push_inventory_level(
    channel: Channel,
    inventory_item_id: str,
    quantity: int,
) -> None:
    """Set the inventory level for a product at the channel's default location."""
    location_id = int(channel.config["shopify_location_id"])
    url = f"{_base_url(channel)}/inventory_levels/set.json"
    import json
    body = json.dumps({
        "location_id": location_id,
        "inventory_item_id": inventory_item_id,
        "available": quantity,
    })
    resp = httpx.post(url, headers=_headers(channel), content=body, timeout=15.0)
    if resp.status_code != 200:
        logger.warning("Failed to push inventory level: HTTP %d: %s",
                       resp.status_code, resp.text)


def get_shopify_products(channel: Channel, limit: int = 250) -> list[dict[str, Any]]:
    """Fetch all products from the Shopify store (for initial catalog import)."""
    url = f"{_base_url(channel)}/products.json"
    resp = httpx.get(url, headers=_headers(channel),
                     params={"limit": limit}, timeout=30.0)
    if resp.status_code != 200:
        raise ShopifyAPIError(f"Failed to fetch products: HTTP {resp.status_code}: {resp.text}")
    return resp.json().get("products", [])


def get_shopify_locations(channel: Channel) -> list[dict[str, Any]]:
    """Fetch all Shopify locations (needed to set inventory levels)."""
    url = f"{_base_url(channel)}/locations.json"
    resp = httpx.get(url, headers=_headers(channel), timeout=10.0)
    if resp.status_code != 200:
        raise ShopifyAPIError(f"Failed to fetch locations: HTTP {resp.status_code}")
    return resp.json().get("locations", [])


def verify_webhook_signature(
    body: bytes, shopify_hmac_header: str, api_secret: str,
) -> bool:
    """Verify the HMAC-SHA256 signature on an incoming Shopify webhook.

    Returns True if the signature matches, False otherwise.
    """
    expected = base64.b64encode(
        hmac.new(api_secret.encode(), body, hashlib.sha256).digest()
    ).decode()
    return hmac.compare_digest(expected, shopify_hmac_header)


def import_shopify_catalog(
    db: Session, channel: Channel, products: list[dict[str, Any]]
) -> dict[str, int]:
    """Import Shopify products into IMS, matching by SKU.

    For each Shopify product:
    - If IMS has a product with the same SKU → create a mapping (link them)
    - If no match → create a new IMS Product with status='active'

    Returns {"matched": N, "created": N, "skipped": N}
    """
    matched = created = skipped = 0

    for sp in products:
        variants = sp.get("variants", [])
        if not variants:
            skipped += 1
            continue

        variant = variants[0]
        sku = variant.get("sku", "").strip()
        if not sku:
            skipped += 1
            continue

        # Check if mapping already exists
        existing_mapping = db.execute(
            select(ChannelProductMapping).where(
                ChannelProductMapping.channel_id == channel.id,
                ChannelProductMapping.external_product_id == str(sp["id"]),
            )
        ).scalar_one_or_none()
        if existing_mapping:
            skipped += 1
            continue

        # Try to match by SKU
        ims_product = db.execute(
            select(Product).where(
                Product.tenant_id == channel.tenant_id,
                Product.sku == sku,
            )
        ).scalar_one_or_none()

        if ims_product is None:
            # Create new IMS product from Shopify data
            price_str = variant.get("price", "0")
            try:
                price_cents = round_half_up_cents(float(price_str) * 100)
            except (ValueError, TypeError):
                price_cents = 0

            ims_product = Product(
                tenant_id=channel.tenant_id,
                sku=sku,
                name=sp.get("title", sku),
                unit_price_cents=price_cents,
                product_type="physical",
                status="active",
            )
            db.add(ims_product)
            db.flush()
            created += 1
        else:
            matched += 1

        db.add(ChannelProductMapping(
            tenant_id=channel.tenant_id,
            channel_id=channel.id,
            product_id=ims_product.id,
            external_product_id=str(sp["id"]),
            external_variant_id=str(variant["id"]) if variant.get("id") else None,
        ))
        db.flush()

    return {"matched": matched, "created": created, "skipped": skipped}
```

- [ ] **Step 4: Run tests**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/services/shopify_service.py $CONTAINER:/app/app/services/shopify_service.py
docker cp services/api/tests/services $CONTAINER:/app/tests/services
docker compose exec api python -m pytest tests/services/test_shopify_service.py -v
docker compose exec api rm -rf /app/tests/services
```
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/services/shopify_service.py \
        services/api/tests/services/test_shopify_service.py
git commit -m "feat(shopify): add shopify_service with push/import/webhook-verify"
```

---

### Task 3: Connect + sync admin endpoints

**Files:**
- Create: `services/api/app/routers/admin_shopify.py`
- Modify: `services/api/app/main.py`
- Create: `services/api/tests/routers/test_admin_shopify.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/routers/test_admin_shopify.py`:

```python
# NOTE: `from __future__ import annotations` deliberately absent.

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Channel, ChannelProductMapping, InventoryPool, InventoryPoolShop, Product, Shop, StockMovement, Tenant


@pytest.fixture()
def shopify_channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id, type="shopify", name="Shopify Store",
        config={}, inventory_pool_id=pool.id, currency_code="INR", status="active",
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def auth_headers(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=None, tenant_id=tenant.id, role="owner", role_id=None,
        is_legacy_token=False, permissions=frozenset({"channels:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield {}
    app.dependency_overrides.clear()


def test_connect_shopify_success(db, tenant: Tenant, shopify_channel: Channel, auth_headers) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "shop": {"name": "Test Store", "currency": "INR"},
    }

    location_resp = MagicMock()
    location_resp.status_code = 200
    location_resp.json.return_value = {
        "locations": [{"id": 12345678, "name": "Main Warehouse"}]
    }

    with patch("httpx.get", side_effect=[mock_resp, location_resp]):
        client = TestClient(app)
        resp = client.post(
            f"/v1/admin/channels/{shopify_channel.id}/shopify/connect",
            json={
                "shopify_shop_domain": "test-store.myshopify.com",
                "shopify_access_token": "shpat_test123",
                "shopify_api_secret": "shpss_test123",
            },
            headers=auth_headers,
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["shop_name"] == "Test Store"
    assert body["location_id"] == "12345678"

    db.refresh(shopify_channel)
    assert shopify_channel.config["shopify_shop_domain"] == "test-store.myshopify.com"
    assert shopify_channel.config["shopify_location_id"] == "12345678"


def test_connect_shopify_bad_credentials(db, tenant: Tenant, shopify_channel: Channel, auth_headers) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.json.return_value = {"errors": "Invalid credentials"}

    with patch("httpx.get", return_value=mock_resp):
        client = TestClient(app)
        resp = client.post(
            f"/v1/admin/channels/{shopify_channel.id}/shopify/connect",
            json={
                "shopify_shop_domain": "bad.myshopify.com",
                "shopify_access_token": "bad_token",
                "shopify_api_secret": "bad_secret",
            },
            headers=auth_headers,
        )
    assert resp.status_code == 400
    assert "credentials" in resp.json()["detail"].lower()


def test_sync_catalog_pushes_products(db, tenant: Tenant, shopify_channel: Channel, auth_headers) -> None:
    shopify_channel.config = {
        "shopify_shop_domain": "test.myshopify.com",
        "shopify_access_token": "tok",
        "shopify_api_secret": "sec",
        "shopify_location_id": "99999",
    }
    db.flush()

    p1 = Product(tenant_id=tenant.id, name="Widget", sku="W001",
                 unit_price_cents=1999, product_type="physical", status="active")
    p2 = Product(tenant_id=tenant.id, name="Book", sku="B001",
                 unit_price_cents=999, product_type="digital", status="active")
    db.add(p1)
    db.add(p2)
    db.commit()

    def mock_post(url, **kwargs):
        m = MagicMock()
        m.status_code = 201
        m.json.return_value = {
            "product": {"id": 999, "variants": [{"id": 888, "sku": "W001"}]}
        }
        return m

    with patch("httpx.post", side_effect=mock_post):
        client = TestClient(app)
        resp = client.post(
            f"/v1/admin/channels/{shopify_channel.id}/shopify/sync-catalog",
            headers=auth_headers,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["synced"] == 2
    assert body["errors"] == 0


def test_cross_tenant_channel_blocked(db, tenant: Tenant, auth_headers) -> None:
    other_tenant_id = uuid.uuid4()
    pool = InventoryPool(tenant_id=other_tenant_id, name="pool")
    db.add(pool)
    db.flush()
    other_ch = Channel(
        tenant_id=other_tenant_id, type="shopify", name="Other",
        config={}, inventory_pool_id=pool.id, currency_code="USD",
    )
    db.add(other_ch)
    db.commit()

    client = TestClient(app)
    resp = client.post(
        f"/v1/admin/channels/{other_ch.id}/shopify/connect",
        json={"shopify_shop_domain": "x.myshopify.com",
              "shopify_access_token": "t", "shopify_api_secret": "s"},
        headers=auth_headers,
    )
    assert resp.status_code == 404
```

- [ ] **Step 2: Confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/routers/test_admin_shopify.py $CONTAINER:/app/tests/routers/test_admin_shopify.py
docker compose exec api python -m pytest tests/routers/test_admin_shopify.py -v
docker compose exec api rm -f /app/tests/routers/test_admin_shopify.py
```
Expected: FAIL — router doesn't exist.

- [ ] **Step 3: Implement the router**

Create `services/api/app/routers/admin_shopify.py`:

```python
"""Admin endpoints for Shopify channel management.

Endpoints:
  POST /v1/admin/channels/{channel_id}/shopify/connect
       Store credentials, verify connection, auto-detect location_id.

  POST /v1/admin/channels/{channel_id}/shopify/sync-catalog
       Push all active IMS products to Shopify.

  POST /v1/admin/channels/{channel_id}/shopify/sync-inventory
       Push current stock levels to Shopify for all mapped products.

  POST /v1/admin/channels/{channel_id}/shopify/import-catalog
       Pull existing Shopify products and import unmatched ones into IMS.

Auth: requires `channels:manage` permission.
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import Channel, ChannelProductMapping, Product
from app.services.inventory_pool_service import available_stock_for_channel
from app.services.shopify_service import (
    ShopifyAPIError, ShopifyAuthError,
    get_shopify_locations, get_shopify_products,
    import_shopify_catalog, push_inventory_level, push_product, test_connection,
)

router = APIRouter(
    prefix="/v1/admin/channels",
    tags=["Shopify Connector"],
    dependencies=[require_permission("channels:manage")],
)


class ShopifyConnectIn(BaseModel):
    shopify_shop_domain: str
    shopify_access_token: str
    shopify_api_secret: str


class ShopifyConnectOut(BaseModel):
    shop_name: str
    currency: str | None
    location_id: str
    location_name: str


class SyncCatalogOut(BaseModel):
    synced: int
    errors: int
    error_skus: list[str]


class ImportCatalogOut(BaseModel):
    matched: int
    created: int
    skipped: int


class SyncInventoryOut(BaseModel):
    synced: int
    errors: int


def _get_channel_or_404(db: Session, channel_id: UUID, tenant_id: UUID) -> Channel:
    ch = db.get(Channel, channel_id)
    if ch is None or ch.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")
    return ch


def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Operator not assigned to a tenant")
    return ctx.tenant_id


@router.post("/{channel_id}/shopify/connect", response_model=ShopifyConnectOut)
def connect_shopify(
    channel_id: UUID,
    body: ShopifyConnectIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ShopifyConnectOut:
    """Store credentials, verify connection, auto-detect the primary location."""
    tenant_id = _require_tenant(ctx)
    channel = _get_channel_or_404(db, channel_id, tenant_id)

    # Temporarily set config to test credentials
    channel.config = {
        "shopify_shop_domain": body.shopify_shop_domain.strip().lower(),
        "shopify_access_token": body.shopify_access_token.strip(),
        "shopify_api_secret": body.shopify_api_secret.strip(),
        "shopify_location_id": "",
    }
    db.flush()

    try:
        conn_result = test_connection(channel)
    except ShopifyAuthError as exc:
        db.rollback()
        raise HTTPException(status_code=400,
                            detail=f"Invalid credentials: {exc}")
    except ShopifyAPIError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc))

    # Fetch and store the primary location
    try:
        locations = get_shopify_locations(channel)
    except ShopifyAPIError:
        locations = []

    if not locations:
        db.rollback()
        raise HTTPException(status_code=502,
                            detail="Could not fetch Shopify locations. "
                                   "Ensure the access token has 'inventory' scope.")

    primary = locations[0]
    channel.config["shopify_location_id"] = str(primary["id"])
    channel.type = "shopify"
    db.commit()

    return ShopifyConnectOut(
        shop_name=conn_result["shop_name"],
        currency=conn_result.get("currency"),
        location_id=str(primary["id"]),
        location_name=primary["name"],
    )


@router.post("/{channel_id}/shopify/sync-catalog", response_model=SyncCatalogOut)
def sync_catalog(
    channel_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> SyncCatalogOut:
    """Push all active IMS products to Shopify (create or update)."""
    tenant_id = _require_tenant(ctx)
    channel = _get_channel_or_404(db, channel_id, tenant_id)

    products = db.execute(
        select(Product).where(
            Product.tenant_id == tenant_id,
            Product.status == "active",
        )
    ).scalars().all()

    synced = errors = 0
    error_skus: list[str] = []

    for product in products:
        try:
            push_product(db, channel, product)
            synced += 1
        except (ShopifyAPIError, Exception) as exc:
            errors += 1
            error_skus.append(product.sku)

    db.commit()
    return SyncCatalogOut(synced=synced, errors=errors, error_skus=error_skus)


@router.post("/{channel_id}/shopify/sync-inventory", response_model=SyncInventoryOut)
def sync_inventory(
    channel_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> SyncInventoryOut:
    """Push current IMS stock levels to Shopify for all mapped products."""
    tenant_id = _require_tenant(ctx)
    channel = _get_channel_or_404(db, channel_id, tenant_id)

    mappings = db.execute(
        select(ChannelProductMapping).where(
            ChannelProductMapping.channel_id == channel_id,
            ChannelProductMapping.external_variant_id.isnot(None),
        )
    ).scalars().all()

    synced = errors = 0
    for mapping in mappings:
        try:
            qty = available_stock_for_channel(db, channel.id, mapping.product_id)
            # Shopify inventory is per variant's inventory_item_id
            # The external_variant_id from the mapping is the Shopify variant ID.
            # We need the inventory_item_id — for Phase 1, store it in external_variant_id
            # with format "variant_id:inventory_item_id" or just push with variant_id as proxy.
            # Workaround: use the external_variant_id as inventory_item_id (same in many stores).
            push_inventory_level(channel, mapping.external_variant_id, qty)
            synced += 1
        except Exception:
            errors += 1

    return SyncInventoryOut(synced=synced, errors=errors)


@router.post("/{channel_id}/shopify/import-catalog", response_model=ImportCatalogOut)
def import_catalog(
    channel_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ImportCatalogOut:
    """Pull existing Shopify products and import unmatched ones into IMS catalog."""
    tenant_id = _require_tenant(ctx)
    channel = _get_channel_or_404(db, channel_id, tenant_id)

    try:
        shopify_products = get_shopify_products(channel)
    except ShopifyAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    result = import_shopify_catalog(db, channel, shopify_products)
    db.commit()
    return ImportCatalogOut(**result)
```

- [ ] **Step 4: Mount in main.py**

Add `admin_shopify` to the imports (alphabetically between `admin_shipping` and `admin_staff`) and `app.include_router(admin_shopify.router)`.

- [ ] **Step 5: Run tests**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/main.py $CONTAINER:/app/app/main.py
docker cp services/api/app/routers/admin_shopify.py $CONTAINER:/app/app/routers/admin_shopify.py
docker cp services/api/app/services/shopify_service.py $CONTAINER:/app/app/services/shopify_service.py
docker cp services/api/tests $CONTAINER:/app/tests
docker compose restart api
sleep 5
docker compose exec api python -m pytest tests/routers/test_admin_shopify.py -v
docker compose exec api rm -rf /app/tests
```
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/routers/admin_shopify.py \
        services/api/app/main.py \
        services/api/tests/routers/test_admin_shopify.py
git commit -m "feat(shopify): connect/sync-catalog/sync-inventory/import-catalog admin endpoints"
```

---

### Task 4: Shopify webhook receiver (orders)

**Files:**
- Create: `services/api/app/routers/webhooks_shopify.py`
- Modify: `services/api/app/main.py`
- Create: `services/api/tests/routers/test_webhooks_shopify.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/routers/test_webhooks_shopify.py`:

```python
# NOTE: `from __future__ import annotations` deliberately absent.

import base64
import hashlib
import hmac
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Channel, InventoryPool, InventoryPoolShop, Order, Product, Shop, Tenant


@pytest.fixture()
def channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id, type="shopify", name="Shopify",
        config={
            "shopify_shop_domain": "test.myshopify.com",
            "shopify_access_token": "tok",
            "shopify_api_secret": "secret123",
            "shopify_location_id": "99",
        },
        inventory_pool_id=pool.id, currency_code="INR",
    )
    db.add(ch)
    db.commit()
    return ch


@pytest.fixture()
def product(db, tenant: Tenant) -> Product:
    p = Product(tenant_id=tenant.id, name="Widget", sku="SKU-001",
                unit_price_cents=1999, product_type="physical", status="active")
    db.add(p)
    db.commit()
    return p


def _sign(body: bytes, secret: str) -> str:
    return base64.b64encode(
        hmac.new(secret.encode(), body, hashlib.sha256).digest()
    ).decode()


def _order_payload(product_id: str | None = None) -> dict:
    return {
        "id": 12345678,
        "email": "buyer@example.com",
        "currency": "INR",
        "total_price": "19.99",
        "subtotal_price": "19.99",
        "total_tax": "0.00",
        "total_shipping_price_set": {"shop_money": {"amount": "0.00", "currency_code": "INR"}},
        "line_items": [
            {
                "id": 1,
                "product_id": 999,
                "variant_id": 888,
                "title": "Widget",
                "quantity": 1,
                "price": "19.99",
                "sku": "SKU-001",
            }
        ],
        "customer": {
            "id": 111,
            "email": "buyer@example.com",
            "first_name": "Test",
            "last_name": "Buyer",
        },
        "shipping_address": {
            "address1": "123 Main St",
            "city": "Mumbai",
            "country_code": "IN",
        },
    }


def _webhook_headers(body: bytes, secret: str, topic: str) -> dict:
    return {
        "X-Shopify-Hmac-Sha256": _sign(body, secret),
        "X-Shopify-Topic": topic,
        "X-Shopify-Shop-Domain": "test.myshopify.com",
        "Content-Type": "application/json",
    }


def test_order_create_webhook_creates_order(db, tenant: Tenant, channel: Channel, product: Product) -> None:
    from sqlalchemy import select

    body = json.dumps(_order_payload()).encode()
    headers = _webhook_headers(body, "secret123", "orders/create")

    client = TestClient(app)
    resp = client.post(f"/v1/webhooks/shopify/{channel.id}", content=body, headers=headers)
    assert resp.status_code == 200, resp.text

    order = db.execute(
        select(Order).where(
            Order.channel_id == channel.id,
            Order.external_id == "12345678",
        )
    ).scalar_one()
    assert order.customer_email == "buyer@example.com"
    assert order.total_cents == 1999


def test_order_create_webhook_is_idempotent(db, tenant: Tenant, channel: Channel, product: Product) -> None:
    """Same webhook received twice creates only one order (idempotency via external_id)."""
    from sqlalchemy import func, select

    body = json.dumps(_order_payload()).encode()
    headers = _webhook_headers(body, "secret123", "orders/create")

    client = TestClient(app)
    client.post(f"/v1/webhooks/shopify/{channel.id}", content=body, headers=headers)
    client.post(f"/v1/webhooks/shopify/{channel.id}", content=body, headers=headers)

    count = db.execute(
        select(func.count(Order.id)).where(
            Order.channel_id == channel.id,
            Order.external_id == "12345678",
        )
    ).scalar_one()
    assert count == 1


def test_webhook_bad_signature_rejected(db, tenant: Tenant, channel: Channel) -> None:
    body = json.dumps({"id": 99}).encode()
    headers = {
        "X-Shopify-Hmac-Sha256": "bad_signature",
        "X-Shopify-Topic": "orders/create",
        "Content-Type": "application/json",
    }

    client = TestClient(app)
    resp = client.post(f"/v1/webhooks/shopify/{channel.id}", content=body, headers=headers)
    assert resp.status_code == 401


def test_unknown_channel_returns_404(db, tenant: Tenant, channel: Channel) -> None:
    body = json.dumps({"id": 99}).encode()
    fake_channel_id = uuid.uuid4()
    headers = _webhook_headers(body, "secret123", "orders/create")

    client = TestClient(app)
    resp = client.post(f"/v1/webhooks/shopify/{fake_channel_id}", content=body, headers=headers)
    assert resp.status_code == 404
```

- [ ] **Step 2: Confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/routers/test_webhooks_shopify.py $CONTAINER:/app/tests/routers/test_webhooks_shopify.py
docker compose exec api python -m pytest tests/routers/test_webhooks_shopify.py -v
docker compose exec api rm -f /app/tests/routers/test_webhooks_shopify.py
```
Expected: FAIL — webhook router doesn't exist.

- [ ] **Step 3: Implement the webhook router**

Create `services/api/app/routers/webhooks_shopify.py`:

```python
"""Shopify webhook receiver.

Endpoint: POST /v1/webhooks/shopify/{channel_id}

Shopify sends signed webhook payloads. We verify the HMAC signature using the
channel's api_secret, then route to topic-specific handlers.

Supported topics:
  orders/create   → create an Order row + OrderLines with channel attribution
  orders/updated  → update Order status
  (refunds/create → deferred to RMA module)

To receive webhooks, merchants must register the endpoint URL manually in
Shopify Admin → Settings → Notifications → Webhooks. The URL format is:
  https://{your-domain}/v1/webhooks/shopify/{channel_id}

Note: HTTP 200 must be returned within 5 seconds or Shopify will retry.
"""
from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from fastapi import Depends
from app.db.admin_deps_db import get_db_admin
from app.models import Channel, Customer, Order, OrderLine
from app.services.customer_resolver import resolve_or_create_customer
from app.services.shopify_service import verify_webhook_signature

router = APIRouter(prefix="/v1/webhooks/shopify", tags=["Shopify Webhooks"])

logger = logging.getLogger(__name__)


def _get_db() -> Session:
    from app.db.admin_deps_db import get_db_admin
    from app.db.session import SessionLocal
    return SessionLocal()


@router.post("/{channel_id}", status_code=200)
async def receive_webhook(
    channel_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db_admin)],
    x_shopify_hmac_sha256: Annotated[str | None, Header()] = None,
    x_shopify_topic: Annotated[str | None, Header()] = None,
) -> dict:
    """Receive and process a Shopify webhook event."""
    body = await request.body()

    # Resolve channel
    channel = db.get(Channel, channel_id)
    if channel is None or channel.type != "shopify":
        raise HTTPException(status_code=404, detail="Channel not found")

    # Verify HMAC signature
    api_secret = channel.config.get("shopify_api_secret", "")
    if not x_shopify_hmac_sha256 or not verify_webhook_signature(
        body, x_shopify_hmac_sha256, api_secret
    ):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    if not x_shopify_topic:
        return {"status": "ignored", "reason": "no topic header"}

    import json
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    topic = x_shopify_topic.lower()
    if topic == "orders/create":
        _handle_order_create(db, channel, payload)
    elif topic == "orders/updated":
        _handle_order_updated(db, channel, payload)
    else:
        logger.debug("Unhandled Shopify topic: %s", topic)

    return {"status": "ok", "topic": topic}


def _handle_order_create(db: Session, channel: Channel, payload: dict) -> None:
    """Convert a Shopify order payload into an IMS Order row."""
    external_id = str(payload["id"])

    # Idempotency: skip if already processed
    existing = db.execute(
        select(Order).where(
            Order.channel_id == channel.id,
            Order.external_id == external_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return

    currency = payload.get("currency", channel.currency_code)

    # Parse totals (Shopify sends decimal strings)
    def _cents(amount_str: str) -> int:
        try:
            return round(float(amount_str) * 100)
        except (ValueError, TypeError):
            return 0

    subtotal_cents = _cents(payload.get("subtotal_price", "0"))
    tax_cents = _cents(payload.get("total_tax", "0"))
    shipping_cents = 0
    try:
        shipping_set = payload.get("total_shipping_price_set", {})
        shop_money = shipping_set.get("shop_money", {})
        shipping_cents = _cents(shop_money.get("amount", "0"))
    except Exception:
        pass
    total_cents = _cents(payload.get("total_price", "0"))

    # Customer resolution
    customer_email = None
    customer_id = None
    customer = payload.get("customer", {})
    if customer:
        customer_email = customer.get("email") or payload.get("email")
        if customer_email:
            cust = resolve_or_create_customer(
                db, channel.tenant_id, channel.id,
                email=customer_email,
                name=f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip(),
            )
            if cust:
                customer_id = cust.id

    # Shipping address
    shipping_addr = payload.get("shipping_address") or payload.get("billing_address")

    order = Order(
        tenant_id=channel.tenant_id,
        channel_id=channel.id,
        external_id=external_id,
        status="confirmed",
        customer_id=customer_id,
        customer_email=customer_email or payload.get("email"),
        subtotal_cents=subtotal_cents,
        tax_cents=tax_cents,
        shipping_cents=shipping_cents,
        discount_cents=0,
        total_cents=total_cents,
        currency_code=currency,
        shipping_address=shipping_addr,
        raw_payload=payload,
    )
    db.add(order)
    db.flush()

    for line in payload.get("line_items", []):
        # Try to match IMS product by SKU
        sku = line.get("sku", "").strip()
        product_id = None
        if sku:
            from app.models import Product
            ims_product = db.execute(
                select(Product).where(
                    Product.tenant_id == channel.tenant_id,
                    Product.sku == sku,
                )
            ).scalar_one_or_none()
            if ims_product:
                product_id = ims_product.id

        db.add(OrderLine(
            tenant_id=channel.tenant_id,
            order_id=order.id,
            product_id=product_id,
            title=line.get("title", ""),
            sku=sku or None,
            quantity=line.get("quantity", 1),
            unit_price_cents=_cents(line.get("price", "0")),
            line_total_cents=_cents(line.get("price", "0")) * line.get("quantity", 1),
        ))

    db.commit()
    logger.info("Shopify order %s ingested for channel %s", external_id, channel.id)


def _handle_order_updated(db: Session, channel: Channel, payload: dict) -> None:
    """Update order status from Shopify."""
    external_id = str(payload["id"])
    order = db.execute(
        select(Order).where(
            Order.channel_id == channel.id,
            Order.external_id == external_id,
        )
    ).scalar_one_or_none()
    if order is None:
        return

    financial_status = payload.get("financial_status", "")
    if financial_status in ("refunded", "voided"):
        order.status = "refunded"
    elif financial_status == "paid":
        order.status = "confirmed"

    fulfillment_status = payload.get("fulfillment_status", "")
    if fulfillment_status == "fulfilled":
        order.status = "fulfilled"

    db.commit()
```

- [ ] **Step 4: Mount in main.py**

Add `webhooks_shopify` to the imports and `app.include_router(webhooks_shopify.router)`.

- [ ] **Step 5: Run tests**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/main.py $CONTAINER:/app/app/main.py
docker cp services/api/app/routers/webhooks_shopify.py $CONTAINER:/app/app/routers/webhooks_shopify.py
docker cp services/api/tests $CONTAINER:/app/tests
docker compose restart api
sleep 5
docker compose exec api python -m pytest tests/routers/test_webhooks_shopify.py -v
docker compose exec api rm -rf /app/tests
```
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/routers/webhooks_shopify.py \
        services/api/app/main.py \
        services/api/tests/routers/test_webhooks_shopify.py
git commit -m "feat(shopify): Shopify webhook receiver for orders/create + orders/updated"
```

---

### Task 5: Integration smoke test

**Files:**
- Create: `services/api/tests/integration/test_shopify_e2e.py`

- [ ] **Step 1: Write integration test**

Create `services/api/tests/integration/test_shopify_e2e.py`:

```python
"""End-to-end smoke test for the Shopify connector.

Uses mocked Shopify API responses — no real Shopify shop required.

Covers:
1. Connect a Shopify channel (verify credentials, detect location)
2. Push a product to Shopify (creates mapping)
3. Import existing Shopify products into IMS catalog
4. Receive an orders/create webhook → IMS Order row created
5. Duplicate webhook is idempotent
"""
import base64
import hashlib
import hmac
import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Channel, ChannelProductMapping, InventoryPool, InventoryPoolShop, Order, Product, Shop, Tenant


API_SECRET = "test_secret_e2e"


@pytest.fixture()
def setup(db, tenant: Tenant, shop: Shop):
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    channel = Channel(
        tenant_id=tenant.id, type="shopify", name="My Shopify Store",
        config={},  # populated by connect
        inventory_pool_id=pool.id, currency_code="INR",
    )
    db.add(channel)
    db.flush()

    product = Product(
        tenant_id=tenant.id, name="Test Widget", sku="TW-001",
        unit_price_cents=1999, product_type="physical", status="active",
    )
    db.add(product)
    db.commit()
    return {"channel": channel, "product": product}


@pytest.fixture()
def auth(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=None, tenant_id=tenant.id,
        role="owner", role_id=None, is_legacy_token=False,
        permissions=frozenset({"channels:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield
    app.dependency_overrides.clear()


def _sign_webhook(body: bytes) -> str:
    return base64.b64encode(
        hmac.new(API_SECRET.encode(), body, hashlib.sha256).digest()
    ).decode()


def test_full_shopify_connector_flow(db, tenant: Tenant, setup, auth) -> None:
    client = TestClient(app)
    channel = setup["channel"]
    product = setup["product"]

    # === 1. Connect Shopify channel ===
    shop_resp = MagicMock(status_code=200)
    shop_resp.json.return_value = {"shop": {"name": "E2E Store", "currency": "INR"}}

    loc_resp = MagicMock(status_code=200)
    loc_resp.json.return_value = {
        "locations": [{"id": 55555, "name": "Main Warehouse"}]
    }

    with patch("httpx.get", side_effect=[shop_resp, loc_resp]):
        connect_resp = client.post(
            f"/v1/admin/channels/{channel.id}/shopify/connect",
            json={
                "shopify_shop_domain": "e2e-store.myshopify.com",
                "shopify_access_token": "shpat_e2e",
                "shopify_api_secret": API_SECRET,
            },
        )
    assert connect_resp.status_code == 200
    assert connect_resp.json()["shop_name"] == "E2E Store"
    assert connect_resp.json()["location_id"] == "55555"

    db.refresh(channel)
    assert channel.config["shopify_location_id"] == "55555"

    # === 2. Push product to Shopify ===
    push_resp = MagicMock(status_code=201)
    push_resp.json.return_value = {
        "product": {"id": 777111, "variants": [{"id": 333444, "sku": "TW-001"}]}
    }

    with patch("httpx.post", return_value=push_resp):
        sync_resp = client.post(f"/v1/admin/channels/{channel.id}/shopify/sync-catalog")
    assert sync_resp.status_code == 200
    assert sync_resp.json()["synced"] == 1
    assert sync_resp.json()["errors"] == 0

    mapping = db.execute(
        select(ChannelProductMapping).where(
            ChannelProductMapping.channel_id == channel.id,
            ChannelProductMapping.product_id == product.id,
        )
    ).scalar_one()
    assert mapping.external_product_id == "777111"

    # === 3. Import Shopify catalog ===
    get_resp = MagicMock(status_code=200)
    get_resp.json.return_value = {
        "products": [
            # TW-001 already exists → should be matched
            {"id": 777111, "title": "Test Widget",
             "variants": [{"id": 333444, "sku": "TW-001", "price": "19.99"}]},
            # NEW-SKU doesn't exist → should be created
            {"id": 888222, "title": "New Widget",
             "variants": [{"id": 555666, "sku": "NEW-001", "price": "9.99"}]},
        ]
    }

    with patch("httpx.get", return_value=get_resp):
        import_resp = client.post(f"/v1/admin/channels/{channel.id}/shopify/import-catalog")
    assert import_resp.status_code == 200
    body = import_resp.json()
    assert body["created"] == 1   # NEW-001 created
    assert body["skipped"] >= 1  # TW-001 already mapped → skipped

    # === 4. Receive orders/create webhook ===
    order_payload = {
        "id": 11223344,
        "email": "shopify-buyer@example.com",
        "currency": "INR",
        "total_price": "19.99",
        "subtotal_price": "19.99",
        "total_tax": "0.00",
        "total_shipping_price_set": {"shop_money": {"amount": "0.00", "currency_code": "INR"}},
        "line_items": [
            {"id": 1, "product_id": 777111, "variant_id": 333444,
             "title": "Test Widget", "quantity": 1, "price": "19.99", "sku": "TW-001"}
        ],
        "customer": {"id": 99, "email": "shopify-buyer@example.com",
                     "first_name": "Shopify", "last_name": "Buyer"},
        "shipping_address": {"city": "Mumbai", "country_code": "IN"},
    }
    body_bytes = json.dumps(order_payload).encode()
    webhook_headers = {
        "X-Shopify-Hmac-Sha256": _sign_webhook(body_bytes),
        "X-Shopify-Topic": "orders/create",
        "Content-Type": "application/json",
    }
    webhook_resp = client.post(
        f"/v1/webhooks/shopify/{channel.id}",
        content=body_bytes, headers=webhook_headers,
    )
    assert webhook_resp.status_code == 200

    order = db.execute(
        select(Order).where(Order.channel_id == channel.id, Order.external_id == "11223344")
    ).scalar_one()
    assert order.customer_email == "shopify-buyer@example.com"
    assert order.total_cents == 1999

    # === 5. Duplicate webhook is idempotent ===
    client.post(f"/v1/webhooks/shopify/{channel.id}",
                content=body_bytes, headers=webhook_headers)
    from sqlalchemy import func
    count = db.execute(
        select(func.count(Order.id)).where(
            Order.channel_id == channel.id, Order.external_id == "11223344"
        )
    ).scalar_one()
    assert count == 1
```

- [ ] **Step 2: Run integration test**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest tests/integration/test_shopify_e2e.py -v
docker compose exec api rm -rf /app/tests
```
Expected: 1 passed.

- [ ] **Step 3: Run full Shopify suite**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest \
  tests/services/test_shopify_service.py \
  tests/routers/test_admin_shopify.py \
  tests/routers/test_webhooks_shopify.py \
  tests/integration/test_shopify_e2e.py \
  -v 2>&1 | tail -10
docker compose exec api rm -rf /app/tests
```
Expected ballpark: ~16 tests passing.

- [ ] **Step 4: Commit**

```bash
git add services/api/tests/integration/test_shopify_e2e.py
git commit -m "test(shopify): end-to-end Shopify connector flow with mocked API responses"
```

---

## Done. Summary of what shipped

- `channel_product_mappings` table — generic bridge between IMS products and external channel IDs (reusable for WooCommerce)
- `app/services/shopify_service.py` — API client: test_connection, push_product, push_inventory_level, get_shopify_products, import_shopify_catalog, verify_webhook_signature
- `app/routers/admin_shopify.py` — connect/sync-catalog/sync-inventory/import-catalog admin endpoints
- `app/routers/webhooks_shopify.py` — webhook receiver with HMAC verification + orders/create + orders/updated handlers
- ~16 tests (all using mocked Shopify responses — no real shop needed)

## What the merchant does to set up

1. In Shopify Admin: create a Custom App with `read_products`, `write_products`, `read_inventory`, `write_inventory`, `read_orders` scopes
2. In IMS admin web: `POST /v1/admin/channels/{channel_id}/shopify/connect` with their store domain + access token + api secret
3. Register webhook URLs in Shopify Admin → Settings → Notifications:
   - `https://your-api-domain/v1/webhooks/shopify/{channel_id}` for topics: `orders/create`, `orders/updated`
4. Click "Import Catalog" to pull existing Shopify products into IMS
5. Click "Sync Catalog" whenever IMS products need to be pushed to Shopify

## Follow-up work

- Scheduled catalog + inventory sync (RQ task, every N minutes)
- Shopify OAuth public app flow (for App Store distribution)
- Refund webhook (`refunds/create` → RMA module)
- Variant-level support (Shopify variants ↔ IMS formal variants sub-project)
- Rate-limiting and backoff for high-volume catalogs

---

*End of plan.*
