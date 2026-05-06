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
    db.add(StockMovement(
        tenant_id=tenant.id, shop_id=shop.id, product_id=product.id,
        quantity_delta=10, movement_type="purchase_receipt",
        idempotency_key=f"seed-{uuid.uuid4().hex}",
    ))
    db.commit()
    return {"channel": channel, "product": product, "shop": shop}


def _h(storefront):
    return {"X-Channel-Id": str(storefront["channel"].id)}


def test_create_cart(db, tenant: Tenant, storefront) -> None:
    client = TestClient(app)
    resp = client.post("/v1/storefront/cart", headers=_h(storefront))
    assert resp.status_code == 201
    body = resp.json()
    assert "cart_token" in body
    assert body["items"] == []
    assert body["total_cents"] == 0


def test_add_item_to_cart(db, tenant: Tenant, storefront) -> None:
    client = TestClient(app)
    cart_resp = client.post("/v1/storefront/cart", headers=_h(storefront))
    token = cart_resp.json()["cart_token"]

    add_resp = client.post(f"/v1/storefront/cart/{token}/items", json={
        "product_id": str(storefront["product"].id), "quantity": 2,
    }, headers=_h(storefront))
    assert add_resp.status_code == 200
    cart = add_resp.json()
    assert len(cart["items"]) == 1
    assert cart["items"][0]["quantity"] == 2
    assert cart["items"][0]["unit_price_cents"] == 1999
    assert cart["total_cents"] == 3998


def test_get_cart(db, tenant: Tenant, storefront) -> None:
    client = TestClient(app)
    cart_resp = client.post("/v1/storefront/cart", headers=_h(storefront))
    token = cart_resp.json()["cart_token"]

    client.post(f"/v1/storefront/cart/{token}/items", json={
        "product_id": str(storefront["product"].id), "quantity": 1,
    }, headers=_h(storefront))

    get_resp = client.get(f"/v1/storefront/cart/{token}", headers=_h(storefront))
    assert get_resp.status_code == 200
    assert len(get_resp.json()["items"]) == 1


def test_update_item_quantity(db, tenant: Tenant, storefront) -> None:
    client = TestClient(app)
    cart_resp = client.post("/v1/storefront/cart", headers=_h(storefront))
    token = cart_resp.json()["cart_token"]

    client.post(f"/v1/storefront/cart/{token}/items", json={
        "product_id": str(storefront["product"].id), "quantity": 1,
    }, headers=_h(storefront))

    update_resp = client.post(f"/v1/storefront/cart/{token}/items", json={
        "product_id": str(storefront["product"].id), "quantity": 3,
    }, headers=_h(storefront))
    assert update_resp.status_code == 200
    assert update_resp.json()["total_cents"] == 5997  # 1999 * 3


def test_remove_item_from_cart(db, tenant: Tenant, storefront) -> None:
    client = TestClient(app)
    cart_resp = client.post("/v1/storefront/cart", headers=_h(storefront))
    token = cart_resp.json()["cart_token"]

    add_resp = client.post(f"/v1/storefront/cart/{token}/items", json={
        "product_id": str(storefront["product"].id), "quantity": 2,
    }, headers=_h(storefront))
    item_id = add_resp.json()["items"][0]["id"]

    del_resp = client.delete(f"/v1/storefront/cart/{token}/items/{item_id}",
                             headers=_h(storefront))
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
    cart_resp = client.post("/v1/storefront/cart", headers=_h(storefront))
    token = cart_resp.json()["cart_token"]

    resp = client.post(f"/v1/storefront/cart/{token}/items", json={
        "product_id": str(draft.id), "quantity": 1,
    }, headers=_h(storefront))
    assert resp.status_code == 404


def test_stock_reservation_created(db, tenant: Tenant, storefront) -> None:
    from sqlalchemy import select
    from app.models import StockReservation

    client = TestClient(app)
    cart_resp = client.post("/v1/storefront/cart", headers=_h(storefront))
    token = cart_resp.json()["cart_token"]

    client.post(f"/v1/storefront/cart/{token}/items", json={
        "product_id": str(storefront["product"].id), "quantity": 2,
    }, headers=_h(storefront))

    reservations = db.execute(
        select(StockReservation).where(
            StockReservation.cart_token == token,
            StockReservation.status == "active",
        )
    ).scalars().all()
    assert len(reservations) == 1
    assert reservations[0].quantity == 2
