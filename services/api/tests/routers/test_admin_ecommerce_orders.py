# NOTE: `from __future__ import annotations` deliberately absent.

import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Channel, InventoryPool, Order, OrderLine, OrderPayment, Tenant


@pytest.fixture()
def channel(db, tenant: Tenant) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"p-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    ch = Channel(tenant_id=tenant.id, type="headless", name=f"c-{uuid.uuid4().hex[:6]}",
                 config={}, inventory_pool_id=pool.id, currency_code="INR")
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def order(db, tenant: Tenant, channel: Channel) -> Order:
    o = Order(
        tenant_id=tenant.id, channel_id=channel.id, status="confirmed",
        customer_email="buyer@example.com",
        subtotal_cents=5000, tax_cents=0, shipping_cents=0,
        discount_cents=0, total_cents=5000, currency_code="INR",
    )
    db.add(o)
    db.flush()
    db.add(OrderLine(
        tenant_id=tenant.id, order_id=o.id, title="Widget",
        quantity=1, unit_price_cents=5000, line_total_cents=5000,
    ))
    db.add(OrderPayment(
        tenant_id=tenant.id, order_id=o.id, provider="stripe",
        provider_ref="pi_test", method="card", amount_cents=5000, status="paid",
    ))
    db.commit()
    return o


@pytest.fixture()
def auth(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin
    fake_ctx = AdminContext(
        user_id=None, tenant_id=tenant.id, role="owner", role_id=None,
        is_legacy_token=False, permissions=frozenset({"orders:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield
    app.dependency_overrides.clear()


def test_list_ecommerce_orders(db, tenant: Tenant, order: Order, auth) -> None:
    resp = TestClient(app).get("/v1/admin/ecommerce-orders")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 1
    assert any(i["id"] == str(order.id) for i in items)


def test_get_ecommerce_order(db, tenant: Tenant, order: Order, auth) -> None:
    resp = TestClient(app).get(f"/v1/admin/ecommerce-orders/{order.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(order.id)
    assert "lines" in body
    assert "payments" in body
    assert "refunds" in body


def test_issue_refund(db, tenant: Tenant, order: Order, auth) -> None:
    resp = TestClient(app).post(
        f"/v1/admin/ecommerce-orders/{order.id}/refund",
        json={"amount_cents": 1000, "reason": "Customer request"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["amount_cents"] == 1000
    assert body["status"] == "issued"


def test_refund_exceeds_order_total_rejected(db, tenant: Tenant, order: Order, auth) -> None:
    resp = TestClient(app).post(
        f"/v1/admin/ecommerce-orders/{order.id}/refund",
        json={"amount_cents": 9999999, "reason": "Too much"},
    )
    assert resp.status_code == 400


def test_order_status_becomes_refunded_on_full_refund(db, tenant: Tenant, order: Order, auth) -> None:
    resp = TestClient(app).post(
        f"/v1/admin/ecommerce-orders/{order.id}/refund",
        json={"amount_cents": 5000, "reason": "Full refund"},
    )
    assert resp.status_code == 201
    db.refresh(order)
    assert order.status == "refunded"
