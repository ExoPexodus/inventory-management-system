# NOTE: `from __future__ import annotations` deliberately absent.

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import (
    Channel, InventoryPool, InventoryPoolShop, Product, ProductPrice, Shop, Tenant,
)


@pytest.fixture()
def channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"POS at {shop.name}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id, type="manual", name=f"channel-{uuid.uuid4().hex[:6]}",
        config={}, inventory_pool_id=pool.id, currency_code="USD",
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def product(db, tenant: Tenant) -> Product:
    p = Product(
        tenant_id=tenant.id, name="Widget",
        sku=f"sku-{uuid.uuid4().hex[:6]}", unit_price_cents=1999,
    )
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
        permissions=frozenset({"currency:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield {}
    app.dependency_overrides.clear()


def test_create_tenant_wide_product_price(db, tenant: Tenant, product: Product, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post(f"/v1/admin/products/{product.id}/prices", json={
        "channel_id": None,
        "currency_code": "EUR",
        "amount_cents": 1899,
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["currency_code"] == "EUR"
    assert body["amount_cents"] == 1899
    assert body["channel_id"] is None


def test_create_channel_specific_product_price(db, tenant: Tenant, channel: Channel, product: Product, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post(f"/v1/admin/products/{product.id}/prices", json={
        "channel_id": str(channel.id),
        "currency_code": "USD",
        "amount_cents": 1799,
    }, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json()["channel_id"] == str(channel.id)


def test_list_product_prices(db, tenant: Tenant, channel: Channel, product: Product, auth_headers) -> None:
    db.add(ProductPrice(
        tenant_id=tenant.id, product_id=product.id, channel_id=None,
        currency_code="EUR", amount_cents=1899,
    ))
    db.add(ProductPrice(
        tenant_id=tenant.id, product_id=product.id, channel_id=channel.id,
        currency_code="USD", amount_cents=1799,
    ))
    db.commit()

    client = TestClient(app)
    resp = client.get(f"/v1/admin/products/{product.id}/prices", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_upsert_replaces_existing(db, tenant: Tenant, channel: Channel, product: Product, auth_headers) -> None:
    """POSTing same (product, channel, currency) twice updates."""
    client = TestClient(app)
    r1 = client.post(f"/v1/admin/products/{product.id}/prices", json={
        "channel_id": None, "currency_code": "EUR", "amount_cents": 1899,
    }, headers=auth_headers)
    r2 = client.post(f"/v1/admin/products/{product.id}/prices", json={
        "channel_id": None, "currency_code": "EUR", "amount_cents": 1999,
    }, headers=auth_headers)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]
    assert r2.json()["amount_cents"] == 1999


def test_delete_product_price(db, tenant: Tenant, product: Product, auth_headers) -> None:
    pp = ProductPrice(
        tenant_id=tenant.id, product_id=product.id, channel_id=None,
        currency_code="EUR", amount_cents=1899,
    )
    db.add(pp)
    db.commit()

    client = TestClient(app)
    resp = client.delete(f"/v1/admin/products/{product.id}/prices/{pp.id}", headers=auth_headers)
    assert resp.status_code == 204


def test_negative_amount_rejected(db, tenant: Tenant, product: Product, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post(f"/v1/admin/products/{product.id}/prices", json={
        "channel_id": None, "currency_code": "EUR", "amount_cents": -100,
    }, headers=auth_headers)
    assert resp.status_code == 422


def test_cross_tenant_product_blocked(db, tenant: Tenant, auth_headers) -> None:
    """Operator can't price a product from a different tenant."""
    other = Tenant(name=f"other-{uuid.uuid4().hex[:6]}", slug=f"other-{uuid.uuid4().hex[:8]}")
    db.add(other)
    db.flush()
    other_p = Product(
        tenant_id=other.id, name="Other",
        sku=f"sku-{uuid.uuid4().hex[:6]}", unit_price_cents=100,
    )
    db.add(other_p)
    db.commit()

    client = TestClient(app)
    resp = client.post(f"/v1/admin/products/{other_p.id}/prices", json={
        "channel_id": None, "currency_code": "EUR", "amount_cents": 100,
    }, headers=auth_headers)
    assert resp.status_code == 404
