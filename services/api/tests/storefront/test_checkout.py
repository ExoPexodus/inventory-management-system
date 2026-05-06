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


def _h(storefront):
    return {"X-Channel-Id": str(storefront["channel"].id)}


def _make_cart(client, storefront, qty=2):
    cart = client.post("/v1/storefront/cart", headers=_h(storefront)).json()
    client.post(f"/v1/storefront/cart/{cart['cart_token']}/items", json={
        "product_id": str(storefront["product"].id), "quantity": qty,
    }, headers=_h(storefront))
    return cart["cart_token"]


def test_get_cart_summary(db, tenant: Tenant, storefront) -> None:
    client = TestClient(app)
    token = _make_cart(client, storefront)

    resp = client.get(f"/v1/storefront/cart/{token}/summary",
                      params={"destination_country": "IN"},
                      headers=_h(storefront))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["subtotal_cents"] == 20000
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

    resp = client.post(f"/v1/storefront/cart/{token}/discount",
                       json={"code": "TEN"}, headers=_h(storefront))
    assert resp.status_code == 200
    body = resp.json()
    assert body["discount_cents"] == 2000  # 20000 * 10%
    assert body["final_subtotal_cents"] == 18000


def test_submit_order_path2(db, tenant: Tenant, storefront) -> None:
    from sqlalchemy import select

    client = TestClient(app)
    token = _make_cart(client, storefront)

    resp = client.post("/v1/storefront/orders", json={
        "cart_token": token,
        "payment_provider": "stripe",
        "payment_reference": "pi_test_12345",
        "customer_email": "shopper@example.com",
        "shipping_address": {"country": "IN", "city": "Mumbai"},
    }, headers=_h(storefront))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "confirmed"
    assert body["customer_email"] == "shopper@example.com"
    assert body["total_cents"] == 20000

    order = db.execute(
        select(Order).where(Order.id == uuid.UUID(body["id"]))
    ).scalar_one()
    assert order.tenant_id == tenant.id
    assert order.channel_id == storefront["channel"].id


def test_submit_order_clears_cart(db, tenant: Tenant, storefront) -> None:
    client = TestClient(app)
    token = _make_cart(client, storefront)

    client.post("/v1/storefront/orders", json={
        "cart_token": token,
        "payment_provider": "cod",
        "payment_reference": "cod-001",
    }, headers=_h(storefront))

    cart = client.get(f"/v1/storefront/cart/{token}", headers=_h(storefront)).json()
    assert cart["items"] == []
