"""End-to-end smoke test for the online-only mode + conversion path."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Channel, Shop, Tenant


@pytest.fixture()
def auth(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=None, tenant_id=tenant.id,
        role="owner", role_id=None, is_legacy_token=False,
        permissions=frozenset({"business_type:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield
    app.dependency_overrides.clear()


def test_retail_default_flags(db, tenant: Tenant, auth) -> None:
    client = TestClient(app)
    resp = client.get("/v1/admin/tenant-settings/business-type")
    assert resp.status_code == 200
    body = resp.json()
    assert body["business_type"] == "retail"
    assert body["show_pos_features"] is True
    assert body["show_ecommerce_features"] is False
    assert body["can_add_online_channel"] is True


def test_set_online_creates_virtual_shop(db, tenant: Tenant, auth) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/tenant-settings/business-type",
                       json={"business_type": "online"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["business_type"] == "online"
    assert body["show_shops_management"] is False
    assert body["can_add_physical_store"] is True

    virtual_shops = db.execute(
        select(Shop).where(Shop.tenant_id == tenant.id, Shop.kind == "virtual")
    ).scalars().all()
    assert len(virtual_shops) == 1
    assert virtual_shops[0].name == "Online Store"


def test_enable_physical_store_creates_shop_and_pos_channel(db, tenant: Tenant, auth) -> None:
    client = TestClient(app)

    # Start as online
    client.post("/v1/admin/tenant-settings/business-type",
                json={"business_type": "online"})

    # Convert to hybrid
    resp = client.post("/v1/admin/setup/enable-physical-store", json={
        "shop_name": "Mumbai Flagship",
        "timezone": "Asia/Kolkata",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["business_type"] == "hybrid"
    assert body["show_shops_management"] is True
    assert body["show_ecommerce_features"] is True

    # Physical shop exists
    physical_shops = db.execute(
        select(Shop).where(Shop.tenant_id == tenant.id, Shop.kind == "physical")
    ).scalars().all()
    assert len(physical_shops) == 1
    assert physical_shops[0].name == "Mumbai Flagship"
    assert physical_shops[0].timezone == "Asia/Kolkata"

    # POS channel exists for it
    pos_channels = db.execute(
        select(Channel).where(
            Channel.tenant_id == tenant.id,
            Channel.type == "pos",
            Channel.shop_id == physical_shops[0].id,
        )
    ).scalars().all()
    assert len(pos_channels) == 1


def test_hybrid_shows_all_surfaces(db, tenant: Tenant, auth) -> None:
    client = TestClient(app)
    client.post("/v1/admin/tenant-settings/business-type",
                json={"business_type": "hybrid"})

    resp = client.get("/v1/admin/tenant-settings/business-type")
    assert resp.status_code == 200
    body = resp.json()
    assert body["show_shops_management"] is True
    assert body["show_pos_features"] is True
    assert body["show_ecommerce_features"] is True
    assert body["can_add_physical_store"] is True
    assert body["can_add_online_channel"] is True


def test_idempotent_set_online(db, tenant: Tenant, auth) -> None:
    client = TestClient(app)
    client.post("/v1/admin/tenant-settings/business-type",
                json={"business_type": "online"})
    client.post("/v1/admin/tenant-settings/business-type",
                json={"business_type": "online"})

    virtual_shops = db.execute(
        select(Shop).where(Shop.tenant_id == tenant.id, Shop.kind == "virtual")
    ).scalars().all()
    assert len(virtual_shops) == 1
