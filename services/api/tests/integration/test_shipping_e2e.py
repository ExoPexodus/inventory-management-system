"""End-to-end smoke test for the shipping engine."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Channel, InventoryPool, InventoryPoolShop, Product, Shop, Tenant


@pytest.fixture()
def channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id, type="headless", name=f"headless-{uuid.uuid4().hex[:6]}",
        config={}, inventory_pool_id=pool.id, currency_code="INR",
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def physical_product(db, tenant: Tenant) -> Product:
    p = Product(
        tenant_id=tenant.id, name="Widget", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=1000, product_type="physical", weight_grams=300,
    )
    db.add(p)
    db.flush()
    return p


@pytest.fixture()
def digital_product(db, tenant: Tenant) -> Product:
    p = Product(
        tenant_id=tenant.id, name="eBook", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=500, product_type="digital",
    )
    db.add(p)
    db.flush()
    return p


@pytest.fixture()
def auth(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=None, tenant_id=tenant.id,
        role="owner", role_id=None, is_legacy_token=False,
        permissions=frozenset({"shipping:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield
    app.dependency_overrides.clear()


def _calc(client, channel_id, product_id, qty=1, subtotal=1000, country="IN", currency="INR"):
    return client.post("/v1/shipping/calculate", json={
        "channel_id": str(channel_id),
        "destination": {"country": country},
        "cart_lines": [{"product_id": str(product_id), "quantity": qty, "unit_price_cents": 1000}],
        "cart_subtotal_cents": subtotal,
        "currency": currency,
    })


def test_full_lifecycle(db, tenant: Tenant, channel: Channel, physical_product: Product, auth) -> None:
    """Create zone+rate via admin API → calculator returns the rate for a matching cart."""
    client = TestClient(app)

    zone_resp = client.post("/v1/admin/shipping/zones", json={
        "channel_id": str(channel.id),
        "name": "India",
        "countries": ["IN"],
    })
    assert zone_resp.status_code == 201
    zone_id = zone_resp.json()["id"]

    rate_resp = client.post(f"/v1/admin/shipping/zones/{zone_id}/rates", json={
        "name": "Standard",
        "base_price_cents": 9900,
        "currency_code": "INR",
        "free_above_cents": 100000,
    })
    assert rate_resp.status_code == 201

    # Below free threshold
    calc = _calc(client, channel.id, physical_product.id, subtotal=1000)
    assert calc.status_code == 200
    options = calc.json()
    assert len(options) == 1
    assert options[0]["name"] == "Standard"
    assert options[0]["price_cents"] == 9900
    assert options[0]["is_free"] is False

    # Above free threshold
    free_calc = _calc(client, channel.id, physical_product.id, subtotal=120000)
    assert free_calc.status_code == 200
    assert free_calc.json()[0]["is_free"] is True
    assert free_calc.json()[0]["price_cents"] == 0


def test_digital_cart_returns_no_rates(db, tenant: Tenant, channel: Channel, digital_product: Product, auth) -> None:
    client = TestClient(app)

    zone_resp = client.post("/v1/admin/shipping/zones", json={
        "channel_id": str(channel.id), "name": "Everywhere",
        "countries": [], "is_catch_all": True,
    })
    client.post(f"/v1/admin/shipping/zones/{zone_resp.json()['id']}/rates", json={
        "name": "Standard", "base_price_cents": 100, "currency_code": "INR",
    })

    calc = _calc(client, channel.id, digital_product.id)
    assert calc.status_code == 200
    assert calc.json() == []


def test_catch_all_serves_unmatched_country(db, tenant: Tenant, channel: Channel, physical_product: Product, auth) -> None:
    client = TestClient(app)

    zone_resp = client.post("/v1/admin/shipping/zones", json={
        "channel_id": str(channel.id), "name": "Rest of World",
        "countries": [], "is_catch_all": True,
    })
    client.post(f"/v1/admin/shipping/zones/{zone_resp.json()['id']}/rates", json={
        "name": "International", "base_price_cents": 49900, "currency_code": "INR",
    })

    calc = _calc(client, channel.id, physical_product.id, country="DE")
    assert calc.status_code == 200
    options = calc.json()
    assert len(options) == 1
    assert options[0]["name"] == "International"
    assert options[0]["price_cents"] == 49900
