# WooCommerce Connector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect an IMS tenant to their WooCommerce store using Consumer Key/Secret credentials — pushing products and inventory from IMS to WooCommerce, importing existing WooCommerce products into IMS catalog on first connect, and receiving WooCommerce order webhooks to create IMS Order rows with full channel attribution.

**Architecture:** Reuses the `channel_product_mappings` table created for the Shopify connector. A `woocommerce_service.py` module wraps all WooCommerce REST API v3 calls. An `admin_woocommerce.py` router exposes connect/sync admin endpoints. A `webhooks_woocommerce.py` router receives and processes WooCommerce events. All tests mock HTTP responses — no real WooCommerce store required for CI.

**WooCommerce API version:** WC REST API v3 (`/wp-json/wc/v3/`)

**Authentication:** HTTP Basic Auth with Consumer Key + Consumer Secret. No OAuth needed for self-hosted WooCommerce.

**Channel.config shape for WooCommerce channels:**
```json
{
  "woocommerce_store_url": "https://mystore.com",
  "woocommerce_consumer_key": "ck_abc123...",
  "woocommerce_consumer_secret": "cs_xyz789...",
  "woocommerce_webhook_secret": "whs_..."
}
```

**Key differences from Shopify connector:**
- Auth: HTTP Basic (consumer_key:consumer_secret) instead of a header token
- Stock: Updated inline on the product (`manage_stock`, `stock_quantity`) instead of a separate inventory endpoint
- Webhook signature: `X-WC-Webhook-Signature` header with HMAC-SHA256 using the webhook secret
- No separate "location" concept — stock lives on the product/variation

**Out of scope (deferred):**
- WooCommerce variable products with attribute-based variations
- Refund webhook (`woocommerce_order_refunded`)
- Scheduled sync

---

### Task 1: WooCommerce service layer

**Files:**
- Create: `services/api/app/services/woocommerce_service.py`
- Create: `services/api/tests/services/test_woocommerce_service.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/services/test_woocommerce_service.py`:

```python
import base64
import hashlib
import hmac as hmac_mod
import json
from unittest.mock import MagicMock, patch
import uuid

import pytest

from app.models import Channel, ChannelProductMapping, InventoryPool, InventoryPoolShop, Product, Shop, Tenant


@pytest.fixture()
def woo_channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id, type="woocommerce", name="My WooCommerce Store",
        config={
            "woocommerce_store_url": "https://mystore.com",
            "woocommerce_consumer_key": "ck_test123",
            "woocommerce_consumer_secret": "cs_test123",
            "woocommerce_webhook_secret": "whs_test123",
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
        description="A great widget",
    )
    db.add(p)
    db.flush()
    return p


def test_test_connection_success(db, woo_channel: Channel) -> None:
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {
        "store_name": "My WooCommerce Store",
        "currency": "INR",
    }

    with patch("httpx.get", return_value=mock_resp):
        from app.services.woocommerce_service import test_connection
        result = test_connection(woo_channel)
        assert result["success"] is True
        assert result["store_name"] == "My WooCommerce Store"


def test_test_connection_bad_credentials(db, woo_channel: Channel) -> None:
    mock_resp = MagicMock(status_code=401)
    mock_resp.json.return_value = {"code": "woocommerce_rest_authentication_error"}

    with patch("httpx.get", return_value=mock_resp):
        from app.services.woocommerce_service import WooCommerceAuthError, test_connection
        with pytest.raises(WooCommerceAuthError):
            test_connection(woo_channel)


def test_push_product_creates_new(db, tenant: Tenant, woo_channel: Channel, product: Product) -> None:
    mock_resp = MagicMock(status_code=201)
    mock_resp.json.return_value = {
        "id": 42,
        "sku": "SKU-001",
        "name": "Widget",
    }

    with patch("httpx.post", return_value=mock_resp):
        from app.services.woocommerce_service import push_product
        mapping = push_product(db, woo_channel, product)
        assert mapping.external_product_id == "42"
        assert mapping.channel_id == woo_channel.id
        assert mapping.product_id == product.id


def test_push_product_updates_existing(db, tenant: Tenant, woo_channel: Channel, product: Product) -> None:
    db.add(ChannelProductMapping(
        tenant_id=tenant.id, channel_id=woo_channel.id,
        product_id=product.id, external_product_id="42",
    ))
    db.flush()

    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"id": 42, "sku": "SKU-001", "name": "Widget"}

    with patch("httpx.put", return_value=mock_resp):
        from app.services.woocommerce_service import push_product
        mapping = push_product(db, woo_channel, product)
        assert mapping.external_product_id == "42"


def test_get_woocommerce_products_parses_response(db, woo_channel: Channel) -> None:
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = [
        {"id": 1, "name": "Widget A", "sku": "SKU-A", "price": "19.99"},
        {"id": 2, "name": "Widget B", "sku": "SKU-B", "price": "29.99"},
    ]

    with patch("httpx.get", return_value=mock_resp):
        from app.services.woocommerce_service import get_woocommerce_products
        products = get_woocommerce_products(woo_channel)
        assert len(products) == 2
        assert products[0]["id"] == 1


def test_verify_webhook_signature_valid() -> None:
    secret = "whs_test"
    body = b'{"id": 12345}'
    digest = base64.b64encode(
        hmac_mod.new(secret.encode(), body, hashlib.sha256).digest()
    ).decode()

    from app.services.woocommerce_service import verify_webhook_signature
    assert verify_webhook_signature(body, digest, secret) is True


def test_verify_webhook_signature_invalid() -> None:
    from app.services.woocommerce_service import verify_webhook_signature
    assert verify_webhook_signature(b'{"id": 12345}', "bad_sig", "secret") is False


def test_import_woocommerce_catalog(db, tenant: Tenant, woo_channel: Channel, product: Product) -> None:
    """Products matching by SKU are mapped; new ones are created."""
    woo_products = [
        # Matches existing product by SKU
        {"id": 100, "name": "Widget", "sku": "SKU-001", "price": "19.99", "status": "publish"},
        # New product not in IMS
        {"id": 200, "name": "New Item", "sku": "NEW-001", "price": "9.99", "status": "publish"},
        # Product without SKU → skipped
        {"id": 300, "name": "No SKU", "sku": "", "price": "5.00", "status": "publish"},
    ]

    from app.services.woocommerce_service import import_woocommerce_catalog
    result = import_woocommerce_catalog(db, woo_channel, woo_products)
    assert result["matched"] == 1    # SKU-001 matched
    assert result["created"] == 1    # NEW-001 created
    assert result["skipped"] == 1    # no-SKU skipped
```

