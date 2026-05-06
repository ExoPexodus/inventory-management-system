# NOTE: `from __future__ import annotations` deliberately absent.

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Channel, InventoryPool, InventoryPoolShop, Product, Shop, Tenant


@pytest.fixture()
def woo_channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id, type="woocommerce", name="WooCommerce",
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


def test_connect_success(db, tenant: Tenant, woo_channel: Channel, auth_headers) -> None:
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"store_name": "My Store", "currency": "INR"}

    with patch("httpx.get", return_value=mock_resp):
        client = TestClient(app)
        resp = client.post(
            f"/v1/admin/channels/{woo_channel.id}/woocommerce/connect",
            json={"woocommerce_store_url": "https://mystore.com",
                  "woocommerce_consumer_key": "ck_test",
                  "woocommerce_consumer_secret": "cs_test",
                  "woocommerce_webhook_secret": "whs_test"},
            headers=auth_headers,
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["store_name"] == "My Store"
    db.refresh(woo_channel)
    assert woo_channel.config["woocommerce_store_url"] == "https://mystore.com"


def test_connect_bad_credentials(db, tenant: Tenant, woo_channel: Channel, auth_headers) -> None:
    mock_resp = MagicMock(status_code=401)
    mock_resp.json.return_value = {}

    with patch("httpx.get", return_value=mock_resp):
        client = TestClient(app)
        resp = client.post(
            f"/v1/admin/channels/{woo_channel.id}/woocommerce/connect",
            json={"woocommerce_store_url": "https://bad.com",
                  "woocommerce_consumer_key": "bad",
                  "woocommerce_consumer_secret": "bad",
                  "woocommerce_webhook_secret": "whs"},
            headers=auth_headers,
        )
    assert resp.status_code == 400
    assert "credentials" in resp.json()["detail"].lower()


def test_sync_catalog(db, tenant: Tenant, woo_channel: Channel, auth_headers) -> None:
    woo_channel.config = {
        "woocommerce_store_url": "https://test.com",
        "woocommerce_consumer_key": "ck",
        "woocommerce_consumer_secret": "cs",
        "woocommerce_webhook_secret": "whs",
    }
    db.flush()
    p = Product(tenant_id=tenant.id, name="Widget", sku="W001",
                unit_price_cents=1999, product_type="physical", status="active")
    db.add(p)
    db.commit()

    def mock_post(url, **kwargs):
        m = MagicMock(status_code=201)
        m.json.return_value = {"id": 42, "sku": "W001"}
        return m

    with patch("httpx.post", side_effect=mock_post):
        client = TestClient(app)
        resp = client.post(
            f"/v1/admin/channels/{woo_channel.id}/woocommerce/sync-catalog",
            headers=auth_headers,
        )
    assert resp.status_code == 200
    assert resp.json()["synced"] >= 1
    assert resp.json()["errors"] == 0


def test_import_catalog(db, tenant: Tenant, woo_channel: Channel, auth_headers) -> None:
    woo_channel.config = {
        "woocommerce_store_url": "https://test.com",
        "woocommerce_consumer_key": "ck",
        "woocommerce_consumer_secret": "cs",
        "woocommerce_webhook_secret": "whs",
    }
    db.flush()
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = [
        {"id": 1, "name": "WC Widget", "sku": "WC-001", "price": "9.99", "status": "publish"},
    ]

    with patch("httpx.get", return_value=mock_resp):
        client = TestClient(app)
        resp = client.post(
            f"/v1/admin/channels/{woo_channel.id}/woocommerce/import-catalog",
            headers=auth_headers,
        )
    assert resp.status_code == 200
    assert resp.json()["created"] == 1
