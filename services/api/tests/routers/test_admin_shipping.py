# NOTE: `from __future__ import annotations` deliberately absent.

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Channel, InventoryPool, InventoryPoolShop, ShippingRate, ShippingZone, Shop, Tenant


@pytest.fixture()
def channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id, type="headless", name=f"headless-{uuid.uuid4().hex[:6]}",
        config={}, inventory_pool_id=pool.id, currency_code="USD",
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
        is_legacy_token=False, permissions=frozenset({"shipping:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield {}
    app.dependency_overrides.clear()


def test_create_zone(db, tenant: Tenant, channel: Channel, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/shipping/zones", json={
        "channel_id": str(channel.id),
        "name": "Domestic",
        "countries": ["IN"],
        "is_catch_all": False,
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Domestic"
    assert body["countries"] == ["IN"]


def test_list_zones(db, tenant: Tenant, channel: Channel, auth_headers) -> None:
    db.add(ShippingZone(
        tenant_id=tenant.id, channel_id=channel.id,
        name="Zone A", countries=["US"], is_catch_all=False,
    ))
    db.commit()

    client = TestClient(app)
    resp = client.get(f"/v1/admin/shipping/zones?channel_id={channel.id}", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_delete_zone(db, tenant: Tenant, channel: Channel, auth_headers) -> None:
    zone = ShippingZone(
        tenant_id=tenant.id, channel_id=channel.id,
        name="Doomed Zone", countries=["ZZ"], is_catch_all=False,
    )
    db.add(zone)
    db.commit()

    client = TestClient(app)
    resp = client.delete(f"/v1/admin/shipping/zones/{zone.id}", headers=auth_headers)
    assert resp.status_code == 204


def test_create_rate(db, tenant: Tenant, channel: Channel, auth_headers) -> None:
    zone = ShippingZone(
        tenant_id=tenant.id, channel_id=channel.id,
        name="Domestic", countries=["IN"], is_catch_all=False,
    )
    db.add(zone)
    db.commit()

    client = TestClient(app)
    resp = client.post(f"/v1/admin/shipping/zones/{zone.id}/rates", json={
        "name": "Standard",
        "base_price_cents": 9900,
        "currency_code": "INR",
        "free_above_cents": 50000,
        "condition_type": "none",
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Standard"
    assert body["base_price_cents"] == 9900
    assert body["free_above_cents"] == 50000


def test_list_rates(db, tenant: Tenant, channel: Channel, auth_headers) -> None:
    zone = ShippingZone(
        tenant_id=tenant.id, channel_id=channel.id,
        name="Z", countries=["IN"], is_catch_all=False,
    )
    db.add(zone)
    db.flush()
    db.add(ShippingRate(
        tenant_id=tenant.id, zone_id=zone.id,
        name="Express", base_price_cents=19900, currency_code="INR",
    ))
    db.commit()

    client = TestClient(app)
    resp = client.get(f"/v1/admin/shipping/zones/{zone.id}/rates", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_delete_rate(db, tenant: Tenant, channel: Channel, auth_headers) -> None:
    zone = ShippingZone(
        tenant_id=tenant.id, channel_id=channel.id,
        name="ZZ", countries=["IN"], is_catch_all=False,
    )
    db.add(zone)
    db.flush()
    rate = ShippingRate(
        tenant_id=tenant.id, zone_id=zone.id,
        name="Doomed Rate", base_price_cents=100, currency_code="INR",
    )
    db.add(rate)
    db.commit()

    client = TestClient(app)
    resp = client.delete(f"/v1/admin/shipping/zones/{zone.id}/rates/{rate.id}", headers=auth_headers)
    assert resp.status_code == 204


def test_cross_tenant_zone_blocked(db, tenant: Tenant, auth_headers) -> None:
    other = Tenant(name=f"other-{uuid.uuid4().hex[:6]}", slug=f"other-{uuid.uuid4().hex[:8]}")
    db.add(other)
    db.flush()
    other_pool = InventoryPool(tenant_id=other.id, name="pool")
    db.add(other_pool)
    db.flush()
    other_ch = Channel(
        tenant_id=other.id, type="headless", name="other-ch",
        config={}, inventory_pool_id=other_pool.id, currency_code="USD",
    )
    db.add(other_ch)
    db.commit()

    client = TestClient(app)
    resp = client.post("/v1/admin/shipping/zones", json={
        "channel_id": str(other_ch.id),
        "name": "Cross-tenant",
        "countries": ["US"],
    }, headers=auth_headers)
    assert resp.status_code == 400
