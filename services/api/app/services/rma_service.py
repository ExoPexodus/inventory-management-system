"""RMA / Refund Request state-machine service.

State transitions:
  requested ──approve──> approved ──execute_refund (card)──> refunded ──close──> closed
      │             ├─reject──> rejected ──close──> closed
      │             ├─cancel (by customer/merchant)──> cancelled
      │             └─wait_for_return (return+refund)──> received ──execute_refund──> refunded
      │
      └─auto_approve (if under threshold)──> approved (same downstream paths)

Cash path: approved ──mark_cash_returned──> refunded
Exchange path: approved ──close (after fulfillment)──> closed (no monetary refund)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status as http_status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Order,
    OrderRefund,
    Product,
    RefundRequest,
    RefundRequestEvent,
    RefundRequestLine,
    Shop,
    StockMovement,
    Tenant,
    Transaction,
)
from app.services.payment_refund import execute_provider_refund

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Input dataclasses
# ---------------------------------------------------------------------------

@dataclass
class CreateLineInput:
    order_line_id: UUID | None
    transaction_line_id: UUID | None
    product_id: UUID | None
    product_name: str
    product_sku: str | None
    quantity_requested: int
    unit_price_cents: int
    exchange_for_product_id: UUID | None = None


@dataclass
class ApprovalLineInput:
    quantity_approved: int
    restock_on_approval: bool


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(UTC)


def _write_event(
    db: Session,
    *,
    request: RefundRequest,
    event_type: str,
    from_status: str | None = None,
    to_status: str | None = None,
    actor_user_id: UUID | None = None,
    actor_kind: str = "system",
    metadata: dict[str, Any] | None = None,
) -> RefundRequestEvent:
    evt = RefundRequestEvent(
        tenant_id=request.tenant_id,
        refund_request_id=request.id,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        actor_user_id=actor_user_id,
        actor_kind=actor_kind,
        event_metadata=metadata,
    )
    db.add(evt)
    return evt


def _send_status_email(db: Session, request: RefundRequest, template_name: str) -> None:
    """Send an RMA email — non-blocking, never raises."""
    try:
        from app.services.rma_email import send_rma_email
        send_rma_email(db, request=request, template_name=template_name)
    except Exception:
        logger.warning("Failed to send RMA email for request %s (template=%s)", request.id, template_name, exc_info=True)


def _compute_total(request: RefundRequest) -> int:
    """Sum line_refund_cents for all lines (+ shipping if refund_shipping)."""
    lines_total = sum(ln.line_refund_cents for ln in request.lines)
    if request.refund_shipping:
        # Shipping amount is stored on the order — look it up
        shipping = 0
        if request.order_id:
            from sqlalchemy.orm import object_session
            sess = object_session(request)
            if sess is not None:
                order = sess.get(Order, request.order_id)
                if order:
                    shipping = order.shipping_cents
        return lines_total + shipping
    return lines_total


def _validate_window(order: Order | None, tenant: Tenant) -> None:
    """Raise 422 if the refund window has closed."""
    if order is None:
        return  # POS transactions — no window check
    reference_dt = order.delivered_at or order.placed_at
    window_days = tenant.refund_window_days or 30
    cutoff = reference_dt + timedelta(days=window_days)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=UTC)
    if _now() > cutoff:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Refund window of {window_days} days has closed for this order",
        )


def _restock_line(db: Session, line: RefundRequestLine, tenant_id: UUID) -> None:
    """Create a stock_in movement for the returned quantity."""
    import uuid as _uuid
    if line.product_id is None or line.quantity_approved <= 0:
        return
    # Find the first shop for this tenant as the restock destination
    shop = db.execute(select(Shop).where(Shop.tenant_id == tenant_id).limit(1)).scalar_one_or_none()
    if shop is None:
        logger.warning("No shops found for tenant %s — cannot restock product %s", tenant_id, line.product_id)
        return
    idempotency_key = f"rma_restock_{line.id}"
    movement = StockMovement(
        tenant_id=tenant_id,
        shop_id=shop.id,
        product_id=line.product_id,
        quantity_delta=line.quantity_approved,
        movement_type="rma_return",
        idempotency_key=idempotency_key,
    )
    db.add(movement)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_refund_request(
    db: Session,
    *,
    tenant_id: UUID,
    order: Order | None = None,
    sale_transaction: Transaction | None = None,
    refund_type: str,
    reason_code: str,
    reason_note: str | None = None,
    lines: list[CreateLineInput],
    customer_id: UUID | None = None,
    customer_email: str | None = None,
    customer_name: str | None = None,
    channel_id: UUID | None = None,
) -> RefundRequest:
    if not lines:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one line is required",
        )
    if reason_code == "other" and not (reason_note or "").strip():
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="reason_note is required when reason_code is 'other'",
        )
    if refund_type not in ("refund_only", "return_refund", "exchange"):
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid refund_type: {refund_type!r}",
        )

    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    _validate_window(order, tenant)

    currency_code = "USD"
    if order is not None:
        currency_code = order.currency_code or "USD"
        channel_id = channel_id or order.channel_id
    elif sale_transaction is not None:
        # transactions don't have currency_code — use tenant default
        currency_code = tenant.default_currency_code or "USD"

    return_shipping_required = refund_type == "return_refund"

    request = RefundRequest(
        tenant_id=tenant_id,
        order_id=order.id if order else None,
        sale_transaction_id=sale_transaction.id if sale_transaction else None,
        channel_id=channel_id,
        customer_id=customer_id,
        customer_email=customer_email,
        customer_name=customer_name,
        refund_type=refund_type,
        status="requested",
        reason_code=reason_code,
        reason_note=reason_note,
        currency_code=currency_code,
        return_shipping_required=return_shipping_required,
    )
    db.add(request)
    db.flush()  # get request.id

    for line_input in lines:
        line = RefundRequestLine(
            refund_request_id=request.id,
            order_line_id=line_input.order_line_id,
            transaction_line_id=line_input.transaction_line_id,
            product_id=line_input.product_id,
            product_name=line_input.product_name,
            product_sku=line_input.product_sku,
            quantity_requested=line_input.quantity_requested,
            unit_price_cents=line_input.unit_price_cents,
            restock_on_approval=tenant.default_restock_on_refund,
            exchange_for_product_id=line_input.exchange_for_product_id,
        )
        db.add(line)

    db.flush()
    db.refresh(request)

    _write_event(db, request=request, event_type="created", to_status="requested", actor_kind="customer")
    db.flush()

    _send_status_email(db, request, "rma_received.html")

    # Auto-approve check
    if tenant.rma_auto_approve_under_cents is not None:
        rough_total = sum(li.unit_price_cents * li.quantity_requested for li in lines)
        if rough_total < tenant.rma_auto_approve_under_cents:
            line_approvals = {
                line.id: ApprovalLineInput(
                    quantity_approved=line.quantity_requested,
                    restock_on_approval=tenant.default_restock_on_refund,
                )
                for line in request.lines
            }
            request = approve_refund_request(
                db,
                request=request,
                approving_user_id=None,
                line_approvals=line_approvals,
                refund_shipping=False,
                auto_approved=True,
            )
            return request

    return request


def approve_refund_request(
    db: Session,
    *,
    request: RefundRequest,
    approving_user_id: UUID | None,
    line_approvals: dict[UUID, ApprovalLineInput],
    refund_shipping: bool,
    auto_approved: bool = False,
) -> RefundRequest:
    if request.status != "requested":
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot approve a request with status '{request.status}'",
        )

    from_status = request.status

    # Apply per-line approvals
    for line in request.lines:
        approval = line_approvals.get(line.id)
        if approval is not None:
            line.quantity_approved = min(approval.quantity_approved, line.quantity_requested)
            line.restock_on_approval = approval.restock_on_approval
            line.line_refund_cents = line.quantity_approved * line.unit_price_cents

    # Compute total
    request.refund_shipping = refund_shipping
    db.flush()
    db.refresh(request)
    request.total_refund_cents = _compute_total(request)
    request.approved_by_user_id = approving_user_id
    request.approved_at = _now()
    request.auto_approved = auto_approved
    request.status = "approved"

    _write_event(
        db, request=request, event_type="status_changed",
        from_status=from_status, to_status="approved",
        actor_user_id=approving_user_id,
        actor_kind="system" if auto_approved else "merchant",
        metadata={"auto_approved": auto_approved, "refund_shipping": refund_shipping},
    )
    db.flush()

    # Immediately execute refund for refund_only type
    if request.refund_type == "refund_only":
        request = execute_refund(db, request=request)
    # For return_refund: wait for goods to arrive (status stays "approved")
    # For exchange: stays "approved" — merchant ships replacement separately

    if not auto_approved:
        _send_status_email(db, request, "rma_approved.html")
    return request


def reject_refund_request(
    db: Session,
    *,
    request: RefundRequest,
    rejecting_user_id: UUID | None,
    reason: str,
) -> RefundRequest:
    if request.status != "requested":
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot reject a request with status '{request.status}'",
        )
    from_status = request.status
    request.status = "rejected"
    request.rejected_reason = reason
    request.rejected_at = _now()

    _write_event(
        db, request=request, event_type="status_changed",
        from_status=from_status, to_status="rejected",
        actor_user_id=rejecting_user_id, actor_kind="merchant",
        metadata={"reason": reason},
    )
    _send_status_email(db, request, "rma_rejected.html")
    return request


def cancel_refund_request(
    db: Session,
    *,
    request: RefundRequest,
    by_customer: bool = False,
    cancelling_user_id: UUID | None = None,
) -> RefundRequest:
    if request.status != "requested":
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot cancel a request with status '{request.status}'",
        )
    from_status = request.status
    request.status = "cancelled"
    request.cancelled_at = _now()

    _write_event(
        db, request=request, event_type="status_changed",
        from_status=from_status, to_status="cancelled",
        actor_user_id=cancelling_user_id,
        actor_kind="customer" if by_customer else "merchant",
    )
    return request


def mark_received(
    db: Session,
    *,
    request: RefundRequest,
    receiving_user_id: UUID | None,
) -> RefundRequest:
    if request.status != "approved":
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot mark received when status is '{request.status}'",
        )
    if request.refund_type != "return_refund":
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="mark_received is only valid for return_refund type",
        )

    from_status = request.status
    request.status = "received"
    request.received_at = _now()

    _write_event(
        db, request=request, event_type="status_changed",
        from_status=from_status, to_status="received",
        actor_user_id=receiving_user_id, actor_kind="merchant",
    )

    # Restock per-line
    for line in request.lines:
        if line.restock_on_approval:
            _restock_line(db, line, request.tenant_id)

    db.flush()

    # Trigger refund
    request = execute_refund(db, request=request)
    return request


def execute_refund(
    db: Session,
    *,
    request: RefundRequest,
) -> RefundRequest:
    """Execute the actual payment provider refund.

    On provider failure: records the failure in an event, leaves status at 'approved'
    (or 'received' for return_refund) so the merchant can retry.
    On cash payment: does NOT advance to refunded — waits for mark_cash_returned.
    """
    if request.status not in ("approved", "received"):
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot execute refund when status is '{request.status}'",
        )

    # Load associated order/transaction
    order = db.get(Order, request.order_id) if request.order_id else None
    txn = db.get(Transaction, request.sale_transaction_id) if request.sale_transaction_id else None

    amount_cents = request.total_refund_cents

    # Skip provider call for exchanges (no monetary refund by default)
    if request.refund_type == "exchange":
        request.status = "refunded"
        request.refunded_at = _now()
        _write_event(db, request=request, event_type="status_changed",
                     from_status="approved", to_status="refunded",
                     metadata={"note": "exchange_no_monetary_refund"})
        _send_status_email(db, request, "rma_refunded.html")
        return request

    if amount_cents <= 0:
        # Nothing to refund (e.g. all quantities 0) — still close out
        request.status = "refunded"
        request.refunded_at = _now()
        _write_event(db, request=request, event_type="status_changed",
                     from_status=request.status, to_status="refunded",
                     metadata={"note": "zero_amount_refund"})
        _send_status_email(db, request, "rma_refunded.html")
        return request

    result = execute_provider_refund(db, order=order, transaction=txn, amount_cents=amount_cents)

    provider_status = result.get("status", "manual")
    provider_ref = result.get("provider_ref")
    error_msg = result.get("error")

    if provider_status in ("manual_cash",):
        # Cash path — do not advance status; merchant must call mark_cash_returned
        _write_event(
            db, request=request, event_type="refund_executed",
            metadata={"status": provider_status, "note": "awaiting_cash_return"},
        )
        return request

    if provider_status == "manual":
        # Unknown provider / no credentials — do not auto-advance; merchant handles out-of-band
        _write_event(
            db, request=request, event_type="refund_executed",
            metadata={"status": "manual", "note": "no_payment_provider_configured"},
        )
        return request

    if provider_status == "failed":
        # Fail soft — record event but do NOT change status
        _write_event(
            db, request=request, event_type="refund_executed",
            metadata={"status": "failed", "error": error_msg, "provider_ref": provider_ref},
        )
        logger.warning("Payment provider refund failed for request %s: %s", request.id, error_msg)
        return request

    # Success (completed / pending)
    request.provider_refund_ref = provider_ref
    from_status = request.status
    request.status = "refunded"
    request.refunded_at = _now()

    # Record an OrderRefund row for e-commerce orders (reuses existing infrastructure)
    if order is not None:
        or_record = OrderRefund(
            tenant_id=request.tenant_id,
            order_id=order.id,
            amount_cents=amount_cents,
            currency_code=request.currency_code,
            reason=f"RMA {request.id}: {request.reason_code}",
            status="issued",
            issued_by_user_id=request.approved_by_user_id,
        )
        db.add(or_record)

    _write_event(
        db, request=request, event_type="refund_executed",
        from_status=from_status, to_status="refunded",
        metadata={"provider_ref": provider_ref, "provider_status": provider_status, "amount_cents": amount_cents},
    )
    _write_event(
        db, request=request, event_type="status_changed",
        from_status=from_status, to_status="refunded",
        metadata={"provider_ref": provider_ref},
    )

    _send_status_email(db, request, "rma_refunded.html")
    return request


def mark_cash_returned(
    db: Session,
    *,
    request: RefundRequest,
    user_id: UUID | None,
) -> RefundRequest:
    if request.status not in ("approved", "received"):
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot mark cash returned when status is '{request.status}'",
        )
    from_status = request.status
    request.cash_returned = True
    request.cash_returned_at = _now()
    request.status = "refunded"
    request.refunded_at = _now()

    _write_event(
        db, request=request, event_type="status_changed",
        from_status=from_status, to_status="refunded",
        actor_user_id=user_id, actor_kind="merchant",
        metadata={"cash_returned": True},
    )
    _send_status_email(db, request, "rma_refunded.html")
    return request


def close_refund_request(
    db: Session,
    *,
    request: RefundRequest,
    user_id: UUID | None = None,
) -> RefundRequest:
    if request.status not in ("refunded", "rejected"):
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot close a request with status '{request.status}'",
        )
    from_status = request.status
    request.status = "closed"
    request.closed_at = _now()

    _write_event(
        db, request=request, event_type="status_changed",
        from_status=from_status, to_status="closed",
        actor_user_id=user_id, actor_kind="merchant",
    )
    return request


def add_comment(
    db: Session,
    *,
    request: RefundRequest,
    comment: str,
    user_id: UUID | None,
    actor_kind: str = "merchant",
) -> RefundRequestEvent:
    evt = _write_event(
        db, request=request, event_type="comment",
        actor_user_id=user_id, actor_kind=actor_kind,
        metadata={"comment": comment},
    )
    return evt
