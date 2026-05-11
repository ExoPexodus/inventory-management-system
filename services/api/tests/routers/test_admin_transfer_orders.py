# NOTE: `from __future__ import annotations` deliberately absent.

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Product, Shop, Tenant, TransferOrder, TransferOrderLine


@pytest.fixture()
def auth_headers(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=None,
        tenant_id=tenant.id,
        role="owner",
        role_id=None,
        is_legacy_token=False,
        permissions=frozenset({"operations:read", "operations:write", "transfers:approve"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield {}
    app.dependency_overrides.clear()


@pytest.fixture()
def two_shops(db, tenant: Tenant):
    s1 = Shop(tenant_id=tenant.id, name=f"ShopA-{uuid.uuid4().hex[:6]}")
    s2 = Shop(tenant_id=tenant.id, name=f"ShopB-{uuid.uuid4().hex[:6]}")
    db.add(s1)
    db.add(s2)
    db.commit()
    db.refresh(s1)
    db.refresh(s2)
    return s1, s2


@pytest.fixture()
def product(db, tenant: Tenant) -> Product:
    p = Product(
        tenant_id=tenant.id,
        sku=f"SKU-{uuid.uuid4().hex[:6]}",
        name="Test Product",
        unit_price_cents=1000,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@pytest.fixture()
def draft_transfer(db, tenant: Tenant, two_shops, product: Product) -> TransferOrder:
    s1, s2 = two_shops
    transfer = TransferOrder(
        tenant_id=tenant.id,
        from_shop_id=s1.id,
        to_shop_id=s2.id,
        status="draft",
    )
    db.add(transfer)
    db.flush()
    db.add(TransferOrderLine(
        transfer_order_id=transfer.id,
        product_id=product.id,
        quantity_requested=5,
    ))
    db.commit()
    db.refresh(transfer)
    return transfer


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_list_transfers_empty(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.get("/v1/admin/transfer-orders", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0
    assert resp.json()["items"] == []


def test_create_transfer(db, tenant: Tenant, two_shops, product: Product, auth_headers) -> None:
    s1, s2 = two_shops
    client = TestClient(app)
    resp = client.post(
        "/v1/admin/transfer-orders",
        json={
            "from_shop_id": str(s1.id),
            "to_shop_id": str(s2.id),
            "lines": [{"product_id": str(product.id), "quantity_requested": 3}],
            "notes": "Test transfer",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "draft"
    assert body["notes"] == "Test transfer"
    assert len(body["lines"]) == 1
    assert body["lines"][0]["quantity_requested"] == 3


def test_create_transfer_same_shop_rejected(db, tenant: Tenant, two_shops, product: Product, auth_headers) -> None:
    s1, _ = two_shops
    client = TestClient(app)
    resp = client.post(
        "/v1/admin/transfer-orders",
        json={
            "from_shop_id": str(s1.id),
            "to_shop_id": str(s1.id),
            "lines": [{"product_id": str(product.id), "quantity_requested": 1}],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_get_transfer(db, tenant: Tenant, draft_transfer: TransferOrder, auth_headers) -> None:
    client = TestClient(app)
    resp = client.get(f"/v1/admin/transfer-orders/{draft_transfer.id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == str(draft_transfer.id)
    assert resp.json()["status"] == "draft"


def test_patch_transfer(db, tenant: Tenant, draft_transfer: TransferOrder, product: Product, auth_headers) -> None:
    client = TestClient(app)
    resp = client.patch(
        f"/v1/admin/transfer-orders/{draft_transfer.id}",
        json={
            "lines": [{"product_id": str(product.id), "quantity_requested": 10}],
            "notes": "Updated notes",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["notes"] == "Updated notes"
    assert body["lines"][0]["quantity_requested"] == 10


def test_cancel_draft_transfer(db, tenant: Tenant, draft_transfer: TransferOrder, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post(f"/v1/admin/transfer-orders/{draft_transfer.id}/cancel", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "cancelled"


def test_submit_transfer(db, tenant: Tenant, draft_transfer: TransferOrder, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post(f"/v1/admin/transfer-orders/{draft_transfer.id}/submit", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    # Without auto-approve threshold it goes to pending_approval
    assert resp.json()["status"] in ("pending_approval", "approved")


def test_list_transfers_filters_by_status(db, tenant: Tenant, two_shops, product: Product, auth_headers) -> None:
    s1, s2 = two_shops
    t_cancelled = TransferOrder(
        tenant_id=tenant.id, from_shop_id=s1.id, to_shop_id=s2.id, status="cancelled",
    )
    db.add(t_cancelled)
    db.commit()

    client = TestClient(app)
    resp = client.get("/v1/admin/transfer-orders?status=cancelled", headers=auth_headers)
    assert resp.status_code == 200
    assert all(item["status"] == "cancelled" for item in resp.json()["items"])


def test_get_nonexistent_transfer_returns_404(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.get(f"/v1/admin/transfer-orders/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404
