# NOTE: `from __future__ import annotations` deliberately absent.

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Channel, Discount, InventoryPool, InventoryPoolShop, Shop, Tenant


@pytest.fixture()
def auth_headers(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=None, tenant_id=tenant.id, role="owner", role_id=None,
        is_legacy_token=False, permissions=frozenset({"discounts:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield {}
    app.dependency_overrides.clear()


def test_create_percentage_discount(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/discounts", json={
        "name": "Summer 20% Off", "code": "SUMMER20",
        "discount_type": "percentage", "value_bps": 2000,
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["code"] == "SUMMER20"
    assert body["discount_type"] == "percentage"
    assert body["value_bps"] == 2000
    assert body["status"] == "active"
    assert body["times_used"] == 0


def test_create_fixed_amount_discount(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/discounts", json={
        "name": "₹500 off", "code": "FLAT500",
        "discount_type": "fixed_amount", "value_cents": 500,
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["value_cents"] == 500


def test_create_free_shipping_discount(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/discounts", json={
        "name": "Free Shipping", "code": "FREESHIP",
        "discount_type": "free_shipping",
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["discount_type"] == "free_shipping"


def test_list_discounts(db, tenant: Tenant, auth_headers) -> None:
    db.add(Discount(tenant_id=tenant.id, name="D1", code="C1",
                    discount_type="percentage", value_bps=1000, status="active"))
    db.add(Discount(tenant_id=tenant.id, name="D2", code="C2",
                    discount_type="fixed_amount", value_cents=200, status="paused"))
    db.commit()

    client = TestClient(app)
    resp = client.get("/v1/admin/discounts", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


def test_update_discount_status(db, tenant: Tenant, auth_headers) -> None:
    disc = Discount(tenant_id=tenant.id, name="Active D", code="ACT",
                    discount_type="percentage", value_bps=500, status="active")
    db.add(disc)
    db.commit()

    client = TestClient(app)
    resp = client.patch(f"/v1/admin/discounts/{disc.id}", json={"status": "paused"},
                        headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "paused"


def test_delete_discount(db, tenant: Tenant, auth_headers) -> None:
    disc = Discount(tenant_id=tenant.id, name="Doomed", code="DOOM",
                    discount_type="percentage", value_bps=100, status="active")
    db.add(disc)
    db.commit()

    client = TestClient(app)
    resp = client.delete(f"/v1/admin/discounts/{disc.id}", headers=auth_headers)
    assert resp.status_code == 204


def test_duplicate_code_rejected(db, tenant: Tenant, auth_headers) -> None:
    db.add(Discount(tenant_id=tenant.id, name="First", code="DUP",
                    discount_type="percentage", value_bps=500, status="active"))
    db.commit()

    client = TestClient(app)
    resp = client.post("/v1/admin/discounts", json={
        "name": "Second", "code": "DUP",
        "discount_type": "percentage", "value_bps": 100,
    }, headers=auth_headers)
    assert resp.status_code == 409


def test_percentage_discount_requires_value_bps(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/discounts", json={
        "name": "Bad", "code": "BAD", "discount_type": "percentage",
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert "value_bps" in resp.json()["detail"].lower()