- [ ] **Step 2: Confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/services $CONTAINER:/app/tests/services
docker compose exec api python -m pytest tests/services/test_woocommerce_service.py -v
docker compose exec api rm -rf /app/tests/services
```
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement woocommerce_service.py**

Create `services/api/app/services/woocommerce_service.py`:

```python
"""WooCommerce REST API v3 service layer.

Auth: HTTP Basic with consumer_key:consumer_secret.
Stock is updated inline on the product (manage_stock + stock_quantity).
Channel.config keys: woocommerce_store_url, woocommerce_consumer_key,
woocommerce_consumer_secret, woocommerce_webhook_secret.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.money import round_half_up_cents
from app.models import Channel, ChannelProductMapping, Product

logger = logging.getLogger(__name__)


class WooCommerceAuthError(Exception):
    """Invalid consumer key/secret."""


class WooCommerceAPIError(Exception):
    """WooCommerce returned an unexpected error."""


def _base_url(channel: Channel) -> str:
    url = channel.config["woocommerce_store_url"].rstrip("/")
    return f"{url}/wp-json/wc/v3"


def _auth(channel: Channel) -> tuple[str, str]:
    return (
        channel.config["woocommerce_consumer_key"],
        channel.config["woocommerce_consumer_secret"],
    )


def test_connection(channel: Channel) -> dict[str, Any]:
    """Verify credentials by calling the /system_status endpoint."""
    url = f"{_base_url(channel)}/system_status"
    resp = httpx.get(url, auth=_auth(channel), timeout=10.0)
    if resp.status_code == 401:
        raise WooCommerceAuthError(
            f"Invalid credentials for {channel.config['woocommerce_store_url']}"
        )
    if resp.status_code != 200:
        raise WooCommerceAPIError(f"WooCommerce returned {resp.status_code}: {resp.text}")
    data = resp.json()
    return {
        "success": True,
        "store_name": data.get("store_name", ""),
        "currency": data.get("currency", ""),
    }


def push_product(db: Session, channel: Channel, product: Product) -> ChannelProductMapping:
    """Create or update a product in WooCommerce and record the mapping.

    Stock is updated inline: manage_stock=true, stock_quantity=<current_qty>.
    """
    mapping = db.execute(
        select(ChannelProductMapping).where(
            ChannelProductMapping.channel_id == channel.id,
            ChannelProductMapping.product_id == product.id,
        )
    ).scalar_one_or_none()

    price_str = f"{product.unit_price_cents / 100:.2f}"
    woo_product = {
        "name": product.name,
        "description": product.description or "",
        "sku": product.sku,
        "regular_price": price_str,
        "status": "publish" if product.status == "active" else "draft",
        "virtual": product.product_type in ("digital", "service", "donation"),
        "downloadable": product.product_type == "digital",
        "tax_status": "none" if product.product_type == "donation" else "taxable",
        "manage_stock": product.track_quantity and product.product_type == "physical",
    }

    if mapping is not None:
        url = f"{_base_url(channel)}/products/{mapping.external_product_id}"
        resp = httpx.put(url, auth=_auth(channel),
                         content=json.dumps(woo_product),
                         headers={"Content-Type": "application/json"},
                         timeout=15.0)
    else:
        url = f"{_base_url(channel)}/products"
        resp = httpx.post(url, auth=_auth(channel),
                          content=json.dumps(woo_product),
                          headers={"Content-Type": "application/json"},
                          timeout=15.0)

    if resp.status_code not in (200, 201):
        raise WooCommerceAPIError(
            f"Failed to push product {product.sku}: HTTP {resp.status_code}: {resp.text}"
        )

    data = resp.json()
    ext_id = str(data["id"])
    now = datetime.now(UTC)

    if mapping is not None:
        mapping.external_product_id = ext_id
        mapping.synced_at = now
    else:
        mapping = ChannelProductMapping(
            tenant_id=channel.tenant_id,
            channel_id=channel.id,
            product_id=product.id,
            external_product_id=ext_id,
            synced_at=now,
        )
        db.add(mapping)
    db.flush()
    return mapping


def get_woocommerce_products(channel: Channel, per_page: int = 100) -> list[dict[str, Any]]:
    """Fetch all products from WooCommerce (for initial catalog import)."""
    url = f"{_base_url(channel)}/products"
    resp = httpx.get(url, auth=_auth(channel),
                     params={"per_page": per_page, "status": "publish"},
                     timeout=30.0)
    if resp.status_code != 200:
        raise WooCommerceAPIError(f"Failed to fetch products: HTTP {resp.status_code}: {resp.text}")
    return resp.json()


def verify_webhook_signature(body: bytes, wc_signature_header: str, webhook_secret: str) -> bool:
    """Verify the HMAC-SHA256 signature on an incoming WooCommerce webhook.

    WooCommerce computes: base64(HMAC-SHA256(body, webhook_secret))
    and sends it in the X-WC-Webhook-Signature header.
    """
    expected = base64.b64encode(
        hmac.new(webhook_secret.encode(), body, hashlib.sha256).digest()
    ).decode()
    return hmac.compare_digest(expected, wc_signature_header)


def import_woocommerce_catalog(
    db: Session, channel: Channel, products: list[dict[str, Any]]
) -> dict[str, int]:
    """Import WooCommerce products into IMS, matching by SKU.

    Returns {"matched": N, "created": N, "skipped": N}
    """
    matched = created = skipped = 0

    for wp in products:
        sku = (wp.get("sku") or "").strip()
        if not sku:
            skipped += 1
            continue

        # Skip if mapping already exists for this WC product ID
        existing = db.execute(
            select(ChannelProductMapping).where(
                ChannelProductMapping.channel_id == channel.id,
                ChannelProductMapping.external_product_id == str(wp["id"]),
            )
        ).scalar_one_or_none()
        if existing:
            skipped += 1
            continue

        # Try to match by SKU in IMS
        ims_product = db.execute(
            select(Product).where(
                Product.tenant_id == channel.tenant_id,
                Product.sku == sku,
            )
        ).scalar_one_or_none()

        if ims_product is None:
            price_str = wp.get("price") or wp.get("regular_price", "0")
            try:
                price_cents = round_half_up_cents(float(price_str) * 100)
            except (ValueError, TypeError):
                price_cents = 0

            ims_product = Product(
                tenant_id=channel.tenant_id,
                sku=sku,
                name=wp.get("name", sku),
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
            external_product_id=str(wp["id"]),
        ))
        db.flush()

    return {"matched": matched, "created": created, "skipped": skipped}
```

- [ ] **Step 4: Run tests**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/services/woocommerce_service.py $CONTAINER:/app/app/services/woocommerce_service.py
docker cp services/api/tests/services $CONTAINER:/app/tests/services
docker compose exec api python -m pytest tests/services/test_woocommerce_service.py -v
docker compose exec api rm -rf /app/tests/services
```
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/services/woocommerce_service.py \
        services/api/tests/services/test_woocommerce_service.py
git commit -m "feat(woocommerce): add woocommerce_service with push/import/webhook-verify"
```

---

### Task 2: Admin connect + sync endpoints

**Files:**
- Create: `services/api/app/routers/admin_woocommerce.py`
- Modify: `services/api/app/main.py`
- Create: `services/api/tests/routers/test_admin_woocommerce.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/routers/test_admin_woocommerce.py`:

```python
# NOTE: `from __future__ import annotations` deliberately absent.

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Channel, ChannelProductMapping, InventoryPool, InventoryPoolShop, Product, Shop, Tenant


@pytest.fixture()
def woo_channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id, type="woocommerce", name="WooCommerce Store",
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


def test_connect_woocommerce_success(db, tenant: Tenant, woo_channel: Channel, auth_headers) -> None:
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {
        "store_name": "My Store", "currency": "INR",
    }

    with patch("httpx.get", return_value=mock_resp):
        client = TestClient(app)
        resp = client.post(
            f"/v1/admin/channels/{woo_channel.id}/woocommerce/connect",
            json={
                "woocommerce_store_url": "https://mystore.com",
                "woocommerce_consumer_key": "ck_test",
                "woocommerce_consumer_secret": "cs_test",
                "woocommerce_webhook_secret": "whs_test",
            },
            headers=auth_headers,
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["store_name"] == "My Store"
    assert body["store_url"] == "https://mystore.com"

    db.refresh(woo_channel)
    assert woo_channel.config["woocommerce_store_url"] == "https://mystore.com"


def test_connect_woocommerce_bad_credentials(db, tenant: Tenant, woo_channel: Channel, auth_headers) -> None:
    mock_resp = MagicMock(status_code=401)
    mock_resp.json.return_value = {"code": "woocommerce_rest_authentication_error"}

    with patch("httpx.get", return_value=mock_resp):
        client = TestClient(app)
        resp = client.post(
            f"/v1/admin/channels/{woo_channel.id}/woocommerce/connect",
            json={
                "woocommerce_store_url": "https://bad.com",
                "woocommerce_consumer_key": "bad_key",
                "woocommerce_consumer_secret": "bad_secret",
                "woocommerce_webhook_secret": "whs",
            },
            headers=auth_headers,
        )
    assert resp.status_code == 400
    assert "credentials" in resp.json()["detail"].lower()


def test_sync_catalog_pushes_products(db, tenant: Tenant, woo_channel: Channel, auth_headers) -> None:
    woo_channel.config = {
        "woocommerce_store_url": "https://test.com",
        "woocommerce_consumer_key": "ck",
        "woocommerce_consumer_secret": "cs",
        "woocommerce_webhook_secret": "whs",
    }
    db.flush()

    p = Product(tenant_id=tenant.id, name="Widget", sku="W001",
                unit_price_cents=1999, product_type="physical", status="active")
    db.add(p)
    db.commit()

    def mock_post(url, **kwargs):
        m = MagicMock(status_code=201)
        m.json.return_value = {"id": 42, "sku": "W001", "name": "Widget"}
        return m

    with patch("httpx.post", side_effect=mock_post):
        client = TestClient(app)
        resp = client.post(
            f"/v1/admin/channels/{woo_channel.id}/woocommerce/sync-catalog",
            headers=auth_headers,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["synced"] >= 1
    assert body["errors"] == 0


def test_import_catalog(db, tenant: Tenant, woo_channel: Channel, auth_headers) -> None:
    woo_channel.config = {
        "woocommerce_store_url": "https://test.com",
        "woocommerce_consumer_key": "ck",
        "woocommerce_consumer_secret": "cs",
        "woocommerce_webhook_secret": "whs",
    }
    db.flush()

    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = [
        {"id": 1, "name": "WC Widget", "sku": "WC-001", "price": "9.99", "status": "publish"},
    ]

    with patch("httpx.get", return_value=mock_resp):
        client = TestClient(app)
        resp = client.post(
            f"/v1/admin/channels/{woo_channel.id}/woocommerce/import-catalog",
            headers=auth_headers,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 1
```

- [ ] **Step 2: Confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/routers/test_admin_woocommerce.py $CONTAINER:/app/tests/routers/test_admin_woocommerce.py
docker compose exec api python -m pytest tests/routers/test_admin_woocommerce.py -v
docker compose exec api rm -f /app/tests/routers/test_admin_woocommerce.py
```
Expected: FAIL — router doesn't exist.

- [ ] **Step 3: Implement admin_woocommerce.py**

Create `services/api/app/routers/admin_woocommerce.py`:

```python
"""Admin endpoints for WooCommerce channel management."""
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
from app.services.woocommerce_service import (
    WooCommerceAPIError, WooCommerceAuthError,
    get_woocommerce_products, import_woocommerce_catalog,
    push_product, test_connection,
)

router = APIRouter(
    prefix="/v1/admin/channels",
    tags=["WooCommerce Connector"],
    dependencies=[require_permission("channels:manage")],
)


class WooCommerceConnectIn(BaseModel):
    woocommerce_store_url: str
    woocommerce_consumer_key: str
    woocommerce_consumer_secret: str
    woocommerce_webhook_secret: str


class WooCommerceConnectOut(BaseModel):
    store_name: str
    store_url: str
    currency: str | None


class SyncCatalogOut(BaseModel):
    synced: int
    errors: int
    error_skus: list[str]


class ImportCatalogOut(BaseModel):
    matched: int
    created: int
    skipped: int


def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Operator not assigned to a tenant")
    return ctx.tenant_id


def _get_channel_or_404(db: Session, channel_id: UUID, tenant_id: UUID) -> Channel:
    ch = db.get(Channel, channel_id)
    if ch is None or ch.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Channel not found")
    return ch


@router.post("/{channel_id}/woocommerce/connect", response_model=WooCommerceConnectOut)
def connect_woocommerce(
    channel_id: UUID,
    body: WooCommerceConnectIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> WooCommerceConnectOut:
    """Store credentials, verify connection."""
    tenant_id = _require_tenant(ctx)
    channel = _get_channel_or_404(db, channel_id, tenant_id)

    channel.config = {
        "woocommerce_store_url": body.woocommerce_store_url.rstrip("/"),
        "woocommerce_consumer_key": body.woocommerce_consumer_key.strip(),
        "woocommerce_consumer_secret": body.woocommerce_consumer_secret.strip(),
        "woocommerce_webhook_secret": body.woocommerce_webhook_secret.strip(),
    }
    db.flush()

    try:
        conn_result = test_connection(channel)
    except WooCommerceAuthError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Invalid credentials: {exc}")
    except WooCommerceAPIError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc))

    channel.type = "woocommerce"
    db.commit()

    return WooCommerceConnectOut(
        store_name=conn_result["store_name"],
        store_url=body.woocommerce_store_url.rstrip("/"),
        currency=conn_result.get("currency"),
    )


@router.post("/{channel_id}/woocommerce/sync-catalog", response_model=SyncCatalogOut)
def sync_catalog(
    channel_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> SyncCatalogOut:
    """Push all active IMS products to WooCommerce."""
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
        except Exception:
            errors += 1
            error_skus.append(product.sku)

    db.commit()
    return SyncCatalogOut(synced=synced, errors=errors, error_skus=error_skus)


@router.post("/{channel_id}/woocommerce/import-catalog", response_model=ImportCatalogOut)
def import_catalog(
    channel_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ImportCatalogOut:
    """Pull existing WooCommerce products and import unmatched ones into IMS."""
    tenant_id = _require_tenant(ctx)
    channel = _get_channel_or_404(db, channel_id, tenant_id)

    try:
        woo_products = get_woocommerce_products(channel)
    except WooCommerceAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    result = import_woocommerce_catalog(db, channel, woo_products)
    db.commit()
    return ImportCatalogOut(**result)
```

- [ ] **Step 4: Mount in main.py**

Add `admin_woocommerce` alphabetically (between `admin_web` and the end of the router list) and `app.include_router(admin_woocommerce.router)`.

- [ ] **Step 5: Run tests**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/main.py $CONTAINER:/app/app/main.py
docker cp services/api/app/routers/admin_woocommerce.py $CONTAINER:/app/app/routers/admin_woocommerce.py
docker cp services/api/app/services/woocommerce_service.py $CONTAINER:/app/app/services/woocommerce_service.py
docker cp services/api/tests $CONTAINER:/app/tests
docker compose restart api
sleep 5
docker compose exec api python -m pytest tests/routers/test_admin_woocommerce.py -v
docker compose exec api rm -rf /app/tests
```
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/routers/admin_woocommerce.py \
        services/api/app/main.py \
        services/api/tests/routers/test_admin_woocommerce.py
git commit -m "feat(woocommerce): connect/sync-catalog/import-catalog admin endpoints"
```

---

### Task 3: Webhook receiver

**Files:**
- Create: `services/api/app/routers/webhooks_woocommerce.py`
- Modify: `services/api/app/main.py`
- Create: `services/api/tests/routers/test_webhooks_woocommerce.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/routers/test_webhooks_woocommerce.py`:

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
        tenant_id=tenant.id, type="woocommerce", name="WooCommerce",
        config={
            "woocommerce_store_url": "https://test.com",
            "woocommerce_consumer_key": "ck",
            "woocommerce_consumer_secret": "cs",
            "woocommerce_webhook_secret": "secret123",
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


def _order_payload() -> dict:
    return {
        "id": 12345,
        "status": "processing",
        "currency": "INR",
        "total": "19.99",
        "subtotal": "19.99",
        "total_tax": "0.00",
        "shipping_total": "0.00",
        "billing": {
            "email": "buyer@example.com",
            "first_name": "Test",
            "last_name": "Buyer",
        },
        "shipping": {
            "address_1": "123 Main St", "city": "Mumbai", "country": "IN",
        },
        "line_items": [
            {
                "id": 1, "product_id": 99, "variation_id": 0,
                "name": "Widget", "quantity": 1, "total": "19.99", "sku": "SKU-001",
            }
        ],
    }


def _headers(body: bytes, secret: str, topic: str) -> dict:
    return {
        "X-WC-Webhook-Signature": _sign(body, secret),
        "X-WC-Webhook-Topic": topic,
        "X-WC-Webhook-Source": "https://test.com",
        "Content-Type": "application/json",
    }


def test_order_created_webhook_creates_order(db, tenant: Tenant, channel: Channel, product: Product) -> None:
    from sqlalchemy import select
    from app.db.session import get_db

    body = json.dumps(_order_payload()).encode()
    headers = _headers(body, "secret123", "order.created")

    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        resp = client.post(f"/v1/webhooks/woocommerce/{channel.id}", content=body, headers=headers)
        assert resp.status_code == 200, resp.text
    finally:
        app.dependency_overrides.pop(get_db, None)

    order = db.execute(
        select(Order).where(Order.channel_id == channel.id, Order.external_id == "12345")
    ).scalar_one()
    assert order.customer_email == "buyer@example.com"
    assert order.total_cents == 1999


def test_order_created_webhook_is_idempotent(db, tenant: Tenant, channel: Channel, product: Product) -> None:
    from sqlalchemy import func, select
    from app.db.session import get_db

    body = json.dumps(_order_payload()).encode()
    headers = _headers(body, "secret123", "order.created")

    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        client.post(f"/v1/webhooks/woocommerce/{channel.id}", content=body, headers=headers)
        client.post(f"/v1/webhooks/woocommerce/{channel.id}", content=body, headers=headers)
    finally:
        app.dependency_overrides.pop(get_db, None)

    count = db.execute(
        select(func.count(Order.id)).where(
            Order.channel_id == channel.id, Order.external_id == "12345"
        )
    ).scalar_one()
    assert count == 1


def test_webhook_bad_signature_rejected(db, tenant: Tenant, channel: Channel) -> None:
    body = json.dumps({"id": 99}).encode()
    headers = {
        "X-WC-Webhook-Signature": "bad_sig",
        "X-WC-Webhook-Topic": "order.created",
        "Content-Type": "application/json",
    }

    from app.db.session import get_db
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        resp = client.post(f"/v1/webhooks/woocommerce/{channel.id}", content=body, headers=headers)
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_unknown_channel_returns_404(db, tenant: Tenant, channel: Channel) -> None:
    body = json.dumps({"id": 99}).encode()
    headers = _headers(body, "secret123", "order.created")

    from app.db.session import get_db
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        resp = client.post(f"/v1/webhooks/woocommerce/{uuid.uuid4()}", content=body, headers=headers)
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 2: Confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/routers/test_webhooks_woocommerce.py $CONTAINER:/app/tests/routers/test_webhooks_woocommerce.py
docker compose exec api python -m pytest tests/routers/test_webhooks_woocommerce.py -v
docker compose exec api rm -f /app/tests/routers/test_webhooks_woocommerce.py
```
Expected: FAIL — router doesn't exist.

- [ ] **Step 3: Implement webhooks_woocommerce.py**

Create `services/api/app/routers/webhooks_woocommerce.py`:

```python
"""WooCommerce webhook receiver.

