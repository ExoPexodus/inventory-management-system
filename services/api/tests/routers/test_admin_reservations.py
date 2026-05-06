# NOTE: `from __future__ import annotations` deliberately absent — see same comment
# in test_entitlements_dep.py (PEP 563 + FastAPI inline-route type hints).

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import (
    Channel, InventoryPool, InventoryPoolShop, Product, Shop, StockReservation, Tenant,
)


@pytest.fixture()
def channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"POS at {shop.name}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id, type="pos", name=f"POS at {shop.name}", config={},
        inventory_pool_id=pool.id, currency_code="USD", shop_id=shop.id,
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def product(db, tenant: Tenant) -> Product:
    p = Product(tenant_id=tenant.id, name="W", sku=f"sku-{uuid.uuid4().hex[:6]}", unit_price_cents=500)
    db.add(p)
    db.flush()
    return p


@pytest.fixture()
def auth_headers(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        role="owner",
        role_id=None,
        is_legacy_token=False,
        permissions=frozenset({"reservations:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield {}
    app.dependency_overrides.clear()


def _seed_reservation(db, *, tenant_id, channel_id, product_id, shop_id, status="active") -> StockReservation:
    res = StockReservation(
        tenant_id=tenant_id,
        channel_id=channel_id,
        product_id=product_id,
        shop_id=shop_id,
        quantity=1,
        cart_token=f"cart-{uuid.uuid4().hex[:8]}",
        purpose="cart",
        status=status,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    db.add(res)
    db.flush()
    return res


def test_list_reservations(db, tenant: Tenant, shop: Shop, channel: Channel, product: Product, auth_headers) -> None:
    _seed_reservation(db, tenant_id=tenant.id, channel_id=channel.id, product_id=product.id, shop_id=shop.id)
    _seed_reservation(db, tenant_id=tenant.id, channel_id=channel.id, product_id=product.id, shop_id=shop.id, status="released")
    db.commit()

    client = TestClient(app)
    resp = client.get("/v1/admin/reservations", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2


def test_filter_by_status(db, tenant: Tenant, shop: Shop, channel: Channel, product: Product, auth_headers) -> None:
    _seed_reservation(db, tenant_id=tenant.id, channel_id=channel.id, product_id=product.id, shop_id=shop.id, status="active")
    _seed_reservation(db, tenant_id=tenant.id, channel_id=channel.id, product_id=product.id, shop_id=shop.id, status="expired")
    db.commit()

    client = TestClient(app)
    resp = client.get("/v1/admin/reservations?status=expired", headers=auth_headers)
    assert resp.status_code == 200
    statuses = {r["status"] for r in resp.json()}
    assert statuses == {"expired"}


def test_manual_release(db, tenant: Tenant, shop: Shop, channel: Channel, product: Product, auth_headers) -> None:
    res = _seed_reservation(db, tenant_id=tenant.id, channel_id=channel.id, product_id=product.id, shop_id=shop.id)
    db.commit()

    client = TestClient(app)
    resp = client.post(f"/v1/admin/reservations/{res.id}/release", headers=auth_headers)
    assert resp.status_code == 204

    db.refresh(res)
    assert res.status == "released"


def test_release_already_released_returns_409(db, tenant: Tenant, shop: Shop, channel: Channel, product: Product, auth_headers) -> None:
    res = _seed_reservation(db, tenant_id=tenant.id, channel_id=channel.id, product_id=product.id, shop_id=shop.id, status="released")
    db.commit()

    client = TestClient(app)
    resp = client.post(f"/v1/admin/reservations/{res.id}/release", headers=auth_headers)
    assert resp.status_code == 409
    assert "active" in resp.json()["detail"].lower()


def test_manual_sweep_expired(db, tenant: Tenant, shop: Shop, channel: Channel, product: Product, auth_headers) -> None:
    res = StockReservation(
        tenant_id=tenant.id, channel_id=channel.id, product_id=product.id,
        shop_id=shop.id, quantity=1, cart_token="cart_old", purpose="cart",
        status="active", expires_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db.add(res)
    db.commit()

    client = TestClient(app)
    resp = client.post("/v1/admin/reservations/sweep-expired", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["expired_count"] == 1


def test_cross_tenant_release_blocked(db, tenant: Tenant, shop: Shop, channel: Channel, product: Product, auth_headers) -> None:
    """Release attempt for a reservation belonging to a different tenant returns 404."""
    other = Tenant(name=f"other-{uuid.uuid4().hex[:6]}", slug=f"other-{uuid.uuid4().hex[:8]}")
    db.add(other)
    db.flush()
    other_shop = Shop(tenant_id=other.id, name="other-shop")
    db.add(other_shop)
    db.flush()
    pool = InventoryPool(tenant_id=other.id, name="other-pool")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=other.id, pool_id=pool.id, shop_id=other_shop.id))
    db.flush()
    other_ch = Channel(
        tenant_id=other.id, type="pos", name="other-pos", config={},
        inventory_pool_id=pool.id, currency_code="USD", shop_id=other_shop.id,
    )
    db.add(other_ch)
    db.flush()
    other_prod = Product(tenant_id=other.id, name="P", sku=f"sku-{uuid.uuid4().hex[:6]}", unit_price_cents=100)
    db.add(other_prod)
    db.flush()
    other_res = _seed_reservation(
        db, tenant_id=other.id, channel_id=other_ch.id,
        product_id=other_prod.id, shop_id=other_shop.id,
    )
    db.commit()

    client = TestClient(app)
    resp = client.post(f"/v1/admin/reservations/{other_res.id}/release", headers=auth_headers)
    assert resp.status_code == 404
