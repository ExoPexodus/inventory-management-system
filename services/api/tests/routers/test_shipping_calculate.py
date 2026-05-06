# NOTE: `from __future__ import annotations` deliberately absent.

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Channel, InventoryPool, InventoryPoolShop, Product, ShippingRate, ShippingZone, Shop, Tenant


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
    )
    db.add(channel)
    db.flush()

    product = Product(
        tenant_id=tenant.id, name="Widget", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=1000, product_type="physical", weight_grams=500,
    )
    db.add(product)
    db.flush()

    zone = ShippingZone(
        tenant_id=tenant.id, channel_id=channel.id,
        name="Domestic", countries=["IN"], is_catch_all=False,
    )
    db.add(zone)
    db.flush()

    rate = ShippingRate(
        tenant_id=tenant.id, zone_id=zone.id,
        name="Standard", base_price_cents=9900, currency_code="INR",
    )
    db.add(rate)
    db.commit()

    return {"channel": channel, "product": product, "rate": rate}


@pytest.fixture()
def auth(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=None, tenant_id=tenant.id,
        role="owner", role_id=None, is_legacy_token=True,
        permissions=frozenset(),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield
    app.dependency_overrides.clear()


def test_calculate_returns_rates(db, tenant: Tenant, setup, auth) -> None:
    client = TestClient(app)
    resp = client.post("/v1/shipping/calculate", json={
        "channel_id": str(setup["channel"].id),
        "destination": {"country": "IN"},
        "cart_lines": [
            {"product_id": str(setup["product"].id), "quantity": 1, "unit_price_cents": 1000}
        ],
        "cart_subtotal_cents": 1000,
        "currency": "INR",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["name"] == "Standard"
    assert body[0]["price_cents"] == 9900
    assert body[0]["currency_code"] == "INR"


def test_calculate_no_shippable_items(db, tenant: Tenant, setup, auth) -> None:
    digital = Product(
        tenant_id=tenant.id, name="eBook", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=500, product_type="digital",
    )
    db.add(digital)
    db.commit()

    client = TestClient(app)
    resp = client.post("/v1/shipping/calculate", json={
        "channel_id": str(setup["channel"].id),
        "destination": {"country": "IN"},
        "cart_lines": [
            {"product_id": str(digital.id), "quantity": 1, "unit_price_cents": 500}
        ],
        "cart_subtotal_cents": 500,
        "currency": "INR",
    })
    assert resp.status_code == 200
    assert resp.json() == []
