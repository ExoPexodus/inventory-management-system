# NOTE: `from __future__ import annotations` deliberately absent.

import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Channel, InventoryPool, Order, Tenant


@pytest.fixture()
def channel_with_shipping(db, tenant: Tenant) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"p-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    ch = Channel(
        tenant_id=tenant.id, type="headless", name=f"c-{uuid.uuid4().hex[:6]}",
        config={
            "shipping_provider": "shiprocket",
            "shiprocket_webhook_secret": "testsecret",
        },
        inventory_pool_id=pool.id, currency_code="INR",
    )
    db.add(ch)
    db.flush()
    db.commit()
    return ch


@pytest.fixture()
def dispatched_order(db, tenant: Tenant, channel_with_shipping: Channel) -> Order:
    o = Order(
        tenant_id=tenant.id, channel_id=channel_with_shipping.id,
        status="confirmed", fulfillment_status="processing",
        awb_code="TEST12345", customer_email="buyer@example.com",
        subtotal_cents=999, tax_cents=0, shipping_cents=0,
        discount_cents=0, total_cents=999, currency_code="INR",
    )
    db.add(o)
    db.commit()
    return o


@pytest.fixture()
def db_override(db, channel_with_shipping: Channel):
    from app.db.session import get_db
    app.dependency_overrides[get_db] = lambda: db
    yield
    app.dependency_overrides.pop(get_db, None)


def test_webhook_updates_fulfillment_status(
    db, tenant: Tenant, channel_with_shipping: Channel,
    dispatched_order: Order, db_override,
) -> None:
    payload = {
        "awb": "TEST12345",
        "current_status": "Delivered",
        "updated_at": "2026-05-08T12:00:00",
        "location": "Mumbai Hub",
    }
    resp = TestClient(app).post(
        f"/v1/webhooks/shiprocket/{channel_with_shipping.id}",
        json=payload,
        headers={"X-Api-Key": "testsecret"},
    )
    assert resp.status_code == 200, resp.text
    db.refresh(dispatched_order)
    assert dispatched_order.fulfillment_status == "delivered"
    assert dispatched_order.delivered_at is not None


def test_webhook_invalid_signature_rejected(
    db, tenant: Tenant, channel_with_shipping: Channel,
    dispatched_order: Order, db_override,
) -> None:
    resp = TestClient(app).post(
        f"/v1/webhooks/shiprocket/{channel_with_shipping.id}",
        json={"awb": "TEST12345", "current_status": "Delivered"},
        headers={"X-Api-Key": "wrongsecret"},
    )
    assert resp.status_code == 401


def test_webhook_unknown_awb_returns_ignored(
    db, tenant: Tenant, channel_with_shipping: Channel, db_override,
) -> None:
    resp = TestClient(app).post(
        f"/v1/webhooks/shiprocket/{channel_with_shipping.id}",
        json={"awb": "UNKNOWN9999", "current_status": "Delivered"},
        headers={"X-Api-Key": "testsecret"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


def test_webhook_duplicate_event_is_idempotent(
    db, tenant: Tenant, channel_with_shipping: Channel,
    dispatched_order: Order, db_override,
) -> None:
    payload = {
        "awb": "TEST12345",
        "current_status": "In Transit",
        "updated_at": "2026-05-08T10:00:00",
        "location": "Delhi Hub",
    }
    # Send twice
    for _ in range(2):
        resp = TestClient(app).post(
            f"/v1/webhooks/shiprocket/{channel_with_shipping.id}",
            json=payload,
            headers={"X-Api-Key": "testsecret"},
        )
        assert resp.status_code == 200

    from app.models import ShipmentEvent
    from sqlalchemy import select
    events = db.execute(
        select(ShipmentEvent).where(ShipmentEvent.order_id == dispatched_order.id)
    ).scalars().all()
    # Only one event despite two webhook calls
    assert len(events) == 1