Endpoint: POST /v1/webhooks/woocommerce/{channel_id}

WooCommerce sends webhooks with X-WC-Webhook-Signature (HMAC-SHA256).
Supported topics: order.created, order.updated.

Register in WooCommerce Admin → WooCommerce → Settings → Advanced → Webhooks.
"""
from __future__ import annotations

import json
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Channel, Order, OrderLine
from app.services.customer_resolver import resolve_or_create_customer
from app.services.woocommerce_service import verify_webhook_signature

router = APIRouter(prefix="/v1/webhooks/woocommerce", tags=["WooCommerce Webhooks"])
logger = logging.getLogger(__name__)


@router.post("/{channel_id}", status_code=200)
async def receive_webhook(
    channel_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    x_wc_webhook_signature: Annotated[str | None, Header()] = None,
    x_wc_webhook_topic: Annotated[str | None, Header()] = None,
) -> dict:
    body = await request.body()

    channel = db.get(Channel, channel_id)
    if channel is None or channel.type != "woocommerce":
        raise HTTPException(status_code=404, detail="Channel not found")

    webhook_secret = channel.config.get("woocommerce_webhook_secret", "")
    if not x_wc_webhook_signature or not verify_webhook_signature(
        body, x_wc_webhook_signature, webhook_secret
    ):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    if not x_wc_webhook_topic:
        return {"status": "ignored", "reason": "no topic header"}

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    topic = x_wc_webhook_topic.lower()
    if topic == "order.created":
        _handle_order_created(db, channel, payload)
    elif topic == "order.updated":
        _handle_order_updated(db, channel, payload)
    else:
        logger.debug("Unhandled WooCommerce topic: %s", topic)

    return {"status": "ok", "topic": topic}


def _handle_order_created(db: Session, channel: Channel, payload: dict) -> None:
    external_id = str(payload["id"])

    existing = db.execute(
        select(Order).where(
            Order.channel_id == channel.id,
            Order.external_id == external_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return

    currency = payload.get("currency", channel.currency_code)

    def _cents(amount_str: str) -> int:
        try:
            return round(float(amount_str) * 100)
        except (ValueError, TypeError):
            return 0

    subtotal_cents = _cents(payload.get("subtotal", "0"))
    tax_cents = _cents(payload.get("total_tax", "0"))
    shipping_cents = _cents(payload.get("shipping_total", "0"))
    total_cents = _cents(payload.get("total", "0"))

    billing = payload.get("billing", {})
    customer_email = billing.get("email") or payload.get("customer_note", {})
    customer_id = None
    if customer_email:
        name = f"{billing.get('first_name', '')} {billing.get('last_name', '')}".strip()
        cust = resolve_or_create_customer(
            db, channel.tenant_id, channel.id,
            email=customer_email, name=name,
        )
        if cust:
            customer_id = cust.id

    shipping = payload.get("shipping", {})
    shipping_addr = {
        "address_1": shipping.get("address_1"),
        "city": shipping.get("city"),
        "country": shipping.get("country"),
    } if shipping else None

    order = Order(
        tenant_id=channel.tenant_id,
        channel_id=channel.id,
        external_id=external_id,
        status="confirmed",
        customer_id=customer_id,
        customer_email=customer_email,
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
        sku = (line.get("sku") or "").strip()
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
            title=line.get("name", ""),
            sku=sku or None,
            quantity=line.get("quantity", 1),
            unit_price_cents=_cents(line.get("total", "0")) // max(line.get("quantity", 1), 1),
            line_total_cents=_cents(line.get("total", "0")),
        ))

    db.commit()
    logger.info("WooCommerce order %s ingested for channel %s", external_id, channel.id)


def _handle_order_updated(db: Session, channel: Channel, payload: dict) -> None:
    external_id = str(payload["id"])
    order = db.execute(
        select(Order).where(
            Order.channel_id == channel.id,
            Order.external_id == external_id,
        )
    ).scalar_one_or_none()
    if order is None:
        return

    wc_status = payload.get("status", "")
    status_map = {
        "completed": "fulfilled",
        "refunded": "refunded",
        "cancelled": "cancelled",
        "processing": "confirmed",
        "pending": "pending",
    }
    if wc_status in status_map:
        order.status = status_map[wc_status]
    db.commit()
```

- [ ] **Step 4: Mount in main.py**

Add `webhooks_woocommerce` to the imports and `app.include_router(webhooks_woocommerce.router)`.

- [ ] **Step 5: Run tests**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/main.py $CONTAINER:/app/app/main.py
docker cp services/api/app/routers/webhooks_woocommerce.py $CONTAINER:/app/app/routers/webhooks_woocommerce.py
docker cp services/api/tests $CONTAINER:/app/tests
docker compose restart api
sleep 5
docker compose exec api python -m pytest tests/routers/test_webhooks_woocommerce.py -v
docker compose exec api rm -rf /app/tests
```
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/routers/webhooks_woocommerce.py \
        services/api/app/main.py \
        services/api/tests/routers/test_webhooks_woocommerce.py
git commit -m "feat(woocommerce): webhook receiver for order.created + order.updated"
```

---

### Task 4: Integration smoke test

**Files:**
- Create: `services/api/tests/integration/test_woocommerce_e2e.py`

- [ ] **Step 1: Write integration test**

Create `services/api/tests/integration/test_woocommerce_e2e.py`:

```python
"""End-to-end smoke test for the WooCommerce connector (mocked API responses)."""
import base64
import hashlib
import hmac
import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import app
from app.models import (
    Channel, ChannelProductMapping, InventoryPool, InventoryPoolShop, Order, Product, Shop, Tenant,
)

WC_WEBHOOK_SECRET = "whs_e2e_test"


@pytest.fixture()
def setup(db, tenant: Tenant, shop: Shop):
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    channel = Channel(
        tenant_id=tenant.id, type="woocommerce", name="My WooCommerce Store",
        config={},
        inventory_pool_id=pool.id, currency_code="INR",
    )
    db.add(channel)
    db.flush()

    product = Product(
        tenant_id=tenant.id, name="E2E Widget", sku="E2E-001",
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


def _sign(body: bytes) -> str:
    return base64.b64encode(
        hmac.new(WC_WEBHOOK_SECRET.encode(), body, hashlib.sha256).digest()
    ).decode()


def test_full_woocommerce_connector_flow(db, tenant: Tenant, setup, auth) -> None:
    client = TestClient(app)
    channel = setup["channel"]
    product = setup["product"]

    # === 1. Connect WooCommerce ===
    mock_conn = MagicMock(status_code=200)
    mock_conn.json.return_value = {"store_name": "E2E WC Store", "currency": "INR"}

    with patch("httpx.get", return_value=mock_conn):
        connect_resp = client.post(
            f"/v1/admin/channels/{channel.id}/woocommerce/connect",
            json={
                "woocommerce_store_url": "https://e2e-store.com",
                "woocommerce_consumer_key": "ck_e2e",
                "woocommerce_consumer_secret": "cs_e2e",
                "woocommerce_webhook_secret": WC_WEBHOOK_SECRET,
            },
        )
    assert connect_resp.status_code == 200
    assert connect_resp.json()["store_name"] == "E2E WC Store"

    db.refresh(channel)
    assert channel.config["woocommerce_store_url"] == "https://e2e-store.com"

    # === 2. Push product to WooCommerce ===
    mock_push = MagicMock(status_code=201)
    mock_push.json.return_value = {"id": 42, "sku": "E2E-001", "name": "E2E Widget"}

    with patch("httpx.post", return_value=mock_push):
        sync_resp = client.post(f"/v1/admin/channels/{channel.id}/woocommerce/sync-catalog")
    assert sync_resp.status_code == 200
    assert sync_resp.json()["synced"] >= 1

    mapping = db.execute(
        select(ChannelProductMapping).where(
            ChannelProductMapping.channel_id == channel.id,
            ChannelProductMapping.product_id == product.id,
        )
    ).scalar_one()
    assert mapping.external_product_id == "42"

    # === 3. Import WooCommerce catalog ===
    mock_import = MagicMock(status_code=200)
    mock_import.json.return_value = [
        # E2E-001 already mapped → skipped
        {"id": 42, "name": "E2E Widget", "sku": "E2E-001", "price": "19.99", "status": "publish"},
        # NEW-WC → created
        {"id": 99, "name": "New WC Widget", "sku": "NEW-WC-001", "price": "5.99", "status": "publish"},
    ]

    with patch("httpx.get", return_value=mock_import):
        import_resp = client.post(f"/v1/admin/channels/{channel.id}/woocommerce/import-catalog")
    assert import_resp.status_code == 200
    body = import_resp.json()
    assert body["created"] == 1
    assert body["skipped"] >= 1

    # === 4. Receive order.created webhook ===
    order_payload = {
        "id": 9876,
        "status": "processing",
        "currency": "INR",
        "total": "19.99",
        "subtotal": "19.99",
        "total_tax": "0.00",
        "shipping_total": "0.00",
        "billing": {"email": "wc-buyer@example.com", "first_name": "WC", "last_name": "Buyer"},
        "shipping": {"address_1": "456 Park Ave", "city": "Delhi", "country": "IN"},
        "line_items": [
            {"id": 1, "product_id": 42, "variation_id": 0,
             "name": "E2E Widget", "quantity": 1, "total": "19.99", "sku": "E2E-001"}
        ],
    }
    body_bytes = json.dumps(order_payload).encode()
    webhook_headers = {
        "X-WC-Webhook-Signature": _sign(body_bytes),
        "X-WC-Webhook-Topic": "order.created",
        "Content-Type": "application/json",
    }

    from app.db.session import get_db
    app.dependency_overrides[get_db] = lambda: db
    try:
        webhook_resp = client.post(
            f"/v1/webhooks/woocommerce/{channel.id}",
            content=body_bytes, headers=webhook_headers,
        )
        assert webhook_resp.status_code == 200

        order = db.execute(
            select(Order).where(Order.channel_id == channel.id, Order.external_id == "9876")
        ).scalar_one()
        assert order.customer_email == "wc-buyer@example.com"
        assert order.total_cents == 1999

        # === 5. Duplicate webhook idempotent ===
        client.post(f"/v1/webhooks/woocommerce/{channel.id}",
                    content=body_bytes, headers=webhook_headers)
        count = db.execute(
            select(func.count(Order.id)).where(
                Order.channel_id == channel.id, Order.external_id == "9876"
            )
        ).scalar_one()
        assert count == 1
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 2: Run integration test**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest tests/integration/test_woocommerce_e2e.py -v
docker compose exec api rm -rf /app/tests
```
Expected: 1 passed.

- [ ] **Step 3: Run full WooCommerce suite**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest \
  tests/services/test_woocommerce_service.py \
  tests/routers/test_admin_woocommerce.py \
  tests/routers/test_webhooks_woocommerce.py \
  tests/integration/test_woocommerce_e2e.py \
  -v 2>&1 | tail -5
docker compose exec api rm -rf /app/tests
```
Expected ballpark: ~17 tests passing.

- [ ] **Step 4: Commit**

```bash
git add services/api/tests/integration/test_woocommerce_e2e.py
git commit -m "test(woocommerce): end-to-end WooCommerce connector flow with mocked API"
```

---

## Done. Summary of what shipped

- `woocommerce_service.py` — test_connection (HTTP Basic), push_product (create/update), get_woocommerce_products, import_woocommerce_catalog, verify_webhook_signature
- `admin_woocommerce.py` — connect, sync-catalog, import-catalog admin endpoints
- `webhooks_woocommerce.py` — webhook receiver with HMAC-SHA256 verification, order.created + order.updated handlers
- ~17 tests, all mocked

## Key differences from Shopify connector

| Aspect | Shopify | WooCommerce |
|---|---|---|
| Auth | `X-Shopify-Access-Token` header | HTTP Basic (`ck_:cs_`) |
| Webhook secret header | `X-Shopify-Hmac-Sha256` | `X-WC-Webhook-Signature` |
| Order topic | `orders/create` | `order.created` |
| Stock update | Separate inventory endpoint | Inline on product |
| Location concept | Required (fetch locations on connect) | None |

## What the merchant does

1. In WooCommerce Admin → WooCommerce → Settings → Advanced → REST API: generate Consumer Key/Secret with "Read/Write" permissions
2. In WooCommerce Admin → WooCommerce → Settings → Advanced → Webhooks: add webhooks for `Order created` and `Order updated`, pointing to `https://your-api-domain/v1/webhooks/woocommerce/{channel_id}`, set a webhook secret
3. In IMS admin web: `POST /v1/admin/channels/{channel_id}/woocommerce/connect`
4. Click "Import Catalog" / "Sync Catalog" as needed

---

*End of plan.*
