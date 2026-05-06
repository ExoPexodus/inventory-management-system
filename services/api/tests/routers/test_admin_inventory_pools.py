import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Channel, InventoryPool, InventoryPoolShop, Shop, Tenant


@pytest.fixture()
def all_shops_pool(db, tenant: Tenant, shop: Shop) -> InventoryPool:
    """Mirror migration: create the tenant's All Shops pool."""
    pool = InventoryPool(tenant_id=tenant.id, name="All Shops")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    return pool


@pytest.fixture()
def pos_channel(db, tenant: Tenant, shop: Shop) -> Channel:
    """Mirror migration: POS channel + single-shop pool for the test shop."""
    pool = InventoryPool(tenant_id=tenant.id, name=f"POS at {shop.name}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id,
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
def auth_headers(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        role="owner",
        role_id=None,
        is_legacy_token=False,
        permissions=frozenset({"inventory_pools:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield {}
    app.dependency_overrides.clear()


def test_list_pools_includes_default(db, tenant: Tenant, all_shops_pool: InventoryPool, auth_headers) -> None:
    client = TestClient(app)
    resp = client.get("/v1/admin/inventory-pools", headers=auth_headers)
    assert resp.status_code == 200
    names = {p["name"] for p in resp.json()}
    assert "All Shops" in names


def test_create_pool_with_shops(db, tenant: Tenant, shop: Shop, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/inventory-pools", json={
        "name": "Custom Pool",
        "shop_ids": [str(shop.id)],
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Custom Pool"
    assert body["shop_ids"] == [str(shop.id)]
    assert body["fulfillment_policy"] == "fulfill_from_primary"


def test_update_pool_membership(db, tenant: Tenant, auth_headers) -> None:
    """PATCH replaces the shop set when shop_ids is provided."""
    pool = InventoryPool(tenant_id=tenant.id, name="patch-target")
    db.add(pool)
    db.flush()

    s1 = Shop(tenant_id=tenant.id, name=f"shop-1-{uuid.uuid4().hex[:6]}")
    s2 = Shop(tenant_id=tenant.id, name=f"shop-2-{uuid.uuid4().hex[:6]}")
    db.add(s1)
    db.add(s2)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=s1.id))
    db.commit()

    client = TestClient(app)
    resp = client.patch(f"/v1/admin/inventory-pools/{pool.id}", json={
        "shop_ids": [str(s2.id)],
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["shop_ids"] == [str(s2.id)]


def test_delete_pool(db, tenant: Tenant, auth_headers) -> None:
    pool = InventoryPool(tenant_id=tenant.id, name="doomed")
    db.add(pool)
    db.commit()

    client = TestClient(app)
    resp = client.delete(f"/v1/admin/inventory-pools/{pool.id}", headers=auth_headers)
    assert resp.status_code == 204


def test_cannot_delete_pool_in_use(db, pos_channel: Channel, auth_headers) -> None:
    """A pool with active channels cannot be deleted (FK is RESTRICT)."""
    pool_in_use_id = pos_channel.inventory_pool_id

    client = TestClient(app)
    resp = client.delete(f"/v1/admin/inventory-pools/{pool_in_use_id}", headers=auth_headers)
    assert resp.status_code == 409
    assert "in use" in resp.json()["detail"].lower()


def test_pool_shop_must_belong_to_tenant(db, tenant: Tenant, auth_headers) -> None:
    """Cross-tenant shop ID rejected."""
    other_tenant = Tenant(name=f"other-{uuid.uuid4().hex[:6]}", slug=f"other-{uuid.uuid4().hex[:8]}")
    db.add(other_tenant)
    db.flush()
    other_shop = Shop(tenant_id=other_tenant.id, name="other-shop")
    db.add(other_shop)
    db.commit()

    client = TestClient(app)
    resp = client.post("/v1/admin/inventory-pools", json={
        "name": "Cross-tenant attempt",
        "shop_ids": [str(other_shop.id)],
    }, headers=auth_headers)
    assert resp.status_code == 400
