# NOTE: `from __future__ import annotations` deliberately absent.

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Channel, InventoryPool, InventoryPoolShop, Product, TaxRegion, TaxRule, Shop, Tenant


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
        tax_included_in_price=False,
    )
    db.add(channel)
    db.flush()

    product = Product(
        tenant_id=tenant.id, name="Widget", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=10000, product_type="physical",
    )
    db.add(product)
    db.flush()

    region = TaxRegion(tenant_id=tenant.id, name="India", country_code="IN")
    db.add(region)
    db.flush()

    db.add(TaxRule(
        tenant_id=tenant.id, region_id=region.id,
        tax_class="standard", label="GST 18%",
        components=[{"label": "GST", "rate_bps": 1800}],
    ))
    db.commit()

    return {"channel": channel, "product": product}


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


def test_calculate_returns_tax(db, tenant: Tenant, setup, auth) -> None:
    client = TestClient(app)
    resp = client.post("/v1/tax/calculate", json={
        "channel_id": str(setup["channel"].id),
        "destination": {"country": "IN"},
        "cart_lines": [
            {"product_id": str(setup["product"].id), "quantity": 1, "unit_price_cents": 10000}
        ],
        "currency": "INR",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_tax_cents"] == 1800
    assert body["tax_included"] is False
    assert len(body["lines"]) == 1
    assert body["lines"][0]["tax_cents"] == 1800


def test_calculate_no_region_returns_zero(db, tenant: Tenant, setup, auth) -> None:
    client = TestClient(app)
    resp = client.post("/v1/tax/calculate", json={
        "channel_id": str(setup["channel"].id),
        "destination": {"country": "DE"},
        "cart_lines": [
            {"product_id": str(setup["product"].id), "quantity": 1, "unit_price_cents": 10000}
        ],
        "currency": "INR",
    })
    assert resp.status_code == 200
    assert resp.json()["total_tax_cents"] == 0
