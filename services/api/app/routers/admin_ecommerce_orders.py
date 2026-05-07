"""Admin endpoints for e-commerce orders (channel orders, not POS transactions)."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import Order, OrderLine, OrderPayment, OrderRefund

router = APIRouter(
    prefix="/v1/admin/ecommerce-orders",
    tags=["Admin E-commerce Orders"],
    dependencies=[require_permission("orders:manage")],
)


class RefundIn(BaseModel):
    amount_cents: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=512)


class RefundOut(BaseModel):
    id: UUID
    order_id: UUID
    amount_cents: int
    currency_code: str
    reason: str | None
    status: str
    created_at: datetime
    model_config = {"from_attributes": True}


class OrderLineOut(BaseModel):
    id: UUID
    product_id: UUID | None
    title: str
    sku: str | None
    quantity: int
    unit_price_cents: int
    line_total_cents: int
    model_config = {"from_attributes": True}


class OrderPaymentOut(BaseModel):
    id: UUID
    provider: str
    provider_ref: str | None
    method: str
    amount_cents: int
    status: str
    model_config = {"from_attributes": True}


class OrderSummaryOut(BaseModel):
    id: UUID
    channel_id: UUID
    status: str
    customer_email: str | None
    customer_phone: str | None
    subtotal_cents: int
    discount_cents: int
    shipping_cents: int
    tax_cents: int
    total_cents: int
    currency_code: str
    placed_at: datetime
    model_config = {"from_attributes": True}


class OrderDetailOut(OrderSummaryOut):
    shipping_address: dict | None
    lines: list[OrderLineOut]
    payments: list[OrderPaymentOut]
    refunds: list[RefundOut]


def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Operator not assigned to a tenant")
    return ctx.tenant_id


def _get_order_or_404(db: Session, order_id: UUID, tenant_id: UUID) -> Order:
    order = db.get(Order, order_id)
    if order is None or order.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.get("", response_model=list[OrderSummaryOut])
def list_orders(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    order_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[Order]:
    tenant_id = _require_tenant(ctx)
    q = select(Order).where(Order.tenant_id == tenant_id).order_by(Order.placed_at.desc())
    if order_status:
        q = q.where(Order.status == order_status)
    q = q.limit(limit).offset(offset)
    return list(db.execute(q).scalars().all())


@router.get("/{order_id}", response_model=OrderDetailOut)
def get_order(
    order_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> OrderDetailOut:
    tenant_id = _require_tenant(ctx)
    order = _get_order_or_404(db, order_id, tenant_id)
    lines = db.execute(select(OrderLine).where(OrderLine.order_id == order.id)).scalars().all()
    payments = db.execute(select(OrderPayment).where(OrderPayment.order_id == order.id)).scalars().all()
    refunds = db.execute(select(OrderRefund).where(OrderRefund.order_id == order.id)).scalars().all()
    return OrderDetailOut(
        id=order.id, channel_id=order.channel_id, status=order.status,
        customer_email=order.customer_email, customer_phone=order.customer_phone,
        subtotal_cents=order.subtotal_cents, discount_cents=order.discount_cents,
        shipping_cents=order.shipping_cents, tax_cents=order.tax_cents,
        total_cents=order.total_cents, currency_code=order.currency_code,
        shipping_address=order.shipping_address, placed_at=order.placed_at,
        lines=list(lines), payments=list(payments), refunds=list(refunds),
    )


@router.post("/{order_id}/refund", response_model=RefundOut, status_code=status.HTTP_201_CREATED)
def issue_refund(
    order_id: UUID,
    body: RefundIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> OrderRefund:
    tenant_id = _require_tenant(ctx)
    order = _get_order_or_404(db, order_id, tenant_id)

    if order.status in ("cancelled", "refunded"):
        raise HTTPException(status_code=400,
                            detail=f"Cannot refund an order with status '{order.status}'")

    existing_refunds = db.execute(
        select(OrderRefund).where(OrderRefund.order_id == order.id)
    ).scalars().all()
    already_refunded = sum(r.amount_cents for r in existing_refunds)
    if already_refunded + body.amount_cents > order.total_cents:
        raise HTTPException(
            status_code=400,
            detail=f"Refund amount {body.amount_cents} exceeds remaining refundable amount "
                   f"{order.total_cents - already_refunded}",
        )

    refund = OrderRefund(
        tenant_id=tenant_id,
        order_id=order.id,
        amount_cents=body.amount_cents,
        currency_code=order.currency_code,
        reason=body.reason,
        status="issued",
        issued_by_user_id=ctx.user_id,
    )
    db.add(refund)

    if already_refunded + body.amount_cents >= order.total_cents:
        order.status = "refunded"
    else:
        order.status = "partially_refunded"

    db.commit()
    db.refresh(refund)
    return refund


@router.post("/{order_id}/dispatch", status_code=status.HTTP_202_ACCEPTED)
def dispatch_order_manual(
    order_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> dict:
    """Manually trigger shipment dispatch. Idempotent — re-runs even if previous attempt failed."""
    tenant_id = _require_tenant(ctx)
    order = _get_order_or_404(db, order_id, tenant_id)
    if order.status not in ("confirmed", "partially_refunded"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot dispatch order with status '{order.status}'"
        )
    from app.worker.queue import task_queue
    task_queue().enqueue("app.worker.tasks.dispatch_shipment", str(order_id), job_timeout=120)
    return {"queued": True, "order_id": str(order_id)}


@router.post("/{order_id}/cancel-shipment", status_code=status.HTTP_200_OK)
def cancel_order_shipment(
    order_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> dict:
    """Cancel the shipment for an order (only before pickup)."""
    tenant_id = _require_tenant(ctx)
    order = _get_order_or_404(db, order_id, tenant_id)
    if not order.awb_code:
        raise HTTPException(status_code=400, detail="Order has not been dispatched yet")
    if order.fulfillment_status in ("delivered", "returned"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel shipment in status '{order.fulfillment_status}'"
        )

    from app.models import Channel as ChannelModel
    channel = db.get(ChannelModel, order.channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")

    from app.services.shipping.registry import get_channel_provider
    from app.services.shipping.base import ShippingNotConfiguredError
    try:
        provider, config = get_channel_provider(channel)
    except ShippingNotConfiguredError:
        raise HTTPException(status_code=400, detail="No shipping provider configured")

    config = {**config, "_provider_order_id": order.provider_order_id or ""}
    success = provider.cancel_shipment(order.awb_code, config)

    if success:
        order.fulfillment_status = "cancelled"
        from datetime import UTC, datetime
        from app.models import ShipmentEvent
        db.add(ShipmentEvent(
            tenant_id=tenant_id, order_id=order.id,
            status="cancelled", occurred_at=datetime.now(UTC),
            provider_event_id=f"manual_cancel:{order.id}",
            description="Shipment cancelled by admin",
            raw_payload={},
        ))
        db.commit()

    return {"cancelled": success, "order_id": str(order_id)}
