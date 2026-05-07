# NOTE: `from __future__ import annotations` deliberately absent.

import uuid
from unittest.mock import MagicMock, patch

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
        tenant_id=tenant.id, type="headless", name="Headless",
        config={"payment_provider": "stripe", "stripe_secret_key": "sk_test_xxx",
                "stripe_publishable_key": "pk_test_xxx",
                "checkout_success_url": "https://shop.com/success"},
        inventory_pool_id=pool.id, currency_code="INR",
    )
    db.add(channel)
    db.flush()
    product = Product(
        tenant_id=tenant.id, name="Widget", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=1999, product_type="physical", status="active",
    )
    db.add(product)
    db.flush()
    db.add(StockMovement(
        tenant_id=tenant.id, shop_id=shop.id, product_id=product.id,
        quantity_delta=10, movement_type="purchase_receipt",
        idempotency_key=f"seed-{uuid.uuid4().hex}",
    ))
    db.commit()
    return {"channel": channel, "product": product}


def _h(storefront): return {"X-Channel-Id": str(storefront["channel"].id)}


def _make_cart_and_session(client, storefront, db):
    from app.db.session import get_db
    cart = client.post("/v1/storefront/cart", headers=_h(storefront)).json()
    token = cart["cart_token"]
    client.post(f"/v1/storefront/cart/{token}/items", json={
        "product_id": str(storefront["product"].id), "quantity": 1,
    }, headers=_h(storefront))
    session_resp = client.post("/v1/storefront/checkout/session", json={
        "cart_token": token,
    }, headers=_h(storefront))
    return session_resp.json()["session_token"]


def test_create_checkout_session(db, tenant: Tenant, storefront) -> None:
    from app.db.session import get_db
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        cart = client.post("/v1/storefront/cart", headers=_h(storefront)).json()
        client.post(f"/v1/storefront/cart/{cart['cart_token']}/items", json={
            "product_id": str(storefront["product"].id), "quantity": 1,
        }, headers=_h(storefront))
        resp = client.post("/v1/storefront/checkout/session", json={
            "cart_token": cart["cart_token"],
        }, headers=_h(storefront))
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert "session_token" in body
        assert "/checkout/" in body["checkout_url"]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_create_payment_intent_stripe(db, tenant: Tenant, storefront) -> None:
    from app.db.session import get_db
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        session_token = _make_cart_and_session(client, storefront, db)
        mock_intent = MagicMock()
        mock_intent.id = "pi_test123"
        mock_intent.client_secret = "pi_test123_secret"
        with patch("stripe.PaymentIntent.create", return_value=mock_intent):
            resp = client.post(f"/v1/checkout/{session_token}/payment-intent", json={
                "customer_email": "buyer@example.com",
                "shipping_address": {"country": "IN"},
            })
        assert resp.status_code == 200, resp.text
        assert resp.json()["client_secret"] == "pi_test123_secret"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_complete_checkout_stripe(db, tenant: Tenant, storefront) -> None:
    from sqlalchemy import select
    from app.db.session import get_db
    from app.models import Order
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        session_token = _make_cart_and_session(client, storefront, db)
        mock_intent = MagicMock()
        mock_intent.status = "succeeded"
        with patch("stripe.PaymentIntent.retrieve", return_value=mock_intent):
            resp = client.post(f"/v1/checkout/{session_token}/complete", json={
                "payment_intent_id": "pi_test123",
                "customer_email": "buyer@example.com",
            })
        assert resp.status_code == 200, resp.text
        result = resp.json()
        assert result["status"] == "completed"
        order = db.execute(
            select(Order).where(Order.id == uuid.UUID(result["order_id"]))
        ).scalar_one()
        assert order.customer_email == "buyer@example.com"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_empty_cart_session_rejected(db, tenant: Tenant, storefront) -> None:
    from app.db.session import get_db
    app.dependency_overrides[get_db] = lambda: db
    try:
        resp = TestClient(app).post("/v1/storefront/checkout/session", json={
            "cart_token": "empty_cart_xxx",
        }, headers=_h(storefront))
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.pop(get_db, None)
