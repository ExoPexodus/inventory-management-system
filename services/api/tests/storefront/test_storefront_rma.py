# NOTE: `from __future__ import annotations` deliberately absent.
#
# Storefront RMA router tests.
# These endpoints require a customer JWT. We override CustomerAuthDep and
# StorefrontChannelDep to avoid real JWT issuance.

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import (
    Channel,
    Customer,
    InventoryPool,
    InventoryPoolShop,
    Order,
    OrderLine,
    RefundRequest,
    Shop,
    Tenant,
)


@pytest.fixture(autouse=True)
def _patch_side_effects():
    with (
        patch("app.services.rma_service.execute_provider_refund", return_value={"status": "manual"}),
        patch("app.services.rma_service._send_status_email"),
    ):
        yield


@pytest.fixture()
def channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id,
        type="headless",
        name=f"ch-{uuid.uuid4().hex[:6]}",
        config={},
        inventory_pool_id=pool.id,
        currency_code="INR",
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def customer(db, tenant: Tenant) -> Customer:
    c = Customer(
        tenant_id=tenant.id,
        phone=f"+91{uuid.uuid4().hex[:8]}",
        email="customer@test.local",
        name="Test Customer",
    )
    db.add(c)
    db.flush()
    return c


@pytest.fixture()
def customer_auth_override(db, tenant: Tenant, channel: Channel, customer: Customer):
    """Override CustomerAuthDep and StorefrontChannelDep for all storefront RMA tests."""
    from app.db.session import get_db
    from app.routers.storefront.auth import (
        CustomerAuth,
        get_current_customer,
        get_storefront_channel,
    )

    fake_customer = CustomerAuth(
        customer_id=customer.id,
        tenant_id=tenant.id,
        channel_id=channel.id,
        email="customer@test.local",
    )
    app.dependency_overrides[get_current_customer] = lambda: fake_customer
    app.dependency_overrides[get_storefront_channel] = lambda: channel
    app.dependency_overrides[get_db] = lambda: db
    yield fake_customer
    app.dependency_overrides.clear()


@pytest.fixture()
def order(db, tenant: Tenant, channel: Channel, customer: Customer) -> Order:
    o = Order(
        tenant_id=tenant.id,
        channel_id=channel.id,
        customer_id=customer.id,
        customer_email="customer@test.local",
        subtotal_cents=1000,
        total_cents=1000,
        currency_code="INR",
    )
    db.add(o)
    db.flush()
    db.add(OrderLine(
        tenant_id=tenant.id,
        order_id=o.id,
        title="Test Product",
        sku="SKU-001",
        quantity=2,
        unit_price_cents=500,
        line_total_cents=1000,
    ))
    db.commit()
    db.refresh(o)
    return o


@pytest.fixture()
def existing_rma(db, tenant: Tenant, order: Order, customer: Customer, channel: Channel) -> RefundRequest:
    req = RefundRequest(
        tenant_id=tenant.id,
        order_id=order.id,
        channel_id=channel.id,
        customer_id=customer.id,
        customer_email="customer@test.local",
        refund_type="refund_only",
        status="requested",
        reason_code="defective",
        currency_code="INR",
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


def test_list_my_rma_empty(db, tenant: Tenant, customer_auth_override) -> None:
    client = TestClient(app)
    resp = client.get(
        "/v1/storefront/refund-requests",
        headers={"X-Channel-Id": str(customer_auth_override.channel_id)},
    )
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_my_rma_returns_own_requests(db, tenant: Tenant, customer_auth_override, existing_rma: RefundRequest) -> None:
    client = TestClient(app)
    resp = client.get(
        "/v1/storefront/refund-requests",
        headers={"X-Channel-Id": str(customer_auth_override.channel_id)},
    )
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.json()]
    assert str(existing_rma.id) in ids


# ---------------------------------------------------------------------------
# Get
# ---------------------------------------------------------------------------


def test_get_own_rma(db, tenant: Tenant, customer_auth_override, existing_rma: RefundRequest) -> None:
    client = TestClient(app)
    resp = client.get(
        f"/v1/storefront/refund-requests/{existing_rma.id}",
        headers={"X-Channel-Id": str(customer_auth_override.channel_id)},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == str(existing_rma.id)


def test_get_other_customers_rma_returns_404(db, tenant: Tenant, customer_auth_override, channel: Channel) -> None:
    """A request belonging to a different customer is not visible."""
    other_customer_id = uuid.uuid4()
    other_req = RefundRequest(
        tenant_id=tenant.id,
        channel_id=channel.id,
        customer_id=None,  # no FK — use NULL for a "different" customer
        customer_email="other@test.local",
        refund_type="refund_only",
        status="requested",
        reason_code="defective",
        currency_code="INR",
    )
    db.add(other_req)
    db.commit()

    client = TestClient(app)
    resp = client.get(
        f"/v1/storefront/refund-requests/{other_req.id}",
        headers={"X-Channel-Id": str(customer_auth_override.channel_id)},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


def test_cancel_own_rma(db, tenant: Tenant, customer_auth_override, existing_rma: RefundRequest) -> None:
    client = TestClient(app)
    resp = client.post(
        f"/v1/storefront/refund-requests/{existing_rma.id}/cancel",
        headers={"X-Channel-Id": str(customer_auth_override.channel_id)},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_create_rma_for_own_order(db, tenant: Tenant, customer_auth_override, order: Order) -> None:
    order_line = order.lines[0]
    client = TestClient(app)
    resp = client.post(
        "/v1/storefront/refund-requests",
        json={
            "order_id": str(order.id),
            "refund_type": "refund_only",
            "reason_code": "defective",
            "lines": [{"order_line_id": str(order_line.id), "quantity_requested": 1}],
        },
        headers={"X-Channel-Id": str(customer_auth_override.channel_id)},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "requested"
    assert body["order_id"] == str(order.id)


def test_create_rma_reason_other_without_note_returns_400(
    db, tenant: Tenant, customer_auth_override, order: Order
) -> None:
    order_line = order.lines[0]
    client = TestClient(app)
    resp = client.post(
        "/v1/storefront/refund-requests",
        json={
            "order_id": str(order.id),
            "refund_type": "refund_only",
            "reason_code": "other",  # requires reason_note
            "lines": [{"order_line_id": str(order_line.id), "quantity_requested": 1}],
        },
        headers={"X-Channel-Id": str(customer_auth_override.channel_id)},
    )
    assert resp.status_code == 400


def test_create_rma_for_unknown_order_returns_404(
    db, tenant: Tenant, customer_auth_override
) -> None:
    client = TestClient(app)
    resp = client.post(
        "/v1/storefront/refund-requests",
        json={
            "order_id": str(uuid.uuid4()),
            "refund_type": "refund_only",
            "reason_code": "defective",
            "lines": [{"order_line_id": str(uuid.uuid4()), "quantity_requested": 1}],
        },
        headers={"X-Channel-Id": str(customer_auth_override.channel_id)},
    )
    assert resp.status_code == 404
