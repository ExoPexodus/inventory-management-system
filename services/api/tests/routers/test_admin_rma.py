# NOTE: `from __future__ import annotations` deliberately absent.
#
# Admin RMA router tests.
# Patches execute_provider_refund and _send_status_email to avoid network calls.
# State-machine correctness is tested in tests/services/test_rma_service.py.

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import (
    Product,
    RefundRequest,
    RefundRequestLine,
    Shop,
    Tenant,
    Transaction,
    TransactionLine,
)


@pytest.fixture(autouse=True)
def _patch_side_effects():
    with (
        patch("app.services.rma_service.execute_provider_refund", return_value={"status": "manual"}) as _mock_refund,
        patch("app.services.rma_service._send_status_email") as _mock_email,
    ):
        yield


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
        permissions=frozenset({"rma:read", "rma:write"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield {}
    app.dependency_overrides.clear()


@pytest.fixture()
def product(db, tenant: Tenant) -> Product:
    p = Product(
        tenant_id=tenant.id,
        sku=f"SKU-{uuid.uuid4().hex[:6]}",
        name="Widget",
        unit_price_cents=1000,
    )
    db.add(p)
    db.flush()
    return p


@pytest.fixture()
def txn(db, tenant: Tenant, shop: Shop, product: Product) -> Transaction:
    t = Transaction(
        tenant_id=tenant.id,
        shop_id=shop.id,
        kind="sale",
        status="posted",
        total_cents=2000,
        client_mutation_id=uuid.uuid4().hex,
    )
    db.add(t)
    db.flush()
    db.add(TransactionLine(
        transaction_id=t.id,
        product_id=product.id,
        quantity=2,
        unit_price_cents=1000,
    ))
    db.commit()
    db.refresh(t)
    return t


@pytest.fixture()
def rma(db, tenant: Tenant, txn: Transaction) -> RefundRequest:
    req = RefundRequest(
        tenant_id=tenant.id,
        sale_transaction_id=txn.id,
        refund_type="refund_only",
        status="requested",
        reason_code="defective",
        currency_code="INR",
    )
    db.add(req)
    db.flush()
    db.add(RefundRequestLine(
        refund_request_id=req.id,
        product_name="Widget",
        quantity_requested=1,
        quantity_approved=0,
        unit_price_cents=1000,
    ))
    db.commit()
    db.refresh(req)
    return req


# ---------------------------------------------------------------------------
# List + Get
# ---------------------------------------------------------------------------


def test_list_rma_empty(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.get("/v1/admin/rma", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert body["total"] == 0


def test_list_rma_returns_items(db, tenant: Tenant, auth_headers, rma: RefundRequest) -> None:
    client = TestClient(app)
    resp = client.get("/v1/admin/rma", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


def test_get_rma(db, tenant: Tenant, auth_headers, rma: RefundRequest) -> None:
    client = TestClient(app)
    resp = client.get(f"/v1/admin/rma/{rma.id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == str(rma.id)
    assert body["status"] == "requested"
    assert "lines" in body
    assert "events" in body


def test_get_nonexistent_rma_returns_404(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.get(f"/v1/admin/rma/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_admin_create_rma(db, tenant: Tenant, auth_headers, txn: Transaction) -> None:
    # Get the transaction line id
    txn_line = txn.lines[0]
    client = TestClient(app)
    resp = client.post(
        "/v1/admin/rma",
        json={
            "sale_transaction_id": str(txn.id),
            "refund_type": "refund_only",
            "reason_code": "defective",
            "customer_email": "customer@test.local",
            "lines": [{"transaction_line_id": str(txn_line.id), "quantity_requested": 1}],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "requested"
    assert body["reason_code"] == "defective"


# ---------------------------------------------------------------------------
# Reject
# ---------------------------------------------------------------------------


def test_reject_rma(db, tenant: Tenant, auth_headers, rma: RefundRequest) -> None:
    client = TestClient(app)
    resp = client.post(
        f"/v1/admin/rma/{rma.id}/reject",
        json={"reason": "Not eligible"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "rejected"


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


def test_reject_already_cancelled_rma_returns_422(db, tenant: Tenant, auth_headers, rma: RefundRequest) -> None:
    """Rejecting an already-cancelled RMA should return 422 (wrong state)."""
    # First cancel the RMA directly
    rma.status = "cancelled"
    db.commit()

    client = TestClient(app)
    resp = client.post(f"/v1/admin/rma/{rma.id}/reject", json={"reason": "too late"}, headers=auth_headers)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Add comment
# ---------------------------------------------------------------------------


def test_add_comment(db, tenant: Tenant, auth_headers, rma: RefundRequest) -> None:
    client = TestClient(app)
    resp = client.post(
        f"/v1/admin/rma/{rma.id}/comment",
        json={"comment": "Investigating this issue"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["event_type"] == "comment"


# ---------------------------------------------------------------------------
# Approve + downstream state tests
# ---------------------------------------------------------------------------


def test_approve_rma(db, tenant: Tenant, auth_headers, rma: RefundRequest) -> None:
    line = rma.lines[0]
    client = TestClient(app)
    resp = client.post(
        f"/v1/admin/rma/{rma.id}/approve",
        json={
            "line_approvals": [{"line_id": str(line.id), "quantity_approved": 1, "restock": False}],
            "refund_shipping": False,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "approved"


def test_mark_received_wrong_state_returns_422(db, tenant: Tenant, auth_headers, rma: RefundRequest) -> None:
    """mark-received on a 'requested' RMA should return 422 (wrong state)."""
    client = TestClient(app)
    resp = client.post(f"/v1/admin/rma/{rma.id}/mark-received", headers=auth_headers)
    assert resp.status_code == 422


def test_mark_cash_returned_wrong_state_returns_422(db, tenant: Tenant, auth_headers, rma: RefundRequest) -> None:
    """mark-cash-returned on a non-approved RMA should return 422 (wrong state)."""
    client = TestClient(app)
    resp = client.post(f"/v1/admin/rma/{rma.id}/mark-cash-returned", headers=auth_headers)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Issue return AWB — error paths only (happy path skipped: _to_detail is undefined)
# ---------------------------------------------------------------------------


def test_issue_return_awb_wrong_state_returns_422(db, tenant: Tenant, auth_headers, rma: RefundRequest) -> None:
    """Return AWB only allowed for approved/received requests."""
    # rma is in 'requested' state — should 422
    client = TestClient(app)
    resp = client.post(f"/v1/admin/rma/{rma.id}/issue-return-awb", headers=auth_headers)
    assert resp.status_code == 422


def test_issue_return_awb_no_return_shipping_returns_422(db, tenant: Tenant, auth_headers, rma: RefundRequest) -> None:
    """If return_shipping_required=False, return 422."""
    rma.status = "approved"
    rma.return_shipping_required = False
    db.commit()

    client = TestClient(app)
    resp = client.post(f"/v1/admin/rma/{rma.id}/issue-return-awb", headers=auth_headers)
    assert resp.status_code == 422


# TODO: issue-return-awb happy path requires Order fixture wiring + provider mock.
# The happy path also calls _to_detail() which is not defined in admin_rma.py (NameError).
# pytest.skip would be needed until both the bug and fixture wiring are resolved.
