# NOTE: `from __future__ import annotations` deliberately absent.

import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Channel, InventoryPool, Order, OrderLine, Tenant


@pytest.fixture()
def channel(db, tenant: Tenant) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"p-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    ch = Channel(tenant_id=tenant.id, type="headless", name=f"c-{uuid.uuid4().hex[:6]}",
                 config={}, inventory_pool_id=pool.id, currency_code="INR")
    db.add(ch)
    db.flush()
    db.commit()
    return ch


@pytest.fixture()
def customer_auth(db, tenant: Tenant, channel: Channel):
    from app.db.session import get_db
    from app.routers.storefront.auth import CustomerAuth, get_current_customer

    fake_customer_id = uuid.uuid4()
    fake_ctx = CustomerAuth(
        customer_id=fake_customer_id,
        tenant_id=tenant.id,
        channel_id=channel.id,
        email="shopper@example.com",
    )
    app.dependency_overrides[get_current_customer] = lambda: fake_ctx
    app.dependency_overrides[get_db] = lambda: db
    yield {"X-Channel-Id": str(channel.id), "customer_id": str(fake_customer_id)}
    app.dependency_overrides.clear()


def test_get_profile(db, tenant: Tenant, channel: Channel, customer_auth) -> None:
    resp = TestClient(app).get(
        "/v1/storefront/customers/me",
        headers={"X-Channel-Id": customer_auth["X-Channel-Id"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "shopper@example.com"


def test_get_orders_empty(db, tenant: Tenant, channel: Channel, customer_auth) -> None:
    resp = TestClient(app).get(
        "/v1/storefront/customers/me/orders",
        headers={"X-Channel-Id": customer_auth["X-Channel-Id"]},
    )
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_orders_returns_customer_orders(
    db, tenant: Tenant, channel: Channel, customer_auth
) -> None:
    order = Order(
        tenant_id=tenant.id, channel_id=channel.id, status="confirmed",
        customer_email="shopper@example.com",
        subtotal_cents=1000, tax_cents=0, shipping_cents=0,
        discount_cents=0, total_cents=1000, currency_code="INR",
    )
    db.add(order)
    db.flush()
    db.add(OrderLine(
        tenant_id=tenant.id, order_id=order.id, title="Widget",
        quantity=1, unit_price_cents=1000, line_total_cents=1000,
    ))
    db.commit()

    resp = TestClient(app).get(
        "/v1/storefront/customers/me/orders",
        headers={"X-Channel-Id": customer_auth["X-Channel-Id"]},
    )
    assert resp.status_code == 200
    orders = resp.json()
    assert len(orders) == 1
    assert orders[0]["id"] == str(order.id)
    assert len(orders[0]["lines"]) == 1
