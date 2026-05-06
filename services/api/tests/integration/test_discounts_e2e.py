"""End-to-end smoke test for the discounts module."""
# NOTE: `from __future__ import annotations` deliberately absent.
# Under PEP 563, FastAPI's get_type_hints() cannot resolve dependency types
# from local scope (becomes a bare string, treated as a query param, 422 on
# every request). See the same comment in test_channels_e2e.py.
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Channel, InventoryPool, InventoryPoolShop, Shop, Tenant


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
def auth(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=None, tenant_id=tenant.id,
        role="owner", role_id=None, is_legacy_token=False,
        permissions=frozenset({"discounts:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield
    app.dependency_overrides.clear()


def _apply(client, channel_id, code, subtotal=10000):
    return client.post("/v1/discounts/apply", json={
        "channel_id": str(channel_id),
        "code": code,
        "cart_subtotal_cents": subtotal,
    })


def test_create_and_apply_percentage(db, tenant: Tenant, channel: Channel, auth) -> None:
    client = TestClient(app)

    resp = client.post("/v1/admin/discounts", json={
        "name": "20% off", "code": "TWENTY",
        "discount_type": "percentage", "value_bps": 2000,
    })
    assert resp.status_code == 201
    assert resp.json()["times_used"] == 0

    apply_resp = _apply(client, channel.id, "TWENTY", subtotal=10000)
    assert apply_resp.status_code == 200
    body = apply_resp.json()
    assert body["discount_amount_cents"] == 2000
    assert body["final_total_cents"] == 8000
    assert body["is_free_shipping"] is False


def test_create_and_apply_free_shipping(db, tenant: Tenant, channel: Channel, auth) -> None:
    client = TestClient(app)

    client.post("/v1/admin/discounts", json={
        "name": "Free Ship", "code": "FREESHIP", "discount_type": "free_shipping",
    })

    apply_resp = _apply(client, channel.id, "FREESHIP", subtotal=5000)
    assert apply_resp.status_code == 200
    assert apply_resp.json()["is_free_shipping"] is True
    assert apply_resp.json()["discount_amount_cents"] == 0


def test_paused_discount_not_applicable(db, tenant: Tenant, channel: Channel, auth) -> None:
    client = TestClient(app)

    resp = client.post("/v1/admin/discounts", json={
        "name": "Was Active", "code": "PAUSE_ME",
        "discount_type": "percentage", "value_bps": 1000,
    })
    disc_id = resp.json()["id"]

    client.patch(f"/v1/admin/discounts/{disc_id}", json={"status": "paused"})

    apply_resp = _apply(client, channel.id, "PAUSE_ME")
    assert apply_resp.status_code == 404


def test_min_subtotal_not_met(db, tenant: Tenant, channel: Channel, auth) -> None:
    client = TestClient(app)

    client.post("/v1/admin/discounts", json={
        "name": "Min 500", "code": "MIN500",
        "discount_type": "percentage", "value_bps": 1000,
        "min_subtotal_cents": 50000,
    })

    apply_resp = _apply(client, channel.id, "MIN500", subtotal=10000)
    assert apply_resp.status_code == 422
    assert "minimum" in apply_resp.json()["detail"].lower()


def test_discount_lifecycle(db, tenant: Tenant, channel: Channel, auth) -> None:
    """Create, list, update, delete — admin management lifecycle."""
    client = TestClient(app)

    create = client.post("/v1/admin/discounts", json={
        "name": "Lifecycle Test", "code": "LIFE",
        "discount_type": "fixed_amount", "value_cents": 300,
    })
    assert create.status_code == 201
    disc_id = create.json()["id"]

    list_resp = client.get("/v1/admin/discounts")
    assert any(d["id"] == disc_id for d in list_resp.json())

    patch = client.patch(f"/v1/admin/discounts/{disc_id}", json={"name": "Renamed"})
    assert patch.status_code == 200
    assert patch.json()["name"] == "Renamed"

    del_resp = client.delete(f"/v1/admin/discounts/{disc_id}")
    assert del_resp.status_code == 204

    list_after = client.get("/v1/admin/discounts")
    assert not any(d["id"] == disc_id for d in list_after.json())
