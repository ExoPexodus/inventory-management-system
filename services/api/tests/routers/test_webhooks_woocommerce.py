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
        config={"woocommerce_store_url": "https://test.com",
                "woocommerce_consumer_key": "ck",
                "woocommerce_consumer_secret": "cs",
                "woocommerce_webhook_secret": "secret123"},
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
        "id": 12345, "status": "processing", "currency": "INR",
        "total": "19.99", "subtotal": "19.99", "total_tax": "0.00", "shipping_total": "0.00",
        "billing": {"email": "buyer@example.com", "first_name": "Test", "last_name": "Buyer"},
        "shipping": {"address_1": "123 Main", "city": "Mumbai", "country": "IN"},
        "line_items": [
            {"id": 1, "product_id": 99, "variation_id": 0,
             "name": "Widget", "quantity": 1, "total": "19.99", "sku": "SKU-001"}
        ],
    }


def _headers(body: bytes, secret: str, topic: str) -> dict:
    return {
        "X-WC-Webhook-Signature": _sign(body, secret),
        "X-WC-Webhook-Topic": topic,
        "Content-Type": "application/json",
    }


def test_order_created_webhook_creates_order(db, tenant: Tenant, channel: Channel, product: Product) -> None:
    from sqlalchemy import select
    from app.db.session import get_db

    body = json.dumps(_order_payload()).encode()
    headers = _headers(body, "secret123", "order.created")

    app.dependency_overrides[get_db] = lambda: db
    try:
        resp = TestClient(app).post(f"/v1/webhooks/woocommerce/{channel.id}", content=body, headers=headers)
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
    from app.db.session import get_db

    body = json.dumps({"id": 99}).encode()
    headers = {"X-WC-Webhook-Signature": "bad_sig", "X-WC-Webhook-Topic": "order.created",
               "Content-Type": "application/json"}

    app.dependency_overrides[get_db] = lambda: db
    try:
        resp = TestClient(app).post(f"/v1/webhooks/woocommerce/{channel.id}", content=body, headers=headers)
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_unknown_channel_returns_404(db, tenant: Tenant, channel: Channel) -> None:
    from app.db.session import get_db

    body = json.dumps({"id": 99}).encode()
    headers = _headers(body, "secret123", "order.created")

    app.dependency_overrides[get_db] = lambda: db
    try:
        resp = TestClient(app).post(f"/v1/webhooks/woocommerce/{uuid.uuid4()}", content=body, headers=headers)
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)
