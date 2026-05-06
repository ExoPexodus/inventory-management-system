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


def _order_payload() -> dict:
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
                "id": 1, "product_id": 999, "variant_id": 888,
                "title": "Widget", "quantity": 1, "price": "19.99", "sku": "SKU-001",
            }
        ],
        "customer": {
            "id": 111, "email": "buyer@example.com",
            "first_name": "Test", "last_name": "Buyer",
        },
        "shipping_address": {"city": "Mumbai", "country_code": "IN"},
    }


def _headers(body: bytes, secret: str, topic: str) -> dict:
    return {
        "X-Shopify-Hmac-Sha256": _sign(body, secret),
        "X-Shopify-Topic": topic,
        "X-Shopify-Shop-Domain": "test.myshopify.com",
        "Content-Type": "application/json",
    }


def test_order_create_webhook_creates_order(db, tenant: Tenant, channel: Channel, product: Product) -> None:
    from sqlalchemy import select

    body = json.dumps(_order_payload()).encode()
    headers = _headers(body, "secret123", "orders/create")

    # Override get_db for webhook too
    from app.db.session import get_db
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        resp = client.post(f"/v1/webhooks/shopify/{channel.id}", content=body, headers=headers)
        assert resp.status_code == 200, resp.text
    finally:
        app.dependency_overrides.pop(get_db, None)

    order = db.execute(
        select(Order).where(Order.channel_id == channel.id, Order.external_id == "12345678")
    ).scalar_one()
    assert order.customer_email == "buyer@example.com"
    assert order.total_cents == 1999


def test_order_create_webhook_is_idempotent(db, tenant: Tenant, channel: Channel, product: Product) -> None:
    from sqlalchemy import func, select
    from app.db.session import get_db

    body = json.dumps(_order_payload()).encode()
    headers = _headers(body, "secret123", "orders/create")

    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        client.post(f"/v1/webhooks/shopify/{channel.id}", content=body, headers=headers)
        client.post(f"/v1/webhooks/shopify/{channel.id}", content=body, headers=headers)
    finally:
        app.dependency_overrides.pop(get_db, None)

    count = db.execute(
        select(func.count(Order.id)).where(
            Order.channel_id == channel.id, Order.external_id == "12345678"
        )
    ).scalar_one()
    assert count == 1


def test_webhook_bad_signature_rejected(db, tenant: Tenant, channel: Channel) -> None:
    from app.db.session import get_db

    body = json.dumps({"id": 99}).encode()
    headers = {
        "X-Shopify-Hmac-Sha256": "bad_signature",
        "X-Shopify-Topic": "orders/create",
        "Content-Type": "application/json",
    }

    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        resp = client.post(f"/v1/webhooks/shopify/{channel.id}", content=body, headers=headers)
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_unknown_channel_returns_404(db, tenant: Tenant, channel: Channel) -> None:
    body = json.dumps({"id": 99}).encode()
    headers = _headers(body, "secret123", "orders/create")

    # Unknown UUID won't be found regardless of which db session is used
    client = TestClient(app)
    resp = client.post(f"/v1/webhooks/shopify/{uuid.uuid4()}", content=body, headers=headers)
    assert resp.status_code == 404
