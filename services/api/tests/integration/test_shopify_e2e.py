"""End-to-end smoke test for the Shopify connector (mocked API responses)."""
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
        config={},
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


def _sign(body: bytes) -> str:
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
    loc_resp.json.return_value = {"locations": [{"id": 55555, "name": "Main Warehouse"}]}

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
            # TW-001 already mapped → skipped
            {"id": 777111, "title": "Test Widget",
             "variants": [{"id": 333444, "sku": "TW-001", "price": "19.99"}]},
            # NEW-001 → created
            {"id": 888222, "title": "New Widget",
             "variants": [{"id": 555666, "sku": "NEW-001", "price": "9.99"}]},
        ]
    }

    with patch("httpx.get", return_value=get_resp):
        import_resp = client.post(f"/v1/admin/channels/{channel.id}/shopify/import-catalog")
    assert import_resp.status_code == 200
    body = import_resp.json()
    assert body["created"] == 1
    assert body["skipped"] >= 1

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
        "X-Shopify-Hmac-Sha256": _sign(body_bytes),
        "X-Shopify-Topic": "orders/create",
        "Content-Type": "application/json",
    }

    from app.db.session import get_db
    app.dependency_overrides[get_db] = lambda: db
    try:
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
        count = db.execute(
            select(func.count(Order.id)).where(
                Order.channel_id == channel.id, Order.external_id == "11223344"
            )
        ).scalar_one()
        assert count == 1
    finally:
        app.dependency_overrides.pop(get_db, None)
