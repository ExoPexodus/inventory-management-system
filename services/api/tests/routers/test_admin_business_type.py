# NOTE: `from __future__ import annotations` deliberately absent.

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Shop, Tenant
from sqlalchemy import select


@pytest.fixture()
def auth_headers(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=None, tenant_id=tenant.id, role="owner", role_id=None,
        is_legacy_token=False, permissions=frozenset({"business_type:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield {}
    app.dependency_overrides.clear()


def test_get_business_type_defaults_to_retail(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.get("/v1/admin/tenant-settings/business-type", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["business_type"] == "retail"
    assert body["show_shops_management"] is True
    assert body["show_pos_features"] is True
    assert body["show_ecommerce_features"] is False
    assert body["can_add_physical_store"] is False
    assert body["can_add_online_channel"] is True


def test_set_business_type_to_online(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/tenant-settings/business-type", json={
        "business_type": "online",
    }, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["business_type"] == "online"
    assert body["show_shops_management"] is False
    assert body["show_ecommerce_features"] is True
    assert body["can_add_physical_store"] is True

    # Virtual shop created
    virtual_shops = db.execute(
        select(Shop).where(Shop.tenant_id == tenant.id, Shop.kind == "virtual")
    ).scalars().all()
    assert len(virtual_shops) == 1
    assert virtual_shops[0].name == "Online Store"


def test_set_business_type_to_hybrid(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/tenant-settings/business-type", json={
        "business_type": "hybrid",
    }, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["business_type"] == "hybrid"
    assert body["show_shops_management"] is True
    assert body["show_ecommerce_features"] is True


def test_get_after_set_online(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    client.post("/v1/admin/tenant-settings/business-type",
                json={"business_type": "online"}, headers=auth_headers)

    resp = client.get("/v1/admin/tenant-settings/business-type", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["business_type"] == "online"
    assert resp.json()["show_shops_management"] is False


def test_invalid_business_type_rejected(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/tenant-settings/business-type", json={
        "business_type": "moon",
    }, headers=auth_headers)
    assert resp.status_code == 422


def test_idempotent_set_online(db, tenant: Tenant, auth_headers) -> None:
    """Setting online twice doesn't create two virtual shops."""
    client = TestClient(app)
    client.post("/v1/admin/tenant-settings/business-type",
                json={"business_type": "online"}, headers=auth_headers)
    client.post("/v1/admin/tenant-settings/business-type",
                json={"business_type": "online"}, headers=auth_headers)

    virtual_shops = db.execute(
        select(Shop).where(Shop.tenant_id == tenant.id, Shop.kind == "virtual")
    ).scalars().all()
    assert len(virtual_shops) == 1
