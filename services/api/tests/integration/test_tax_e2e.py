"""End-to-end smoke test for the tax engine."""
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
        tax_included_in_price=False,
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def product(db, tenant: Tenant) -> Product:
    p = Product(
        tenant_id=tenant.id, name="Widget", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=10000, product_type="physical",
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
        permissions=frozenset({"tax:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield
    app.dependency_overrides.clear()


def _calc(client, channel_id, product_id, subtotal=10000, country="IN", state=None, currency="INR"):
    dest = {"country": country}
    if state:
        dest["state"] = state
    return client.post("/v1/tax/calculate", json={
        "channel_id": str(channel_id),
        "destination": dest,
        "cart_lines": [{"product_id": str(product_id), "quantity": 1, "unit_price_cents": subtotal}],
        "currency": currency,
    })


def test_india_gst_split_exclusive(db, tenant: Tenant, channel: Channel, product: Product, auth) -> None:
    """Create India region + CGST+SGST rule → correct tax split on calculate."""
    client = TestClient(app)

    region = client.post("/v1/admin/tax/regions", json={"name": "India GST", "country_code": "IN"})
    assert region.status_code == 201
    region_id = region.json()["id"]

    rule = client.post(f"/v1/admin/tax/regions/{region_id}/rules", json={
        "tax_class": "standard", "label": "GST 18%",
        "components": [
            {"label": "CGST", "rate_bps": 900},
            {"label": "SGST", "rate_bps": 900},
        ],
    })
    assert rule.status_code == 201

    resp = _calc(client, channel.id, product.id, subtotal=10000, country="IN")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_tax_cents"] == 1800
    assert body["tax_included"] is False
    components = body["lines"][0]["components"]
    assert len(components) == 2
    assert components[0]["label"] == "CGST"
    assert components[0]["tax_cents"] == 900
    assert components[1]["label"] == "SGST"
    assert components[1]["tax_cents"] == 900


def test_donation_zero_tax(db, tenant: Tenant, channel: Channel, auth) -> None:
    """Donation product always gets 0 tax even with a matching region+rule."""
    client = TestClient(app)

    region = client.post("/v1/admin/tax/regions", json={"name": "India", "country_code": "IN"})
    region_id = region.json()["id"]
    client.post(f"/v1/admin/tax/regions/{region_id}/rules", json={
        "tax_class": "standard", "label": "GST 18%",
        "components": [{"label": "GST", "rate_bps": 1800}],
    })

    donation = Product(
        tenant_id=tenant.id, name="Donate", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=500, product_type="donation",
    )
    db.add(donation)
    db.commit()

    resp = _calc(client, channel.id, donation.id, subtotal=500)
    assert resp.status_code == 200
    assert resp.json()["total_tax_cents"] == 0


def test_no_region_zero_tax(db, tenant: Tenant, channel: Channel, product: Product, auth) -> None:
    """No region configured → 0 tax."""
    client = TestClient(app)
    resp = _calc(client, channel.id, product.id, country="IN")
    assert resp.status_code == 200
    assert resp.json()["total_tax_cents"] == 0
