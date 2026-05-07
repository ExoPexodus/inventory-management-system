import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.models import Channel, InventoryPool, Order, OrderLine, Tenant, WebhookDeliveryLog, WebhookEndpoint
from app.services.webhook_service import fire_event, generate_secret


@pytest.fixture()
def channel(db, tenant: Tenant) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    ch = Channel(tenant_id=tenant.id, type="headless", name=f"wh-{uuid.uuid4().hex[:6]}",
                 config={}, inventory_pool_id=pool.id, currency_code="INR")
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def endpoint(db, tenant: Tenant) -> WebhookEndpoint:
    ep = WebhookEndpoint(
        tenant_id=tenant.id,
        url="https://merchant.example.com/webhooks",
        secret=generate_secret(),
        events=["order.confirmed"],
        status="active",
    )
    db.add(ep)
    db.flush()
    return ep


@pytest.fixture()
def order(db, tenant: Tenant, channel: Channel) -> Order:
    o = Order(
        tenant_id=tenant.id, channel_id=channel.id, status="confirmed",
        customer_email="buyer@example.com",
        subtotal_cents=1999, tax_cents=0, shipping_cents=0,
        discount_cents=0, total_cents=1999, currency_code="INR",
    )
    db.add(o)
    db.flush()
    db.add(OrderLine(
        tenant_id=tenant.id, order_id=o.id, title="Widget",
        quantity=1, unit_price_cents=1999, line_total_cents=1999,
    ))
    db.flush()
    return o


def test_fire_event_creates_delivery_log_and_enqueues(
    db, tenant: Tenant, endpoint: WebhookEndpoint, order: Order
) -> None:
    with patch("app.services.webhook_service._enqueue_delivery") as mock_enqueue:
        count = fire_event(db, tenant.id, "order.confirmed", {"order_id": str(order.id)})

    assert count == 1
    mock_enqueue.assert_called_once()
    log = db.query(WebhookDeliveryLog).filter_by(tenant_id=tenant.id).first()
    assert log is not None
    assert log.event_type == "order.confirmed"
    assert log.status == "pending"
    assert log.payload["event"] == "order.confirmed"


def test_fire_event_skips_disabled_endpoint(db, tenant: Tenant, endpoint: WebhookEndpoint) -> None:
    endpoint.status = "disabled"
    db.flush()
    with patch("app.services.webhook_service._enqueue_delivery") as mock_enqueue:
        count = fire_event(db, tenant.id, "order.confirmed", {})
    assert count == 0
    mock_enqueue.assert_not_called()


def test_fire_event_skips_unsubscribed_event(db, tenant: Tenant, endpoint: WebhookEndpoint) -> None:
    with patch("app.services.webhook_service._enqueue_delivery") as mock_enqueue:
        count = fire_event(db, tenant.id, "order.updated", {})
    assert count == 0
    mock_enqueue.assert_not_called()


def test_fire_event_unknown_type_skipped(db, tenant: Tenant, endpoint: WebhookEndpoint) -> None:
    with patch("app.services.webhook_service._enqueue_delivery") as mock_enqueue:
        count = fire_event(db, tenant.id, "nonexistent.event", {})
    assert count == 0
    mock_enqueue.assert_not_called()


def test_fire_event_no_endpoints_returns_zero(db, tenant: Tenant) -> None:
    count = fire_event(db, tenant.id, "order.confirmed", {})
    assert count == 0


def test_deliver_webhook_success(db, tenant: Tenant, endpoint: WebhookEndpoint) -> None:
    from app.services.webhook_service import _execute_delivery
    log = WebhookDeliveryLog(
        tenant_id=tenant.id, endpoint_id=endpoint.id,
        event_type="order.confirmed",
        payload={"id": str(uuid.uuid4()), "event": "order.confirmed", "data": {}},
        status="pending",
    )
    db.add(log)
    db.commit()

    mock_resp = MagicMock(status_code=200, text="OK")
    with patch("httpx.post", return_value=mock_resp):
        result = _execute_delivery(db, str(log.id))

    assert result == "delivered"
    db.refresh(log)
    assert log.status == "delivered"
    assert log.response_status == 200
    assert log.delivered_at is not None


def test_deliver_webhook_failure_schedules_retry(
    db, tenant: Tenant, endpoint: WebhookEndpoint
) -> None:
    from app.services.webhook_service import _execute_delivery
    log = WebhookDeliveryLog(
        tenant_id=tenant.id, endpoint_id=endpoint.id,
        event_type="order.confirmed",
        payload={"id": str(uuid.uuid4()), "event": "order.confirmed", "data": {}},
        status="pending",
    )
    db.add(log)
    db.commit()

    mock_resp = MagicMock(status_code=500, text="Server Error")
    with patch("httpx.post", return_value=mock_resp), \
         patch("app.services.webhook_service._enqueue_delivery"):
        result = _execute_delivery(db, str(log.id))

    assert result == "retry_scheduled"
    db.refresh(log)
    assert log.status == "pending"
    assert log.attempt_count == 1
    assert log.next_retry_at is not None
