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
from app.models import Channel, ChannelProductMapping, InventoryPool, InventoryPoolShop, Order, Product, Shop, Tenant

WC_SECRET = "whs_e2e"


@pytest.fixture()
def setup(db, tenant: Tenant, shop: Shop):
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    channel = Channel(
        tenant_id=tenant.id, type="woocommerce", name="WC Store",
        config={}, inventory_pool_id=pool.id, currency_code="INR",
    )
    db.add(channel)
    db.flush()
    product = Product(
        tenant_id=tenant.id, name="WC Widget", sku="WC-E2E-001",
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
        user_id=None, tenant_id=tenant.id, role="owner", role_id=None,
        is_legacy_token=False, permissions=frozenset({"channels:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield
    app.dependency_overrides.clear()


def _sign(body: bytes) -> str:
    return base64.b64encode(
        hmac.new(WC_SECRET.encode(), body, hashlib.sha256).digest()
    ).decode()


def test_full_woocommerce_flow(db, tenant: Tenant, setup, auth) -> None:
    client = TestClient(app)
    channel, product = setup["channel"], setup["product"]

    # 1. Connect
    mock_conn = MagicMock(status_code=200)
    mock_conn.json.return_value = {"store_name": "E2E WC Store", "currency": "INR"}
    with patch("httpx.get", return_value=mock_conn):
        r = client.post(f"/v1/admin/channels/{channel.id}/woocommerce/connect", json={
            "woocommerce_store_url": "https://wc-e2e.com",
            "woocommerce_consumer_key": "ck_e2e",
            "woocommerce_consumer_secret": "cs_e2e",
            "woocommerce_webhook_secret": WC_SECRET,
        })
    assert r.status_code == 200
    assert r.json()["store_name"] == "E2E WC Store"
    db.refresh(channel)
    assert channel.config["woocommerce_store_url"] == "https://wc-e2e.com"

    # 2. Push product
    mock_push = MagicMock(status_code=201)
    mock_push.json.return_value = {"id": 55, "sku": "WC-E2E-001"}
    with patch("httpx.post", return_value=mock_push):
        r = client.post(f"/v1/admin/channels/{channel.id}/woocommerce/sync-catalog")
    assert r.status_code == 200
    assert r.json()["synced"] >= 1
    mapping = db.execute(
        select(ChannelProductMapping).where(
            ChannelProductMapping.channel_id == channel.id,
            ChannelProductMapping.product_id == product.id,
        )
    ).scalar_one()
    assert mapping.external_product_id == "55"

    # 3. Import catalog
    mock_import = MagicMock(status_code=200)
    mock_import.json.return_value = [
        {"id": 55, "name": "WC Widget", "sku": "WC-E2E-001", "price": "19.99", "status": "publish"},
        {"id": 66, "name": "New WC Item", "sku": "NEW-WC-001", "price": "4.99", "status": "publish"},
    ]
    with patch("httpx.get", return_value=mock_import):
        r = client.post(f"/v1/admin/channels/{channel.id}/woocommerce/import-catalog")
    assert r.status_code == 200
    assert r.json()["created"] == 1
    assert r.json()["skipped"] >= 1

    # 4. Receive order.created webhook
    order_payload = {
        "id": 9999, "status": "processing", "currency": "INR",
        "total": "19.99", "subtotal": "19.99", "total_tax": "0.00", "shipping_total": "0.00",
        "billing": {"email": "wc-e2e@example.com", "first_name": "WC", "last_name": "Buyer"},
        "shipping": {"address_1": "1 Test St", "city": "Pune", "country": "IN"},
        "line_items": [
            {"id": 1, "product_id": 55, "variation_id": 0,
             "name": "WC Widget", "quantity": 1, "total": "19.99", "sku": "WC-E2E-001"}
        ],
    }
    body_bytes = json.dumps(order_payload).encode()
    wh_headers = {
        "X-WC-Webhook-Signature": _sign(body_bytes),
        "X-WC-Webhook-Topic": "order.created",
        "Content-Type": "application/json",
    }

    from app.db.session import get_db
    app.dependency_overrides[get_db] = lambda: db
    try:
        r = client.post(f"/v1/webhooks/woocommerce/{channel.id}", content=body_bytes, headers=wh_headers)
        assert r.status_code == 200
        order = db.execute(
            select(Order).where(Order.channel_id == channel.id, Order.external_id == "9999")
        ).scalar_one()
        assert order.customer_email == "wc-e2e@example.com"
        assert order.total_cents == 1999

        # 5. Duplicate idempotent
        client.post(f"/v1/webhooks/woocommerce/{channel.id}", content=body_bytes, headers=wh_headers)
        count = db.execute(
            select(func.count(Order.id)).where(
                Order.channel_id == channel.id, Order.external_id == "9999"
            )
        ).scalar_one()
        assert count == 1
    finally:
        app.dependency_overrides.pop(get_db, None)
