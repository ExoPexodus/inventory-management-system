# NOTE: `from __future__ import annotations` deliberately absent.

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Channel, Discount, InventoryPool, InventoryPoolShop, Shop, Tenant


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
    disc = Discount(
        tenant_id=tenant.id, name="10% off", code="TEN",
        discount_type="percentage", value_bps=1000, status="active",
    )
    db.add(disc)
    db.commit()
    return {"channel": channel, "discount": disc}


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


def test_apply_discount_endpoint(db, tenant: Tenant, setup, auth) -> None:
    client = TestClient(app)
    resp = client.post("/v1/discounts/apply", json={
        "channel_id": str(setup["channel"].id),
        "code": "TEN",
        "cart_subtotal_cents": 10000,
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["discount_amount_cents"] == 1000
    assert body["final_total_cents"] == 9000
    assert body["is_free_shipping"] is False


def test_apply_unknown_code_returns_404(db, tenant: Tenant, setup, auth) -> None:
    client = TestClient(app)
    resp = client.post("/v1/discounts/apply", json={
        "channel_id": str(setup["channel"].id),
        "code": "NOPE",
        "cart_subtotal_cents": 10000,
    })
    assert resp.status_code == 404


def test_apply_ineligible_discount_returns_422(db, tenant: Tenant, setup, auth) -> None:
    disc2 = Discount(
        tenant_id=tenant.id, name="High min", code="HIGHMIN",
        discount_type="percentage", value_bps=500, status="active",
        min_subtotal_cents=50000,
    )
    db.add(disc2)
    db.commit()

    client = TestClient(app)
    resp = client.post("/v1/discounts/apply", json={
        "channel_id": str(setup["channel"].id),
        "code": "HIGHMIN",
        "cart_subtotal_cents": 1000,
    })
    assert resp.status_code == 422
    assert "minimum" in resp.json()["detail"].lower()
