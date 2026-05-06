# NOTE: `from __future__ import annotations` deliberately absent.

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Channel, ChannelProductMapping, InventoryPool, InventoryPoolShop, Product, Shop, Tenant


@pytest.fixture()
def shopify_channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id, type="shopify", name="Shopify Store",
        config={}, inventory_pool_id=pool.id, currency_code="INR", status="active",
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
        is_legacy_token=False, permissions=frozenset({"channels:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield {}
    app.dependency_overrides.clear()


def test_connect_shopify_success(db, tenant: Tenant, shopify_channel: Channel, auth_headers) -> None:
    mock_shop = MagicMock(status_code=200)
    mock_shop.json.return_value = {"shop": {"name": "Test Store", "currency": "INR"}}

    mock_loc = MagicMock(status_code=200)
    mock_loc.json.return_value = {"locations": [{"id": 12345678, "name": "Main Warehouse"}]}

    with patch("httpx.get", side_effect=[mock_shop, mock_loc]):
        client = TestClient(app)
        resp = client.post(
            f"/v1/admin/channels/{shopify_channel.id}/shopify/connect",
            json={
                "shopify_shop_domain": "test-store.myshopify.com",
                "shopify_access_token": "shpat_test123",
                "shopify_api_secret": "shpss_test123",
            },
            headers=auth_headers,
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["shop_name"] == "Test Store"
    assert body["location_id"] == "12345678"

    db.refresh(shopify_channel)
    assert shopify_channel.config["shopify_shop_domain"] == "test-store.myshopify.com"
    assert shopify_channel.config["shopify_location_id"] == "12345678"


def test_connect_shopify_bad_credentials(db, tenant: Tenant, shopify_channel: Channel, auth_headers) -> None:
    mock_resp = MagicMock(status_code=401)
    mock_resp.json.return_value = {"errors": "Invalid credentials"}

    with patch("httpx.get", return_value=mock_resp):
        client = TestClient(app)
        resp = client.post(
            f"/v1/admin/channels/{shopify_channel.id}/shopify/connect",
            json={
                "shopify_shop_domain": "bad.myshopify.com",
                "shopify_access_token": "bad_token",
                "shopify_api_secret": "bad_secret",
            },
            headers=auth_headers,
        )
    assert resp.status_code == 400
    assert "credentials" in resp.json()["detail"].lower()


def test_sync_catalog_pushes_products(db, tenant: Tenant, shopify_channel: Channel, auth_headers) -> None:
    shopify_channel.config = {
        "shopify_shop_domain": "test.myshopify.com",
        "shopify_access_token": "tok",
        "shopify_api_secret": "sec",
        "shopify_location_id": "99999",
    }
    db.flush()

    p1 = Product(tenant_id=tenant.id, name="Widget", sku="W001",
                 unit_price_cents=1999, product_type="physical", status="active")
    p2 = Product(tenant_id=tenant.id, name="Book", sku="B001",
                 unit_price_cents=999, product_type="digital", status="active")
    db.add(p1)
    db.add(p2)
    db.commit()

    def mock_post(url, **kwargs):
        m = MagicMock(status_code=201)
        m.json.return_value = {
            "product": {"id": 999, "variants": [{"id": 888, "sku": "W001"}]}
        }
        return m

    with patch("httpx.post", side_effect=mock_post):
        client = TestClient(app)
        resp = client.post(
            f"/v1/admin/channels/{shopify_channel.id}/shopify/sync-catalog",
            headers=auth_headers,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["synced"] == 2
    assert body["errors"] == 0


def test_cross_tenant_channel_blocked(db, tenant: Tenant, auth_headers) -> None:
    import uuid as _uuid
    from app.models import Tenant as TenantModel

    other_tenant = TenantModel(name=f"other-{_uuid.uuid4().hex[:6]}", slug=f"ot-{_uuid.uuid4().hex[:8]}")
    db.add(other_tenant)
    db.flush()

    other_pool = InventoryPool(tenant_id=other_tenant.id, name="pool")
    db.add(other_pool)
    db.flush()

    other_ch = Channel(
        tenant_id=other_tenant.id, type="shopify", name="Other",
        config={}, inventory_pool_id=other_pool.id, currency_code="USD",
    )
    db.add(other_ch)
    db.commit()

    client = TestClient(app)
    resp = client.post(
        f"/v1/admin/channels/{other_ch.id}/shopify/connect",
        json={"shopify_shop_domain": "x.myshopify.com",
              "shopify_access_token": "t", "shopify_api_secret": "s"},
        headers=auth_headers,
    )
    assert resp.status_code == 404
