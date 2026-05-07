# NOTE: `from __future__ import annotations` deliberately absent.

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
        tenant_id=tenant.id, type="headless", name="Headless",
        config={}, inventory_pool_id=pool.id, currency_code="INR",
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


def test_setup_stripe(db, tenant: Tenant, channel: Channel, auth_headers) -> None:
    resp = TestClient(app).post(f"/v1/admin/channels/{channel.id}/payment/setup-stripe", json={
        "stripe_secret_key": "sk_test_xxx", "stripe_publishable_key": "pk_test_xxx",
        "checkout_success_url": "https://shop.com/success",
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["payment_provider"] == "stripe"
    db.refresh(channel)
    assert channel.config["stripe_secret_key"] == "sk_test_xxx"


def test_setup_razorpay(db, tenant: Tenant, channel: Channel, auth_headers) -> None:
    resp = TestClient(app).post(f"/v1/admin/channels/{channel.id}/payment/setup-razorpay", json={
        "razorpay_key_id": "rzp_test_xxx", "razorpay_key_secret": "secret",
        "checkout_success_url": "https://shop.com/success",
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["payment_provider"] == "razorpay"


def test_get_payment_config_unconfigured(db, tenant: Tenant, channel: Channel, auth_headers) -> None:
    resp = TestClient(app).get(f"/v1/admin/channels/{channel.id}/payment/config", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["configured"] is False


def test_stripe_overwrites_razorpay(db, tenant: Tenant, channel: Channel, auth_headers) -> None:
    client = TestClient(app)
    client.post(f"/v1/admin/channels/{channel.id}/payment/setup-razorpay", json={
        "razorpay_key_id": "rzp", "razorpay_key_secret": "sec",
        "checkout_success_url": "https://shop.com/success",
    }, headers=auth_headers)
    resp = client.post(f"/v1/admin/channels/{channel.id}/payment/setup-stripe", json={
        "stripe_secret_key": "sk_test", "stripe_publishable_key": "pk_test",
        "checkout_success_url": "https://shop.com/success",
    }, headers=auth_headers)
    assert resp.json()["payment_provider"] == "stripe"
