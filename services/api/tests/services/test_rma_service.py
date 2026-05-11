"""Unit tests for the RMA state-machine service (rma_service.py).

Payment provider and email send paths are mocked so tests stay deterministic
and don't make network calls.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.models import (
    Channel,
    InventoryPool,
    InventoryPoolShop,
    Order,
    OrderLine,
    OrderPayment,
    Product,
    RefundRequest,
    Shop,
    Tenant,
)
from app.services import rma_service
from app.services.rma_service import (
    ApprovalLineInput,
    CreateLineInput,
    approve_refund_request,
    cancel_refund_request,
    close_refund_request,
    create_refund_request,
    execute_refund,
    mark_cash_returned,
    mark_received,
    reject_refund_request,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _silence_email():
    """Stop _send_status_email from making any real attempts during tests."""
    with patch("app.services.rma_service._send_status_email") as m:
        yield m


@pytest.fixture()
def channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id, type="headless", name=f"ch-{uuid.uuid4().hex[:6]}",
        config={}, inventory_pool_id=pool.id, currency_code="INR",
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def product(db, tenant: Tenant) -> Product:
    p = Product(
        tenant_id=tenant.id,
        sku=f"SKU-{uuid.uuid4().hex[:6]}",
        name="Widget",
        unit_price_cents=2000,
    )
    db.add(p)
    db.flush()
    return p


def _make_order(db, tenant: Tenant, channel: Channel, *, delivered_days_ago: int = 1) -> Order:
    now = datetime.now(UTC)
    placed = now - timedelta(days=delivered_days_ago + 2)
    delivered = now - timedelta(days=delivered_days_ago)
    order = Order(
        tenant_id=tenant.id,
        channel_id=channel.id,
        status="delivered",
        customer_email="buyer@example.com",
        subtotal_cents=4000,
        total_cents=4000,
        currency_code="INR",
        placed_at=placed,
        delivered_at=delivered,
    )
    db.add(order)
    db.flush()
    return order


def _make_order_line(db, order: Order, product: Product, quantity: int = 2) -> OrderLine:
    line = OrderLine(
        tenant_id=order.tenant_id,
        order_id=order.id,
        product_id=product.id,
        title=product.name,
        sku=product.sku,
        quantity=quantity,
        unit_price_cents=product.unit_price_cents,
        line_total_cents=product.unit_price_cents * quantity,
    )
    db.add(line)
    db.flush()
    return line


def _line_input(order_line: OrderLine, qty: int) -> CreateLineInput:
    return CreateLineInput(
        order_line_id=order_line.id,
        transaction_line_id=None,
        product_id=order_line.product_id,
        product_name=order_line.title,
        product_sku=order_line.sku,
        quantity_requested=qty,
        unit_price_cents=order_line.unit_price_cents,
    )


# ---------------------------------------------------------------------------
# create_refund_request
# ---------------------------------------------------------------------------

def test_create_basic_request_starts_in_requested(db, tenant: Tenant, channel, product) -> None:
    order = _make_order(db, tenant, channel)
    ol = _make_order_line(db, order, product)
    req = create_refund_request(
        db, tenant_id=tenant.id, order=order,
        refund_type="refund_only", reason_code="damaged",
        lines=[_line_input(ol, 1)],
    )
    assert req.status == "requested"
    assert req.currency_code == "INR"
    assert len(req.lines) == 1
    assert req.lines[0].quantity_requested == 1
    assert req.lines[0].quantity_approved == 0  # not yet approved


def test_create_rejects_empty_lines(db, tenant: Tenant, channel) -> None:
    order = _make_order(db, tenant, channel)
    with pytest.raises(HTTPException) as exc_info:
        create_refund_request(
            db, tenant_id=tenant.id, order=order,
            refund_type="refund_only", reason_code="damaged",
            lines=[],
        )
    assert exc_info.value.status_code == 422


def test_create_other_reason_requires_note(db, tenant: Tenant, channel, product) -> None:
    order = _make_order(db, tenant, channel)
    ol = _make_order_line(db, order, product)
    with pytest.raises(HTTPException) as exc_info:
        create_refund_request(
            db, tenant_id=tenant.id, order=order,
            refund_type="refund_only", reason_code="other", reason_note="",
            lines=[_line_input(ol, 1)],
        )
    assert exc_info.value.status_code == 422
    assert "reason_note" in exc_info.value.detail


def test_create_invalid_refund_type(db, tenant: Tenant, channel, product) -> None:
    order = _make_order(db, tenant, channel)
    ol = _make_order_line(db, order, product)
    with pytest.raises(HTTPException) as exc_info:
        create_refund_request(
            db, tenant_id=tenant.id, order=order,
            refund_type="banana", reason_code="damaged",
            lines=[_line_input(ol, 1)],
        )
    assert exc_info.value.status_code == 422


def test_create_outside_refund_window_rejected(db, tenant: Tenant, channel, product) -> None:
    tenant.refund_window_days = 14
    db.flush()
    order = _make_order(db, tenant, channel, delivered_days_ago=30)
    ol = _make_order_line(db, order, product)
    with pytest.raises(HTTPException) as exc_info:
        create_refund_request(
            db, tenant_id=tenant.id, order=order,
            refund_type="refund_only", reason_code="changed_mind",
            lines=[_line_input(ol, 1)],
        )
    assert exc_info.value.status_code == 422
    assert "window" in exc_info.value.detail.lower()


def test_create_under_auto_approve_threshold_auto_approves(db, tenant: Tenant, channel, product) -> None:
    tenant.rma_auto_approve_under_cents = 10000  # auto-approve everything under ₹100
    db.flush()
    order = _make_order(db, tenant, channel)
    db.add(OrderPayment(
        tenant_id=tenant.id, order_id=order.id,
        method="cash", amount_cents=order.total_cents, status="paid",
    ))
    db.flush()
    ol = _make_order_line(db, order, product, quantity=1)

    # Patch payment refund to keep this deterministic
    with patch("app.services.rma_service.execute_provider_refund") as mock_refund:
        mock_refund.return_value = {"status": "manual_cash", "provider_ref": None, "error": None}
        req = create_refund_request(
            db, tenant_id=tenant.id, order=order,
            refund_type="refund_only", reason_code="damaged",
            lines=[_line_input(ol, 1)],
        )

    assert req.auto_approved is True
    # Cash payment path keeps status at "approved" pending the manual mark
    assert req.status in ("approved", "refunded")


# ---------------------------------------------------------------------------
# approve_refund_request
# ---------------------------------------------------------------------------

def test_approve_refund_only_with_card_payment_executes_immediately(db, tenant, channel, product) -> None:
    order = _make_order(db, tenant, channel)
    db.add(OrderPayment(
        tenant_id=tenant.id, order_id=order.id,
        method="card", provider="stripe", amount_cents=order.total_cents, status="paid",
    ))
    ol = _make_order_line(db, order, product, quantity=2)
    db.flush()
    req = create_refund_request(
        db, tenant_id=tenant.id, order=order,
        refund_type="refund_only", reason_code="wrong_item",
        lines=[_line_input(ol, 1)],
    )

    with patch("app.services.rma_service.execute_provider_refund") as mock_refund:
        mock_refund.return_value = {"status": "completed", "provider_ref": "re_test123", "error": None}
        result = approve_refund_request(
            db, request=req, approving_user_id=None,
            line_approvals={req.lines[0].id: ApprovalLineInput(quantity_approved=1, restock_on_approval=False)},
            refund_shipping=False,
        )
    assert result.status == "refunded"
    assert result.provider_refund_ref == "re_test123"
    assert result.lines[0].quantity_approved == 1
    assert result.lines[0].line_refund_cents == product.unit_price_cents


def test_approve_return_refund_stays_at_approved(db, tenant, channel, product) -> None:
    order = _make_order(db, tenant, channel)
    db.add(OrderPayment(
        tenant_id=tenant.id, order_id=order.id,
        method="card", provider="stripe", amount_cents=order.total_cents, status="paid",
    ))
    ol = _make_order_line(db, order, product)
    db.flush()
    req = create_refund_request(
        db, tenant_id=tenant.id, order=order,
        refund_type="return_refund", reason_code="damaged",
        lines=[_line_input(ol, 2)],
    )

    result = approve_refund_request(
        db, request=req, approving_user_id=None,
        line_approvals={req.lines[0].id: ApprovalLineInput(quantity_approved=2, restock_on_approval=False)},
        refund_shipping=False,
    )
    # Return_refund waits for the goods to come back before executing the refund
    assert result.status == "approved"
    assert result.return_shipping_required is True


def test_approve_only_valid_from_requested(db, tenant, channel, product) -> None:
    order = _make_order(db, tenant, channel)
    ol = _make_order_line(db, order, product)
    db.flush()
    req = create_refund_request(
        db, tenant_id=tenant.id, order=order,
        refund_type="refund_only", reason_code="damaged",
        lines=[_line_input(ol, 1)],
    )
    req.status = "rejected"
    db.flush()
    with pytest.raises(HTTPException) as exc_info:
        approve_refund_request(
            db, request=req, approving_user_id=None,
            line_approvals={req.lines[0].id: ApprovalLineInput(quantity_approved=1, restock_on_approval=False)},
            refund_shipping=False,
        )
    assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# reject / cancel
# ---------------------------------------------------------------------------

def test_reject_transitions_to_rejected(db, tenant, channel, product) -> None:
    order = _make_order(db, tenant, channel)
    ol = _make_order_line(db, order, product)
    db.flush()
    req = create_refund_request(
        db, tenant_id=tenant.id, order=order,
        refund_type="refund_only", reason_code="damaged",
        lines=[_line_input(ol, 1)],
    )
    result = reject_refund_request(db, request=req, rejecting_user_id=None, reason="duplicate request")
    assert result.status == "rejected"
    assert result.rejected_at is not None
    assert result.rejected_reason == "duplicate request"


def test_cancel_only_valid_from_requested(db, tenant, channel, product) -> None:
    order = _make_order(db, tenant, channel)
    ol = _make_order_line(db, order, product)
    db.flush()
    req = create_refund_request(
        db, tenant_id=tenant.id, order=order,
        refund_type="refund_only", reason_code="damaged",
        lines=[_line_input(ol, 1)],
    )
    result = cancel_refund_request(db, request=req, by_customer=True)
    assert result.status == "cancelled"

    # Cannot cancel an already-cancelled request
    with pytest.raises(HTTPException) as exc_info:
        cancel_refund_request(db, request=result, by_customer=True)
    assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# mark_received → execute_refund
# ---------------------------------------------------------------------------

def test_mark_received_for_return_refund_executes_and_refunds(db, tenant, channel, product, shop) -> None:
    order = _make_order(db, tenant, channel)
    db.add(OrderPayment(
        tenant_id=tenant.id, order_id=order.id,
        method="card", provider="razorpay", amount_cents=order.total_cents, status="paid",
    ))
    ol = _make_order_line(db, order, product)
    db.flush()

    req = create_refund_request(
        db, tenant_id=tenant.id, order=order,
        refund_type="return_refund", reason_code="damaged",
        lines=[_line_input(ol, 2)],
    )
    approve_refund_request(
        db, request=req, approving_user_id=None,
        line_approvals={req.lines[0].id: ApprovalLineInput(quantity_approved=2, restock_on_approval=True)},
        refund_shipping=False,
    )
    assert req.status == "approved"

    with patch("app.services.rma_service.execute_provider_refund") as mock_refund:
        mock_refund.return_value = {"status": "completed", "provider_ref": "rzp_re_001", "error": None}
        result = mark_received(db, request=req, receiving_user_id=None)

    assert result.status == "refunded"
    assert result.received_at is not None
    assert result.refunded_at is not None
    assert result.provider_refund_ref == "rzp_re_001"


# ---------------------------------------------------------------------------
# cash payment path
# ---------------------------------------------------------------------------

def test_cash_payment_approval_waits_for_manual_mark(db, tenant, channel, product) -> None:
    order = _make_order(db, tenant, channel)
    db.add(OrderPayment(
        tenant_id=tenant.id, order_id=order.id,
        method="cash", amount_cents=order.total_cents, status="paid",
    ))
    ol = _make_order_line(db, order, product)
    db.flush()
    req = create_refund_request(
        db, tenant_id=tenant.id, order=order,
        refund_type="refund_only", reason_code="changed_mind",
        lines=[_line_input(ol, 1)],
    )

    with patch("app.services.rma_service.execute_provider_refund") as mock_refund:
        mock_refund.return_value = {"status": "manual_cash", "provider_ref": None, "error": None}
        approved = approve_refund_request(
            db, request=req, approving_user_id=None,
            line_approvals={req.lines[0].id: ApprovalLineInput(quantity_approved=1, restock_on_approval=False)},
            refund_shipping=False,
        )

    # Cash path keeps status at "approved" — refund not yet "given"
    assert approved.status == "approved"
    assert approved.cash_returned is False

    refunded = mark_cash_returned(db, request=approved, user_id=None)
    assert refunded.status == "refunded"
    assert refunded.cash_returned is True
    assert refunded.cash_returned_at is not None


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------

def test_close_only_valid_from_terminal_states(db, tenant, channel, product) -> None:
    order = _make_order(db, tenant, channel)
    ol = _make_order_line(db, order, product)
    db.flush()
    req = create_refund_request(
        db, tenant_id=tenant.id, order=order,
        refund_type="refund_only", reason_code="damaged",
        lines=[_line_input(ol, 1)],
    )
    # Cannot close a still-pending request
    with pytest.raises(HTTPException) as exc_info:
        close_refund_request(db, request=req)
    assert exc_info.value.status_code == 422

    reject_refund_request(db, request=req, rejecting_user_id=None, reason="test")
    result = close_refund_request(db, request=req)
    assert result.status == "closed"
    assert result.closed_at is not None
