# NOTE: `from __future__ import annotations` deliberately absent.
#
# Cashier RMA endpoint tests.

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Product, Shop, Tenant, Transaction, TransactionLine


@pytest.fixture(autouse=True)
def _patch_side_effects():
    with (
        patch("app.services.rma_service.execute_provider_refund", return_value={"status": "manual"}),
        patch("app.services.rma_service._send_status_email"),
    ):
        yield


@pytest.fixture()
def device_auth_override(db, tenant: Tenant, shop: Shop):
    """Override get_device_auth and get_db so the cashier endpoint uses our test session."""
    from app.auth.deps import DeviceAuth, get_device_auth
    from app.db.session import get_db

    fake_device = DeviceAuth(
        device_id=uuid.uuid4(),
        tenant_id=tenant.id,
        shop_ids=[shop.id],
    )
    app.dependency_overrides[get_device_auth] = lambda: fake_device
    app.dependency_overrides[get_db] = lambda: db
    yield fake_device
    app.dependency_overrides.clear()


@pytest.fixture()
def product(db, tenant: Tenant) -> Product:
    p = Product(
        tenant_id=tenant.id,
        sku=f"SKU-{uuid.uuid4().hex[:6]}",
        name="Cashier Widget",
        unit_price_cents=500,
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
        total_cents=1000,
        client_mutation_id=uuid.uuid4().hex,
    )
    db.add(t)
    db.flush()
    db.add(TransactionLine(
        transaction_id=t.id,
        product_id=product.id,
        quantity=2,
        unit_price_cents=500,
    ))
    db.commit()
    db.refresh(t)
    return t


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_cashier_create_refund_request(db, tenant: Tenant, txn: Transaction, device_auth_override) -> None:
    txn_line = txn.lines[0]
    client = TestClient(app)
    resp = client.post(
        "/v1/cashier/refund-requests",
        json={
            "sale_transaction_id": str(txn.id),
            "refund_type": "refund_only",
            "reason_code": "defective",
            "customer_email": "buyer@test.local",
            "lines": [{"transaction_line_id": str(txn_line.id), "quantity_requested": 1}],
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "requested"
    assert body["reason_code"] == "defective"
    assert body["refund_type"] == "refund_only"


def test_cashier_create_rma_wrong_tenant_txn(db, tenant: Tenant, device_auth_override) -> None:
    """A transaction from a different tenant should return 404."""
    other_tenant_id = uuid.uuid4()
    fake_txn_id = uuid.uuid4()

    client = TestClient(app)
    resp = client.post(
        "/v1/cashier/refund-requests",
        json={
            "sale_transaction_id": str(fake_txn_id),
            "refund_type": "refund_only",
            "reason_code": "defective",
            "lines": [{"transaction_line_id": str(uuid.uuid4()), "quantity_requested": 1}],
        },
    )
    assert resp.status_code == 404


def test_cashier_create_rma_reason_other_requires_note(db, tenant: Tenant, txn: Transaction, device_auth_override) -> None:
    txn_line = txn.lines[0]
    client = TestClient(app)
    resp = client.post(
        "/v1/cashier/refund-requests",
        json={
            "sale_transaction_id": str(txn.id),
            "refund_type": "refund_only",
            "reason_code": "other",  # requires reason_note
            "lines": [{"transaction_line_id": str(txn_line.id), "quantity_requested": 1}],
        },
    )
    assert resp.status_code == 400
