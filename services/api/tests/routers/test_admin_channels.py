# NOTE: `from __future__ import annotations` deliberately absent — see same comment
# in test_entitlements_dep.py (PEP 563 + FastAPI inline-route type hints).

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import (
    Channel, InventoryPool, InventoryPoolShop, Shop, Tenant, TenantLicenseCache,
)


@pytest.fixture()
def licensed_tenant(db, tenant: Tenant) -> Tenant:
    """Pro plan with max_channels=5."""
    db.add(TenantLicenseCache(
        tenant_id=tenant.id,
        subscription_status="active",
        plan_codename="pro",
        max_shops=5,
        max_employees=20,
        storage_limit_mb=10000,
        last_synced_at=datetime.now(UTC),
    ))
    db.commit()
    return tenant


@pytest.fixture()
def all_shops_pool(db, licensed_tenant: Tenant, shop: Shop) -> InventoryPool:
    """Mirror migration: create the tenant's All Shops pool with the test shop in it."""
    pool = InventoryPool(tenant_id=licensed_tenant.id, name="All Shops")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=licensed_tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    return pool


@pytest.fixture()
def pos_channel(db, licensed_tenant: Tenant, shop: Shop) -> Channel:
    """Mirror migration: create POS channel + single-shop pool for the test shop."""
    pool = InventoryPool(tenant_id=licensed_tenant.id, name=f"POS at {shop.name}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=licensed_tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=licensed_tenant.id,
        type="pos",
        name=f"POS at {shop.name}",
        config={},
        inventory_pool_id=pool.id,
        currency_code="USD",
        shop_id=shop.id,
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def auth_headers(db, licensed_tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=uuid.uuid4(),
        tenant_id=licensed_tenant.id,
        role="owner",
        role_id=None,
        is_legacy_token=False,
        permissions=frozenset({"channels:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield {}
    app.dependency_overrides.clear()


def test_list_channels_includes_pos(db, pos_channel: Channel, auth_headers) -> None:
    """List should include the POS channel created in the fixture."""
    client = TestClient(app)
    resp = client.get("/v1/admin/channels", headers=auth_headers)
    assert resp.status_code == 200
    types = {c["type"] for c in resp.json()}
    assert "pos" in types


def test_create_manual_channel(db, licensed_tenant: Tenant, all_shops_pool: InventoryPool, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/channels", json={
        "type": "manual",
        "name": "B2B Phone Orders",
        "inventory_pool_id": str(all_shops_pool.id),
        "currency_code": "USD",
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["type"] == "manual"
    assert body["name"] == "B2B Phone Orders"
    assert body["status"] == "active"


def test_cannot_create_pos_channel_via_api(db, all_shops_pool: InventoryPool, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/channels", json={
        "type": "pos",
        "name": "rogue-pos",
        "inventory_pool_id": str(all_shops_pool.id),
        "currency_code": "USD",
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert "pos" in resp.json()["detail"].lower()


def test_cannot_delete_pos_channel(db, pos_channel: Channel, auth_headers) -> None:
    client = TestClient(app)
    resp = client.delete(f"/v1/admin/channels/{pos_channel.id}", headers=auth_headers)
    assert resp.status_code == 400
    assert "pos" in resp.json()["detail"].lower()


def test_max_channels_entitlement_enforced(db, tenant: Tenant, shop: Shop) -> None:
    """A free-plan tenant (max_channels=1) with one existing channel hits 403 on second create."""
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    db.add(TenantLicenseCache(
        tenant_id=tenant.id,
        subscription_status="active",
        plan_codename="free",
        max_shops=1, max_employees=2, storage_limit_mb=500,
        last_synced_at=datetime.now(UTC),
    ))
    # Create the "All Shops" pool + one POS channel (current_count=1)
    pool = InventoryPool(tenant_id=tenant.id, name="All Shops")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    pos_pool = InventoryPool(tenant_id=tenant.id, name=f"POS at {shop.name}")
    db.add(pos_pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pos_pool.id, shop_id=shop.id))
    db.add(Channel(
        tenant_id=tenant.id, type="pos", name=f"POS at {shop.name}",
        config={}, inventory_pool_id=pos_pool.id, currency_code="USD", shop_id=shop.id,
    ))
    db.commit()

    fake_ctx = AdminContext(
        user_id=uuid.uuid4(), tenant_id=tenant.id,
        role="owner", role_id=None, is_legacy_token=False,
        permissions=frozenset({"channels:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    try:
        client = TestClient(app)
        resp = client.post("/v1/admin/channels", json={
            "type": "manual",
            "name": "Should-Be-Rejected",
            "inventory_pool_id": str(pool.id),
            "currency_code": "USD",
        })
        assert resp.status_code == 403, resp.text
        body = resp.json()
        assert body["detail"]["error"] == "plan_upgrade_required"
        assert body["detail"]["required_feature"] == "max_channels"
    finally:
        app.dependency_overrides.clear()
